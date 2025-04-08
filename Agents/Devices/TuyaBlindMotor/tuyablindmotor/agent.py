"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread, Lock
from queue import Queue, Empty

import altolib

import tinytuya

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


POLLFREQ = 5


class BlindMotorDiscovery():
    "The Singleton Class"

    @staticmethod
    def discover():
        return tinytuya.deviceScan()


class BlindMotor():

    def __init__(self, tuya_device_id, ip_address, local_key):
        self.tuyaoutlet = tinytuya.OutletDevice(tuya_device_id, ip_address, local_key)
        self.tuyaoutlet.set_version(3.3)

    def get_status(self):
        tmp = self.tuyaoutlet.status()
        return {
            "state": tmp['dps']['1'],
            "percent": tmp['dps']['2']
        }

    def set_open(self):
        tmp = self.tuyaoutlet.set_status('open', switch=1)
        return {
            "state": tmp['dps']['1'],
            "percent": tmp['dps']['2']
        }

    def set_close(self):
        tmp = self.tuyaoutlet.set_status('close', switch=1)
        return {
            "state": tmp['dps']['1'],
            "percent": tmp['dps']['2']
        }


def blindmotor_factory(devtype):
    if devtype == "tuya_blind_motor":
        return BlindMotorDevice
    if devtype == "Another":
        return Another

    raise Exception(f"Unknown device type {devtype}")


class BlindMotorDevice(altolib.AltoCurtainDevice, altolib.AltoDeviceSensor):

    def __init__(self, controller, devid, **kwargs):
        super().__init__(controller, devid, 2) # 0 motor, 1 device sensor
        self.ATMODEVICEMAP = {
            "percent": "percent", # Position percentage
        }
        self.datapoint_supported["device"] = [x for x in self.ATMODEVICEMAP.keys()]
        self._sample_init()

        # Now setup the map
        # self.set_subdevice_name(0, "motor")

        self.tuya_device_id = devid
        self.ip_address = kwargs.get("ip_address", None)
        self.local_key = kwargs.get("local_key", None)
        self.blindmotor = BlindMotor(self.tuya_device_id, self.ip_address, self.local_key)

        self.info = {
            "tuya_device_id": self.tuya_device_id,
            "ip_address": self.ip_address,
            "local_key": self.local_key
        }

        self.queue = Queue()
        self.comm_stop = False
        self.comm_thread = Thread(target=self._poll_thread)
        self.comm_thread.setDaemon(True)
        self.comm_thread.start()

    def _sample_init(self):
        # for idx in range(0, self.number_subdevices):
        #     self.current_state[idx]["sensor"] = {"device": {}}
        self.data_map.update(self.ATMODEVICEMAP)
        self.initialise_data("device", self.ATMODEVICEMAP.keys())
    
    def _poll_thread(self):
        while not self.comm_stop:
            to = True
            try:
                cmd = self.queue.get(block=True, timeout=POLLFREQ)
                to = False
            except Empty:
                cmd = "polling"
            except Exception as e:
                _log.debug(f"ERROR: tuya blind motor thread queue problem: {e}")
                cmd = "skip"

            try:
                cmd = self.convert_command(cmd)
                if cmd:
                    ret = getattr(self.blindmotor, cmd)()
                    self._update_state(ret)
            except Exception as e:
                _log.debug(f"ERROR: tuya blind motor thread failed: {e}")
            if not to:
                self.queue.task_done()
        _log.debug(f"Thread for {self.device_id} is end.")

    def open_curtain(self, subdev):
        if subdev in [0, "motor"]:
            self.queue.put("open")

    def close_curtain(self, subdev):
        if subdev in [0, "motor"]:
            self.queue.put("close")

    def convert_command(self, cmd):
        commands = {
            "open": "set_open",
            "close": "set_close",
            "polling": "get_status"
        }
        try:
            return commands[cmd]
        except:
            if cmd != "skip":
                _log.debug("Unknown command {}".format(cmd))
            return None

    def _update_state(self, data):
        try:
            # self.update_curtain_state("motor", data["state"])
            self.update_curtain_state(0, data["state"])
            self._update_device_data(data.copy())
        except Exception as e:
            _log.error(f'BlindMotorDevice _update_state {e}')
    
    def _update_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.ATMODEVICEMAP.values():
                    vals[k] = v
            subdev_id = 1
            this_type = "device"
            # _log.debug(f'''_update_device_data {vals}''')
            self.set_sensor_data(
                {**vals}, subdev_id, this_type
            )
        except Exception as e:
            _log.error(f"Device _update_device_data problem: {e}")
            return


def tuyablindmotor(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyablindmotor
    :rtype: Tuyablindmotor
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
        [{}, "netatmo", {}, "Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyablindmotor(topic, **kwargs)


class Tuyablindmotor(altolib.AltoDiscoverableAgent, altolib.AltoCurtain, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyablindmotor, self).__init__(topic, **kwargs)

        self._sampling_rate_cd = 15 # overlide default start polling time
        self.auto_send = True  # We update at high frequecy, let the agent manage
        self.discovery_lock = Lock()

        _log.debug("vip_identity: " + self.core.identity)

    def start_discovery(self):
        if not self.discovery_lock.locked():
            _log.debug("Blind motor: starting discovery")
            thread = Thread(target=self._discover_thread, name="tuya", daemon=True)
            thread.start()
        else:
            _log.debug("Discovery in progress")

    def _discover_thread(self):
        with self.discovery_lock:
            try:
                devices_found = BlindMotorDiscovery.discover()
                for ip in devices_found:
                    tuya_id = devices_found[ip]['gwId']
                    vers = devices_found[ip]['version']
                    if vers == "3.3":
                        if tuya_id in self.devices:
                            Motor = blindmotor_factory(self.devices[tuya_id][0])
                            tuya_conf = {
                                "ip_address": ip,
                                "local_key": self.devices[tuya_id][1]
                            }
                            newdev = Motor(self, tuya_id, **tuya_conf)
                            self.register_new_device(newdev)
                            _log.debug(f"Got device at {ip}.")
            except Exception as e:
                _log.error(f"Got exception {e}")
                _log.exception(e)
            return

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        for dev in self.device_list.values():
            dev.comm_stop = True
            dev.queue.put("skip")


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyablindmotor, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
