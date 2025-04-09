"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

import re
import pendulum
from volttron.platform.scheduling import periodic, cron
import requests

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


DATAPOINT_MAPPING = {
    "station": {
        "stationID": "location",
        "obsTimeUtc": "timestamp",
        "uv": "uv_index",
        "winddir": "wind_direction",
        "humidity": "humidity",
        "temp": "ambient_temperature",
        "heatIndex": "heat_index",
        "dewpt": "dew_point_temperature",
        "windChill": "wind_chill",
        "windSpeed": "wind_speed",
        "windGust": "wind_gust",
        "pressure": "pressure",
        "precipRate": "precipitation_rate",
        "precipTotal": "precipitation_total",
        "elev": "elevation",
        "solarRadiation": "solar_radiation"
    },
    "latlon": {
        "validTimeLocal": "timestamp",
        "cloudCeiling": "cloud_ceiling",
        "cloudCoverPhrase": "cloud_condition",
        "iconCode": "icon_code",
        "precip1Hour": "precipitation_1hour",
        "precip6Hour": "precipitation_6hour",
        "precip24Hour": "precipitation_24hour",
        "pressureAltimeter": "pressure",
        "relativeHumidity": "humidity",
        "temperature": "ambient_temperature",
        "temperatureDewPoint": "dew_point_temperature",
        "temperatureFeelsLike": "feels_like_temperature",
        "temperatureHeatIndex": "heat_index_temperature",
        "temperatureWindChill": "wind_chill_temperature",
        "uvIndex": "uv_index",
        "visibility": "visibility",
        "windDirection": "wind_direction",
        "windGust": "wind_gust",
        "windSpeed": "wind_speed",
        "wxPhraseLong": "weather_condition",
    },
    "hourly_forecast_by_latlon": {
        "validTimeLocal": "timestamp",
        "cloudCover": "forecast_cloud_cover_percentage",
        "iconCode": "forecast_icon_code",
        "precipChance": "forecast_precipitation_change",
        "precipType": "forecast_precipitation_type",
        "pressureMeanSeaLevel": "forecast_pressure",
        "relativeHumidity": "forecast_humidity",
        "temperature": "forecast_ambient_temperature",
        "temperatureDewPoint": "forecast_dew_point_temperature",
        "temperatureFeelsLike": "forecast_feels_like_temperature",
        "temperatureHeatIndex": "forecast_heat_index_temperature",
        "temperatureWindChill": "forecast_wind_chill_temperature",
        "uvIndex": "forecast_uv_index",
        "visibility": "forecast_visibility",
        "windDirection": "forecast_wind_direction",
        "windGust": "forecast_wind_gust",
        "windSpeed": "forecast_wind_speed",
        "wxPhraseLong": "forecast_weather_condition",
    },
    "hourly_forecast_by_station": {
        "fcst_valid_local": "timestamp",
        "temp": "forecast_ambient_temperature",
        "dewpt": "forecast_dew_point_temperature",
        "hi": "forecast_heat_index_temperature",
        "wc": "forecast_wind_chill_temperature",
        "feels_like": "forecast_feels_like_temperature",
        "icon_code": "forecast_icon_code",
        "phrase_32char": "forecast_weather_condition",
        "precip_type": "forecast_precipitation_type",
        "rh": "forecast_humidity",
        "wspd": "forecast_wind_speed",
        "wdir": "forecast_wind_direction",
        "gust": "forecast_wind_gust",
        "clds": "forecast_cloud_cover",
        "vis": "forecast_visibility",
        "mslp": "forecast_pressure",
        "uv_index_raw": "forecast_uv_index",
    }
}

