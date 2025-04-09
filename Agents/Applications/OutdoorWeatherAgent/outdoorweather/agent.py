"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import pyrebase
import pendulum
import threading
import pandas as pd
from datetime import datetime, timedelta
import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.scheduling import periodic, cron
from pprint import pformat
from typing import Dict, List, Tuple, Union
import requests
from volttron.platform.messaging.health import STATUS_GOOD, STATUS_BAD, STATUS_STARTING, STATUS_UNKNOWN
import json
_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

# configuration and setting firebase
firebase_config = {
    "apiKey": "AIzaSyD9tk_eukD0pyRUAWO9lFqMTy4hGbTFJJA",
    "authDomain": "altogetstarted.firebaseapp.com",
    "databaseURL": "https://altogetstarted-default-rtdb.firebaseio.com",
    "storageBucket": "altogetstarted.appspot.com",
}
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()


def outdoorweather(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: OutdoorWeather
    :rtype: OutdoorWeather
    """
    try:
        config = utils.load_config(config_path)
    except Exception as er:
        print(er)
        config = {}
    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    heartbeat_period = int(config.get("heartbeat_period", 10))
    message = config.get('message', "DEFAULT_MESSAGE")
    return OutdoorWeather(setting1, heartbeat_period, message, **kwargs)


class OutdoorWeather(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, heartbeat_period=10, message="message", **kwargs):
        super(OutdoorWeather, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self._logfn = _log.info
        self.setting1 = setting1
        self.publish_value = 1
        self._heartbeat_period = heartbeat_period
        self._message = message
        self.default_config = {"setting1": setting1}

        self._heartbeat_period = heartbeat_period

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        try:
            setting1 = int(config["setting1"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.setting1 = setting1

    def scrape_outdoor_weather(self, **kw) -> dict:
        """Scrape data from weather underground."""

        def worker(dt):
            a = requests.get(
                f"https://api.weather.com/v1/location/{kw['location']}:9:TH/observations/historical.json?apiKey=6532d6454b8aa370768e63d6ba5a832e&units=e&startDate={dt}")
            b = json.loads(a.text)
            c = pd.DataFrame(b["observations"])
            data[dt] = c

        yesterday = pendulum.yesterday('Asia/Bangkok')
        tomorrow = pendulum.tomorrow('Asia/Bangkok')
        _valid_time = datetime(year=yesterday.year, month=yesterday.month, day=yesterday.day)
        _end_time = datetime(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)
        data = {}
        num_th = 20
        while _end_time > _valid_time:
            threads = []
            for i in range(num_th):
                if _end_time <= _valid_time:
                    break
                dt = _valid_time.strftime("%Y%m%d")
                t = threading.Thread(target=worker, args=(dt,))
                threads.append(t)

                _valid_time += timedelta(days=1)

            for t in threads:
                t.start()

            for t in threads:
                t.join()

        return data

    def preprocess_data(self, data: dict):
        """
        Proprocess data
        :param data: outdoor weather [dict]
        :return: today weather pandas dataframe
        """
        dfdata = pd.concat([data[k] for k in data], axis=0)
        df = dfdata.copy()
        df = df.sort_values(by="valid_time_gmt")

        df["datetime"] = pd.to_datetime(df["valid_time_gmt"].astype(int) * 1e9, yearfirst=True) + timedelta(hours=7)
        df = df.set_index("datetime")

        columns = ['obs_name', 'temp', 'rh', 'pressure', 'wspd', 'wx_phrase', 'clds', 'precip_total', 'precip_hrly']
        df = df[columns]

        # Rename columns to be consistent with firebase node
        df = df.rename(
            columns={'obs_name': 'location', 'temp': 'temperature', 'rh': 'relative_humidity', 'wspd': 'wind_speed',
                     'wx_phrase': 'weather'})

        df["temperature"] = round((df["temperature"] - 32) / 9 * 5, 2)
        df["pressure"] = round(df["pressure"] * 33.86, 2)
        df['wind_speed'] = round(df['wind_speed'] * 1.609, 2)

        today = pendulum.today('Asia/Bangkok').to_date_string()
        return df.loc[today]

    def prepare_dict(self, df) -> dict:
        """
        Prepare python dict in the format that can update firebase
        :param df: pandas dataframe contains today weather data
        :return:
        """
        last_record = df.iloc[-1]
        data = {
            'location': last_record['location'],
            'latest_record_datetime': str(df.index[-1]),
            'temperature': {'value': float(last_record['temperature']), 'unit': 'celcius'},
            'relative_humidity': {'value': float(last_record['relative_humidity']), 'unit': '%'},
            'pressure': {'value': float(last_record['pressure']), 'unit': 'mbar'},
            'weather': last_record['weather'],
            'wind_speed': {'value': float(last_record['wind_speed']), 'unit': 'km/h'},
            'updated_at': pendulum.now('Asia/Bangkok').int_timestamp,
        }

        return data

    def prep_daily_weather_df(self, dfw) -> dict:
        datetime_list, unix_timestamp_list = [], []
        for minute in range(0, 1440, 30):
            datetime = pendulum.today('Asia/Bangkok').add(minutes=minute)
            unix_timestamp = datetime.int_timestamp
            datetime_list.append(datetime.to_datetime_string())
            unix_timestamp_list.append(unix_timestamp)

        df = pd.DataFrame()
        df['datetime'] = datetime_list
        df['unix_timestamp'] = unix_timestamp_list
        df['weather'] = 'None'

        for column in ['temperature', 'relative_humidity', 'pressure', 'wind_speed']:
            df[column] = 0

        df.update(dfw.reset_index(), overwrite=True)
        df = df.drop(columns=['datetime'])

        # # df['datetime'] = datetime_list
        df.set_index('unix_timestamp', inplace=True)

        return df.to_dict()

    def prep_weather_forecast_data(self):
        link = 'https://api.weather.com/v1/location/VTBD:9:TH/forecast/hourly/24hour.json?units=e&language=en-US&apiKey=6532d6454b8aa370768e63d6ba5a832e'
        res = requests.get(link)
        print(json.loads(res.text)['metadata'])
        df = pd.DataFrame(json.loads(res.text)['forecasts'])
        df['datetime'] = pd.to_datetime(df['fcst_valid_local'].map(lambda x: pendulum.parse(x).to_datetime_string()))

        # Rename columns to be consistent with firebase node
        df = df.rename(columns={'temp': 'temperature', 'rh': 'relative_humidity', 'wspd': 'wind_speed',
                                'phrase_32char': 'weather'})

        columns = ['datetime', 'temperature', 'relative_humidity', 'wind_speed', 'weather', 'fcst_valid']
        df = df[columns]
        df = df.set_index('fcst_valid')
        df = df.drop(columns=['datetime'])

        df["temperature"] = round((df["temperature"] - 32) / 9 * 5, 2)
        df['wind_speed'] = round(df['wind_speed'] * 1.609, 2)
        return df.to_dict()

    def update_firebase(self, data_to_update: dict, daily_weather_to_update: dict):
        """Update firebase with the latest data"""
        db.child("building").child("pmcu").child("pages").child("dashboard").child("outdoor_weather").update(
            data_to_update)
        db.child("building").child("pmcu").child("pages").child("dashboard").child("daily_weather").update(
            daily_weather_to_update)

    def update_weather_forecast_firebase(self, weather_forecast_data_to_update):
        """Update firebase with the weather forecast data"""
        db.child("building").child("pmcu").child("pages").child("dashboard").child("weather_forecast").update(weather_forecast_data_to_update)


    def run_all_methods(self):
        """Method to be executed as cron every 15 minutes"""
        try:
            # Step 1: Scrape data from weather underground.
            weather_data = self.scrape_outdoor_weather(location='VTBD')

            """
            Step 2: Preprocess data
                2.1 load data as a pandas dataframe
                2.2 drop unused columns
                2.3 convert units
            """
            dfw = self.preprocess_data(weather_data)

            # Step 3: Prepare python dict in the format that can update firebase
            data_to_update = self.prepare_dict(dfw)
            daily_weather_to_update = self.prep_daily_weather_df(dfw)

            # Step 4: Update firebase with the latest data
            self.update_firebase(data_to_update, daily_weather_to_update)

            print("Done Cron job")
        except Exception as e:
            print(f"run all fn error: {e}")

    def run_weather_forecast(self):
        try:
            # Step 1: Consume forecast api
            weather_forecast_data_to_update = self.prep_weather_forecast_data()

            # Step 2: Update data to firebase!
            self.update_weather_forecast_firebase(weather_forecast_data_to_update)
            print("Done Weather Forecast Cron job")
        except Exception as e:
            print(f"run weather forecast error: {e}")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        _log.debug("VERSION IS: {}".format(self.core.version()))
        # self.run_all_methods()
        self.core.schedule(cron('*/15 * * * *'), self.run_all_methods)

        self.core.schedule(cron('30 23 * * *'), self.run_weather_forecast)
        # self.run_weather_forecast()


    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        # Example publish to pubsub
        # self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # using the agent's core to schedule a task
        # self.core.schedule(periodic(5), self.sayhi)
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

def main():
    """Main method called to start the agent."""
    utils.vip_main(outdoorweather,
                   version=__version__)

if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
