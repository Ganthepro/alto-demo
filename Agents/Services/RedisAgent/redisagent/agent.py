"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from altolib import AltoHealth
from .redis_handler import RedisHandler

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def redisagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: RedisAgent
    :rtype: RedisAgent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    redis_config = config.get('redis_config', dict())
    associated_devices = config.get('associated_devices', dict())

    return RedisAgent(redis_config, associated_devices, **kwargs)


class RedisAgent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, redis_config=dict(), associated_devices=dict(), **kwargs):
        super(RedisAgent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.redis_config = redis_config
        self.associated_devices = associated_devices

        self.default_config = {
            "redis_config": self.redis_config,
            "associated_devices": self.associated_devices
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
        
        # define custom heartbeat and health payload
        self.custom_health = AltoHealth(self.core, self.vip.pubsub, heartbeat_period=60, verbose=False)
        
        # set intial status for functions and devices
        self.function_names = [
            "_update_redis_database",
            "_update_calculated_redis_database",
            # "request_datapoint_subdevices",
            # "request_datapoint_calculated"
        ]
        self.custom_health.set_pending_status(names=self.function_names, type_label='function')
        
        # track function status (need to use this approach to pass `self` into decorator function)
        self._update_redis_database_track = AltoHealth.track_status(self.custom_health)(self._update_redis_database)
        self._update_calculated_redis_database_track = AltoHealth.track_status(self.custom_health)(self._update_calculated_redis_database)
        # TODO: handle the tracking of RPC functions
        self.request_datapoint_subdevices = AltoHealth.track_status(self.custom_health)(self.request_datapoint_subdevices)
        self.request_datapoint_calculated = AltoHealth.track_status(self.custom_health)(self.request_datapoint_calculated)

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
            redis_config = config.get('redis_config', dict())
            associated_devices = config.get('associated_devices', dict())
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        
        self.redis_config = redis_config
        self.associated_devices = associated_devices

        # create Redis handler object
        if all(elem in list(self.redis_config.keys()) for elem in ['host', 'port', 'password', 'database']):
            self.redis_handler = RedisHandler(
                host=self.redis_config.get('host'),
                port=self.redis_config.get('port'),
                password=self.redis_config.get('password'),
                database=self.redis_config.get('database')
            )
        else:
            self.redis_handler = None
            _log.error("ERROR PROCESSING CONFIGURATION: incomplete `redis_config` information")

        # construct all topic names for raw-measured data
        if 'sensor' in self.associated_devices.keys():
            self.topic_names = list()
            for agent_id in self.associated_devices["sensor"].keys():
                _device_ids = self.associated_devices["sensor"][agent_id]
                for _device_id in _device_ids:
                    _topic_name = f"sensor/{agent_id}/{_device_id}/event"
                    self.topic_names.append(_topic_name)
            self.topic_names = sorted(self.topic_names)
        else:
            self.topic_names = list()
            _log.error("ERROR PROCESSING CONFIGURATION: incomplete `associated_devices` information (sensor)")

        # construct all topic names for calculated data
        if 'calculated' in self.associated_devices.keys():
            self.calculated_topic_names = list()
            for agent_id in self.associated_devices["calculated"].keys():
                _device_ids = self.associated_devices["calculated"][agent_id]
                for _device_id in _device_ids:
                    _topic_name = f"calculated/{agent_id}/{_device_id}/event"
                    self.calculated_topic_names.append(_topic_name)
            self.calculated_topic_names = sorted(self.calculated_topic_names)
        else:
            self.calculated_topic_names = list()
            _log.error("ERROR PROCESSING CONFIGURATION: incomplete `associated_devices` information (calculated)")

        self._create_subscriptions()

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        # subscribe to raw IoT data
        for topic_name in self.topic_names:
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=str(topic_name),
                                    callback=self._update_redis_database_track)

        # subscribe to Calculated data
        for topic_name in self.calculated_topic_names:
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=str(topic_name),
                                    callback=self._update_calculated_redis_database_track)

    def _update_redis_database(self, peer, sender, bus, topic, headers, message: dict):
        """
        Callback triggered by the subscription topics to update data to Redis database for raw-measured data
        """
        # _log.debug(f"{self.core.identity}: received message: Peer: {peer}, Sender: {sender}:, Bus: {bus}, Topic: {topic}, Headers: {headers}, Message: {json.dumps(message)}")
        if isinstance(message, str):
            message: dict = json.loads(message)
        device_id = message.get('device_id')
        subdevice_name = message.get('subdevice_name')
        
        # handle `nan` data in power meter
        if topic.startswith("sensor/modbus_power_meter"):
            if subdevice_name == "total":
                power_factor = message.get('power_factor')
                message['power_factor'] = str(power_factor)

        if self.redis_handler is not None:
            self.redis_handler.hset(str(device_id), str(subdevice_name), json.dumps(message))

    def _update_calculated_redis_database(self, peer, sender, bus, topic, headers, message: dict):
        """
        Callback triggered by the subscription topics to update data to Redis database for calculated data
        """
        # _log.debug(f"{self.core.identity}: received message: Peer: {peer}, Sender: {sender}:, Bus: {bus}, Topic: {topic}, Headers: {headers}, Message: {json.dumps(message)}")
        if isinstance(message, str):
            message: dict = json.loads(message)
        device_id = message.get('device_id')
        subdevice_name = message.get('type')
        if self.redis_handler is not None:
            self.redis_handler.hset(str(device_id), str(subdevice_name), json.dumps(message))

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        pass

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def request_datapoint_subdevices(self, device_ids: list):
        """Request datapoint from Redis database based on input parameters"""
        if self.redis_handler is None:
            return json.dumps(dict())
        
        results = dict()
        _exclude_keys = ["device_id", "subdevice_idx", "subdevice_name", "type"]
        for device_id in device_ids:
            # get data from Redis database based on hash-name
            data: dict = self.redis_handler.hget_all(device_id)
            # convert subdevice-json to dict
            _data = dict()
            for subdevice_key in data.keys():
                # load data from json
                _subdev_payload: dict = json.loads(data.get(subdevice_key))
                _type = _subdev_payload.get('type')
                # remove unnecessary keys
                for _exclude_key in _exclude_keys:
                    _subdev_payload.pop(_exclude_key, None)
                # construct payload format
                subdev_payload = {str(_type): _subdev_payload}
                _data[subdevice_key] = subdev_payload
            results[device_id] = _data
        return json.dumps(results)

    @RPC.export
    def request_datapoint_calculated(self, device_ids: list, datapoints: list):
        """Request datapoint from Redis database based on input parameters"""
        if self.redis_handler is None:
            return json.dumps(dict())
        
        results = dict()
        _exclude_keys = ["device_id", "subdevice_idx", "subdevice_name", "type", "location"]
        for device_id in device_ids:
            # get data from Redis database based on hash-name
            data: dict = self.redis_handler.hget_all(device_id)
            # convert subdevice-json to dict
            _data = dict()
            for datapoint in datapoints:
                # load data from json
                if datapoint not in data.keys():
                    continue
                _subdev_payload: dict = json.loads(data.get(datapoint))
                # remove unnecessary keys
                for _exclude_key in _exclude_keys:
                    _subdev_payload.pop(_exclude_key, None)
                # construct payload format
                _data[datapoint] = _subdev_payload
            results[device_id] = _data
        return json.dumps(results)


def main():
    """Main method called to start the agent."""
    utils.vip_main(redisagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
