"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import altolib
import requests
import sys
from volttron.platform.agent import utils

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class FirebaseDevice(altolib.AltoLoggerDevice):
    def __init__(self, controller, devid, enable_firebase_local=False, logtype=None):
        super().__init__(controller, devid, logtype)
        self.data = {}
        self.enable_firebase_local = enable_firebase_local

    @property
    def url(self):
        return f"{self.controller.host}:{self.controller.port}{self.controller.target}"

    def log_data(self, data):
        _log.debug(f"Saving {data}")
        devid = data["device_id"]
        subdevid = data["subdevice_idx"]
        if devid not in self.data:
            self.data[devid] = {}
        if subdevid not in self.data[devid]:
            self.data[devid][subdevid] = {}
        for k, v in data.items():
            if k not in ["datapoint", "value"]:
                self.data[devid][subdevid][k] = v
        self.data[devid][subdevid][data["datapoint"]] = data["value"]

    def flush_data(self):
        """
        We log the data directly
        """
        _log.debug(f"Firebase local server to {self.url} -> {self.data}")
        for dev in [k for k in self.data.keys()]:
            subdata = self.data[dev]
            del self.data[dev]
            _log.debug(f"Logging for {dev} with {subdata}")
            for mydata in subdata.values():
                _log.debug(f"\tSublogging with {mydata}")
                try:
                    payload = {}
                    for x in mydata:
                        if x in ["device_id", "subdevice_idx", "location", "type"]:
                            if x == "subdevice_idx":
                                payload["subdevice"] = f"subdev_{mydata[x]}"
                            elif x == "type":
                                payload["schema"] = mydata[x]
                            else:
                                payload[x] = mydata[x]

                    payload["data"] = {}
                    for k, v in mydata.items():
                        if k not in ["device_id", "subdevice_idx", "location", "type"]:
                            payload["data"][k] = v
                    _log.debug(f"\n\tPayload {payload}")
                    response = requests.post(self.url, json=payload)
                    _log.debug(
                        "Response HTTP Status Code: {status_code}".format(
                            status_code=response.status_code
                        )
                    )
                    _log.debug(f"Response HTTP Response Body: {response.content}")

                    # firebase local
                    if self.enable_firebase_local:
                        response = requests.post(f"{self.controller.host}:8050{self.controller.target}", json=payload)
                        _log.debug(
                            "Response HTTP Status Code: {status_code}".format(
                                status_code=response.status_code
                            )
                        )
                        _log.debug(f"Response HTTP Response Body: {response.content}")
                        # end firebase local
                except requests.exceptions.RequestException as f:
                    _log.debug(f"HTTP Request failed: {f}")
                except Exception as e:
                    _log.debug(f"Something went wrong: {e}")


def firebaselogger(config_path, **kwargs):
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
    kwargs["agent_name"] = config.get("agent_name", "firebaselogger")
    kwargs["host"] = config.get("host", "http://localhost")
    kwargs["port"] = config.get("port", 8088)
    kwargs["target"] = config.get("target", "/submit")
    kwargs["logtype"] = config.get("logtype", None)
    kwargs["enable_firebase_local"] = config.get("enable_firebase_local", False)

    return Firebaselogger(topic, **kwargs)


class Firebaselogger(altolib.AltoDatalogger):
    """
    Document agent constructor here.
    """

    def register_self(self):
        if self.logtype is not None:
            for idx, v in enumerate(self.logtype):
                _log.debug(f'''Firebaselogger {v}''')
                ndev = FirebaseDevice(self, self.agent_name + str(idx), self.enable_firebase_local, v)
                self.register_new_device(ndev)
        else:
            _log.debug(f'''Firebaselogger logtype {self.logtype}''')
            ndev = FirebaseDevice(self, self.agent_name, self.enable_firebase_local, None)
            self.register_new_device(ndev)


def main():
    """Main method called to start the agent."""
    utils.vip_main(firebaselogger, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass