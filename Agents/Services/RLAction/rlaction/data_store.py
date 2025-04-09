"""
This module contain all supported input sources
"""

import time
from datetime import timedelta
import threading
import json

import requests
import pandas as pd
import pendulum
import numpy as np

from rlaction import (_log,
                      AltoNotImpl)


def data_store_factory(dtype):
    if dtype == "netatmo_data":
        return NetatmoData
    if dtype == "modbus_meter_data":
        return ModbusMeterData
    if dtype == "underground_data":
        return UndergroundData
    if dtype == "outdoor_weather_data":
        return OutdoorWeatherData
    if dtype == "occupant_data":
        return OccupantData
    if dtype == "tuya_env_data":
        return TuyaEnvData
    if dtype == "tuya_aq_data":
        return TuyaAQData
    if dtype == "hvac_data":
        return HVACData
    if dtype == "airveda_data":
        return AirvedaData
    if dtype == 'lorawan_env_data':
        return LoRaWANEnvData
    if dtype == 'lorawan_iaq_data':
        return LoRaWANIAQData

    raise Exception(f"Unknown data_store {dtype}")


class DataStore:

    def __init__(self, data_id, expiration=600):
        self._data_id = data_id
        self._data = {}
        self._unix_timestamp = None
        self._expiration = expiration
    
    def _update_time(self):
        self._unix_timestamp = time.time()

    @property
    def unix_timestamp(self):
        return self._unix_timestamp

    @property
    def data(self):
        return self._data

    def check_update(self):
        if self._unix_timestamp is None:
            return False
        if (self._unix_timestamp + self._expiration) < time.time():
            return False
        return True

    def update_data(self, data):
        """
        Method that MUST be overridden to update the actual data
        """

        raise AltoNotImpl("update_data method must be implemented")


class NetatmoData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
            "co2": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 1:
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._data["co2"] = data["co2"]
                    self._update_time()
                    _log.debug(f"NetatmoData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"NetatmoData update_data {self._data_id} {e}")


class ModbusMeterData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "power": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 3:
                    self._data["power"] = data["power"]
                    self._update_time()
                    _log.debug(f"ModbusMeterData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"ModbusMeterData update_data {self._data_id} {e}")


class UndergroundData(DataStore):

    def __init__(self, data_id, station_key=""):
        super().__init__(data_id)
        self._station_key = station_key
        self._data = {
            "humidity": None,
            "dew_point": None,
            "pressure": None,
            "temperature": None
        }

    def update_data(self, data):
        if data is None:
            ret_data = self._fetch_data()

    def _fetch_data(self):
        try:
            start_time = pendulum.yesterday('Asia/Bangkok')
            end_time = pendulum.now('Asia/Bangkok')

            # call API : get weather data
            df = self.get_outdoor_weather_data(self._station_key, start_time, end_time)

            # declare neccessary columns and firebase node names
            columns = ["wx_phrase", "temp", "dewPt", "rh", "pressure", "wspd", "wdir_cardinal", "valid_time_gmt"]

            # _log.debug(f'''UndergroundData _fetch_data {df.columns}''')

            df = df[columns]

            # convert data type from int64 to float64
            data_to_convert = list(df.select_dtypes([np.number]).columns)
            for name in data_to_convert:
                df[name] = df[name].astype(float)

            last_row = df.iloc[-1]

            # create dict to update to firebase
            data = {
                "weather_condition": {"unit": "None", "value": last_row["wx_phrase"]}, 
                "temperature": {"unit": "celsius", "value": self.fahrenheit_to_celsius(last_row["temp"])},
                "dew_point": {"unit": "celsius", "value": self.fahrenheit_to_celsius(last_row["dewPt"])},
                "humidity": {"unit": "%", "value": last_row["rh"]},
                "pressure": {"unit": "mb", "value": self.pressure_inHg_to_mbar(last_row["pressure"])},
                "wind_speed": {"unit": "km/h", "value": self.mph_to_kmh(last_row["wspd"])},
                "wind_direction": {"unit": "None", "value": last_row["wdir_cardinal"]},
                "updated_at": int(last_row["valid_time_gmt"])
            }

            # _log.debug(f"UndergroundData _fetch_data {self._data_id} {data}")

            self._data["humidity"] = data["humidity"]["value"]
            self._data["dew_point"] = data["dew_point"]["value"]
            self._data["pressure"] = data["pressure"]["value"]
            self._data["temperature"] = data["temperature"]["value"]
            self._update_time()
            _log.debug(f"UndergroundData _fetch_data {self._data_id} {self._unix_timestamp} {self._data}")

        except Exception as e:
            _log.error(f"UndergroundData _fetch_data {self._data_id} {e}")

    def get_outdoor_weather_data(self, station_key="", start_time=pendulum.datetime(2021, 6, 1, tz='Asia/Bangkok'), end_time=pendulum.now('Asia/Bangkok')):
        dt = pendulum.now('Asia/Bangkok')
        _valid_time = start_time
        _end_time = end_time
        Data = {}

        def worker(dt):
            a = requests.get("https://api.weather.com/v1/location/{}:9:TH/observations/historical.json?apiKey=6532d6454b8aa370768e63d6ba5a832e&units=e&startDate={}".format(station_key, dt))
            b = json.loads(a.text)
            c = pd.DataFrame(b["observations"])
            Data[dt] = c
            
        num_th = 20
        while _end_time > _valid_time:
            
            threads = []        
            for i in range(num_th):            
                if _end_time <= _valid_time:
                    break
                
                dt = _valid_time.strftime("%Y%m%d")
                t = threading.Thread(target=worker, args=(dt,))
                threads.append(t)       
                _valid_time = _valid_time.add(days=1)
                
            for t in threads:
                t.start()           
            for t in threads:
                t.join()

        df = pd.concat([Data[k] for k in Data], axis=0)

        # Remove columns with NULL more than 90% data as null.
        cols_to_delete = df.columns[df.isnull().sum()/len(df) > .90]
        df.drop(cols_to_delete, axis = 1, inplace = True)

        df = df.sort_values(by="valid_time_gmt")

        df["datetime"] = pd.to_datetime(df["valid_time_gmt"].astype(int)*1e9) + timedelta(hours=7)
        df = df.reset_index(drop=True)
        df = df.set_index("datetime")

        # Drop irrelevant columns
        columns = ['key', 'class', 'expire_time_gmt', 'obs_id', 'obs_name']
        df.drop(columns=columns, inplace=True)

        return df

    def fahrenheit_to_celsius(self, temperature):
        celsius = (temperature-32)*5/9
        return round(celsius, 2)

    def pressure_inHg_to_mbar(self, pressure):
        mbar = pressure * 33.8639
        return round(mbar, 2)

    def mph_to_kmh(self, wind_speed):
        kmh = wind_speed * 1.6
        return round(kmh, 2)


class OutdoorWeatherData(DataStore):

    def __init__(self, data_id, firebase_path=""):
        super().__init__(data_id)
        self._firebase_path = firebase_path
        self._data = {
            "solar_irradiance": None,
            "wind_speed": None,
            "temperature": None
        }

    @property
    def firebase_path(self):
        return self._firebase_path

    def update_data(self, data):
        try:
            if data is not None:
                self._data["solar_irradiance"] = data["data"].get("total_irradiance", self._data["solar_irradiance"])
                self._data["wind_speed"] = data["data"].get("wind_speed", self._data["wind_speed"])
                self._data["temperature"] = data["data"].get("ambient_temperature", self._data["temperature"])
                self._update_time()
                _log.debug(f"OutdoorWeatherData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"OutdoorWeatherData update_data {self._data_id} {e}")

    def data_from_firebase(self, message):
        # _log.debug(f"OutdoorWeatherData data_from_firebase {self._data_id} {message}")
        self.update_data(message)


class OccupantData(DataStore):

    def __init__(self, data_id, firebase_path=""):
        super().__init__(data_id)
        self._firebase_path = firebase_path
        self._data = {
            "count_people_in": None,
            "count_people_out": None
        }

    @property
    def firebase_path(self):
        return self._firebase_path

    def update_data(self, data):
        try:
            if data is not None:
                self._data["count_people_in"] = data["data"].get("count_people_in", self._data["count_people_in"])
                self._data["count_people_out"] = data["data"].get("count_people_out", self._data["count_people_out"])
                self._update_time()
                _log.debug(f"OccupantData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"OutdoorWeatherData update_data {self._data_id} {e}")

    def data_from_firebase(self, message):
        # _log.debug(f"OccupantData data_from_firebase {self._data_id} {message}")
        self.update_data(message)


class TuyaEnvData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._update_time()
                    _log.debug(f"TuyaEnvData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"TuyaEnvData update_data {self._data_id} {e}")


class TuyaAQData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
            "co2": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._data["co2"] = data["co2"]
                    self._update_time()
                    _log.debug(f"TuyaAQData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"TuyaAQData update_data {self._data_id} {e}")


class HVACData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "set_temperature": None,
        }
    
    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "ac":
                    self._data["set_temperature"] = data["set_temperature"]
                    self._update_time()
                    _log.debug(f"HVACData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"HVACData update_data {self._data_id} {e}")

class AirvedaData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
            "co2": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._data["co2"] = data["co2"]
                    self._update_time()
                    _log.debug(f"AirvedaData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"AirvedaData update_data {self._data_id} {e}")


class LoRaWANEnvData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._update_time()
                    _log.debug(f"LoRaWANEnvData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"LoRaWANEnvData update_data {self._data_id} {e}")
            

class LoRaWANIAQData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
            "co2": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._data["co2"] = data["co2"]
                    self._update_time()
                    _log.debug(f"LoRaWANIAQData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"LoRaWANIAQData update_data {self._data_id} {e}")
            