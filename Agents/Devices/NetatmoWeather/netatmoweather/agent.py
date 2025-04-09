"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import requests
import json
import time
import copy
import altolib
from threading import Thread
from queue import Queue
from volttron.platform.agent import utils
# from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


AUTH_URL = "https://api.netatmo.com/oauth2/token"
HOME_COACH_URL = "https://api.netatmo.com/api/gethomecoachsdata"
WEATHER_STATION_URL = "https://api.netatmo.com/api/getstationsdata"


class NetatmoAuth:

    def __init__(self, client_id, client_secret, username, password, scope=None):
        if scope is None:
            scope = "read_homecoach" # read_homecoach for gethomecoachsdata
        self._grant_type = "password"
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._scope = scope

        self._get_access_token()
    
    def _get_access_token(self):
        datas = {
            "grant_type": self._grant_type,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": self._username,
            "password": self._password,
            "scope": self._scope
        }
        try:
            res = requests.post(AUTH_URL, data=datas)
            _log.info(res.status_code)
            # _log.debug(res.content)

            if res.status_code == 200:
                res_json = json.loads((res.content).decode())
                # _log.debug(res_json)
                self._access_token = res_json["access_token"]
                self._refresh_token = res_json["refresh_token"]
                self._expiration = int(res_json['expire_in']/2.0 + time.time())
        except Exception as e:
            _log.error(f'NetatmoAuth _get_access_token {e}')

    def _renew_access_token(self):
        datas = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret
        }
        try:
            res = requests.post(AUTH_URL, data=datas)
            _log.info(res.status_code)
            # _log.debug(res.content)

            if res.status_code == 200:
                res_json = json.loads((res.content).decode())
                # _log.debug(res_json)
                self._access_token = res_json["access_token"]
                self._refresh_token = res_json["refresh_token"]
                self._expiration = int(res_json['expire_in']/2.0 + time.time())
        except Exception as e:
            _log.error(f'NetatmoAuth _renew_access_token {e}')
    
    @property
    def access_token(self):
        if time.time() >= self._expiration:
            self._renew_access_token()
        return self._access_token


class NetatmoAPI:

    def __init__(self, client_id, client_secret, username, password):
        self._netatmo_auth = NetatmoAuth(client_id, client_secret, username, password, "read_station read_homecoach")

        self._devices = {
            "weather": [],
            "aircare": []
        }

    def update_self(self, client_id, client_secret, username, password):
        self._netatmo_auth = NetatmoAuth(client_id, client_secret, username, password, "read_station read_homecoach")

        self._devices = {
            "weather": [],
            "aircare": []
        }

    def get_data(self):
        # get weather
        self._devices["weather"] = []
        try:
            headers = {
                "Authorization": f'Bearer {self._netatmo_auth.access_token}'
            }
            res = requests.post(WEATHER_STATION_URL, headers=headers)
            _log.info(res.status_code)
            # _log.debug(res.content)
            if res.status_code == 200:
                    res_json = json.loads((res.content).decode())
                    self._devices["weather"] = res_json["body"]["devices"]
        except Exception as e:
            _log.error(f'NetatmoAPI get weather data error {e}')

        # get aircare
        self._devices["aircare"] = []
        try:
            headers = {
                "Authorization": f'Bearer {self._netatmo_auth.access_token}'
            }
            res = requests.post(HOME_COACH_URL, headers=headers)
            _log.info(res.status_code)
            # _log.debug(res.content)
            if res.status_code == 200:
                    res_json = json.loads((res.content).decode())
                    self._devices["aircare"] = res_json["body"]["devices"]
        except Exception as e:
            _log.error(f'NetatmoAPI get aircare data error {e}')

    @property
    def devices(self):
        return self._devices


def device_factory(devtype):
    if devtype == "NAMain":
        return NAIndoorDevice
    if devtype == "NAModule4":
        return NAExtIndoorDevice
    if devtype == "NHC":
        return NANHCDevice

    raise Exception(f"Unknown device type {devtype}")


class NAIndoorDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    """
    This is the main netatmo indoor device
    """

    def __init__(self, controller, mac_addr, nb_subdev):
        super().__init__(controller, mac_addr, nb_subdev)
        self.ATMODEVICEMAP = {
            "date_setup": "date_setup",
            "last_setup": "last_setup",
            "type": "type",
            "last_status_store": "last_status_store",
            "module_name": "module_name",
            "firmware": "firmware",
            "wifi_status": "wifi_status",
            "reachable": "reachable",
            "co2_calibrating": "co2_calibrating",
            "data_type": "data_type",
            "station_name": "station_name",
            "home_id": "home_id",
            "home_name": "home_name"
        }

        self.ATMOENVIMAP = {
            "time_utc": "time_utc",
            "temperature": "Temperature",
            "co2": "CO2",
            "humidity": "Humidity",
            "noise": "Noise",
            "pressure": "Pressure",
            "absolute_pressure": "AbsolutePressure",
            "min_temp": "min_temp",
            "max_temp": "max_temp",
            "date_max_temp": "date_max_temp",
            "date_min_temp": "date_min_temp",
            "temp_trend": "temp_trend",
            "pressure_trend": "pressure_trend"
        }

        self.ATMOLOCATIONMAP = {
            "altitude": "altitude",
            "city": "city",
            "country": "country",
            "timezone": "timezone",
            "latitude": "latitude",
            "longitude": "longitude"
        }

        self.datapoint_supported["device"] = [x for x in self.ATMODEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.ATMOENVIMAP.keys()]
        self.datapoint_supported["location"] = [x for x in self.ATMOLOCATIONMAP.keys()]
        self._sample_init()

    def __str__(self):
        return "NAMain"

    def to_environment_temperature(self, val):
        return round(float(val), 2)

    def to_environment_co2(self, val):
        return round(float(val), 2)

    def to_environment_humidity(self, val):
        return round(float(val), 2)

    def to_environment_noise(self, val):
        return round(float(val), 2)

    def to_environment_pressure(self, val):
        return round(float(val), 2)

    def to_environment_absolute_pressure(self, val):
        return round(float(val), 2)

    def to_environment_min_temp(self, val):
        return round(float(val), 2)

    def to_environment_max_temp(self, val):
        return round(float(val), 2)

    def _sample_init(self):
        for idx in range(0, self.number_subdevices):
            self.current_state[idx] = {"sensor": {"device": {}, "environment": {}, "location": {}}}
        self.data_map.update(self.ATMODEVICEMAP)
        self.data_map.update(self.ATMOENVIMAP)
        self.data_map.update(self.ATMOLOCATIONMAP)
        self.initialise_data("device", self.ATMODEVICEMAP.keys())
        self.initialise_data("environment", self.ATMOENVIMAP.keys())
        self.initialise_data("location", self.ATMOLOCATIONMAP.keys())

    def _update_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMODEVICEMAP.values():
                    if k == "data_type":
                        vals[k] = ",".join(v)
                    else:
                        vals[k] = v
            subdev_id = 0
            this_type = "device"
            # _log.debug(f'''_update_device_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
        except Exception as e:
            _log.error(f"Device _update_device_data problem: {e}")
            return

    def _update_environment_data(self, data):
        # _log.debug(f'''_update_environment_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOENVIMAP.values():
                    vals[k] = v
            subdev_id = 1
            this_type = "environment"
            # _log.debug(f'''_update_environment_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
            # _log.debug(f'''_update_environment_data 2 {self.current_state}''')
            # current_type_val = self.current_state[subdev_id]["sensor"][this_type]
            # mydata = current_type_val.copy()
            # mydata["type"] = this_type
            # self.controller.emit_event_sample(self, subdev_id, mydata)
        except Exception as e:
            _log.error(f"Device _update_environment_data problem: {e}")
            return

    def _update_location_data(self, data):
        # _log.debug(f'''_update_location_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOLOCATIONMAP.values():
                    vals[k] = v
                elif k == "location":
                    vals["latitude"] = v[0]
                    vals["longitude"] = v[1]
            subdev_id = 2
            this_type = "location"
            # _log.debug(f'''_update_location_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
            # _log.debug(f'''_update_location_data set_sensor_data''')
        except Exception as e:
            _log.error(f"Device _update_location_data problem: {e}")
            return

    def send_sample_thread(self, data):
        _log.debug(f'''NAIndoorDevice''')
        try:
            if data is not None:
                self._update_device_data(data)
                self._update_environment_data(data["dashboard_data"])
                self._update_location_data(data["place"])
                return
        except Exception as e:
            _log.error(f"Device NAIndoorDevice send_sample_thread problem: {e}")
            return

    # def to_environment_timestamp(self, val):
    #     tstmp = self.tz.localize(dt.datetime.fromtimestamp(val)).astimezone(
    #         pytz.timezone("UTC")
    #     )
    #     return tstmp.replace(tzinfo=dt.timezone.utc).isoformat()


