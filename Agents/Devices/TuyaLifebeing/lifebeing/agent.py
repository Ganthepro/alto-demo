"""
Agent documentation goes here.
"""
import gevent.monkey
gevent.monkey.patch_all()

__docformat__ = 'reStructuredText'

import logging
import sys

import pendulum
from gevent import spawn, joinall, sleep
from altoutils.tuya.cloud import TuyaAPI, TuyaAuth

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


def device_factory(devtype):
    if devtype == "lifebeing_sensor":
        return LifeBeingSensor
    

class LifeBeingSensor(object):
    
    def __init__(self, controller: Agent, device_id: str):
        self._controller = controller
        self._device_id = device_id
        self.data_map = {
            "presence_state": "presence_state",
            "sensitivity": "sensitivity",
            "online_status": "online_status"
        }
        self.point_name_map = {
            "presence": "occupied",
            "none": "unoccupied"
        }
    
    def get_status(self):
        """
        Get the status of the device
        
        """
        
        try:
            message: dict = {}
            data_info = self._controller.tuya_api.get_information(self._device_id)
            if data_info['success']:
                message["online_status"] = "online" if data_info['result']['online'] else "offline"
            
            if message["online_status"] == "online":
                data = self._controller.tuya_api.get_status(self._device_id)
                if data['success']:
                    for payload in data["result"]:
                        if payload["code"] in list(self.data_map.keys()):
                            if payload["value"] in self.point_name_map:
                                message[self.data_map[payload["code"]]] = self.point_name_map[payload["value"]]
                            else:
                                message[self.data_map[payload["code"]]] = payload["value"]
                    self._emit_message(message)
        except Exception as e:
            _log.exception(f"Error, {self.__class__} get_status: {e}")
    
    def _emit_message(self, message):
        datetime = pendulum.now().isoformat()
        message.update({
            "device_id": self._device_id,
            "subdevice_idx": 0,
            "type": "sensor",
            "timestamp": datetime,
            "unix_timestamp": int(pendulum.parse(datetime).timestamp())
        })
        self._controller.publish(self._device_id, message)

def lifebeing(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Lifebeing
    :rtype: Lifebeing
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get("agent_name", "lifebeing")
    sampling_rate = config.get("sampling_rate", 5)
    tuya_credential = config.get("tuya_credential", {})
    devices = config.get("devices", {})

    return Lifebeing(agent_name, sampling_rate, tuya_credential, devices, **kwargs)


class Lifebeing(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name: str, sampling_rate: int, tuya_credential: dict, devices: dict, **kwargs):
        super(Lifebeing, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.agent_name = agent_name
        self.sampling_rate = sampling_rate
        self.tuya_credential = tuya_credential
        self.devices = devices

        self.default_config = {
            "agent_name": agent_name,
            "sampling_rate": sampling_rate,
            "tuya_credential": tuya_credential,
            "devices": devices
        }
        
        self.device_list: dict = {}
        self.tuya_client: TuyaAPI = None

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
    
    def send_sample_data(self):
        try:
            for device_instance in self.device_list.values():
                device_instance.get_status()
        except Exception as e:
            _log.exception(f"{self.__class__.__name__}, Error send_sample_data: {e}")
    
    def _build_devices(self, device_id: str, device_type: str):
        if device_id not in self.device_list:
            try:
                device = device_factory(device_type)(self, device_id)
                self.device_list[device_id] = device
            except Exception as e:
                _log.exception(f"{self.__class__.__name__}. Error _build_device: {e}")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.info("Configuring Agent")

        try:
            agent_name = config.get("agent_name", "lifebeing")
            sampling_rate = config.get("sampling_rate", 60)
            tuya_credential = config.get("tuya_credential", {})
            devices = config.get("devices", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.sampling_rate = sampling_rate
        self.tuya_credential = tuya_credential
        self.devices = devices
        
        self.tuya_client = TuyaAPI(TuyaAuth(
            tuya_credential['client_id'],
            tuya_credential['client_secret']
            ))
        
        for device_id, dev_type in devices.items():
            self._build_devices(device_id, dev_type[0])
        
        self.core.schedule(periodic(self.sampling_rate), self.send_sample_data)
        
    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="sensor",
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        pass

    def publish(self, device_id: str, message: dict):
        try:
            headers = {
                "requesterID": self.core.identity,
                "message_type": "event",
                "Timestamp": pendulum.now('UTC').isoformat()
            }
            topic = f"sensor/{self.core.identity}/{device_id}/event"
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=topic,
                headers=headers,
                message=message
            )
            _log.info(f"{self.__class__.__name__}, Published to {topic}: {message}")
        except Exception as e:
            _log.exception(f"{self.__class__.__name__}, Error publishing to {topic}: {e}")

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
    
    @property
    def tuya_api(self):
        return self.tuya_client


def main():
    """Main method called to start the agent."""
    utils.vip_main(lifebeing, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
