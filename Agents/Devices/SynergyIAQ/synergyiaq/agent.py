"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import pendulum
import time

from altolib import (
    AltoMQTTAgent, 
    AltoEnvironSensor,
    AltoDeviceSensor,
    AltoSensor
)

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


class SynergyIAQDevice(AltoEnvironSensor, AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, ip_address):
        super().__init__(controller, devid, nb_subdev)
        _log.debug(f"Initialise {self.__class__.__name__} with device_id: {devid}")
        self._ip_address = ip_address
        self.SYNERGY_ENV_MAP = {
            "temperature": "temperature",
            "humidity": "humidity",
            "dewpoint": "dewpoint",
            "pm25": "PM2.5",
            "pm10": "PM10",
            "co2": "CO2",
            "voc_index": "VOCIndex"
        }
        self.SYNERGY_DEVICE_MAP = {
            "device_status": "device_status"
        }
        self.datapoint_supported['environment'] = [datapoint for datapoint in self.SYNERGY_ENV_MAP]
        self.datapoint_supported['device'] = [datapoint for datapoint in self.SYNERGY_DEVICE_MAP]
        self._sample_init()
    
    def _sample_init(self):
        self.data_map.update(self.SYNERGY_ENV_MAP)
        self.data_map.update(self.SYNERGY_DEVICE_MAP)
        self.initialise_data('environment', self.SYNERGY_ENV_MAP.keys())
        self.initialise_data('device', self.SYNERGY_DEVICE_MAP.keys())
    
    def received_data(self, data):
        vals = {}
        for datapoint, value in data.items():
            if datapoint in self.SYNERGY_ENV_MAP.values():
                vals[datapoint] = value
    
        self._emit_environment_data(vals)
        self._emit_device_data({
            "device_status": "online"
        })
        _log.info(f"Data from device_id: {self.device_id} with data: {vals}")

    def _emit_environment_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type='environment')
        except Exception as err:
            _log.exception(f"Error in _emit_environment_data: {err}")
    
    def _emit_device_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type='device')
        except Exception as err:
            _log.exception(f"Error in _emit_device_data: {err}")
        

def synergyiaq(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Synergyiaq
    :rtype: Synergyiaq
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")
    
    topic = config.get('topic', '')
    for key, value in zip(
        [
            "agent_name",
            "devices",
            "heartbeat",
            "mqtt_topics",
            "mqtt_server",
            "mqtt_port",
            "mqtt_user",
            "mqtt_password",
            "mqtt_prefix",
        ],
        [
            "mqtt_iaq",
            {},
            120,
            [
                "stat/#",
                "tele/#",
                "syntech/iaq/#",
            ],
            "127.0.0.1",
            1883,
            "",
            "",
            ""
        ]
    ):
        kwargs[key] = config.get(key, value)
        
    return Synergyiaq(topic, **kwargs)


class Synergyiaq(AltoMQTTAgent, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Synergyiaq, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}
        self.devices_list = {}
    
    def _build_device(self, device_id, ip_address, number_subdevice):
        if device_id not in self.devices_list:
            self.devices_list[device_id] = SynergyIAQDevice(self, device_id, number_subdevice, ip_address)
            _log.info(f"Build device registerd device_id: {device_id}")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        for device_id, props in self.devices.items():
            self._build_device(device_id, props['ip_address'], props['number_subdevice'])
    
    def process_mqtt_message(self, client, myself, message):
        """
        Synergy IAQ MQTT message
        topic: syntech/iaq/{mac_address}/data
        message: {
            "temperature": 30.6,
            "humidity": 50,
            "dewpoint": 19.2,
            "PM2.5": 25,
            "pm10": 56,
            "CO2": 500,
            "VOCIndex": 1
        }
        """
        
        topic = message.topic
        payload = message.message
        _log.debug(f"Got MQTT message with topic: {topic},payload: {payload}")
        split_mqtt_topic = topic.split("/")
        if split_mqtt_topic[0] == "syntech" and split_mqtt_topic[1] == "iaq":
            if len(split_mqtt_topic) == 4:
                device_id = split_mqtt_topic[2]
                if device_id in self.devices_list:
                    self.devices_list[device_id].received_data(payload)
    
    def publish(self, topic, payload, mtype):
        timestamp = int(time.time())
        device_id = payload.get('device_id')
        topic = f"sensor/{self.core.identity}/{device_id}/event"
        datetime = pendulum.from_timestamp(timestamp).to_atom_string()
        headers = {
            "requesterID": self.core.identity,
            "message_type": mtype,
            "Timestamp": datetime
        }
        payload.update({
            "timestampe": datetime,
            "unix_timestamp": timestamp
        })
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            headers=headers,
            message=payload
        )


def main():
    """Main method called to start the agent."""
    utils.vip_main(synergyiaq, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