# class NAExtIndoorDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor, altolib.AltoElectricSensor):
class NAExtIndoorDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    """
    This is the additional netatmo indoor device
    """

    def __init__(self, controller, mac_addr, nb_subdev):
        super().__init__(controller, mac_addr, nb_subdev)
        self.ATMODEVICEMAP = {
            "type": "type",
            "module_name": "module_name",
            "last_setup": "last_setup",
            "data_type": "data_type",
            "reachable": "reachable",
            "firmware": "firmware",
            "last_message": "last_message",
            "last_seen": "last_seen",
            "rf_status": "rf_status"
        }

        self.ATMOENVIMAP = {
            "time_utc": "time_utc",
            "temperature": "Temperature",
            "co2": "CO2",
            "humidity": "Humidity",
            "min_temp": "min_temp",
            "max_temp": "max_temp",
            "date_max_temp": "date_max_temp",
            "date_min_temp": "date_min_temp",
            "temp_trend": "temp_trend"
        }

        self.ATMOLOCATIONMAP = {
            "altitude": "altitude",
            "city": "city",
            "country": "country",
            "timezone": "timezone",
            "latitude": "latitude",
            "longitude": "longitude"
        }

        self.ATMOELECTRICMAP = {
            "battery_percent": "battery_percent",
            "battery_vp": "battery_vp"
        }

        self.datapoint_supported["device"] = [x for x in self.ATMODEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.ATMOENVIMAP.keys()]
        self.datapoint_supported["location"] = [x for x in self.ATMOLOCATIONMAP.keys()]
        self.datapoint_supported["electric"] = [x for x in self.ATMOELECTRICMAP.keys()]
        self._sample_init()

    def __str__(self):
        return "NAModule4"

    def to_environment_temperature(self, val):
        return round(float(val), 2)

    def to_environment_co2(self, val):
        return round(float(val), 2)

    def to_environment_humidity(self, val):
        return round(float(val), 2)

    def to_environment_min_temp(self, val):
        return round(float(val), 2)

    def to_environment_max_temp(self, val):
        return round(float(val), 2)

    def _sample_init(self):
        for idx in range(0, self.number_subdevices):
            self.current_state[idx] = {"sensor": {"device": {}, "environment": {}, "location": {}, "electric": {}}}
        self.data_map.update(self.ATMODEVICEMAP)
        self.data_map.update(self.ATMOENVIMAP)
        self.data_map.update(self.ATMOLOCATIONMAP)
        self.data_map.update(self.ATMOELECTRICMAP)
        self.initialise_data("device", self.ATMODEVICEMAP.keys())
        self.initialise_data("environment", self.ATMOENVIMAP.keys())
        self.initialise_data("location", self.ATMOLOCATIONMAP.keys())
        self.initialise_data("electric", self.ATMOELECTRICMAP.keys())

    def _update_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMODEVICEMAP.values():
                    if k == "data_type":
                        vals[k] = ",".join(v)
                    else:
                        vals[k] = v
            subdev_id = 0
            this_type = "device"
            # _log.debug(f'''_update_device_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
        except Exception as e:
            _log.error(f"Device _update_device_data problem: {e}")
            return

    def _update_environment_data(self, data):
        # _log.debug(f'''_update_environment_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOENVIMAP.values():
                    vals[k] = v
            subdev_id = 1
            this_type = "environment"
            # _log.debug(f'''_update_environment_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
        except Exception as e:
            _log.error(f"Device _update_environment_data problem: {e}")
            return
    
    def _update_location_data(self, data):
        # _log.debug(f'''_update_location_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOLOCATIONMAP.values():
                    vals[k] = v
                elif k == "location":
                    vals["latitude"] = v[0]
                    vals["longitude"] = v[1]
            subdev_id = 2
            this_type = "location"
            # _log.debug(f'''_update_location_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
            # _log.debug(f'''_update_location_data set_sensor_data''')
        except Exception as e:
            _log.error(f"Device _update_location_data problem: {e}")
            return

    def _update_electric_data(self, data):
        # _log.debug(f'''_update_electric_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOELECTRICMAP.values():
                    vals[k] = v
            subdev_id = 3
            this_type = "electric"
            # _log.debug(f'''_update_electric_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
        except Exception as e:
            _log.error(f"Device _update_electric_data problem: {e}")
            return

    def send_sample_thread(self, data):
        _log.debug(f'''NAExtIndoorDevice''')
        try:
            if data is not None:
                self._update_device_data(data)
                self._update_environment_data(data["dashboard_data"])
                self._update_location_data(data["place"])
                self._update_electric_data(data)
                return
        except Exception as e:
            _log.error(f"Device update_sensor_data problem: {e}")
            return


class NANHCDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    """
    This is the NHC aircare device
    """

    def __init__(self, controller, mac_addr, nb_subdev):
        super().__init__(controller, mac_addr, nb_subdev)
        self.ATMODEVICEMAP = {
            "date_setup": "date_setup",
            "last_setup": "last_setup",
            "type": "type",
            "last_status_store": "last_status_store",
            "module_name": "module_name",
            "firmware": "firmware",
            "wifi_status": "wifi_status",
            "reachable": "reachable",
            "co2_calibrating": "co2_calibrating",
            "data_type": "data_type",
            "station_name": "station_name"
        }

        self.ATMOENVIMAP = {
            "time_utc": "time_utc",
            "temperature": "Temperature",
            "co2": "CO2",
            "humidity": "Humidity",
            "noise": "Noise",
            "pressure": "Pressure",
            "absolute_pressure": "AbsolutePressure",
            "health_idx": "health_idx",
            "min_temp": "min_temp",
            "max_temp": "max_temp",
            "date_max_temp": "date_max_temp",
            "date_min_temp": "date_min_temp",
        }

        self.ATMOLOCATIONMAP = {
            "altitude": "altitude",
            "city": "city",
            "country": "country",
            "timezone": "timezone",
            "latitude": "latitude",
            "longitude": "longitude"
        }

        self.datapoint_supported["device"] = [x for x in self.ATMODEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.ATMOENVIMAP.keys()]
        self.datapoint_supported["location"] = [x for x in self.ATMOLOCATIONMAP.keys()]
        self._sample_init()

    def __str__(self):
        return "NHC"

    def to_environment_temperature(self, val):
        return round(float(val), 2)

    def to_environment_co2(self, val):
        return round(float(val), 2)

    def to_environment_humidity(self, val):
        return round(float(val), 2)

    def to_environment_noise(self, val):
        return round(float(val), 2)

    def to_environment_pressure(self, val):
        return round(float(val), 2)

    def to_environment_absolute_pressure(self, val):
        return round(float(val), 2)

    def to_environment_health_idx(self, val):
        return round(float(val), 2)

    def to_environment_min_temp(self, val):
        return round(float(val), 2)

    def to_environment_max_temp(self, val):
        return round(float(val), 2)

    def _sample_init(self):
        for idx in range(0, self.number_subdevices):
            self.current_state[idx] = {"sensor": {"device": {}, "environment": {}, "location": {}}}
        self.data_map.update(self.ATMODEVICEMAP)
        self.data_map.update(self.ATMOENVIMAP)
        self.data_map.update(self.ATMOLOCATIONMAP)
        self.initialise_data("device", self.ATMODEVICEMAP.keys())
        self.initialise_data("environment", self.ATMOENVIMAP.keys())
        self.initialise_data("location", self.ATMOLOCATIONMAP.keys())

    def _update_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMODEVICEMAP.values():
                    if k == "data_type":
                        vals[k] = ",".join(v)
                    else:
                        vals[k] = v
            subdev_id = 0
            this_type = "device"
            # _log.debug(f'''_update_device_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
        except Exception as e:
            _log.error(f"Device _update_device_data problem: {e}")
            return

    def _update_environment_data(self, data):
        # _log.debug(f'''_update_environment_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOENVIMAP.values():
                    vals[k] = v
            subdev_id = 1
            this_type = "environment"
            # _log.debug(f'''_update_environment_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
            # _log.debug(f'''_update_environment_data 2 {self.current_state}''')
            # current_type_val = self.current_state[subdev_id]["sensor"][this_type]
            # mydata = current_type_val.copy()
            # mydata["type"] = this_type
            # self.controller.emit_event_sample(self, subdev_id, mydata)
        except Exception as e:
            _log.error(f"Device _update_environment_data problem: {e}")
            return

    def _update_location_data(self, data):
        # _log.debug(f'''_update_location_data''')
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMOLOCATIONMAP.values():
                    vals[k] = v
                elif k == "location":
                    vals["latitude"] = v[0]
                    vals["longitude"] = v[1]
            subdev_id = 2
            this_type = "location"
            # _log.debug(f'''_update_location_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
            # _log.debug(f'''_update_location_data set_sensor_data''')
        except Exception as e:
            _log.error(f"Device _update_location_data problem: {e}")
            return

    def send_sample_thread(self, data):
        _log.debug(f'''NANHCDevice''')
        try:
            if data is not None:
                self._update_device_data(data)
                self._update_environment_data(data["dashboard_data"])
                self._update_location_data(data["place"])
                return
        except Exception as e:
            _log.error(f"Device NANHCDevice send_sample_thread problem: {e}")
            return


