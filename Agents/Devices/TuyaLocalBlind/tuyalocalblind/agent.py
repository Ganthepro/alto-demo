"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
from gevent import sleep

from threading import Thread, Lock
from queue import Queue, Empty

import altolib
import tinytuya as tuya

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron, periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

ERROR = ["901", "902", "903", "904", "906", "907", "908"]

class Tinytuya:

    def __init__(self, device_id, ip_address, local_key):
        self._device_id = device_id
        self._ip_address = ip_address
        self._local_key = local_key
        self.tuyaoutlet = tuya.OutletDevice(device_id, ip_address, local_key)
        self.tuyaoutlet.set_version(3.3)

    def get_status(self):
        ret = self.tuyaoutlet.status()
        if "Error" in ret:
            if ret["Err"] in ERROR:
                _log.warning(f"Tinytuya Error: {self._device_id} {ret['Error']}")
                del self.tuyaoutlet
                self.reinstantiation_device()
                return None
            elif ret["Err"] == "905":
                _log.warning(f"Tinytuya Error: {self._device_id} {ret['Error']}")
                return False
            elif ret["Err"] == "900":
                _log.warning(f"Tinytuya Error: {self._device_id}, Please check ip address and local key")
        return ret
    
    def reinstantiation_device(self):
        self.tuyaoutlet = tuya.OutletDevice(self._device_id, self._ip_address, self._local_key)
        self.tuyaoutlet.set_version(3.3)
    
    def open_curtain(self):
        ret = self.tuyaoutlet.set_value(1, "open")
        if "Error" in ret:
            _log.error(f"Tinytuya open_curtain Error: {self._device_id} {ret}")
            return False
        return True

    def close_curtain(self):
        ret = self.tuyaoutlet.set_value(1, "close")
        if "Error" in ret:
            _log.error(f"Tinytuya close_curtain Error: {self._device_id} {ret}")
            return False
        return True

    def stop_curtain(self):
        ret = self.tuyaoutlet.set_value(1, "stop")
        if "Error" in ret:
            _log.error(f"Tinytuya stop_curtain Error: {self._device_id} {ret}")
            return False
        return True

    def set_position(self, percent_position: int):
        blind_range = [0, 100]
        if percent_position < blind_range[0] or percent_position > blind_range[1]:
            _log.error("Percent position to set out of Range")
            return False
        ret = self.tuyaoutlet.set_value(2, int(percent_position))
        if "Error" in ret:
            _log.error(f"Tinytuya set_position Error: {self._device_id} {ret}")
            return False
        return True

def device_factory(devtype):
    if devtype == "tuyablinds":
        return TuyaBlindDevice

    raise Exception(f"Unknown device type {devtype}")

