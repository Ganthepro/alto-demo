"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import sys
import altolib
from netatmo import WeatherStation
import datetime as dt
import pytz
from volttron.platform.agent import utils

NETATMOMAP = {
    "temperature": "Temperature",
    "humidity": "Humidity",
    "pressure": "Pressure",
    "noise": "Noise",
    "co2": "CO2",
    "rain": "Rain",
    "wind": "WindStrength",
    "wind_angle": "WindAngle",
    "gust": "GustStrength",
    "gust_angle": " GusdtAngle",
    "voltage": "battery_vp",
    "timestamp": "time_utc",
}
MBPORT = 502


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class NAMainDevice(altolib.AltoEnvironSensor):
    """
    This is the Circutor 1 phase device
    """

    def __init__(self, controller, mac_addr, nb_subdev):
        super().__init__(controller, mac_addr, nb_subdev)
        self.datapoint_supported["environment"] += [
            "wind",
            "wind_angle",
            "gust",
            "gust_angle",
        ]
        # Now setup the map
        self.data_map.update(NETATMOMAP)
        del self.data_map["voltage"]
        self.initialise_data("environment", NETATMOMAP.keys())
        self.tz = None

    def to_environment_timestamp(self, val):
        tstmp = self.tz.localize(dt.datetime.fromtimestamp(val)).astimezone(
            pytz.timezone("UTC")
        )
        return tstmp.replace(tzinfo=dt.timezone.utc).isoformat()


class NADevice(altolib.AltoEnvironSensor, altolib.AltoElectricSensor):
    """
    This is the Circutor 1 phase device
    """

    def __init__(self, controller, mac_addr, nb_subdev):
        super().__init__(controller, mac_addr, nb_subdev)
        self.datapoint_supported["environment"] += [
            "wind",
            "wind_angle",
            "gust",
            "gust_angle",
        ]
        # Now setup the map
        self.data_map.update(NETATMOMAP)
        self.initialise_data("electric", NETATMOMAP.keys())
        self.initialise_data("environment", NETATMOMAP.keys())
        self.tz = None

    def to_electric_voltage(self, val):
        return val / 1000

    def to_environment_timestamp(self, val):
        tstmp = self.tz.localize(dt.datetime.fromtimestamp(val)).astimezone(
            pytz.timezone("UTC")
        )
        return tstmp.replace(tzinfo=dt.timezone.utc).isoformat()

    def to_electric_timestamp(self, val):
        return self.to_environment_timestamp(val)


def netatmo(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Blremote
    :rtype: Blremote
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        [
            "devices",
            "client_id",
            "secret",
            "username",
            "password",
            "agent_name",
            "timezones",
            "default_timezone",
        ],
        [[], "", "", "", "", "netatmo", {}, "Asia/Bangkok"],
    ):
        kwargs[x] = config.get(x, y)

    return Netatmo(topic, **kwargs)


class Netatmo(altolib.AltoBridgeAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        self.auto_send = False  # We update at low frequecy, let the agent manage
        # self.discovery_lock = Lock()
        self.sample_locks = {}
        _log.debug("vip_identity: " + self.core.identity)
        if self.client_id:
            self.netatmo = WeatherStation(
                {
                    "client_id": self.client_id,
                    "client_secret": self.secret,
                    "username": self.username,
                    "password": self.password,
                }
            )
        else:
            self.netatmo = None

    def _process_sample_data(self, adev):
        try:
            sample = []
            if "_id" in adev and adev["_id"] in self.devices:
                if "dashboard_data" in adev:
                    sample = adev["dashboard_data"].copy()
                    if "battery_vp" in adev:
                        sample["battery_vp"] = adev["battery_vp"]

                if sample:
                    if adev["_id"] not in self.device_list:
                        if "battery_vp" not in adev:
                            newdev = NAMainDevice(self, adev["_id"], 1)
                        else:
                            newdev = NADevice(self, adev["_id"], 1)
                        try:
                            newdev.tz = pytz.timezone(self.timezones[adev["_id"]])
                        except:
                            newdev.tz = pytz.timezone(self.default_timezone)
                        self.register_new_device(newdev)
                    self.device_list[adev["_id"]].set_sensor_data(sample)
                    self.device_list[adev["_id"]].event_sensor_sample(
                        "all", "all", "all"
                    )
        except Exception as e:
            _log.error(f"Problem when parsing semsor data: {e}")

    def send_samples(self):

        try:
            self.netatmo.get_data()
        except Exception as e:
            _log.error(f"Problem when retrieving semsor data: {e}")
            return
        if self.netatmo.devices:
            for adev in self.netatmo.devices:
                try:
                    self._process_sample_data(adev)
                    for mdev in adev["modules"]:
                        self._process_sample_data(mdev)
                except Exception as e:
                    _log.error(f"Problem when parsing semsor data: {e}")
        else:
            _log.debug(
                f"Did not get data with {self.netatmo.client_id}, {self.netatmo.client_secret} for {self.netatmo.username} with {self.netatmo.password} using token {self.netatmo.access_token}"
            )

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        if (
            self.netatmo is None
            or self.netatmo.client_id != self.client_id
            or self.netatmo.username != self.username
        ):
            self.netatmo = WeatherStation(
                {
                    "client_id": self.client_id,
                    "client_secret": self.secret,
                    "username": self.username,
                    "password": self.password,
                }
            )


def main():
    """Main method called to start the agent."""
    utils.vip_main(netatmo, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
