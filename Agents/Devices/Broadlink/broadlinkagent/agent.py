"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import altolib
import base64
import json
import logging
import struct
import sys
import time
import broadlink
from broadlink.exceptions import ReadError, StorageError
from threading import Thread, Lock
from queue import Queue, Empty
from typing import Any, List, Mapping, Union, Callable, Optional

# from broadlink.exceptions import ReadError, StorageError
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

SUPPORTEDREMOTETYPE = ["RM2", "RM4"]
SUPPORTEDSENSORTYPE = ["A1"]
LEARNTO = 20

BROADLINKMAP = {
    "temperature": "temperature",
    "humidity": "humidity",
    "luminosity_sub": "light",
    "air_quality_sub": "air_quality",
    "noise_sub": "noise",
}


class BroadlinkRemote(altolib.AltoRemoteCDevice):
    """ Now this is a broadlink device
    """

    def __init__(
        self, controller: Agent, devid: str, dev_type: str, ip: str
    ) -> altolib.AltoDevice:
        super().__init__(controller, devid, 1)
        self.dev_type = dev_type
        self.ip_address = ip
        self.queue = Queue()
        self.thread = None

    def _to_broadlink(self, pulses: List[int]):
        array = bytearray()

        for pulse in pulses:
            pulse = round(pulse * 269 / 8192)  # 32.84ms units

            if pulse < 256:
                array += bytearray(struct.pack(">B", pulse))  # big endian (1-byte)
            else:
                array += bytearray([0x00])  # indicate next number is 2-bytes
                array += bytearray(struct.pack(">H", pulse))  # big endian (2-bytes)

        packet = bytearray([0x26, 0x00])  # 0x26 = IR, 0x00 = no repeats
        packet += bytearray(struct.pack("<H", len(array)))  # little endian byte count
        packet += array
        packet += bytearray([0x0D, 0x05])  # IR terminator

        # Add 0s to make ultimate packet size a multiple of 16 for 128-bit AES encryption.
        remainder = (
            len(packet) + 4
        ) % 16  # rm.send_data() adds 4-byte header (02 00 00 00)
        if remainder:
            packet += bytearray(16 - remainder)

        return packet

    def _communication_thread(self):
        while True:
            try:
                cmd, param = self.queue.get()
                self.queue.task_done()
                if cmd == "Die":
                    return
                if cmd == "Send":
                    code, cid = param
                    self._send_thread(code, cid)
                if cmd == "LearnIR":
                    self._learn_thread(param)
                if cmd == "LearnRF":
                    self._learn_rf_thread(param)
            except Exception as e:
                _log.debug(f"Remote communication problem: {e}")

    def command_send_code(self, message: Mapping[str, Any], is_raw: bool) -> None:
        # Code is a list of on/off durations. Translate that to Broadlink, if needed
        # We ignore any subsevice_idx ...
        if is_raw:
            scode = base64.b64decode(message["code"])
        else:
            scode = self._to_broadlink(message["code"])
        self.queue.put_nowait(("Send", [scode, message["cid"]]))

    def _send_thread(self, code, cid):
        """Sending code
        """
        _log.debug(f"sending for devices:{self.device_id}")

        try:
            _log.debug(f"devices type:{self.dev_type} and address {self.ip_address}")
            dev = broadlink.gendevice(
                self.dev_type,
                (self.ip_address, 80),
                "".join(self.device_id.split(":")),
            )
            _log.debug(f"devices is:{dev.type} and dict {dir(dev)}")
            dev.auth()
            dev.send_data(code)
            _log.debug("Data sent")
            del dev
            with self.controller.emit_lock:
                self.online_status(True)
                self.controller.emit_event_sent(self, 0, cid, True)

        except Exception as e:
            _log.debug(f"Error: Something went wrong when sending data. Error was: {e}")
            _log.exception(e)
            with self.controller.emit_lock:
                self.controller.emit_event_sent(self, 0, cid, False)
                self.online_status(False)

    def command_learn_code_ir(self, message):
        """Here message must be a dictionary with 3 keys:
             device_id: the device id should be == to self.device_id
             subdevice_idx: ignored for these devices
             cid: An id to be included in the reply
        """

        self.queue.put_nowait(("LearnIR", message["cid"]))

    #
    def _learn_thread(self, cid):
        """Sending code
        """
        _log.debug(f"Learning commmand for device {self.device_id}")

        try:
            dev = broadlink.gendevice(
                self.dev_type,
                (self.ip_address, 80),
                "".join(self.device_id.split(":")),
            )
            dev.auth()
            with self.controller.emit_lock:
                self.online_status(True)
            dev.enter_learning()
            _log.debug("Device {} learning...".format(dev))
            start = time.time()
            data = None
            while time.time() - start < LEARNTO:
                time.sleep(1)
                try:
                    data = dev.check_data()
                    if data:
                        break
                except (ReadError, StorageError):
                    continue
                else:
                    break
            else:
                _log.debug("Learning problem: No data received...")
                with self.controller.emit_lock:
                    self.controller.emit_event_learnt(self, 0, cid, "")
                del dev
                return
            with self.controller.emit_lock:
                self.controller.emit_event_learnt(
                    self, 0, cid, base64.b64encode(data).decode()
                )
            del dev
        except Exception as e:
            with self.controller.emit_lock:
                self.controller.emit_event_learnt(self, 0, cid, "")
                self.online_status(False)
            _log.debug("Problem whilst learning: {}".format(e))
            _log.exception(e)

    def command_learn_code_rf(self, message):
        """Here message must be a dictionary with 3 keys:
             device_id: the device id should be == to self.device_id
             subdevice_idx: ignored for these devices
             cid: An id to be included in the reply
        """
        self.queue.put_nowait(("LearnRF", message["cid"]))

    def _learn_rf_thread(self, cid):
        _log.debug(f"Learning rf commmand for device {self.device_id}")

        try:
            dev = broadlink.gendevice(
                self.dev_type,
                (self.ip_address, 80),
                "".join(self.device_id.split(":")),
            )
            dev.auth()
            with self.controller.emit_lock:
                self.online_status(True)
            dev.sweep_frequency()

            start = time.time()
            data = None

            while time.time() - start < LEARNTO:
                time.sleep(1)
                try:
                    data = dev.check_frequency()
                    if data:
                        break
                except (ReadError, StorageError):
                    continue
                else:
                    break

            if not data:
                with self.controller.emit_lock:
                    self.controller.emit_event_learnt(self, 0, cid, "")
                dev.cancel_sweep_frequency()
                del dev
                return

            with self.controller.emit_lock:
                self.controller.emit_event_next(self, 0, cid)
            time.sleep(3)
            dev.find_rf_packet()

            start = time.time()
            data = None
            while time.time() - start < LEARNTO:
                time.sleep(1)
                try:
                    data = dev.check_data()
                    if data:
                        break
                except (ReadError, StorageError):
                    continue
                else:
                    break
            else:
                _log.debug("Learning problem: No data received...")
                with self.controller.emit_lock:
                    self.controller.emit_event_learnt(self, 0, cid, "")
                del dev
                return
            with self.controller.emit_lock:
                self.controller.emit_event_learnt(
                    self, 0, cid, base64.b64encode(data).decode()
                )
            del dev
        except Exception as e:
            with self.controller.emit_lock:
                self.controller.emit_event_learnt(self, 0, cid, "")
                self.online_status(False)
            _log.debug("Problem whilst learning: {}".format(e))
            _log.exception(e)

    def update_device(self, device):
        """
        We overload this so we can update the IP address
        """
        self.ip_address = device.ip_address

        return self  # return updated self

    def start(self):
        if self.thread is None:
            self.thread = Thread(
                target=self._communication_thread, name="broadlink", daemon=True
            )
            self.thread.start()

    def die(self):
        self.queue.put_nowait(["Die", None])


