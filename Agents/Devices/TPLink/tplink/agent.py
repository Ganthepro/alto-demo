"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import altolib
import logging
import sys
import json
from threading import Thread, Lock
from queue import Queue, Empty
from struct import pack
import socket
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"
DISCOVERY_TIMEOUT = 3
TPLINK_PORT = 9999
POLLFREQ = 5

TPLINKMAP = {"current": "current", "voltage": "voltage", "power": "power"}

# Encryption and Decryption of TP-Link Smart Home Protocol
# XOR Autokey Cipher with starting key = 171
def tplink_encrypt(request: str) -> bytearray:
    """
    Encrypt a request for a TP-Link Smart Home Device.
    :param request: plaintext request data
    :return: ciphertext request
    """
    key = 171

    plainbytes = request.encode()
    buffer = bytearray(pack(">I", len(plainbytes)))

    for plainbyte in plainbytes:
        cipherbyte = key ^ plainbyte
        key = cipherbyte
        buffer.append(cipherbyte)

    return bytes(buffer)


def tplink_decrypt(ciphertext: bytes) -> str:
    """
    Decrypt a response of a TP-Link Smart Home Device.
    :param ciphertext: encrypted response data
    :return: plaintext response
    """
    key = 171
    buffer = []

    for cipherbyte in ciphertext:
        plainbyte = key ^ cipherbyte
        key = cipherbyte
        buffer.append(plainbyte)

    plaintext = bytes(buffer)

    return plaintext.decode()


class TPPlug(altolib.AltoSwitchDevice, altolib.AltoElectricSensor):
    """
    This is the TPLink device
    """

    def __init__(self, controller, devid, ip_address, info):
        super().__init__(controller, devid, 2)
        # Now setup the map
        self.ip_address = ip_address
        self.info = info
        self.data_map.update(TPLINKMAP)
        self.initialise_data("electric", TPLINKMAP.keys())
        self.set_subdevice_name(0, "relay")
        self.set_subdevice_name(1, "led")
        self.queue = Queue()
        self.comm_stop = False
        self.comm_thread = Thread(target=self._poll_thread, name="tplink", daemon=True)
        self.comm_thread.start()

    def _poll_thread(self):
        while not self.comm_stop:
            to = True
            try:
                cmd = self.queue.get(block=True, timeout=POLLFREQ)
                to = False
                # _log.debug(f"\n\nGot {cmd} -> {self.dbg_cnt}")
            except Empty:
                cmd = "polling"
                # self.queue.put("energy")
                # _log.debug(f"\n\nGot nothing -> {self.dbg_cnt}")
            except Exception as e:
                _log.debug(f"ERROR: tplink thread queue problem: {e}")
                cmd = "skip"

            try:
                cmd = self.convert_command(cmd)
                if cmd:
                    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock_tcp.connect((self.ip_address, TPLINK_PORT))
                    sock_tcp.send(tplink_encrypt(cmd))
                    da = sock_tcp.recv(2048)
                    sock_tcp.close()
                    self._decode_json(tplink_decrypt(da[4:]))
            except Exception as e:
                _log.debug(f"ERROR: tplink thread failed: {e}")
            if not to:
                self.queue.task_done()
        _log.debug(f"Thread for {self.device_id}: This is the end, my friend.")

    def turn_on(self, subdev):
        if subdev in [0, "relay"]:
            self.queue.put("on")
        elif subdev in [1, "led"]:
            self.queue.put("led_on")

    def turn_off(self, subdev):
        if subdev in [0, "relay"]:
            self.queue.put("off")
        elif subdev in [1, "led"]:
            self.queue.put("led_off")

    def to_electric_current(self, val):
        return val

    def to_electric_voltage(self, val):
        return val

    def to_electric_power(self, val):
        return val

    def convert_command(self, cmd):
        commands = {
            "info": {"system": {"get_sysinfo": {}}},
            "status": {"system": {"get_sysinfo": {}}},
            "on": {"system": {"set_relay_state": {"state": 1}}},
            "off": {"system": {"set_relay_state": {"state": 0}}},
            "led_on": {"system": {"set_led_off": {"off": 0}}},
            "led_off": {"system": {"set_led_off": {"off": 1}}},
            "cloudinfo": {"cnCloud": {"get_info": {}}},
            "wlanscan": {"netif": {"get_scaninfo": {"refresh": 0}}},
            "time": {"time": {"get_time": {}}},
            "schedule": {"schedule": {"get_rules": {}}},
            "countdown": {"count_down": {"get_rules": {}}},
            "antitheft": {"anti_theft": {"get_rules": {}}},
            "reboot": {"system": {"reboot": {"delay": 1}}},
            "reset": {"system": {"reset": {"delay": 1}}},
            "energy": {"emeter": {"get_realtime": {}}},
            "polling": {"system": {"get_sysinfo": {}}, "emeter": {"get_realtime": {}}},
        }
        try:
            return json.dumps(commands[cmd])
        except:
            if cmd != "skip":
                _log.debug("Unknown command {}".format(cmd))
            return None

    def _decode_json(self, data):

        state = {}
        conve_json = json.loads(data)
        # _log.debug("Data received: {}".format(conve_json))
        try:
            if "system" in conve_json:
                self.name = str(conve_json["system"]["get_sysinfo"]["dev_name"])
                if str(conve_json["system"]["get_sysinfo"]["relay_state"]) == "0":
                    self.update_switch_state("relay", "off")
                elif str(conve_json["system"]["get_sysinfo"]["relay_state"]) == "1":
                    self.update_switch_state("relay", "on")
                if str(conve_json["system"]["get_sysinfo"]["led_off"]) == "0":
                    self.update_switch_state("led", "on")
                elif str(conve_json["system"]["get_sysinfo"]["led_off"]) == "1":
                    self.update_switch_state("led", "off")

            if "emeter" in conve_json:
                data = conve_json["emeter"]["get_realtime"]
                self.set_sensor_data(data, 0)

        except Exception as e:
            _log.debug(f"Error: could not decode message: {conve_json} {e}")


