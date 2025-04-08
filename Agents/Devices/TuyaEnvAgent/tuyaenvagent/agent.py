"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from threading import Thread
from queue import Queue
from gevent import spawn, joinall

from altolib import (
    AltoEnvironSensor,
    AltoDeviceSensor,
    AltoBridgeAgent,
    AltoSensor
)
from altoutils.tuya.cloud import (
    TuyaEnvSensor,
    TuyaAPI,
    TuyaAuth
)

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.2"


def device_factory(devtype):
    if devtype == "tuya_aq":
        return AQDevice
    elif devtype == "tuya_env":
        return TempHumidDevice
    elif devtype == "tuya_env_battery":
        return TempHumidBatteryDevice
    elif devtype == "tuya_aq_multi_detector":
        return AQMultiDetectorDevice

    raise f"device factory error, no {devtype} on this factory"


class AQDevice(AltoEnvironSensor, AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, tuya_api, **kwarg):
        super().__init__(controller, devid, nb_subdev)
        self.TUYAENVMAP = {
            "ch2o": "ch2o_value",
            "pm25": "pm25_value",
            "voc": "voc_value",
            "co2": "co2_value",
            "temperature": "temp_current",
            "humidity": "humidity_value"
        }

        self.TUYADEVICEMAP = {
            "online_status":"online_status",
            "device_status": "device_status"
        }
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self._sample_init()

        self._tuya_device = TuyaEnvSensor(self.device_id, tuya_api)
    
    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals_env = {}
        vals_device = {}
        res = self._tuya_device.get_status()
        res_info = self._tuya_device.get_information()
        try:
            if res['success']:
                for payload in res['result']:
                    if payload['code'] in self.TUYAENVMAP.values():
                        vals_env.update({
                            payload['code']: payload['value']
                        })
                self._emit_environment_data(vals_env)
                _log.debug(f"AQDevice get_status: {res['result']}")
            else:
                _log.debug(f"AQDevice get_status Failed: {res['result']}")
        except Exception as err:
            _log.error(f"AQDevice get_status Exception: {err}")
        
        try:
            if res_info['success']:
                status_bool = res_info['result']['online']
                status = "online" if status_bool else "offline"
                vals_device.update({
                    "device_status": status,
                    "online_status": status_bool
                })
                _log.debug(f"AQDevice get_status device_status: {status}")
                self._emit_device_data(vals_device)
            else:
                _log.debug(f"AQDevice get_status Failed device_status: {res_info['result']}")
        except Exception as err:
            _log.error(f"AQDevice get_status Exception: {err}")

    def _emit_environment_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAENVMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"AQDevice _emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"AQDevice _emit_device_data Exception: {e}")
    
    def to_environment_temperature(self, val):
        return round(float(val), 1)

    def to_environment_humidity(self, val):
        return round(float(val), 1)

    def to_environment_co2(self, val):
        return round(float(val), 1)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


class TempHumidDevice(AltoEnvironSensor, AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, tuya_api, **kwarg):
        super().__init__(controller, devid, nb_subdev)
        self.TUYAENVMAP = {
            "temperature": "va_temperature",
            "humidity": "humidity_value"
        }
        self.TUYADEVICEMAP = {
            "online_status":"online_status"
        }
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self._sample_init()

        self._tuya_device = TuyaEnvSensor(self.device_id, tuya_api)
    
    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals_env = {}
        vals_device = {}
        res = self._tuya_device.get_status()
        res_info = self._tuya_device.get_information()
        try:
            if res['success'] == True:
                for payload in res['result']:
                    if payload['code'] in self.TUYAENVMAP.values():
                        vals_env.update({
                            payload['code']: payload['value']
                        })
                self._emit_environment_data(vals_env)
                _log.debug(f"TempHumidDevice get_status: {res['result']}")
            else:
                _log.debug(f"TempHumidDevice get_status Failed: {res['result']}")
        except Exception as err:
            _log.error(f"TempHumidDevice get_statue Exception: {err}")
        
        try:
            if res_info['success']:
                status_bool = res_info['result']['online']
                status = "online" if status_bool else "offline"
                vals_device.update({
                    "device_status": status,
                    "online_status": status_bool
                })
                _log.debug(f"TempHumidDevice get_status device_status: {status}")
                self._emit_device_data(vals_device)
            else:
                _log.debug(f"TempHumidDevice get_status Failed device_status: {res_info['result']}")
        except Exception as err:
            _log.error(f"TempHumidDevice get_statue Exception: {err}")
    
    def _emit_environment_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAENVMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"TempHumidDevice _emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"TempHumidDevice _emit_device_data Exception: {e}")
    
    def to_environment_temperature(self, val):
        return round(float(val/10), 1)

    def to_environment_humidity(self, val):
        return round(float(val), 1)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