class BroadlinkSensor(altolib.AltoEnvironSensor):
    """ Now this is a broadlink device
    """

    def __init__(
        self, controller: Agent, devid: str, dev_type: str, ip: str
    ) -> altolib.AltoDevice:
        super().__init__(controller, devid, 1)
        self.dev_type = dev_type
        self.ip_address = ip
        self.data_map.update(BROADLINKMAP)
        self.initialise_data("environment", BROADLINKMAP.keys())
        self.queue = Queue()
        self.thread = None

    def to_environment_temperature(self, val):
        return val

    def to_environment_humidity(self, val):
        return val

    def to_environment_luminosity_sub(self, val):
        if val.lower() == "unknown":
            return None
        return val

    def to_environment_noise_sub(self, val):
        if val.lower() == "unknown":
            return None
        return val

    def to_environment_air_quality_sub(self, val):
        if val.lower() == "unknown":
            return None
        return val

    def _communication_thread(self):
        while True:
            try:
                cmd = self.queue.get()
                self.queue.task_done()
                if cmd == "Die":
                    return
                if cmd == "Get":
                    self._get_data()
            except Exception as e:
                _log.debug(f"Sensor communication problem: {e}")

    def get_data(self):
        """
        Get the data for the device and send the info
        """
        self.queue.put_nowait("Get")

    def _get_data(self):
        """The tread to get the info
        """
        try:
            dev = broadlink.gendevice(
                self.dev_type,
                (self.ip_address, 80),
                "".join(self.device_id.split(":")),
            )
            dev.auth()
            sensor_data = dev.check_sensors()
            _log.debug(sensor_data)
            with self.controller.emit_lock:
                self.online_status(True)
                self.set_sensor_data(sensor_data)
        except Exception as e:
            _log.debug(f"Problem whilst sampling: {e}")
            _log.exception(e)
            with self.controller.emit_lock:
                self.online_status(False)

    def update_device(self, device):
        """
        We overload this so we can update the IP address
        """
        self.ip_address = device.ip_address
        return self  # return updated self

    def start(self):
        if self.thread is None:
            self.thread = Thread(
                target=self._communication_thread, name="broadlink", daemon=True
            )
            self.thread.start()

    def die(self):
        self.queue.put_nowait("Die")


def broadlinkagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Blremote
    :rtype: Blremote
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "broadlink")

    return Broadlink(topic, **kwargs)


class Broadlink(altolib.AltoDiscoverableAgent, altolib.AltoRemoteC, altolib.AltoSensor):
    """
    This is the agent for Broadlink devices. It supports remote control devices and sensors..
    """

    def __init__(self, topic="", **kwargs):
        super().__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.emit_lock = Lock()

    def emit_event_sent(
        self, dev, subdevice_idx: int, cid: str, result: bool
    ) -> None:
        """
        Send the 'sent' event.

        """

        topic = (
            self.topic + "remotec/" + self.agent_name + "/" + dev.device_id + "/sent"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "cid": cid,
            "sent": result,
            "type": "remotec" ## tbd
        }
        self.publish(topic, payload, "event")

    def start_discovery(self):
        _log.debug("Starting discovery")
        thread = Thread(target=self._discover_thread, name="broadlink", daemon=True)
        # thread.setDaemon(True)
        thread.start()

    def _discover_thread(self):
        try:
            _log.debug("Looking for devices")
            devs = broadlink.discover(timeout=5)
            _log.debug(f"Found {len(devs)} devices")
            for dev in devs:
                _log.debug(f"Found a {dev.type} coded {dev.devtype} at {dev.host}")
                if dev.type in SUPPORTEDREMOTETYPE + SUPPORTEDSENSORTYPE:
                    mac = "".join(format(x, "02x") for x in dev.mac)
                    mac = ":".join(
                        [mac[x] + mac[x + 1] for x in range(0, len(mac), 2)]
                    )
                    ip = dev.host[0]
                    if dev.type in SUPPORTEDSENSORTYPE:
                        newdev = BroadlinkSensor(self, mac, dev.devtype, ip)
                    else:
                        newdev = BroadlinkRemote(self, mac, dev.devtype, ip)
                    self.register_new_device(newdev)
                    self.device_list[newdev.device_id].start()
        except Exception as e:
            _log.debug(f"Error : Something went wrong with discovery. Error was: {e}")
            _log.exception(e)

    def send_samples(self):
        _log.debug("sending samples")
        for dev in self.device_list.values():
            if isinstance(dev, BroadlinkSensor):
                dev.get_data()

    def last_rites(self):
        for dev in self.device_list.values():
            dev.die()


def main():
    """Main method called to start the agent."""
    utils.vip_main(broadlinkagent, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
