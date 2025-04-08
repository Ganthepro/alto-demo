"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from threading import Thread, Lock
from queue import Queue, Empty

import altolib

from altoutils.tuya import cloud
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

def device_factory(devtype):
    if devtype == "tuya_blind_motor":
        return BlindMotorDevice
    if devtype == "Another":
        return Another
    
    raise Exception(f"Unknown device type {devtype}")

class BlindMotorDevice(altolib.AltoCurtainDevice, altolib.AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, tuya_api, **kwarg):
        super().__init__(controller, devid, 1)
        self.ATMODEVICEMAP = {
            "percent_position": "percent_control",
            "work_state": "work_state",
            "status": "online_status"
        }
        self.datapoint_supported["device"] = [x for x in self.ATMODEVICEMAP.keys()]
        self._sample_init()

        self._tuya_curtain = cloud.TuyaCurtain(self.device_id, tuya_api)

    def _sample_init(self):
        self.data_map.update(self.ATMODEVICEMAP)
        self.initialise_data("device", self.ATMODEVICEMAP.keys())

    def get_status(self):
        res_info = self._tuya_curtain.get_information()
        res = self._tuya_curtain.get_status()
        vals = {}
        control = res["result"][0]["value"]
        vals.update({res["result"][1]["code"]: res["result"][1]["value"]})
        vals.update({res["result"][3]["code"]: res["result"][3]["value"]})
        vals.update({"online_status": res_info["result"]["online"]})
        self.update_control_state(0, control)
        self._emit_device_data(vals)
        self.emit_event_motor()
        _log.debug(f"BlindMotorDevice get_status: {self.device_id} {res}")

    def open_curtain(self, subdev):
        if subdev == 0:
            body = {"commands":[
                            {
                                "code":"control",
                                "value":"open"
                            }
                           ]
                }
            ret = self._tuya_curtain.open_curtain(body)
            _log.info(f"BlindMotorDevice open_curtain: {self.device_id} {ret}")
    
    def close_curtain(self, subdev):
        if subdev == 0:
            body = {"commands":[
                            {
                                "code":"control",
                                "value":"close"
                            }
                           ]
                }
            ret = self._tuya_curtain.close_curtain(body)
            _log.info(f"BlindMotorDevice close_curtain: {self.device_id} {ret}")
    
    def stop_curtain(self, subdev):
        if subdev == 0:
            body = {"commands":[
                            {
                                "code":"control",
                                "value":"stop"
                            }
                           ]
                }
            ret = self._tuya_curtain.stop_curtain(body)
            _log.info(f"BlindMotorDevice stop_curtain: {self.device_id} {ret}")

    def set_percent_position(self, subdev, position: int):
        position_range = [0, 100]
        if subdev == 0:
            if isinstance(position, str):
                position = int(position)
            body = {"commands":[
                            {
                                "code": "percent_control",
                                "value": position
                            }
                           ]
                }
            if position < position_range[0] or position > position_range[1]:
                _log.error(f"Set percent position Out of range")
            else:
                ret = self._tuya_curtain.set_percent_position(body)
                _log.info(f"BlindMotorDevice set_percent_position: {self.device_id} {ret}")

    def emit_event_motor(self):
        self.controller.emit_event_motor(self)

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMODEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"BlindmotorDevice _emit_device_data: Exception {e}")
            
def tuyacloudcurtain(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyacloudcurtain
    :rtype: Tuyacloudcurtain
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic =  config.get("topic", "")

    for x, y in zip(
        [
            "devices",
            "agent_name",
            "timezones",
            "default_timezone",
            "sampling_rate"
        ],
        [{}, "tuyacloudcurtain", "Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyacloudcurtain(topic, **kwargs)


class Tuyacloudcurtain(altolib.AltoBridgeAgent, altolib.AltoCurtain, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyacloudcurtain, self).__init__(topic, **kwargs)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

        self.queue = Queue()

        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

        self.tuya_api = None

        _log.debug("vip_identity: " + self.core.identity)

    def _build_device(self, dev_type, dev_id, nb_subdev=1):
        # _log.debug(f'''_build_device {dev_type} {dev_id}''')
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, nb_subdev, self.tuya_api)
            # _log.debug(f'''_build_device {dev_type} {dev_id} {newdev}''')
            self.register_new_device(newdev)

    def send_samples(self):
        for k, v in self.device_list.items():
            try:
                self._add_job({
                    "instance": v,
                    "data": None
                })
            except Exception as e:
                _log.error(f"Tuyacloudcurtain send_samples: {e}")
    
    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.
        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        # self.tuya_auth = cloud.TuyaAuth(self.tuya_credential["client_id"], self.tuya_credential["client_secret"])
        self.tuya_api = cloud.TuyaAPI(cloud.TuyaAuth(self.tuya_credential["client_id"], 
                                                    self.tuya_credential["client_secret"]))
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, 1)

    def last_rites(self):
        self._add_job("Die")

    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _send_samples_thread(self):
        while True:
            job = self.queue.get()
            self.queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            # _log.debug("_send_samples_thread")
            try:
                job["instance"].get_status()
            except Exception as e:
                _log.error(f"TuyaCloudCurtain _send_samples_thread: {e}")
def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyacloudcurtain, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