def weatherunderground(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Weatherunderground
    :rtype: Weatherunderground
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    site_name = config.get('site_name', None)
    wu_api_settings = config.get('wu_api_settings', dict())
    
    return Weatherunderground(site_name, wu_api_settings, **kwargs)


class Weatherunderground(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, site_name: str, wu_api_settings: dict, **kwargs):
        super(Weatherunderground, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.site_name = site_name
        
        # Parse the WU API settings
        self.station_id = wu_api_settings.get("station_id")
        self.lat = wu_api_settings.get("lat")
        self.lon = wu_api_settings.get("lon")
        
        # Saving latest published payloads to avoid republishing the same data
        self.latest_payloads = {
            'station_current': dict(),
            'latlon_current': dict(),
            'station_forecast': dict(),
            'latlon_forecast': dict()
        }

        if isinstance(self.lat, (int, float)):
            self.lat = round(self.lat, 2)
        if isinstance(self.lon, (int, float)):
            self.lon = round(self.lon, 2)
        
        self.default_config = {
            "site_name": site_name,
            "wu_api_settings": wu_api_settings,
        }

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
            site_name = config.get('site_name', None)
            wu_api_settings = config.get('wu_api_settings', dict())

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.site_name = site_name
        
        # Parse the WU API settings
        self.station_id = wu_api_settings.get("station_id")
        self.lat = wu_api_settings.get("lat")
        self.lon = wu_api_settings.get("lon")
        
        if isinstance(self.lat, (int, float)):
            self.lat = round(self.lat, 2)
        else:
            self.lat = None
            
        if isinstance(self.lon, (int, float)):
            self.lon = round(self.lon, 2)
        else:
            self.lon = None
                
        # Set cron job to run every 1 minutes
        self.core.schedule(periodic(60), self.emit_current_weather_data)
        self.core.schedule(cron("30 23 */1 * *"), self.emit_forecast_weather_data)

    def set_site_station_id(self, station_id: str):
        """
        Set the station ID for the site.
        """
        self.station_id = station_id
        
    def set_site_lat_lon(self, lat: float, lon: float):
        """
        Set the latitude and longitude for the site.
        """
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            self.lat = round(self.lat, 2)
            self.lon = round(self.lon, 2)
        else:
            _log.error("ERROR: lat and lon must be float or int")
    
    def _retrieve_api_key(self):
        """
        Scrape the API key from the WU website homepage.
        """
        url = 'https://www.wunderground.com/'
        response = requests.get(url)

        text = response.text
        pattern = r'apiKey=(.*?)&'

        # Search for matches using the pattern
        match = re.search(pattern, text)

        # Print the captured text
        if match:
            captured_text = match.group(1)
            self.api_key = captured_text
            
    def get_current_weather_observation(self, unit: str = 'metric', by: str = 'station'):
        """
        Get the current weather observation by either official WU station or by lat/lon
        
        Args:
            unit (str): Either 'imperial' or 'metric'
            by (str): Either 'station' or 'latlon'
            
            There are few differences between getting data from official WU station and lat/lon coordinate.
            - The current weather conditions from official WU stations are updated every few seconds.
            - The current weather conditions from lat/lon coordinate are updated every 10 minutes.
            
        Returns:
            dict: The current weather observation
        
        """
        # Step 1: Retrieve API key
        self._retrieve_api_key()
        
        # Step 2: Parse the unit arg
        if unit == 'imperial':
            unit_code = 'e'
        elif unit == 'metric':
            unit_code = 'm'
        else:
            logging.error("unit must be either imperial or 'si'")
            return None
        
        # Step 3: Check whether to get data from the WU station or lat/lon coordinate and retrieve the data
        if by == 'station':
            if self.station_id is None:
                logging.error("Site station_id is not set")
                return None
            url = f'https://api.weather.com/v2/pws/observations/current?apiKey={self.api_key}&units={unit_code}&stationId={self.station_id}&format=json'
        elif by == 'latlon':
            if self.lat is None or self.lon is None:
                logging.error("Site lat and lon are not set")
                return None
            url = f"https://api.weather.com/v3/wx/observations/current?apiKey={self.api_key}&geocode={self.lat}%2C{self.lon}&units={unit_code}&language=en-US&format=json"
        response = requests.get(url)
        
        if response.status_code != 200:
            logging.error(f"Failed to get current weather observation. Status code: {response.status_code}")
            return None
        
        # Step 4: Parse the data
        if by == "station":
            data = response.json()['observations'][0]
            data.update(data.pop(unit))
        elif by == "latlon":
            data = response.json()
            
        # Step 5: Preprocess the data
        data_payload = dict()
        for wu_conv, dp in DATAPOINT_MAPPING[by].items():
            value = data.get(wu_conv)
            if value is not None:
                data_payload[dp] = value    
        
        data_payload['timestamp'] = pendulum.parse(data_payload['timestamp']).isoformat()
        data_payload['unix_timestamp'] = pendulum.parse(data_payload['timestamp']).timestamp()
        
        return data_payload

    def get_forecast_weather_observation(self, unit: str = 'metric', by: str = 'station'):
        """
        Get the current weather observation by either official WU station or by lat/lon
        
        Args:
            unit (str): Either 'imperial' or 'metric'
            by (str): Either 'station' or 'latlon'
            
            There are few differences between getting data from official WU station and lat/lon coordinate.
            - The list of points is different
            - The forecast weather data queried by station is only available for airport stations (station starting with "V" like VTBS, VTBD).
            
        Returns:
            dict: The current weather observation
            
        """
        # Step 1: Retrieve API key
        self._retrieve_api_key()
        
        # Step 2: Parse the unit arg
        if unit == 'imperial':
            unit_code = 'e'
        elif unit == 'metric':
            unit_code = 'm'
        else:
            logging.error("unit must be either imperial or 'si'")
            return None
        
        # Step 3: Check whether to get data from the WU station or lat/lon coordinate and retrieve the data
        if by == 'station':
            if self.station_id is None:
                logging.error("Site station_id is not set")
                return None
            elif not self.station_id.startswith('V'):
                logging.error("Only airport stations (station starting with 'V') are supported for forecast weather data")
                return None
            url = f"https://api.weather.com/v1/location/{self.station_id}:9:TH/forecast/hourly/24hour.json?units={unit_code}&language=en-US&apiKey={self.api_key}"
        elif by == 'latlon':
            if self.lat is None or self.lon is None:
                logging.error("Site lat and lon are not set")
                return None
            url = f"https://api.weather.com/v3/wx/forecast/hourly/1day?apiKey={self.api_key}&geocode={self.lat}%2C{self.lon}&language=en-US&units={unit_code}&format=json"
        response = requests.get(url)
        
        if response.status_code != 200:
            logging.error(f"Failed to get current weather observation. Status code: {response.status_code}")
            return None
        
        # Step 4: Parse and preprocess the data
        lod = list()
        if by == "station":
            data = response.json()['forecasts']  # List
            for row in data:
                entry = dict()
                for wu_conv, dp in DATAPOINT_MAPPING["hourly_forecast_by_station"].items():
                    value = row.get(wu_conv)
                    if value is not None:
                        entry[dp] = value
                entry['timestamp'] = pendulum.parse(entry['timestamp']).isoformat()
                entry['unix_timestamp'] = pendulum.parse(entry['timestamp']).timestamp()
                lod.append(entry)
                
        elif by == "latlon":
            data = response.json()  # Dictionary of lists
            for i in range(24):
                entry = dict()
                for wu_conv, dp in DATAPOINT_MAPPING["hourly_forecast_by_latlon"].items():
                    lov = data.get(wu_conv)  # List of values
                    if value is not None:
                        lod[dp] = lov[i]
                entry['timestamp'] = pendulum.parse(entry['timestamp']).isoformat()
                entry['unix_timestamp'] = pendulum.parse(entry['timestamp']).timestamp()
                lod.append(entry)
        
        return lod

    def emit_current_weather_data(self):
        """
        Publish the current weather data to the message bus.
        """
        
        for datasource in ['station', 'latlon']:

            payload = self.get_current_weather_observation(unit='metric', by=datasource)
            if payload == self.latest_payloads[datasource + '_current']:
                _log.info(f"Current weather data from {datasource} is not updated. Skip publishing.")
                continue
            else:
                self.latest_payloads[datasource + '_current'] = payload

            if datasource == 'station':
                location = self.station_id
            elif datasource == 'latlon':
                location = f"{self.lat}_{self.lon}"

            topic = f'weather/{self.core.identity}/{location}/event'

            payload.update({
                'location': location,
                'type': 'weather',
                'device_id': datasource + '_' + location
            })

            self.vip.pubsub.publish(peer='pubsub', topic=topic, message=payload)
            _log.info(f"Published current weather data to {topic} with payload: {payload}")
    
    def emit_forecast_weather_data(self):
        """
        Publish the forecast weather data to the message bus.
        
        A total of 24 messages (each correspond to hourly forecast) of data will be published every 23:30 of everyday.
        """

        for datasource in ['station', 'latlon']:

            payload = self.get_forecast_weather_observation(unit='metric', by=datasource)
            if payload == self.latest_payloads[datasource + '_forecast']:
                _log.info(f"Forecasted weather data from {datasource} is not updated. Skip publishing.")
                continue
            else:
                self.latest_payloads[datasource + '_forecast'] = payload

            if datasource == 'station':
                location = self.station_id
            elif datasource == 'latlon':
                location = f"{self.lat}_{self.lon}"

            topic = f'weather_forecast/{self.core.identity}/{location}/event'

            payload.update({
                'location': location,
                'type': 'weather_forecast',
                'aggregate_type': 'avg_1h',
                'device_id': datasource + '_' + location
            })

            self.vip.pubsub.publish(peer='pubsub', topic=topic, message=payload)
            _log.info(f"Published forecast weather data to {topic} with payload: {payload}")

def main():
    """Main method called to start the agent."""
    utils.vip_main(weatherunderground, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
