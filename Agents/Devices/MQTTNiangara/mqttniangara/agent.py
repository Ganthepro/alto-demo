"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
import ast
import random

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

import altolib

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class AltoGeneralSensor(altolib.AltoSensorDevice):
    """
    This is one of the various sensor's type. This one for general data.
    The general sensor is an unformatted sensor data.
    So, please use this for debug only.
    """

    def __init__(self, controller, devid, nbsubdev = 1):
        super().__init__(controller, devid, nbsubdev)
        self.datapoint_supported["general"] = []

        for idx in range(self.number_subdevices):
            self.current_state[idx]["sensor"]["general"] = {}
    
    def update_datapoint_supported(self, datapoint):
        if datapoint not in self.datapoint_supported["general"]:
            self.datapoint_supported["general"].append(datapoint)
    
    def update_data_map(self, data_map):
        self.data_map.update(data_map)
    
    def initialise_data(self, sensor_type, datapoints):
        """
        Set the initial data for all subdevice to None for all datapoint set in datapoints
        :param sensor_type: One of "environment","electric","device",
        :type sensor_type: str
        :param datapoints: the list of datapoint name supported by the device
        :type datapoints: list
        :returns: None
        :rtype: None
        """
        for idx in range(self.number_subdevices):
            if sensor_type in self.current_state[idx]["sensor"]:
                thissd = self.current_state[idx]["sensor"][sensor_type]
                for attr in set(self.datapoint_supported[sensor_type]).intersection(
                    set(datapoints)
                ):
                    if attr not in thissd:
                        thissd[attr] = None
                if "timestamp" not in thissd:
                    thissd["timestamp"] = None
            else:
                _log.error(f"This device does not support {sensor_type} sensors.")
        _log.debug(f"Devices initialised as {self.current_state[0]}.")


def mqttniangara(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Mqttniangara
    :rtype: Mqttniangara
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        ["vm_map", "agent_name", "mqtt_topics"],
        [["_", "_", "upper"], "mqttniagara", ["tele/#", "stat/#"]],
    ):
        kwargs[x] = config.get(x, y)

    return Mqttniangara(topic, **kwargs)


class Mqttniangara(altolib.AltoMQTTAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Mqttniangara, self).__init__(topic, **kwargs)
        _log.debug(f"vip_identity: {self.core.identity} with kwargs {kwargs}")

        self._sampling_rate_cd = 15 # overlide default start polling time
        self.auto_send = True  # set to True if you need set_sensor_data can be auto update after meet condition
        # self.discovery_lock = Lock()
        self.sample_locks = {}
    
    def send_samples(self):
        _log.debug(f'''send_samples {self.device_list}''')

    def process_mqtt_message(self, client, myself, msg):
        """
        The callback for when a PUBLISH message is received from the server.
        """

        _log.debug(f"Got MQTT message from {client} for {msg.topic} --> {msg.payload}")
        # for topic in self.mqtt_topics:
        #     usetopic = topic.replace("#", "")
        #     # _log.debug("Checking MQTT {} {} vs {} {}".format(msg.topic.__class__,msg.topic,usetopic,msg.topic.startswith(usetopic)))
        #     if msg.topic.startswith(usetopic):
        #         pass
        try:
            topic_in = msg.topic.split("/")
            newstate = msg.payload.decode().lower()
            newstate = ast.literal_eval(newstate)
            dp = topic_in[-1]
            del topic_in[-1]
            devid = ":".join(topic_in)
            _log.debug(f"newstate: {newstate}")
            # dp_value = random.randint(0, 99)
            dp_value = newstate.get("value", -1)
            if devid not in self.device_list:
                self.register_new_device(
                    AltoGeneralSensor(self, devid)
                )
                self.device_list[devid].update_datapoint_supported(dp)
                self.device_list[devid].update_data_map({dp: dp})
                self.device_list[devid].initialise_data("general", [dp])
                self.device_list[devid].set_sensor_data({dp: dp_value}, 0, "general")
            else:
                self.device_list[devid].update_datapoint_supported(dp)
                self.device_list[devid].update_data_map({dp: dp})
                self.device_list[devid].initialise_data("general", [dp])
                self.device_list[devid].set_sensor_data({dp: dp_value}, 0, "general")
        except Exception as e:
            _log.debug(f"Mqttniangara {e}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(mqttniangara, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
