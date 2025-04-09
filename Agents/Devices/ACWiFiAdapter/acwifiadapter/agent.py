"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import altolib
from threading import Thread, Lock
from queue import PriorityQueue, Queue
import gevent

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic

import requests
import json

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class DaikinWiFiAdapterHandler:

    def __init__(self, ip_addr):
        self._ip_addr = ip_addr

    def get_status(self):
        try:
            r_control_info = requests.get(("http://" + self._ip_addr + "/aircon/get_control_info"), timeout=9)
            r_json = r_control_info.json()
            _log.debug(f"status {r_control_info.status_code} {r_json}")

            r_sensor_info = requests.get(("http://" + self._ip_addr + "/aircon/get_sensor_info"), timeout=9)
            rs_json = r_sensor_info.json()
            _log.debug(f"status {r_sensor_info.status_code} {rs_json}")

            if r_control_info.status_code == 200 and r_sensor_info.status_code == 200:
                if r_json["ret"] == "OK" and rs_json["ret"] == "OK":
                    ret = {}
                    m_map = {
                        "auto": "A",
                        "high": "7",
                        "medium": "5",
                        "low": "3"
                    }
                    m_map_swap = dict([(value, key) for key, value in m_map.items()])
                    ret["fan_speed"] = m_map_swap[str(r_json["param"]["f_rate"])]
                    m_map = {
                        "swing": "0",
                        "position_0": "1",
                        "position_1": "2",
                        "position_2": "3",
                        "position_3": "4",
                        "position_4": "5"
                    }
                    m_map_swap = dict([(value, key) for key, value in m_map.items()])
                    ret["fan_direction"] = m_map_swap[str(r_json["param"]["f_dir"])]
                    ret["set_temp"] = int(r_json["param"]["stemp"])
                    m_map = {
                        "cool": "1",
                        "fan": "0",
                        "dry": "2"
                    }
                    m_map_swap = dict([(value, key) for key, value in m_map.items()])
                    ret["operation_mode"] = m_map_swap[str(r_json["param"]["mode"])]
                    m_map = {
                        "on": "1",
                        "off": "0",
                    }
                    m_map_swap = dict([(value, key) for key, value in m_map.items()])
                    ret["on_off"] = m_map_swap[str(r_json["param"]["pow"])]
                    ret["alert"] = str(r_json["param"]["alert"])

                    ret["room_temp"] = round(float(rs_json["param"]["htemp"]), 2)
                    ret["ambient_temp"] = round(float(rs_json["param"]["otemp"]), 2)
                    ret["malfunction_code"] = rs_json["param"]["err"]
                    return ret

        except Exception as er:
            _log.error(f"DaikinWiFiAdapterHandler get_status error {er}")

        return None

    def set_on_off(self, mode):
        m_map = {
            "on": "1",
            "off": "0",
        }
        if not mode in m_map:
            return False

        try:
            r_control_info = requests.get((f"http://{self._ip_addr}/aircon/set_control_info?pow={m_map[mode]}"), timeout=9)
            r_json = r_control_info.json()
            _log.debug(f"set_on_off status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            _log.error(f"DaikinWiFiAdapterHandler set_on_off error {er}")
        
        return False

    def set_mode(self, mode):
        m_map = {
            "cool": "1",
            "fan": "0",
            "dry": "2"
        }
        if not mode in m_map:
            return False

        try:
            r_control_info = requests.get((f"http://{self._ip_addr}/aircon/set_control_info?mode={m_map[mode]}"), timeout=9)
            r_json = r_control_info.json()
            _log.debug(f"set_mode status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            _log.error(f"DaikinWiFiAdapterHandler set_mode error {er}")
        
        return False
    
    def set_fan(self, mode):
        m_map = {
            "auto": "A",
            "high": "7",
            "medium": "5",
            "low": "3"
        }
        if not mode in m_map:
            return False

        try:
            r_control_info = requests.get((f"http://{self._ip_addr}/aircon/set_control_info?f_rate={m_map[mode]}"), timeout=9)
            r_json = r_control_info.json()
            _log.debug(f"set_fan status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            _log.error(f"DaikinWiFiAdapterHandler set_fan error {er}")
        
        return False
    
    def set_fan_direction(self, mode):
        "swing", "position_0", "position_1", "position_2", "position_3", "position_4"
        m_map = {
            "swing": "0",
            "position_0": "1",
            "position_1": "2",
            "position_2": "3",
            "position_3": "4",
            "position_4": "5"
        }
        if not mode in m_map:
            return False

        try:
            r_control_info = requests.get((f"http://{self._ip_addr}/aircon/set_control_info?f_dir={m_map[mode]}"), timeout=9)
            r_json = r_control_info.json()
            _log.debug(f"set_fan_direction status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            _log.error(f"DaikinWiFiAdapterHandler set_fan_direction error {er}")
        
        return False
    
    def set_temperature(self, set_point):
        set_point = int(set_point)
        if set_point < 18 or set_point > 32:
            return False

        try:
            r_control_info = requests.get((f"http://{self._ip_addr}/aircon/set_control_info?stemp={set_point}"), timeout=9)
            r_json = r_control_info.json()
            _log.debug(f"set_temperature {set_point} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            _log.error(f"DaikinWiFiAdapterHandler set_temperature error {er}")


def device_factory(devtype):
    if devtype == "daikin_wifi_adapter":
        return DaikinWiFiAdapter
    
    raise Exception(f"Unknown device type {devtype}")


DAIKIN_WIFI_ADAPTER_DEVICE = {
    "status_code": "status_code",
    "error_code": "error_code",
    "device_status": "device_status",
    "last_updated": "last_updated"
}

class DaikinWiFiAdapter(altolib.AltoHVACDevice, altolib.AltoDeviceSensor):

    def __init__(self, controller, devid, ac_addr):
        super().__init__(controller, devid, 1)
        self._ac_addr = ac_addr
        self.capabilities = {
            "mode": ["off", "cool", "fan", "dry"],
            "set_temperature": [16.0, 32.0],
            "fan": ["auto", "high", "medium", "low"],
            "louver": ["swing", "position_0", "position_1", "position_2", "position_3", "position_4"],
            "room_temperature": [0.0, 100.0],
            "read_lock": True,
            "source": ["ac_remote", "c2d", "rl_correction", "rl_action", "web", "trivial", "automation"],
            "update_type": ["normal", "force"],
        }
        self.current_state[0]["hvac"] = {
            "on": False,
            "oper": "cool",
            "set_temperature": 25.0,
            "room_temperature": 25.0,
            "fan": "auto",
            "louver": "swing",
            "read_lock": [],
            "source": "ac_remote",
            "update_type": "normal",
        }

        self._daikin_wifi_adapter_handler = DaikinWiFiAdapterHandler(self._ac_addr)
        self.datapoint_supported["device"] = [x for x in DAIKIN_WIFI_ADAPTER_DEVICE.keys()]
        self._sample_init()
        self._is_commanded = False
        self.was_updated = False

        self.last_source = "ac_remote"

    def _sample_init(self):
        self.data_map.update(DAIKIN_WIFI_ADAPTER_DEVICE)
        self.initialise_data("device", DAIKIN_WIFI_ADAPTER_DEVICE.keys())

    @property
    def current_state_mode(self):
        if not self.current_state[0]["hvac"]["on"]:
            return "off"
        return self.current_state[0]["hvac"]["oper"]

    @property
    def current_state_fan(self):
        return self.current_state[0]["hvac"]["fan"]

    @property
    def current_state_louver(self):
        return self.current_state[0]["hvac"]["louver"]
    
    @property
    def current_state_set_temperature(self):
        return self.current_state[0]["hvac"]["set_temperature"]
    
    @property
    def current_state_room_temperature(self):
        return self.current_state[0]["hvac"]["room_temperature"]
    
    @property
    def current_state_update_type(self):
        return self.current_state[0]["hvac"]["update_type"]
    
    def to_schema(self, prop, value):
        return value

    def command_set_mode(self, mode):
        self._is_commanded = True
        on_off = "off"
        if mode != "off":
            on_off = "on"
        if mode == "off":
            ret = self._daikin_wifi_adapter_handler.set_on_off(mode)
        else:
            ret = self._daikin_wifi_adapter_handler.set_on_off("on")
            gevent.sleep(0.3)
            ret = self._daikin_wifi_adapter_handler.set_mode(mode)
        if not ret:
            return
        self.update_mode(mode, on_off)
        _log.debug(f"DaikinWiFiAdapter command_set_mode: Success {self._ac_addr}")

    def _command_set_set_temperature(self, temp) -> None:
        """
        Set the temperature. Make sure it is valid and is not locked.
        We are not using _command_set_generic because the testes are differents
        """
        if "set_temperature" not in self.capabilities:
            _log.error("Mode is not supported.")

        if (
            temp < self.capabilities["set_temperature"][0]
            or temp > self.capabilities["set_temperature"][1]
        ):
            _log.error(
                f"Set temperature {temp} is out of range. Must be between {self.capabilities['set_temperature'][0]} and {self.capabilities['set_temperature'][1]}."
            )

        if (
            "lock" in self.capabilities
            and "set_temperature" in self.current_hvac_state["lock"]
        ):
            if (
                temp < self.current_hvac_state["lock"]["set_temperature"][0]
                and temp > self.current_hvac_state["lock"]["set_temperature"][1]
            ):
                _log.warning(f"Set temperature is locked and cannot be set to {temp}")

        try:
            self.command_set_set_temperature(temp)
        except Exception as e:
            _log.error("Could not set temperature")
            _log.exception(e)

    def command_set_set_temperature(self, value):
        self._is_commanded = True
        ret = self._daikin_wifi_adapter_handler.set_temperature(set_point=value)
        if not ret:
            return False
        self.update_set_temperature(value)
        _log.debug(f"DaikinWiFiAdapter command_set_temperature: Success {self._ac_addr}")

    def command_set_fan(self, mode):
        self._is_commanded = True
        ret = self._daikin_wifi_adapter_handler.set_fan(mode)
        if not ret:
            return False
        self.update_fan(mode)
        _log.debug(f"DaikinWiFiAdapter command_set_fan: Success {self._ac_addr}")
    
    def command_set_louver(self, mode):
        self._is_commanded = True
        ret = self._daikin_wifi_adapter_handler.set_fan_direction(mode)
        if not ret:
            return False
        self.update_fan_direction(mode)
        _log.debug(f"DaikinWiFiAdapter command_set_fan_direction: Success {self._ac_addr}")
    
    def command_set_source(self, source):
        self.update_source(source)
    
    def update_source(self, value):
        res = self._update_generic("source", value)
        
    def update_mode(self, mode_oper, mode_on_off):
        if mode_on_off == "on":
            res = self._update_generic("on", True)
            if res:
                self.was_updated = True
        else:
            res = self._update_generic("on", False)
            if res:
                self.was_updated = True
        res_oper = self._update_generic("oper", mode_oper)
        if res_oper:
            self.was_updated = True
    
    def update_set_temperature(self, value):
        res = self._update_generic("set_temperature", value)
        if res:
            self.was_updated = True

    def update_room_temperature(self, value):
        if value < self.capabilities['room_temperature'][0] or value > self.capabilities['room_temperature'][1]:
            return
        res = self._update_generic("room_temperature", value)
    
    def update_fan(self, mode):
        res = self._update_generic("fan", mode)
        if res:
            self.was_updated = True

    def update_fan_direction(self, mode):
        res = self._update_generic("louver", mode)
    
    def update_status_code(self, value):
        if value == 'normal':
            self.set_sensor_data({
                "status_code": value,
                "device_status": "online"
                },
                subdevice=0,
                sensor_type="device"
                )
        else:
            self.set_sensor_data({
                "status_code": value,
                "device_status": "offline"
                },
                subdevice=0,
                sensor_type="device"
                )
    
    def update_error_code(self, value):
        self.set_sensor_data({"error_code": value}, subdevice=0, sensor_type="device")

    def get_data(self):
        ret = self._daikin_wifi_adapter_handler.get_status()
        if not ret:
            self.update_status_code("unnormal")
            return
        self.update_status_code("normal")
        self.update_error_code(ret["malfunction_code"])

    def to_environment_room_temperature(self, val):
        return val

    def force_emit_state(self):
        res = self._update_generic("update_type", "force")
        self.update_source(self.last_source)
        self.controller.emit_event_state(self.device_id)
        res = self._update_generic("update_type", "normal")
        self.update_source("ac_remote")
    
    def update_state(self):
        if not self._is_commanded:
            ret = self._daikin_wifi_adapter_handler.get_status()
            self.update_mode(ret["operation_mode"], ret["on_off"])
            self.update_fan(ret["fan_speed"])
            self.update_fan_direction(ret["fan_direction"])
            self.update_set_temperature(ret["set_temp"])
            self.update_room_temperature(ret["room_temp"])
            self.emit_event_state()
        else:
            self._is_commanded = False
    
    def emit_event_state(self, val=None):
        if self.was_updated:
            self.last_source = self.current_state[0]["hvac"]["source"]
            self.was_updated = False
            self.controller.emit_event_state(self.device_id)
            self.update_source("ac_remote")
    
    def get_device_status(self):
        state = self.current_state[0]['sensor']['device']['status_code']
        if state == 'normal':
            return True
        return False


def acwifiadapter(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Acwifiadapter
    :rtype: Acwifiadapter
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip([
        "agent_name",
        "sampling_rate",
        "devices",
        "default_timezone"
    ],["ac_wifi_adapter", 60, {}, "Asia/Bangkok"]):
        kwargs[x] = config.get(x, y)

    return Acwifiadapter(topic, **kwargs)


class Acwifiadapter(altolib.AltoBridgeAgent, altolib.AltoHVAC, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Acwifiadapter, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

        self.use_cmd_set_all = False

    def _build_device(self, dev_type, dev_id, ac_addr):
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, ac_addr)
            self.register_new_device(newdev)
        
    def send_samples(self):
        _log.debug("sending samples")
        for dev in self.device_list.values():
            dev.get_data()

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """

        super().configure(config_name, action, contents)

        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, v[1])

    # def _create_subscriptions(self, topic):
    #     """
    #     Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
    #     the _handle_publish callback
    #     """
    #     self.vip.pubsub.unsubscribe("pubsub", None, None)

    #     self.vip.pubsub.subscribe(peer='pubsub',
    #                               prefix=topic,
    #                               callback=self._handle_publish)

    @Core.schedule(periodic(60))
    def poll_state(self):
        _log.debug("poll_state")
        for adev in self.device_list.values():
            try:
                adev.update_state()
            except Exception as e:
                _log.error(f"poll_state: {e}")
                etype, value, traceback = sys.exc_info()
                _log.error(f"{etype} {value} {traceback}")
    
    @Core.schedule(periodic(300))
    def force_emit_state(self):
        _log.debug("force_emit_state")
        for adev in self.device_list.values():
            try:
                adev.force_emit_state()
            except Exception as e:
                _log.error(f"force_emit_state: {e}")
                etype, value, traceback = sys.exc_info()
                _log.error(f"{etype} {value} {traceback}")
    
    @RPC.export
    def get_device_status(self):
        status_list = []
        for dev, instance in self.device_list.items():
            status_list.append({dev: instance.get_device_status()})
        return status_list

    def handle_command_hvac(self, topic, message):
        """
             Handle the commands meant for the hvac schema. Essentially the 'ac' command.
        """

        if not self.use_cmd_set_all: # if false using old hvac handle
            super().handle_command_hvac(topic, message)
            
            devid, func = topic
            if func == "command":
                if "device_id" in message:
                    devid = message["device_id"]
                targetdev = self.device_list[devid]
                targetdev.emit_event_state()
            return


def main():
    """Main method called to start the agent."""
    utils.vip_main(acwifiadapter, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
