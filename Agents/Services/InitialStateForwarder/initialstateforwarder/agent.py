"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
import datetime
import json
from ISStreamer.Streamer import Streamer

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class InitialState:

    def __init__(self, bucket_name: str, bucket_key: str, access_key: str):
        self._bucket_name = bucket_name
        self._bucket_key = bucket_key
        self._access_key = access_key
        self._streamer = None
        self._connect()
    
    def _connect(self):
        _log.info("Connecting to InitialState...")
        self._streamer = Streamer(bucket_name=self._bucket_name, bucket_key=self._bucket_key, access_key=self._access_key)
        self.publish_object({"ISforwarder_status": "Online"})
        _log.info(f"InitiailState Connected Bucket_name: {self._bucket_name}")
    
    def publish_object(self, data_object: dict, timestamp: int = None) -> None:
        if timestamp is None:
            self._streamer.log_object(data_object, epoch=int(time.time()))
        else:
            self._streamer.log_object(data_object, epoch=int(timestamp))
        self._streamer.flush()
        _log.debug(f"Publish object to InitialState: {data_object}")
    
    def publish_data(self, key: str, value) -> None:
        self._streamer.log(key, value)
        self._streamer.flush()
        _log.debug(f"Publish data to InitialState key: {key}, value: {value}")


def initialstateforwarder(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Initialstateforwarder
    :rtype: Initialstateforwarder
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    bucket_name = config.get("bucket_name", "")
    bucket_key = config.get("bucket_key", "")
    access_key = config.get("access_key", "")
    devices = config.get("devices", {})

    return Initialstateforwarder(bucket_name, bucket_key, access_key, devices, **kwargs)


class Initialstateforwarder(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, bucket_name: str, bucket_key: str, access_key: str, devices: dict, **kwargs):
        super(Initialstateforwarder, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._bucket_name = bucket_name
        self._bucket_key = bucket_key
        self._access_key = access_key
        self._devices = devices
        self._controller_streamer = None

        self.default_config = {
                                "bucket_name": self._bucket_name,
                                "bucket_key": self._bucket_key,
                                "access_key": self._access_key,
                                "devices": self._devices
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
            bucket_name = config["bucket_name"]
            bucket_key = config["bucket_key"]
            access_key = config["access_key"]
            devices = config["devices"] 
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        
        self._bucket_name = bucket_name
        self._bucket_key = bucket_key
        self._access_key = access_key
        self._devices = devices

        self._controller_streamer = InitialState(self._bucket_name, self._bucket_key, self._access_key)
        self._create_subscriptions()
        
    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """        
        self.vip.pubsub.unsubscribe("pubsub", None, None)
        
        for schema, schema_prop in self._devices.items():
            for agent, agent_prop in schema_prop.items():
                for device_id in agent_prop:
                    self.vip.pubsub.subscribe(
                        peer='pubsub',
                        prefix=f'{schema}/{agent}/{device_id}/event',
                        callback=self._handle_publish
                    )
                    _log.debug(f"Subcribe to topic: {schema}/{agent}/{device_id}/event")
                        

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        _log.debug(f"received message from topic: {topic}, message: {message}")
        schema, agent, device_id, mtype = topic.split("/")
        topic_schema = ["charger", "sensor", "hvac", "rein", "rein_output", "os_memory"]
        try:
            t = time.time()
            if schema in topic_schema:
                if schema == "charger":
                    if t - self.time >= 180:
                        data = {message["device_id"]: "Offline"}
                        self.forward_to_initial_state(data)
                    else:
                        data = {message["device_id"]: "Online"}
                        self.forward_to_initial_state(data)
                elif schema == "rein":
                    pass
                elif schema == "rein_output":
                    pass
                elif schema == "sensor":
                    self._handle_sensor_message(message)
                elif schema == "os_memory":
                    data = {}
                    data[message["memory_usage_id"]] = "Online"
                    data["device_id"] = message["memory_usage_id"]
                    for k, v in message["data"].items():
                        data[k] = v["memory_usage"]
                    self.time_checked[message["memory_usage_id"]] = time.time()
                    self._controller_streamer.publish_object(data)
                    _log.debug(
                        f"Update time_check device_id: {message['memory_usage_id']}, time: {datetime.datetime.fromtimestamp(self.time_checked[message['memory_usage_id']])}"
                    )
            else:
                _log.debug("Schema Out of Range")
        except Exception as e:
            _log.error(f"_handle_publish: Exception {e}")
    
    def _handle_sensor_message(self, message: dict):
        # message = {"device_id": "xxx", "subdevice_idx": 0, "subdevice_name": "subdev_0", "type": "environment",...}
        ignore_key = ["device_id", "subdevice_idx", "subdevice_name", "type", "timestamp", "unix_timestamp"]
        data_type = message['type']
        if data_type == 'environment':
            for key, value in message.items():
                if key not in ignore_key:
                    self._controller_streamer.publish_object({f"{message['device_id']}_{key}": value}, message['unix_timestamp'])
        elif data_type == 'electric':
            for key, value in message.items():
                if key not in ignore_key:
                    self._controller_streamer.publish_object({f"{message['device_id']}_{key}": value}, message['unix_timestamp'])
        elif data_type == 'device':
            self._controller_streamer.publish_object({message['device_id']: message['device_status']}, message['unix_timestamp'])

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        self._controller_streamer.publish_object({"ISforwarder_status": "Offline"})
        _log.info(f"Stopped InitialStateForwarder Agents")


def main():
    """Main method called to start the agent."""
    utils.vip_main(initialstateforwarder, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass