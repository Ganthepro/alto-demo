"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
import time
from threading import Thread

import pendulum
import paho.mqtt.client as mqtt

from altolib import (
    AltoEnvironSensor,
    AltoDeviceSensor,
    AltoBridgeAgent,
    AltoSensor,
    AltoMQTTAgent
)

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


class MQTTHandler:
    
    def __init__(self, controller: Agent, host: str, port: int, username: str = "", password: str = "", topics: list = []):
        self._controller = controller
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._topics = topics
        
        self._client: mqtt = mqtt.Client()
        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message
        self._client.on_subscribe = self.on_subscribe
        self._client.on_disconnect = self.on_disconnect
        
    def connect(self):
        if self._username and self._password:
            self._client.username_pw_set(self._username, self._password)
        self._client.connect(self._host, self._port)
        if self._topics:
            for topic in self._topics:
                self.subscribe(topic, 0)
        
        self.run()
    
    def run(self):
        try:
            self._client.loop_forever()
        except Exception as e:
            _log.exception(f"MQTTHandler run Error: {e}")
    
    def subscribe(self, topic: str, qos: int = 0):
        self._client.subscribe(topic, qos)
    
    def publish(self, topic: str, payload: dict):
        self._client.publish(topic, payload)
    
    def disconnect(self):
        self._client.disconnect()
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            _log.debug(f"Connected Successfully")
        else:
            _log.warning(f"Error with connection rc: {rc}")
    
    def on_message(self, client, userdata, message):
        _log.debug(f"MQTTHandler on_message: {message.payload}")
        if isinstance(message.payload, bytes):
            msg = json.loads(message.payload.decode('utf-8'))
        self._controller._handle_mqtt_message(msg)
    
    def on_subscribe(self, client, userdata, mid, granted_qos):
        pass
        
    def on_disconnect(self, client, userdata, rc):
        pass
        

def device_factory(devtype: str):
    if devtype == 'em300':
        return EM300
    elif devtype == 'am107':
        return AM107
    
    raise f"Device factory error, no {devtype} on this factory"


class EM300(AltoEnvironSensor, AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, **kwargs):
        self._last_updated = int(time.time())
        super().__init__(controller, devid, nb_subdev)
        self.LORAWANENVMAP = {
            "temperature": "temperature",
            "humidity": "humidity"
        }
        self.LORAWANDEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
            "rssi": "rssi",
            "loRaSNR": "loRaSNR",
        }
        self.datapoint_supported['environment'] = [x for x in self.LORAWANENVMAP.keys()]
        self.datapoint_supported['device'] = [x for x in self.LORAWANDEVICEMAP.keys()]
        self._sample_init()
        
    def _sample_init(self):
        self.data_map.update(self.LORAWANENVMAP)
        self.data_map.update(self.LORAWANDEVICEMAP)
        self.initialise_data('environment', self.LORAWANENVMAP.keys())
        self.initialise_data('device', self.LORAWANDEVICEMAP.keys())
    
    def handle_data(self, data: dict):
        _log.debug(f"EM300 handle_data")
        """
        data = {
            "device_name": "AQI Sensor",
            "temperature": 24,
            "battery": 100,
            "datetime": "2022-11-04T13:25:02.027245Z",
            "rssi": -50
        }
        """
        env_data = {}
        dev_data = {}
        dev_data.update({
            "device_status": "online",
            "online_status": True
        })
        self._last_updated = int(pendulum.parse(data['datetime']).timestamp())
        for key, value in data.items():
            if key in self.LORAWANENVMAP.values():
                env_data[key] = value
            elif key in self.LORAWANDEVICEMAP.values():
                dev_data[key] = value
        _log.debug(f"EM300 data from {data['device_name']}: {env_data}")
        self._emit_environment_data(env_data)
        self._emit_device_data(dev_data)

    def _emit_environment_data(self, data):
        try:
            vals = {}
            for datapoint, value in data.items():
                if datapoint in self.LORAWANENVMAP.values():
                    vals[datapoint] = value
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.exception(f"EM300 _emit_environment_data Error: {e}")
    
    def _emit_device_data(self, data):
        try:
            vals = {}
            for datapoint, value in data.items():
                if datapoint in self.LORAWANDEVICEMAP.values():
                    vals[datapoint] = value
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.exception(f"EM300 _emit_device_data Error: {e}")
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']

    @property
    def last_updated(self):
        return self._last_updated