class TempHumidBatteryDevice(AltoEnvironSensor, AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, tuya_api, **kwarg):
        super().__init__(controller, devid, nb_subdev)
        self.TUYAENVMAP = {
            "temperature": "va_temperature",
            "humidity": "va_humidity"
        }
        self.TUYADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
            "battery_state": "battery_state"
        }
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self._sample_init()

        self._tuya_device = TuyaEnvSensor(self.device_id, tuya_api)
    
    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals_env = {}
        vals_device = {}
        res = self._tuya_device.get_status()
        res_info = self._tuya_device.get_information()
        try:
            if res['success']:
                for payload in res['result']:
                    if payload['code'] in self.TUYAENVMAP.values():
                        vals_env.update({
                            payload['code']: payload['value']
                        })
                    elif payload['code'] in self.TUYADEVICEMAP.values():
                        if payload['value'] == "middle":
                            vals_device.update({
                                payload['code']: "medium"
                            })
                        else:
                            vals_device.update({
                                payload['code']: payload['value']
                            })
                _log.debug(f"TempHumidBatteryDevice get_status env:{vals_env}")
                self._emit_environment_data(vals_env)
            else:
                _log.debug(f"TempHumidBatteryDevice get_status Failed env: {res['result']}")
        except Exception as err:
            _log.error(f"TempHumidBatteryDevice get_statue Exception: {err}")
        
        try:
            if res_info['success']:
                status_bool = res_info['result']['online']
                status = "online" if status_bool else "offline"
                vals_device.update({
                    "device_status": status,
                    "online_status": status_bool
                })
                _log.debug(f"TempHumidBatteryDevice get_status device_status: {status}")
                self._emit_device_data(vals_device)
            else:
                _log.debug(f"TempHumidBatteryDevice get_status Failed device_status: {res_info['result']}")
        except Exception as err:
            _log.error(f"TempHumidBatteryDevice get_statue Exception: {err}")
    
    def _emit_environment_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAENVMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"TempHumidBatteryDevice _emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"TempHumidBatteryDevice _emit_device_data Exception: {e}")
    
    def to_environment_temperature(self, val):
        return round(float(val/10), 1)

    def to_environment_humidity(self, val):
        return round(float(val), 1)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


class AQMultiDetectorDevice(AltoEnvironSensor, AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, tuya_api, **kwarg):
        super().__init__(controller, devid, nb_subdev)
        self.TUYAENVMAP = {
            "co2": "ch2o_value",
            "temperature": "va_temperature",
            "pm25": "va_humidity",
            "humidity": "pm25_value",
            "noise": "voc_value",
            "illuminance": "co2_value"
        }

        self.TUYADEVICEMAP = {
            "online_status":"online_status",
            "device_status": "device_status"
        }
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self._sample_init()

        self._tuya_device = TuyaEnvSensor(self.device_id, tuya_api)
    
    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals_read = {}
        reverse_read = {}
        vals_env = {}
        vals_device = {}
        for k, v in self.TUYAENVMAP.items():
            reverse_read[v] = k

        res = self._tuya_device.get_status()
        res_info = self._tuya_device.get_information()
        try:
            if res['success']:
                for payload in res['result']:
                    if payload['code'] in self.TUYAENVMAP.values():
                        vals_env.update({
                            payload['code']: payload['value']
                        })
                        vals_read.update({reverse_read[payload['code']]: payload['value']})
                self._emit_environment_data(vals_env)
                _log.debug(f"AQMultiDetectorDevice get_status: {vals_read}")
            else:
                _log.debug(f"AQMultiDetectorDevice get_status Failed: {res['result']}")
        except Exception as err:
            _log.error(f"AQMultiDetectorDevice get_statue Exception: {err}")
        
        try:
            if res_info['success']:
                status_bool = res_info['result']['online']
                status = "online" if status_bool else "offline"
                vals_device.update({
                    "device_status": status,
                    "online_status": status_bool
                })
                _log.debug(f"AQMultiDetectorDevice get_status device_status: {status}")
                self._emit_device_data(vals_device)
            else:
                _log.debug(f"AQMultiDetectorDevice get_status Failed device_status: {res_info['result']}")
        except Exception as err:
            _log.error(f"AQMultiDetectorDevice get_status Exception: {err}")

    def _emit_environment_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAENVMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"AQMultiDetectorDevice _emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"AQMultiDetectorDevice _emit_device_data Exception: {e}")
    
    def to_environment_temperature(self, val):
        return round(float(val), 1)

    def to_environment_humidity(self, val):
        return round(float(val), 1)
    
    def to_environment_co2(self, val):
        return round(float(val), 1)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


def tuyaenvagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyaenvagent
    :rtype: Tuyaenvagent
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
        [{}, "tuyaenv", "Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyaenvagent(topic, **kwargs)


class Tuyaenvagent(AltoBridgeAgent, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyaenvagent, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self._sampling_rate_cd = 15
        self.auto_send =True
        self.sample_lock = {}

        # self.queue = Queue()

        # self.getsample_thread = Thread(target=self._send_samples_thread)
        # self.getsample_thread.setDaemon(True)
        # self.getsample_thread.start()

        self.tuya_api = None
    
    def _build_device(self, dev_type, dev_id, nb_subdev=1):
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, nb_subdev, self.tuya_api)
            self.register_new_device(newdev)
        
    def send_samples(self):
        spawn_list = []
        for k, v in self.device_list.items():
            try:
                # self._add_job({"instance":v})
                spawn_list.append(spawn(v.get_status))
            except Exception as e:
                _log.error(f"Tuyaenvagent send_samples: Exception {e}")
        joinall(spawn_list)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.tuya_api = TuyaAPI(
            TuyaAuth(
                self.tuya_credential["client_id"],
                self.tuya_credential["client_secret"]
            )
        )
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, 1)
    
    def last_rites(self):
        self._add_job("Die")
    
    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            _log.error(e)
    
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
                _log.error(f"Tuyaenvagnet _send_samples_thread: Exception {e}")

    @RPC.export
    def get_device_status(self):
        status_list = []
        for dev, instance in self.device_list.items():
            status_list.append({dev: instance.get_device_status()})
        return status_list
    

def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyaenvagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