def tplink(config_path, **kwargs):
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
    kwargs["agent_name"] = config.get("agent_name", "tplink")

    return TPLink(topic, **kwargs)


class TPLink(altolib.AltoDiscoverableAgent, altolib.AltoSwitch, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        self.auto_send = False  # We update at high frequecy, let the agent manage
        self.discovery_lock = Lock()
        _log.debug("vip_identity: " + self.core.identity)

    def start_discovery(self):
        if not self.discovery_lock.locked():
            _log.debug("Starting discovery")
            thread = Thread(target=self._discover_thread, name="tplink", daemon=True)
            thread.start()
        else:
            _log.debug("Discovery in progress")

    def _discover_thread(self):
        with self.discovery_lock:
            DISCOVERY_QUERY = {
                "system": {"get_sysinfo": None},
                "emeter": {"get_realtime": None},
                "smartlife.iot.dimmer": {"get_dimmer_parameters": None},
                "smartlife.iot.common.emeter": {"get_realtime": None},
                "smartlife.iot.smartbulb.lightingservice": {"get_light_state": None},
            }
            target = "255.255.255.255"

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(DISCOVERY_TIMEOUT)

            req = json.dumps(DISCOVERY_QUERY)
            _log.debug(f"Sending discovery to {target}:{TPLINK_PORT}")

            encrypted_req = tplink_encrypt(req)
            for x in range(3):
                sock.sendto(encrypted_req[4:], (target, TPLINK_PORT))

            _log.debug(f"Waiting {DISCOVERY_TIMEOUT} seconds for responses...")

            try:
                while True:
                    data, addr = sock.recvfrom(4096)
                    ip, port = addr
                    info = json.loads(tplink_decrypt(data))
                    _log.debug(f"Got info {info}")
                    thisdev = info
                    try:
                        for key in ["system", "get_sysinfo", "model"]:
                            if key in thisdev:
                                thisdev = thisdev[key]
                        if not thisdev.startswith("HS"):
                            continue
                    except:
                        continue
                    mac = info["system"]["get_sysinfo"]["mac"].lower()
                    newdev = TPPlug(self, mac, ip, info)
                    self.register_new_device(newdev)
                    _log.debug(f"Got device at {ip}.")
            except socket.timeout:
                _log.debug("Got socket timeout, which is okay.")
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
    utils.vip_main(tplink, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
