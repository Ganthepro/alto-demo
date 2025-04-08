"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
from threading import Thread, Lock
from queue import Queue, Empty

from altolib import (
    AltoDeviceSensor,
    AltoElectricSensor,
    AltoBridgeAgent,
    AltoSensor,
    AltoSwitchDevice,
    AltoSwitch
)
from altoutils.tuya.cloud import (
    TuyaAuth,
    TuyaAPI,
    TuyaMeter
)

from gevent import spawn, joinall
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

def device_factory(devtype):
    if devtype == "tuya_single_phase":
        return TuyaSinglePhaseMeter
    if devtype == "tuya_three_phase":
        return TuyaThreePhaseMeter

class TuyaSinglePhaseMeter(AltoDeviceSensor, AltoElectricSensor, AltoSwitchDevice):
    
    def __init__(self, controller, devid, nb_subdev, tuya_api, **kwargs):
        super().__init__(controller, devid, 1)
        self.TUYAELECTRICMAP = {
            "voltage": "voltage",
            "current": "electricCurrent",
            "power": "power",
            "energy": "forward_energy_total"
        }
        self.TUYADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status"
        }
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported["electric"] = [x for x in self.TUYAELECTRICMAP.keys()]
        self._tuya_meter = TuyaMeter(self.device_id, tuya_api)
        self._sample_init()
    
    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.data_map.update(self.TUYAELECTRICMAP)
        self.initialise_data("device", self.TUYADEVICEMAP)
        self.initialise_data("electric", self.TUYAELECTRICMAP)
    
    def get_status(self):
        vals_elec = {}
        res = self._tuya_meter.get_status()
        res_info = self._tuya_meter.get_information()
        try:
            if res is not None:
                for data_list in res['result']:
                    if data_list['code'] in self.TUYAELECTRICMAP.values():
                        vals_elec[data_list['code']] = data_list['value']
                    elif data_list['code'] == "phase_a":
                        for data, value in json.loads(data_list['value']).items():
                            if data in self.TUYAELECTRICMAP.values():
                                vals_elec[data] = value
                    elif data_list['code'] == "switch":
                        state = "on" if data_list['value'] else "off"
                        self.update_switch_state(0, state)
                _log.info(f"TuyaSinglePhaseMeter get_status electric data :{vals_elec}")
                self._emit_electric_data(vals_elec)
        except Exception as status_err:
            _log.error(f"TuyaSinglePhaseMeter get_status: electric data Exception {status_err}")
        
        try:
            if res_info is not None:
                status_bool = res_info['result']['online']
                status = "online" if status_bool else "offline"
                self._emit_device_data({
                    "device_status": status,
                    "online_status": status_bool
                })
        except Exception as device_status_err:
            _log.error(f"TuyaSinglePhaseMeter get_status: device data Exception {device_status_err}")
    
    def turn_on(self, subdev):
        _log.info(f"TuyaSinglePhaseMeter turn_on: {self.device_id}")
        if subdev == 0:
            command = {
                "code": "switch",
                "value": True
            }
            ret = self._tuya_meter.turn_on(command)
            if ret is not None:
                self.update_switch_state(subdev, "on")
                _log.info(f"TuyaSinglePhaseMeter turn_on: {self.device_id} Done")
            else:
                _log.warning(f"TuyaSinglePhaseMeter turn_on Failed: {self.device_id}")

    def turn_off(self, subdev):
        _log.info(f"TuyaSinglePhaseMeter turn_off: {self.device_id}")
        if subdev == 0:
            command = {
                "code": "switch",
                "value": False
            }
            ret = self._tuya_meter.turn_off(command)
            if ret is not None:
                self.update_switch_state(subdev, "off")
                _log.info(f"TuyaSinglePhaseMeter turn_off: {self.device_id} Done")
            else:
                _log.warning(f"TuyaSinglePhaseMeter turn_off Failed: {self.device_id}")

    def _emit_electric_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAELECTRICMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="electric")
        except Exception as e:
            _log.error(f"TuyaSinglePhaseMeter _emit_electric_data: Exception {e}")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"TuyaSinglePhaseMeter _emit_device_data: Exception {e}")
            

class TuyaThreePhaseMeter(AltoDeviceSensor, AltoSwitchDevice, AltoElectricSensor):
    pass


def tuyameter(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyameter
    :rtype: Tuyameter
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
        [{}, "tuyameter", "Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyameter(topic, **kwargs)


class Tuyameter(AltoBridgeAgent, AltoSensor, AltoSwitch):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyameter, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
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
                _log.error(f"Tuyameter send_samples: Exception {e}")
        joinall(spawn_list)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.tuya_api = TuyaAPI(TuyaAuth(
            self.tuya_credential["client_id"],
            self.tuya_credential["client_secret"]
        ))
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, 1)

    # def last_rites(self):
    #     self._add_job("Die")
    
    # def _add_job(self, job):
    #     try:
    #         self.queue.put_nowait(job)
    #     except Exception as e:
    #         _log.debug(e)
    
    # def _send_samples_thread(self):
    #     while True:
    #         job = self.queue.get()
    #         self.queue.task_done()
    #         if isinstance(job, str):
    #             if job == "Die":
    #                 return
    #         try:
    #             job["instance"].get_status()
    #         except Exception as e:
    #             _log.error(f"Tuyameter _send_samples_thread: Exception {e}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyameter, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
