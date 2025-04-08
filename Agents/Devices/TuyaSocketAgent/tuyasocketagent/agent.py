"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread, Lock
from queue import Queue, Empty

from altolib import (
    AltoSwitchDevice,
    AltoDeviceSensor,
    AltoElectricSensor,
    AltoSwitch,
    AltoSensor,
    AltoBridgeAgent
)

from altoutils.tuya.cloud import TuyaAuth, TuyaAPI, TuyaSocket
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from gevent import spawn, joinall

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "2.0"

def device_factory(devtype):
    if devtype == "tuya_wall_socket":
        return WallSocketDevice
    elif devtype == "tuya_plug_elec":
        return PlugElectricDevice
    
    raise Exception(f"Unknown device type: {devtype}")


class WallSocketDevice(AltoSwitchDevice, AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, tuya_api, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.TUYADEVICEMAP = {
            "device_status": "device_status",
            "online_status": "online_status"
        }
        self.device_name = device_name
        self._tuya_socket = TuyaSocket(devid, tuya_api)
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()
    
    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
    
    def get_status(self):
        map_switch_subdev = {
            "switch_1": 0,
            "switch_2": 1
        }
        ret_info = self._tuya_socket.get_information()
        try:
            if ret_info['success']:
                status = "online" if ret_info['result']['online'] else "offline"
                _log.info(f"WallSocketDevice get_status device_status: {status}")
                self._emit_device_data({
                    "device_status": status,
                    "online_status": ret_info['result']['online']
                })
                if status == "offline":
                    return
            else:
                _log.warning(f"WallSocketDevice get_status failed: {ret_info['result']}")
        except Exception as err_info:
            _log.error(f"WallSocketDevice get_status Error: {err_info}")
        
        val_read = {}
        ret = self._tuya_socket.get_status()
        try:
            if ret['success']:
                for payload in ret['result']:
                    if payload['code'] in map_switch_subdev:
                        state = "on" if payload['value'] else "off"
                        val_read.update({
                            payload['code']: state
                        })
                        self.update_switch_state(map_switch_subdev[payload['code']], state)
                _log.info(f"WallSocketDevice get_status: {self.device_name} {val_read}")
            else:
                _log.warning(f"WallSocketDevice get_status failed: {ret['result']}")
        except Exception as err:
            _log.error(f"WallSocketDevice get_status Error: {err}")
    
    def turn_on(self, subdev: int):
        body = {
            "commands": [
                {
                    "code": f"switch_{subdev + 1}",
                    "value": True
                }
            ]
        }
        ret = self._tuya_socket.turn_on(body)
        if ret["result"] == True:
            self.update_switch_state(subdev, "on")
            _log.debug(f"WallSocketDevice turn_on {self.device_id} success")
        else:
            _log.warning(f"WallSocketDevice turn_on {self.device_id} failed")
    
    def turn_off(self, subdev: int):
        body = {
            "commands": [
                {
                    "code": f"switch_{subdev + 1}",
                    "value": False
                }
            ]
        }
        ret = self._tuya_socket.turn_off(body)
        if ret["result"] == True:
            self.update_switch_state(subdev, "off")
            _log.debug(f"WallSocketDevice turn_off {self.device_id} success")
        else:
            _log.warning(f"WallSocketDevice turn_off {self.device_id} failed")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"WallSocketDevice _emit_deivce_data: Exception {e}")
    

