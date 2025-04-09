"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import json
import sys
import altolib
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

# Name of this module


class TasmotaDevice(altolib.AltoSwitchDevice):
    """
        Representing a single tasmota device
    """

    def turn_on(self, subdev):
        mqttdev = self.controller.v_to_m(self.device_id)
        topic = "cmnd/" + mqttdev + f"/POWER{subdev+1}"
        topic = topic.replace("//", "/")
        self.controller.send_mqtt_message(topic, "ON")

    def turn_off(self, subdev):
        mqttdev = self.controller.v_to_m(self.device_id)
        topic = "cmnd/" + mqttdev + f"/POWER{subdev+1}"
        topic = topic.replace("//", "/")
        self.controller.send_mqtt_message(topic, "OFF")

    def update_device(self, device):
        """
        In some cases, we may not have all idx, so check and keep what we already know
        """
        if self.number_subdevices < device.number_subdevices:
            self.name_subdevices += [
                f"subdev_{i}"
                for i in range(self.number_subdevices, device.number_subdevices)
            ]
            self.number_subdevices = device.number_subdevices
            self.current_state = {**device.current_state, **self.current_state}

        return self


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


class Tasmota(altolib.AltoMQTTAgent, altolib.AltoSwitch):
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

                    if function.startswith("power"):
                        subdevice_idx = function.replace("power", "")
                        if subdevice_idx:
                            subdevice_idx = int(subdevice_idx) - 1
                        else:
                            subdevice_idx = 0
                        newstate = msg.payload.decode().lower()
                        self.device_list[device].update_switch_state(
                            subdevice_idx, newstate
                        )

                    elif function in ["result", "state"]:
                        thispayload = json.loads(msg.payload.decode())
                        relaystate = {}
                        for k, v in thispayload.items():
                            lk = k.lower()
                            if lk.startswith("power"):
                                try:
                                    subdevice_idx = int(lk.replace("power", "")) - 1
                                except:
                                    subdevice_idx = 0
                                relaystate[subdevice_idx] = v.lower()
                        _log.debug(f'''Create tas mqtt {device}, {max(relaystate.keys()) + 1}''')
                        self.register_new_device(
                            TasmotaDevice(self, device, max(relaystate.keys()) + 1)
                        )

                        for k, v in relaystate.items():
                            self.device_list[device].update_switch_state(k, v)
                        break
                    elif function == "lwt":
                        if device in self.device_list:
                            newstate = msg.payload.decode().lower() == "online"
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
