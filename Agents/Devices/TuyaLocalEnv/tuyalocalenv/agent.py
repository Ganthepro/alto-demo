"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
from gevent import spawn, joinall

from threading import Thread
from queue import Queue

import altolib
from altoutils.tuya.local import LocalTuya

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron, periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.2"


def device_factory(devtype):
    if devtype == "tuya_temp_humid":
        return TempHumidDevice
    elif devtype == "tuya_aq":
        return AQDevice
    elif devtype == "tuya_aq_multi_detector":
        return AQMultiDetectorDevice
    
    raise Exception(f"Unknown device type {devtype}")


class TempHumidDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.ip_address = ip_address
        self.local_key = local_key
        self.TUYAENVMAP = {
            "temperature": "1",
            "humidity": "2"
        }
        self.TUYADEVICEMAP = {
            "device_status": "device_status",
            "online_status": "online_status"
        }
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()
        self.get_status_count = 0
        self.offline_count = 0

        self._local_tuya = LocalTuya(devid, ip_address, local_key)

    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals = {}
        vals_read = {}
        rev_map = {}
        for k, v in self.TUYAENVMAP.items():
            rev_map.update({v: k})
        try:
            ret = self._local_tuya.get_status()
            if "Err" in ret:
                if self.offline_count == 10:
                    self._emit_device_data({
                        "online_status": False,
                        "device_status": "offline"
                        })
                    _log.warning(f"TempHumidDevice get_status Offline: {self.device_id}")
                    return
                _log.warning(f"TempHumidDevice get_status Failed: {self.device_id}, count: {self.offline_count}")
                self.offline_count += 1
                return

            self.offline_count = 0
            if ("1" in ret['dps']) and ("2" in ret['dps']):
                for k, v in ret['dps'].items():
                    if k in self.TUYAENVMAP.values():
                        vals.update({k: v})
                        if rev_map[k] == "temperature":
                            vals_read.update({rev_map[k]: v/10})
                        else:
                            vals_read.update({rev_map[k]: v})
                self._emit_device_data({
                    "online_status": True,
                    "device_status": "online"
                    })
                self._emit_environment_data(vals)
                _log.debug(f"TempHumidDevice get_status: {self.device_id} {vals_read}")
            else:
                self._local_tuya.reconnect()
        except Exception as e:
            _log.error(f"TempHumidDevice get_status Exception: {e}")

    def _emit_environment_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"_emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"_emit_device_data Exception: {e}")

    def to_environment_temperature(self, val):
        return round(float(val/10), 1)

    def to_environment_humidity(self, val):
        return round(float(val), 1)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


class AQDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.TUYAENVMAP = {
            "temperature": "2",
            "humidity": "3",
            "co2": "4",
            "ch2o": "5",
            "tvoc": "6",
            "pm25": "7"
        }
        self.TUYADEVICEMAP = {
            "device_status": "device_status",
            "online_status": "online_status",
        }
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()
        self.get_status_count = 0
        self.offline_count = 0

        self._local_tuya = LocalTuya(devid, ip_address, local_key)

    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals = {}
        vals_read = {}
        rev_map = {}
        for k, v in self.TUYAENVMAP.items():
            rev_map.update({v: k})
        try:
            ret = self._local_tuya.get_status()
            if "Err" in ret:
                if self.offline_count == 10:
                    self._emit_device_data({
                        "online_status": False,
                        "device_status": "offline"
                        })
                    _log.warning(f"AQDevice get_status Offline: {self.device_id}")
                    return
                _log.warning(f"AQDevice get_status Failed: {self.device_id}, count: {self.offline_count}")
                self.offline_count += 1
                return

            self.offline_count = 0
            if ("2" in ret['dps']) and ("3" in ret['dps']) and ("4" in ret['dps']):
                for k, v in ret['dps'].items():
                    if k in self.TUYAENVMAP.values():
                        if k == "5":
                            vals.update({k: v/1000})
                            vals_read.update({rev_map[k]: v/1000})
                        elif k == "6":
                            vals.update({k: v/1000})
                            vals_read.update({rev_map[k]: v/1000})
                        else:
                            vals.update({k: v})
                            vals_read.update({rev_map[k]: v})
                self._emit_device_data({
                    "online_status": True,
                    "device_status": "online"
                    })
                self._emit_environment_data(vals)
                _log.debug(f"AQDevice get_status: {self.device_id} {vals_read}")
            else:
                self._local_tuya.reconnect()
        except Exception as e:
            _log.error(f"AQDevice get_status Exception: {e}")

    def _emit_environment_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"_emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"_emit_device_data Exception: {e}")

    def to_environment_temperature(self, val):
        return round(float(val), 1)

    def to_environment_humidity(self, val):
        return round(float(val), 1)

    def to_environment_co2(self, val):
        return round(float(val), 1)
    
    def get_device_status(self):
        return self.current_state[0]['sensor']['device']['online_status']