class TuyaBlindDevice(altolib.AltoCurtainDevice, altolib.AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.TUYADEVICEMAP = {
            "percent_position": "2",
            "device_status": "device_status",
            "online_status": "online_status",
            "last_updated": "last_updated"
        }
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()
        self.get_status_count = 0
        self.offline_count = 0
        self._is_device_online = False

        self.tiny_tuya = Tinytuya(devid, ip_address, local_key)
    
    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
    
    def get_status(self):
        vals = {}
        vals_read = {}
        rev_map = {}
        for k, v in self.TUYADEVICEMAP.items():
            rev_map.update({v: k})
        try:
            ret = self.tiny_tuya.get_status()
            if not ret:
                if self.offline_count == 5:
                    self._is_device_online = False
                    self._emit_device_data({
                        "online_status": False,
                        "device_status": "offline"
                        })
                    _log.warning(f"TuyaBlindDevice get_status: {self.device_id} Offline")
                    self.get_status_count = 0
                    self.offline_count = 0
                else:
                    self.offline_count += 1
                    _log.warning(f"Offline Counting: {self.offline_count}")
            else:
                if ret is None:
                    _log.debug(f"Reinstantiate device by None: {self.device_id}")
                    return
                # if "2" not in ret['dps']:
                #     if self.get_status_count == 3:
                #         self.tiny_tuya.reinstantiation_device()
                #         _log.debug(f"get_status_count = 3, Reinstantiate device: {self.device_id}")
                #     else:
                #         self.get_status_count += 1
                #         self.get_status()
                #         return

                self.get_status_count = 0
                for k, v in ret['dps'].items():
                    if k == "1":
                        self.update_control_state(0, v)
                        vals_read.update({"control_state": v})
                    elif k in self.TUYADEVICEMAP.values():
                        vals.update({k: v})
                        vals_read.update({rev_map[k]: v})
                
                if not self._is_device_online:
                    self._is_device_online = True
                    self.offline_count = 0
                    self.stop_curtain(0)
                    return

                if self.offline_count != 0:
                    self.offline_count = 0
                    self.stop_curtain(0)
                    return

                vals.update({
                    "online_status": True,
                    "device_status": "online"
                    # "last_updated": time.time()
                    })
                self.emit_event_motor()
                self._emit_device_data(vals)
                _log.debug(f"TuyaBlindDevice get_status: {self.device_id} {vals_read}")
        except Exception as e:
            _log.error(f"TuyaBlindDevice get_status: Exception {e}")
    
    def open_curtain(self, subdev):
        if subdev == 0:
            ret = self.tiny_tuya.open_curtain()
            if not ret:
                _log.error(f"TuyaBlindDevice open_curtain: {self.device_id} Failed")
            else:
                _log.debug(f"TuyaBlindDevice open_curtain: {self.device_id} Success")

    def close_curtain(self, subdev):
        if subdev == 0:
            ret = self.tiny_tuya.close_curtain()
            if not ret:
                _log.error(f"TuyaBlindDevice close_curtain: {self.device_id} Failed")
            else:
                _log.debug(f"TuyaBlindDevice close_curtain: {self.device_id} Success")

    def stop_curtain(self, subdev):
        if subdev == 0:
            ret = self.tiny_tuya.stop_curtain()
            if not ret:
                _log.error(f"TuyaBlindDevice stop_curtain: {self.device_id} Failed")
            else:
                _log.debug(f"TuyaBlindDevice stop_curtain: {self.device_id} Success")

    def set_percent_position(self, subdev, position: int):
        if subdev == 0:
            ret = self.tiny_tuya.set_position(position)
            if not ret:
                _log.error(f"TuyaBlindDevice set_percent_position: {self.device_id} Failed")
            else:
                _log.debug(f"TuyaBlindDevice set_percent_position: {self.device_id} Success")

    def emit_event_motor(self):
        self.controller.emit_event_motor(self)
    
    def _emit_device_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"_emit_environment_data: Exception {e}")
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


def tuyalocalblind(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyalocalblind
    :rtype: Tuyalocalblind
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
            "timezone",
            "default_timezone",
            "sampling_rate"
        ],
        [{}, "tuyalocalblind", "Asia/Bangkok", "", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyalocalblind(topic, **kwargs)


class Tuyalocalblind(altolib.AltoBridgeAgent, altolib.AltoCurtain, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyalocalblind, self).__init__(topic, **kwargs)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

        self.queue = Queue()

        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

        _log.debug("vip_identity: " + self.core.identity)
    
    def _build_device(self, devtype, dev_id, ip_address, local_key, nb_subdev=1):
        if dev_id not in self.device_list:
            Sensor = device_factory(devtype)
            newdev = Sensor(self, dev_id, nb_subdev, ip_address, local_key)
            self.register_new_device(newdev)
    
    def send_samples(self):
        for k, v in self.device_list.items():
            try:
                self._add_job({"instance": v})
            except Exception as e:
                _log.error(f"Tuyalocalblind send_samples: Exception {e}")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, v[1], v[2])

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
                _log.error(f"Tuyalocalblind _send_samples_thread: Exception {e}")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def get_device_status(self):
        status_list = []
        for dev, instance in self.device_list.items():
            status_list.append({dev: instance.get_device_status()})
        return status_list

def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyalocalblind, 
                   version=__version__)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
 