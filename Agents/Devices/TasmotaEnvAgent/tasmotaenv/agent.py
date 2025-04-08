"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import json
import sys
import ast
import altolib
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

SONOFFENVMAP = {
    "temperature": "temperature",
    "humidity": "humidity"
}

SONOFFZBBRIDGE = {
    "child_devices": "child_devices"
}
# Name of this module

class Sonoff_env(altolib.AltoEnvironSensor):
    """
    This is the Circutor 1 phase device
    """

    def __init__(self, controller, dev_id, nb_subdev=1):
        super().__init__(controller, dev_id, nb_subdev)

        # Now setup the map
        self.data_map.update(SONOFFENVMAP)
        self.initialise_data("environment", SONOFFENVMAP.keys())


    def to_environment_timestamp(self, val):
        tstmp = self.tz.localize(dt.datetime.fromtimestamp(val)).astimezone(
            pytz.timezone("UTC")
        )
        return tstmp.replace(tzinfo=dt.timezone.utc).isoformat()

    def to_environment_temperature(self, val):
        return val

    def to_environment_humidity(self, val):
        return val
class SonoffZigbeeBridge(altolib.AltoDeviceSensor):


    def __init__(self, controller, dev_id, nb_subdev=1):
        super().__init__(controller, dev_id, nb_subdev)

        # Now setup the map
        self.data_map.update(SONOFFZBBRIDGE)
        self.initialise_data("device", SONOFFZBBRIDGE.keys())


def tasmota(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Tasmota
    :rtype: Tasmota
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        ["vm_map", "agent_name", "mqtt_topics"],
        [["_", "_", "upper"], "tasmota", ["tele/#", "stat/#"]],
    ):

        kwargs[x] = config.get(x, y)

    return Tasmota(topic, **kwargs)


class Tasmota(altolib.AltoMQTTAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        _log.debug(f"vip_identity: {self.core.identity} with kwargs {kwargs}")

    def m_to_v(self, dev):
        """
        Translate device name from MQTT to Volttron
        """
        vc, mc, fc = self.vm_map
        device = dev.split(mc)
        if fc.lower() == "upper":
            device = device[0] + vc + device[1].lower()
        elif fc.lower() == "lower":
            device = device[0] + vc + device[1].upper()
        else:
            device = device[0] + vc + device[1]
        return device

    def v_to_m(self, dev):

        vc, mc, fc = self.vm_map
        device = dev.split(vc)
        if fc.lower() == "upper":
            device = device[0] + mc + device[1].upper()
        elif fc.lower() == "lower":
            device = device[0] + mc + device[1].lower()
        else:
            device = device[0] + mc + device[1]
        return device

    # The callback for when a PUBLISH message is received from the server.
    def process_mqtt_message(self, client, myself, msg):
        _log.debug(f"Got MQTT message from {client} for {msg.topic} --> {msg.payload}")
        for topic in self.mqtt_topics:
            usetopic = topic.replace("#", "")
            # _log.debug("Checking MQTT {} {} vs {} {}".format(msg.topic.__class__,msg.topic,usetopic,msg.topic.startswith(usetopic)))
            if msg.topic.startswith(usetopic):
                try:
                    dev, function = [
                        x for x in msg.topic.replace(usetopic, "").split("/") if x
                    ]
                    device = self.m_to_v(dev)
                    function = function.lower()
                    if device not in self.device_list and function not in [
                        "state",
                        "result",
                    ]:
                        # Ask for state
                        self.request_state(device)
                        break
                    _log.debug(f"msg in payload: {msg.payload.decode().lower()}")
                    if function.startswith("sensor"):

                        newstate = msg.payload.decode().lower()
                        newstate = ast.literal_eval(newstate)
                        if "zbreceived" in newstate:
                            zb_data = newstate["zbreceived"]
                            _log.debug(f"zb_data: {zb_data}")
                            child_devices = [k for k in zb_data]
                            for devid in zb_data:
                                if devid not in self.device_list:
                                    self.register_new_device(
                                        Sonoff_env(self, devid)
                                    )
                                    _log.debug(child_devices)
                                    self.device_list[device].set_sensor_data({"child_devices":child_devices},0)
                                sensor_data = {}
                                for dp in SONOFFENVMAP:
                                    sensor_data[dp] = zb_data[devid].get(dp, None)
                                _log.debug(f"sensor data: {sensor_data}")
                                self.device_list[devid].set_sensor_data(
                                    sensor_data, 0
                                )

                    elif function in ["result", "state"]:
                        self.register_new_device(
                            SonoffZigbeeBridge(self, device)
                        )
                        break
                    elif function == "lwt":
                        if device in self.device_list:
                            newstate = msg.payload.decode().lower()
                            self.device_list[device].online_status(newstate)

                except Exception as e:
                    _log.debug("\n\nOpps: {}".format(e))
                    _log.exception(e)

    @RPC.export
    def request_state(self, device_id):
        """
        Requerst status over MQTT
        """
        # thisdev = self.v_to_m(device_id)
        topic = "cmnd/tasmotas/STATE"
        # topic = "cmnd/" + thisdev + "/STATE"
        self.send_mqtt_message(topic, None)


def main():
    """Main method called to start the agent."""
    utils.vip_main(tasmota, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