class PlugElectricDevice(AltoSwitchDevice, AltoDeviceSensor, AltoElectricSensor):
    
    def __init__(self, controller, devid, nb_subdev, tuya_api, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.TUYADEVICEMAP = {
            "device_status": "device_status",
            "online_status": "online_status"
        }
        self.TUYAELECTRICMAP = {
            "voltage": "cur_voltage",
            "current": "cur_current",
            "power": "cur_power",
            "energy": "add_ele"
        }
        self.device_name = device_name
        self._tuya_socket = TuyaSocket(devid, tuya_api)
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported["electric"] = [x for x in self.TUYAELECTRICMAP.keys()]
        self._sample_init()
    
    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.data_map.update(self.TUYAELECTRICMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("electric", self.TUYAELECTRICMAP.keys())
    
    def get_status(self):
        ret_info = self._tuya_socket.get_information()
        try:
            if ret_info['success']:
                status = "online" if ret_info['result']['online'] else "offline"
                _log.info(f"PlugElectricDevice get_status device_status: {status}")
                self._emit_device_data({
                    "device_status": status,
                    "online_status": ret_info['result']['online']
                })
                if status == "offline":
                    return
            else:
                _log.warning(f"PlugElectricDevice get_status failed: {ret_info['result']}")
        except Exception as err_info:
            _log.error(f"PlugElectricDevice get_status Error: {err_info}")
        
        vals = {}
        ret = self._tuya_socket.get_status()
        try:
            if ret['success']:
                self.update_switch_state(0, "on" if ret['result'][0]['value'] else "off")
                for payload in ret['result']:
                    if payload['code'] in self.TUYAELECTRICMAP.values():
                        vals[payload['code']] = payload['value']
                _log.info(f"PlugElectricDevice get_status {self.device_name}: {vals}")
                self._emit_electric_data(vals)
            else:
                _log.warning(f"PlugElectricDevice get_status failed: {ret['result']}")
        except Exception as err:
            _log.error(f"PlugElectricDevice get_status Error: {err}")
    
    def turn_on(self, subdev: int):
        if subdev == 0:
            body = {
                "commands": [
                    {
                        "code": "switch_1",
                        "value": True
                    }
                ]
            }
            ret = self._tuya_socket.turn_on(body)
            if ret["result"] == True:
                self.update_switch_state(0, "on")
                _log.debug(f"PlugElectricDevice turn_on {self.device_id} success")
            else:
                _log.warning(f"PlugElectricDevice turn_on {self.device_id} failed")
    
    def turn_off(self, subdev: int):
        if subdev == 0:
            body = {
                "commands": [
                    {
                        "code": "switch_1",
                        "value": False
                    }
                ]
            }
            ret = self._tuya_socket.turn_off(body)
            print(ret)
            if ret["result"] == True:
                self.update_switch_state(0, "off")
                _log.debug(f"PlugElectricDevice turn_off {self.device_id} success")
            else:
                _log.warning(f"PlugElectricDevice turn_off {self.device_id} failed")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"PlugElectricDevice _emit_deivce_data: Exception {e}")

    def _emit_electric_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAELECTRICMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="electric")
        except Exception as e:
            _log.error(f"PlugElectricDevice _emit_electric_data: Exception {e}")
    
    def to_electric_voltage(self, val):
        return round(float(val/10), 2)
    
    def to_electric_current(self, val):
        return round(float(val/1000), 2)
    
    def to_electric_power(self, val):
        return round(float(val/10000), 2)
    
    def to_electric_energy(self, val):
        return round(float(val/100), 2)
    
        
def tuyasocketagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyasocketagent
    :rtype: Tuyasocketagent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")

    for x, y in zip([
        "devices",
        "agent_name",
        "timezones",
        "default_timezone",
        "sampling_rate"
    ],
    [{}, "tuyasocket", "Asia/Bangkok", 60]):

        kwargs[x] = config.get(x, y)

    return Tuyasocketagent(topic, **kwargs)


class Tuyasocketagent(AltoBridgeAgent, AltoSwitch, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyasocketagent, self).__init__(topic, **kwargs)
        
        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

        # self.queue = Queue()

        # self.getsample_thread = Thread(target=self._send_samples_thread)
        # self.getsample_thread.setDaemon(True)
        # self.getsample_thread.start()

        self.tuya_api = None

        _log.debug("vip_identity: " + self.core.identity)

    def _build_device(self, dev_type, dev_id, nb_subdev, device_name):
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, nb_subdev, self.tuya_api, device_name)
            self.register_new_device(newdev)
    
    def send_samples(self):
        spawn_list = []
        for k, v in self.device_list.items():
            try:
                # self._add_job({"instance":v})
                spawn_list.append(spawn(v.get_status()))
            except Exception as e:
                _log.error(f"Tuyasocketagent send_samples: Exception {e}")
        joinall(spawn_list)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.tuya_api = TuyaAPI(TuyaAuth(self.tuya_credential["client_id"],
                                                    self.tuya_credential["client_secret"]))
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, v[1], v[2])

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
                _log.error(f"Tuyasocketagent _send_samples_thread: Exception {e}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyasocketagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
