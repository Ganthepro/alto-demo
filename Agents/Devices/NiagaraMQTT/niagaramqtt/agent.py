"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

import pendulum

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


def niagaramqtt(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Niagaramqtt
    :rtype: Niagaramqtt
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    devices = config.get("devices", {})
    device_mapping = config.get("device_mapping", {})
    point_mapping = config.get("point_mapping", {})

    return Niagaramqtt(devices, device_mapping, point_mapping, **kwargs)


class Niagaramqtt(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, devices, device_mapping, point_mapping, **kwargs):
        super(Niagaramqtt, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.devices: dict = devices
        self.device_mapping: dict = device_mapping
        self.point_mapping: dict = point_mapping

        self.default_config = {
            "devices": devices,
            "device_mapping": device_mapping,
            "point_mapping": point_mapping
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
            devices = config.get("devices", {})
            device_mapping = config.get("device_mapping", {})
            point_mapping = config.get("point_mapping", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.devices = devices
        self.device_mapping = device_mapping
        self.point_mapping = point_mapping
        
        self._create_subscriptions()

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for schema, agent_prop in self.devices.items():
            for agent, device_list in agent_prop.items():
                for device_id in device_list:
                    self.vip.pubsub.subscribe(
                        peer='pubsub',
                        prefix=f"{schema}/{agent}/{device_id}/event",
                        callback=self._handle_publish
                    )
                    _log.info(f"Subscribed to {schema}/{agent}/{device_id}/event")

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        
        """
        
        _log.debug(f"Got MQTT Logger topic: {topic}, message: {message}")
        if sender != self.core.identity:
            msg: dict = {}
            schema, agent, device_id, mtype = topic.split("/")
            try:
                if message:
                    msg["timestamp"] = message["timestamp"]
                    msg["unix_timestamp"] = message["unix_timestamp"]
                    
                    if device_id in self.device_mapping:
                        msg["device_id"] = self.device_mapping[device_id]
                        
                        # fCU reforming
                        if device_id.startswith("fCU"):
                            for datapoint, value in message.items():
                                # datapoint: StartStopStatus_000, AirConModeStatus_000, ...
                                # value: off, cool, ...
                                if datapoint not in ["timestamp", "unix_timestamp", "device_id"]:
                                    if datapoint[:-4] in self.point_mapping["fCU"]:
                                        if datapoint.startswith("StartStopStatus"):
                                            if value:
                                                continue
                                            else:
                                                msg["mode"] = "off"
                                        elif datapoint.startswith("AirConModeStatus"):
                                            if "mode" not in msg:
                                                msg["mode"] = value
                                            else:
                                                continue
                                        else:
                                            msg[self.point_mapping["fCU"][datapoint[:-4]]] = value
                            _log.debug(f"fCU message reforming: {msg}")
                            msg["type"] = "ac"
                                
                        # iAQ reforming
                        if device_id.startswith("iAQ"):
                            for keys, values in message.items():
                                if keys not in ["timestamp", "unix_timestamp", "device_id"]:
                                    if keys in self.point_mapping["iAQ"]:
                                        msg[self.point_mapping["iAQ"][keys]] = values
                            msg["type"] = "environment"
                        
                        # power meter reforming
                        elif device_id.startswith("power"):
                            for keys, values in message.items():
                                if keys not in ["timestamp", "unix_timestamp", "device_id"]:
                                    if keys in self.point_mapping["powerMeter"]:
                                        msg[self.point_mapping["powerMeter"][keys]] = values
                            msg["type"] = "electric"
                        
                        # inverter reforming
                        elif device_id.startswith("inverter"):
                            for keys, values in message.items():
                                if keys not in ["timestamp", "unix_timestamp", "device_id"]:
                                    if keys in self.point_mapping["inverter"]:
                                        msg[self.point_mapping["inverter"][keys]] = values
                            msg["type"] = "electric"

                        _log.debug(f"message reforming: {msg}")
                        self.publish(f"{schema}/{self.core.identity}/{msg['device_id']}/event", msg, mtype)
            except Exception as e:
                _log.exception(f"_handle_publish error: {e}")
    
    def publish(self, topic, value, mtype) -> None:
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            message=value,
            headers={
                "requesterID": self.core.identity,
                "message_type": mtype,
                "Timestamp": pendulum.now('UTC').to_atom_string()
            }
        )
        _log.debug(f"Niagara MQTT Published topic: {topic}, message: {value}")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        # Example publish to pubsub
        self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # Example RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(niagaramqtt, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
