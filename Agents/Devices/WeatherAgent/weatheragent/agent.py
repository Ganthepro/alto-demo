"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import sys
import altolib
import requests
import datetime as dt
import pytz
import json
from volttron.platform.agent import utils

WEATHERMAP = {
    "temperature": "temp_c",
    "temperature_sub": "feelslike_c",
    "humidity": "humidity",
    "pressure": "pressure_mb",
    "wind": "wind_kph",
    "wind_angle": "wind_degree",
    "gust": "gust_kph",
    "timestamp": "last_updated_epoch",
    "visibility": "vis_km",
    "cloud": "cloud",
    "uv": "uv",
    "rain": "precip_mm",
}
MBPORT = 502


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class WeatherDevice(altolib.AltoEnvironSensor):
    """
    This is the Circutor 1 phase device
    """

    def __init__(self, controller, devid, nb_subdev, api, lat, lon, tz):
        super().__init__(controller, devid, nb_subdev)
        self.datapoint_supported["environment"] += [
            "wind",
            "wind_angle",
            "gust",
            "visibility",
            "cloud",
            "uv",
            "rain",
        ]
        # Now setup the map
        self.data_map.update(WEATHERMAP)
        self.initialise_data("environment", WEATHERMAP.keys())
        self.api = api
        self.latitude = lat
        self.longitude = lon
        self.tz = pytz.timezone(tz)
        self.url = "https://api.weatherapi.com/v1/current.json"

    def to_environment_timestamp(self, val):
        tstmp = self.tz.localize(dt.datetime.fromtimestamp(val)).astimezone(
            pytz.timezone("UTC")
        )
        return tstmp.replace(tzinfo=dt.timezone.utc).isoformat()

    def get_data(self):
        params = {"key": self.api}
        params["q"] = f"{self.latitude},{self.longitude}"
        # _log.debug(f"Getting data with {self.current_state[0]}")
        try:
            res = requests.get(self.url, params=params)
            # _log.debug(f"Got code {res.status_code} with {res.text}")
            if res.status_code == 200:
                data = json.loads(res.text)
                data["current"].update(data["current"]["condition"])
                self.set_sensor_data(data["current"])
            else:
                _log.error(
                    f"Could not retrieve weather data: Return code {res.status_code}"
                )
        except Exception as e:
            _log.debug(f"Error when retrieving Weather data: {e}")

    def get_location_data(self, lat, lon):
        params = {"key": self.api}
        params["q"] = f"{lat},{lon}"
        try:
            res = requests.get(self.url, params=params)
            if res.status_code == 200:
                data = json.loads(res.text)
                data["current"].update(data["current"]["condition"])
                pdata = {"status": "ok"}
                for dp, sp in self.data_map.items():
                    if sp in data["current"]:
                        pdata[dp] = getattr(self, f"to_environment_{dp}", lambda x: x)(
                            data["current"][sp]
                        )
                for dp in ["name", "region", "country"]:
                    if dp in data["location"]:
                        if dp == "name":
                            kn = "location"
                        else:
                            kn = dp
                        pdata[kn] = data["location"][dp]
                return pdata
            else:
                pdata = {
                    "status": "error",
                    "error_msg": f"Return code {res.status_code}",
                }
        except Exception as e:
            _log.debug(f"Error when retrieving location weather data: {e}")


def weather(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: weather
    :rtype: weather
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        ["api_key", "latitude", "longitude", "agent_name", "timezone",],
        ["", 13.752744, 100.668494, "weather", "Asia/Bangkok"],
    ):
        kwargs[x] = config.get(x, y)

    return Weather(topic, **kwargs)


class Weather(altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        # self.discovery_lock = Lock()
        self.sample_locks = {}
        _log.debug("vip_identity: " + self.core.identity)
        self.weather = None
        self.register_self()

    def register_self(self):
        if self.api_key:
            self.weather = WeatherDevice(
                self,
                "weatherapi",
                1,
                self.api_key,
                self.latitude,
                self.longitude,
                self.timezone,
            )
            self.device_list[self.weather.device_id] = [self.weather]
            self.set_heartbeat_status("GOOD")

    def handle_request_sensor(self, topic, message):
        """
             Handles devinfo.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Sensor request handler cannot parse topic")
        _log.debug(f"Weather Request with {message}")
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            elif func == "weather":
                msg = {"rid": message["rid"], "device_id": devid}
                data = self.weather.get_location_data(
                    message["latitude"], message["longitude"]
                )
                msg.update(data)
                self.publish(message["reply_to"], msg, "response")
            else:
                _log.warning(f"Request {func} is not know to the sensor schema")
        except Exception as e:
            _log.debug("\n\nOpps in switch request: {}".format(e))
            _log.exception(e)

    def send_samples(self):
        if self.weather:
            self.weather.get_data()


def main():
    """Main method called to start the agent."""
    utils.vip_main(weather, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