def netatmoweather(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Netatmoweather
    :rtype: Netatmoweather
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        [
            "netatmos",
            "agent_name",
            "timezones",
            "default_timezone",
            "sampling_rate"
        ],
        [{}, "netatmo", {}, "Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Netatmoweather(topic, **kwargs)


class Netatmoweather(altolib.AltoBridgeAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Netatmoweather, self).__init__(topic, **kwargs)
        self._sampling_rate_cd = 15 # overlide default start polling time
        self.auto_send = True  # set to True if you need set_sensor_data can be auto update after meet condition
        # self.discovery_lock = Lock()
        self.sample_locks = {}
        self.queue = Queue()
        _log.debug("vip_identity: " + self.core.identity)

        self.netatmo_apis = {}
        for k, v in self.netatmos.items():
            if v["client_id"] and v["client_secret"] and v["password"]:
                self.netatmo_apis[k] = NetatmoAPI(v["client_id"], v["client_secret"], k, v["password"])
            else:
                _log.debug("Please provide all requires netatmo credentials")
        
        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

    def _build_device(self, dev_type, dev_id, nb_subdev=1):
        # _log.debug(f'''_build_device {dev_type} {dev_id}''')
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, nb_subdev)
            # _log.debug(f'''_build_device {dev_type} {dev_id} {newdev}''')
            self.register_new_device(newdev)

    def send_samples(self):
        _log.debug(f'''send_samples {self.device_list}''')
        # _log.debug(f'''send_samples {self.client_id} {self.client_secret} {self.username} {self.password} {self.netatmo} {self.device_list}''')
        # _log.debug(f'''send_samples {self.netatmo.client_id} {self.netatmo.client_secret} {self.netatmo.username} {self.netatmo.password}''')
        for k, v in self.netatmo_apis.items():
            try:
                v.get_data()
            except Exception as e:
                _log.error(f"Problem when retrieving netatmo sensor data: {e}")
                continue

            # _log.debug(f'''send_samples netatmo_apis.devices {v.devices}''')
            try:
                if v.devices["weather"]:
                    # _log.debug(f'''weather''')
                    for main_dev in v.devices["weather"]:
                        for idx, conf_dev in enumerate(self.netatmos[k]["devices"]):
                            # _log.debug(f'''send_samples 1 {conf_dev}''')
                            if main_dev["_id"] == conf_dev[0] and main_dev["type"] == conf_dev[1]:
                                self._build_device(main_dev["type"], main_dev["_id"], nb_subdev=3)
                                break
                        for addi_dev in main_dev["modules"]:
                            for idx, conf_dev in enumerate(self.netatmos[k]["devices"]):
                                if addi_dev["_id"] == conf_dev[0] and addi_dev["type"] == conf_dev[1]:
                                    self._build_device(addi_dev["type"], addi_dev["_id"], nb_subdev=4)
                                    break
                if v.devices["aircare"]:
                    # _log.debug(f'''aircare''')
                    for main_dev in v.devices["aircare"]:
                        for idx, conf_dev in enumerate(self.netatmos[k]["devices"]):
                            # _log.debug(f'''send_samples 1 {conf_dev} {main_dev["_id"] == conf_dev[0] and main_dev["type"] == conf_dev[1]}''')
                            if main_dev["_id"] == conf_dev[0] and main_dev["type"] == conf_dev[1]:
                                # _log.debug(f'''send_samples 1 {conf_dev[0]} {conf_dev[1]}''')
                                self._build_device(main_dev["type"], main_dev["_id"], nb_subdev=3)
                                break
            except Exception as e:
                _log.error(f"Problem when process netatmo data: {e}")
                return

            _log.debug(f'''send_samples netatmo_apis {k}''')
            try:
                if v.devices["weather"]:
                    for main_dev in v.devices["weather"]:
                        if main_dev["_id"] in self.device_list:
                            data = None
                            if str(self.device_list[main_dev["_id"]]) == "NAMain":
                                data = copy.deepcopy(main_dev)
                                del data["modules"]
                            try:
                                self._add_job({
                                    "instance": self.device_list[main_dev["_id"]],
                                    "data": data
                                })
                            except Exception as e:
                                _log.debug(f"{e.message}, {e.args}")
                        for addi_dev in main_dev["modules"]:
                            if addi_dev["_id"] in self.device_list:
                                data = None
                                if str(self.device_list[addi_dev["_id"]]) == "NAModule4":
                                    data = copy.deepcopy(addi_dev)
                                    data["place"] = copy.deepcopy(main_dev["place"])
                                try:
                                    self._add_job({
                                        "instance": self.device_list[addi_dev["_id"]],
                                        "data": data
                                    })
                                except Exception as e:
                                    _log.debug(f"{e.message}, {e.args}")
                if v.devices["aircare"]:
                    for main_dev in v.devices["aircare"]:
                        if main_dev["_id"] in self.device_list:
                                data = None
                                if str(self.device_list[main_dev["_id"]]) == "NHC":
                                    data = copy.deepcopy(main_dev)
                                try:
                                    self._add_job({
                                        "instance": self.device_list[main_dev["_id"]],
                                        "data": data
                                    })
                                except Exception as e:
                                    _log.debug(f"{e.message}, {e.args}")
            except Exception as e:
                _log.error(f"Problem when add queue netatmo data: {e}")
                return

        # _log.debug(f'''send_samples 2 {self.device_list}''')

        # try:
        #     for k, v in self.device_list.items():
        #         v.update_sensor_data(self.netatmo.devices)
        # except Exception as e:
        #     _log.error(f"Problem when update netatmo data: {e}")
        #     return

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)

        self.device_list = {}
        for k, v in self.netatmos.items():
            if k not in self.netatmo_apis:
                if v["client_id"] and v["client_secret"] and v["password"]:
                    self.netatmo_apis[k] = NetatmoAPI(v["client_id"], v["client_secret"], k, v["password"])
                else:
                    _log.debug("Please provide all requires netatmo credentials")
            else:
                if v["client_id"] and v["client_secret"] and v["password"]:
                    self.netatmo_apis[k].update_self(v["client_id"], v["client_secret"], k, v["password"])
                else:
                    _log.debug("Please provide all requires netatmo credentials")

    def last_rites(self):
        self._add_job("Die")

    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _send_samples_thread(self):
        while True:
            job = self.queue.get()
            self.queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            # _log.debug("_send_samples_thread")
            job["instance"].send_sample_thread(job["data"])


def main():
    """Main method called to start the agent."""
    utils.vip_main(netatmoweather, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