class AM107(AltoEnvironSensor, AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self._last_updated = int(time.time())
        self.LORAWANENVMAP = {
            "temperature": "temperature",
            "humidity": "humidity",
            "co2": "co2"
        }
        self.LORAWANDEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
            "battery": "battery",
            "rssi": "rssi"
        }
        self.datapoint_supported['environment'] = [x for x in self.LORAWANENVMAP.keys()]
        self.datapoint_supported['device'] = [x for x in self.LORAWANDEVICEMAP.keys()]
        self._sample_init()
        
    def _sample_init(self):
        self.data_map.update(self.LORAWANENVMAP)
        self.data_map.update(self.LORAWANDEVICEMAP)
        self.initialise_data('environment', self.LORAWANENVMAP.keys())
        self.initialise_data('device', self.LORAWANDEVICEMAP.keys())
    
    def handle_data(self, data: dict):
        _log.debug(f"AM107 handle_data")
        """
        data = {
            "device_name": "AQI Sensor",
            "temperature": 24,
            "humidity", "co2": 1000,
            "battery": 100,
            "datetime": "2022-11-04T13:25:02.027245Z",
            "rssi": -50
        }
        """
        env_data = {}
        dev_data = {}
        dev_data.update({
            "device_status": "online",
            "online_status": True
        })
        self._last_updated = int(pendulum.parse(data['datetime']).timestamp())
        for key, value in data.items():
            if key in self.LORAWANENVMAP.values():
                env_data[key] = value
            elif key in self.LORAWANDEVICEMAP.values():
                dev_data[key] = value
        _log.debug(f"AM107 data from {data['device_name']}: {env_data}")
        self._emit_environment_data(env_data)
        self._emit_device_data(dev_data)

    def _emit_environment_data(self, data):
        try:
            vals = {}
            for datapoint, value in data.items():
                if datapoint in self.LORAWANENVMAP.values():
                    vals[datapoint] = value
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.exception(f"AM107 _emit_environment_data Error: {e}")
    
    def _emit_device_data(self, data):
        try:
            vals = {}
            for datapoint, value in data.items():
                if datapoint in self.LORAWANDEVICEMAP.values():
                    vals[datapoint] = value
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.exception(f"AM107 _emit_device_data Error: {e}")
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']

    @property
    def last_updated(self):
        return self._last_updated
    

def lorawanenv(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Lorawanenv
    :rtype: Lorawanenv
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get('topic', "")
    for x, y in zip(
        [
            "devices",
            "agent_name",
            "timezone",
            "default_timezone",
            "sampling_rate"
        ],
        [{}, "", "Asia/Bangkok", "", 0]
    ):
        kwargs[x] = config.get(x, y)

    return Lorawanenv(topic, **kwargs)


class Lorawanenv(AltoBridgeAgent, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Lorawanenv, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}
        self.mqtt_thread = None
    
    def _build_device(self, devtype, devid, nb_subdev):
        _log.debug(f"lorawan _build_device with devtype: {devtype}, devid: {devid}, nb_subdev: {nb_subdev}")
        if devid not in self.device_list:
            Sensor = device_factory(devtype)
            newdev = Sensor(self, devid, nb_subdev)
            self.register_new_device(newdev)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        
        self.mqtt_handler: MQTTHandler = MQTTHandler(
            self,
            self.mqtt_config['host'],
            self.mqtt_config['port'],
            self.mqtt_config['username'],
            self.mqtt_config['password'],
            self.mqtt_config['topics']
        )
        self.device_list = {}
        for device_id, device_config in self.devices.items():
            self._build_device(
                device_config['device_type'],
                device_id,
                device_config['number_subdevice']
            )
        
        self.core.schedule(cron(self.status_interval), self.check_status)
        self.mqtt_thread = Thread(target=self.mqtt_handler.connect)
        self.mqtt_thread.setDaemon(True)
        self.mqtt_thread.start()
        
    def check_status(self):
        _log.debug(f"lorawanenv check_status")
        for instance in self.device_list.values():
            if int(time.time()) - instance.last_updated > self.offline_period:
                instance._emit_device_data({
                    "device_status": "offline",
                    "online_status": False
                })
    
    def _handle_mqtt_message(self, msg: dict):
        try:
            device_id = msg.get("device_id", "")
            rxinfo = msg.get('rxInfo', [])
            payload = msg.get('payload', {})
            payload.update({
                "battery": msg.get('battery', ""),
                "device_name": msg.get("device_name", ""),
                "datetime": msg.get('datetime', ""),
                "rssi": rxinfo[0]['rssi']
            })
            if device_id in self.device_list:
                self.device_list[device_id].handle_data(payload)
        except Exception as e:
            _log.exception(f"lorawanenv _handle_mqtt_message Error: {e}")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        self.mqtt_handler.disconnect()

    @RPC.export
    def get_device_status(self):
        status_list = []
        for dev, instance in self.device_list.items():
            status_list.append({dev: instance.get_device_status()})
        return status_list


def main():
    """Main method called to start the agent."""
    utils.vip_main(lorawanenv, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