class AQMultiDetectorDevice(altolib.AltoEnvironSensor, altolib.AltoDeviceSensor):
    
    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.TUYAENVMAP = {
            "co2": "2",
            "temperature": "18",
            "pm25": "19",
            "humidity": "20",
            "noise": "21",
            "illuminance": "22"
        }
        self.TUYADEVICEMAP = {
            "device_status": "device_status",
            "online_status": "online_status",
        }
        self.datapoint_supported["environment"] = [x for x in self.TUYAENVMAP.keys()]
        self.datapoint_supported["device"] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()
        self.get_status_count = 0
        self.offline_count = 0

        self._local_tuya = LocalTuya(devid, ip_address, local_key)

    def _sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("environment", self.TUYAENVMAP.keys())
    
    def get_status(self):
        vals = {}
        vals_read = {}
        rev_map = {}
        for k, v in self.TUYAENVMAP.items():
            rev_map.update({v: k})
        try:
            ret = self._local_tuya.get_status()
            if "Err" in ret:
                if self.offline_count == 10:
                    self._emit_device_data({
                        "online_status": False,
                        "device_status": "offline"
                        })
                    _log.warning(f"AQMultiDetectorDevice get_status Offline: {self.device_id}")
                    return
                _log.warning(f"AQMultiDetectorDevice get_status Failed: {self.device_id}, count: {self.offline_count}")
                self.offline_count += 1
                return

            self.offline_count = 0
            if ("2" in ret['dps']) and ("18" in ret['dps']) and ("20" in ret['dps']):
                for k, v in ret['dps'].items():
                    if k in self.TUYAENVMAP.values():
                        vals.update({k: v})
                        vals_read.update({rev_map[k]: v})
                self._emit_device_data({
                    "online_status": True,
                    "device_status": "online"
                    })
                self._emit_environment_data(vals)
                _log.debug(f"AQMultiDetectorDevice get_status: {self.device_id} {vals_read}")
            else:
                self._local_tuya.reconnect()
        except Exception as e:
            _log.error(f"AQMultiDetectorDevice get_status Exception: {e}")

    def _emit_environment_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"AQMultiDetectorDevice _emit_environment_data Exception: {e}")

    def _emit_device_data(self, data):
        try:
            self.set_sensor_data({**data}, subdevice=0, sensor_type="device")
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


def tuyalocalenv(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyalocalenv
    :rtype: Tuyalocalenv
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
        [{}, "", "Asia/Bangkok", "", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyalocalenv(topic, **kwargs)


class Tuyalocalenv(altolib.AltoBridgeAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyalocalenv, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}
        
        # self.queue = Queue()

        # self.getsample_thread = Thread(target=self._send_samples_thread)
        # self.getsample_thread.setDaemon(True)
        # self.getsample_thread.start()

    def _build_device(self, devtype, dev_id, ip_address, local_key, nb_subdev=1):
        if dev_id not in self.device_list:
            Sensor = device_factory(devtype)
            newdev = Sensor(self, dev_id, nb_subdev, ip_address, local_key)
            self.register_new_device(newdev)
    
    def send_samples(self):
        spawn_list = []
        for k, v in self.device_list.items():
            try:
                # self._add_job({"instance": v})
                spawn_list.append(spawn(v.get_status))
            except Exception as e:
                _log.error(f"Tuyalocalenv send_samples: Exception {e}")
        joinall(spawn_list)

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
                _log.error(f"Tuyalocalenv _send_samples_thread: Exception {e}")
    
    @RPC.export
    def get_device_status(self):
        status_list = []
        for dev, instance in self.device_list.items():
            status_list.append({dev: instance.get_device_status()})
        return status_list

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyalocalenv, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass