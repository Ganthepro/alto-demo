"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

import pendulum
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron, periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


class DataStore(object):
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self._data: dict = {}
    
    def update_data(self, message):
        filter_key = ["timestamp", "unix_timestamp", "device_id", "type", "subdevice_idx"]
        for key, value in message.items():
            if key not in filter_key:
                self._data[key] = value
    
    @property
    def data(self):
        return self._data


def occupancydetection(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Occupancydetection
    :rtype: Occupancydetection
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    occupancy_groups = config.get("occupancy_groups", [])
    threshold = config.get("threshold", {})

    return Occupancydetection(occupancy_groups, threshold, **kwargs)


class Occupancydetection(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, occupancy_groups, threshold, **kwargs):
        super(Occupancydetection, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.occupancy_groups: list = []
        self.threshold: dict = {}
        
        self.group_device: dict = {}
        self.device_stored: dict = {}

        self.default_config = {
            "occupancy_groups": occupancy_groups,
            "threshold": threshold
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
            occupancy_groups = config.get("occupancy_groups", [])
            threshold = config.get("threshold", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.occupancy_groups = occupancy_groups
        self.threshold = threshold

        self._create_subscriptions()
        
        self.core.schedule(periodic(3), self._check_occupancy)

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for zones in self.occupancy_groups:
            for zone, device_group in zones.items():
                self.group_device[zone] = device_group
                for agent_name, device_list in device_group.items():
                    for device in device_list:
                        self.device_stored[device] = DataStore(device)
                        self.vip.pubsub.subscribe(
                            peer='pubsub',
                            prefix=f"sensor/{agent_name}/{device}/event",
                            callback=self._handle_publish
                        )
                    _log.info(f"Subscribed to sensor/{agent_name}/{device}/event")

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        if sender == self.core.identity:
            return
        
        schema, agent_name, device, mtype = topic.split("/")
        if schema == "sensor" and mtype == "event":
            if device in self.device_stored:
                self.device_stored[device].update_data(message)
    
    def _check_occupancy(self):
        try:
            # STEP 1: Get all data from devices
            all_devices_data = self.get_all_data()
            
            # Check data of lifebeing that is occupied or unoccupied in key of "presense_state"
            for zone, device_group in self.group_device.items():
                for occ_device in device_group['lifebeing']:
                    if occ_device in all_devices_data:
                        if all_devices_data[occ_device]['presence_state'] == "unoccupied":
                            _log.debug(f"Zone {zone} is unoccupied")
                            for device_id in device_group['tuya_air_quality']:
                                co2_condition = self.check_co2_condition(device_id, all_devices_data[device_id])
                                message = self.check_temperature_condition(device_id, all_devices_data[device_id])
                                for relay in device_group["tuya_plug"]:
                                    message.update({"device_id": relay})
                                    self.publish(message)
                        elif all_devices_data[occ_device]['presence_state'] == "occupied":
                            for relay in device_group['tuya_plug']:
                                self.publish({
                                    "device_id": relay, 
                                    "command": {
                                        "state": "off"
                                    }
                                })
                            _log.debug(f"Zone: {zone} is occupied")
        except Exception as e:
            _log.error(f"Error in _check_occupancy: {e}")
    
    def check_co2_condition(self, iaq_device_id: str, iaq_data: dict):   
        if iaq_data['co2'] > self.threshold[iaq_device_id]['co2']['maximum']:
            _log.debug(f"This zone is occupied on condition: co2 is too higher that {self.threshold[iaq_device_id]['co2']['maximum']}")
            return False
        elif iaq_data['co2'] < self.threshold[iaq_device_id]['co2']['minimum']:
            _log.debug(f"This zone is occupied on condition: co2 is too lower that {self.threshold[iaq_device_id]['co2']['minimum']}")
            return True
            
    def check_temperature_condition(self, iaq_device_id: str, iaq_data: dict):
        message: dict = {}
        if iaq_data['temperature'] < self.threshold[iaq_device_id]['temperature']['maximum']:
            _log.debug(f"This zone is occupied on condition: temperature is lower that {self.threshold[iaq_device_id]['temperature']['maximum']}")
            message.update({
                "command": {
                    "state": "on"
                }
            })
            return message
        elif iaq_data['temperature'] > self.threshold[iaq_device_id]['temperature']['maximum']:
            _log.debug(f"This zone is occupied on condition: temperature is too higher that {self.threshold[iaq_device_id]['temperature']['maximum']}")
            message.update({
                "command": {
                    "state": "off"
                }
            })
            return message
        if iaq_data['temperature'] <= self.threshold[iaq_device_id]['temperature']['minimum']:
            _log.debug(f"This zone is occupied on condition: temperature is too lower that {self.threshold[iaq_device_id]['temperature']['minimum']}")
            message.update({
                "command": {
                    "state": "on"
                }
            })
            return message
        return message

    def get_all_data(self):
        devices_data: dict = {}
        for device_id in self.device_stored:
            devices_data[device_id] = self.device_stored[device_id].data
        _log.debug(f"devices_data: {devices_data}")
        return devices_data

    def publish(self, message):
        datetime = pendulum.now('UTC').isoformat()
        timestamp = int(pendulum.parse(datetime).timestamp())
        message.update({
            "timestamp": datetime,
            "unix_timestamp": timestamp
        })
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=f"switch/tuya_plug/{message['device_id']}/command",
            message=message
        )


def main():
    """Main method called to start the agent."""
    utils.vip_main(occupancydetection, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
