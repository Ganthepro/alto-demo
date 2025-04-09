"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
from threading import Thread, Lock
from queue import Queue, Empty
import pendulum

import altolib
from altoutils.airvedalib import airveda_cloud

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

def device_factory(devtype):
    if devtype == "airveda": # Airveda CO2 PM2.5 Air Quality 
        return AirvedaDevice 

class AirvedaDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, airveda_api, **kwargs):
        super().__init__(controller, devid, 1)
        self.AIRVEDAENVMAP = {
            "pm25": "pm25_value",
            "pm10": "pm10_value",
            "AQI": "AQI",
            "co2": "co2",
            "temperature": "temperature",
            "humidity": "humidity"
        }
        self.AIRVEDADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
            "last_updated": "last_updated"
        }
        self.datapoint_supported["environment"] = [x for x in self.AIRVEDAENVMAP.keys()]
        self.datapoint_supported["device"] = [x for x in self.AIRVEDADEVICEMAP.keys()]
        self._sample_init()

        self._airveda = airveda_cloud.AirvedaAQ(self.device_id, airveda_api)
    
    def _sample_init(self):
        self.data_map.update(self.AIRVEDAENVMAP)
        self.data_map.update(self.AIRVEDADEVICEMAP)
        self.initialise_data("environment", self.AIRVEDAENVMAP.keys())
        self.initialise_data("device", self.AIRVEDADEVICEMAP.keys())
    
    def get_status(self):
        vals = {}
        vals_dev = {}
        res = self._airveda.get_status()
        if res is not None:
            last_updated_timestamp = pendulum.parse(res["last_updated"]).timestamp()
            if time.time() - last_updated_timestamp <= 600:
                vals_dev.update({
                    "online_status": True,
                    "device_status": "online",
                    "last_updated": last_updated_timestamp
                    })
                for k, v in res.items():
                    if k in self.AIRVEDAENVMAP.values():
                        vals.update({k: v})
                _log.debug(f"AirvedaDevice get_status: {vals}, last_updated: {pendulum.from_timestamp(last_updated_timestamp, tz='Asia/Bangkok')}")
                self._emit_device_data(vals_dev)
                self._emit_environment_data(vals)
            else:
                vals_dev.update({
                    "online_status": False,
                    "device_status": "offline",
                    "last_updated": last_updated_timestamp
                })
                _log.debug(f"AirvedaDevice get_status: offline, last_updated: {pendulum.from_timestamp(last_updated_timestamp, tz='Asia/Bangkok')}")
                self._emit_device_data(vals_dev)

    def _emit_environment_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"AirvedaDevice _emit_environment_data: Exception {e}")
    
    def _emit_device_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"AirvedaDevice _emit_device_data: Exception {e}")

    def to_environment_temperature(self, val):
        return round(float(val), 2)
    
    def to_environment_humidity(self, val):
        return round(float(val), 2)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


def airveda(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Airveda
    :rtype: Airveda
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")

    for x, y in zip(
        [
            "devices",
            "agent_name",
            "timezones",
            "default_timezone",
            "sampling_rate"
        ],
        [{}, "airveda", "","Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Airveda(topic, **kwargs)


class Airveda(altolib.AltoBridgeAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Airveda, self).__init__(topic, **kwargs)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

        self.queue = Queue()

        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

        self.airveda_api = None

        _log.debug("vip_identity: " + self.core.identity)

    def _build_device(self, dev_type, dev_id, nb_subdev=1):
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, nb_subdev, self.airveda_api)
            self.register_new_device(newdev)
        
    def send_samples(self):
        for k, v in self.device_list.items():
            try:
                self._add_job({"instance":v})
            except Exception as e:
                _log.error(f"Airveda send_samples: Exception {e}")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.airveda_api = airveda_cloud.AirvedaAPI(airveda_cloud.AirvedaAuth(self.airveda_credential["email"],
                                                            self.airveda_credential["password"]))

        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, 1)
    
    def last_rites(self):
        self._add_job("Die")
    
    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            _log.debug(e)
    
    def _send_samples_thread(self):
        while True:
            job = self.queue.get()
            self.queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            try:
                job["instance"].get_status()
            except Exception as e:
                _log.error(f"Airveda _send_samples_thread: Exception {e}")
    
    @RPC.export
    def get_device_status(self):
        status_list = []
        for dev, instance in self.device_list.items():
            status_list.append({dev: instance.get_device_status()})
        return status_list
    
def main():
    """Main method called to start the agent."""
    utils.vip_main(airveda, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
