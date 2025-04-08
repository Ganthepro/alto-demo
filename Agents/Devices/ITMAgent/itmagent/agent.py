"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import altolib
from altoutils.ITMlib import ITM
from threading import Thread, Lock
from queue import PriorityQueue, Queue
import sys
import gevent

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

def device_factory(devtype):
    if devtype == "itm_ac":
        return ITMAC
    if devtype == "itm_oau":
        return ITMOAUAC

ITMDEVICE = {
    "status_code": "status_code",
    "error_code": "error_code",
    "device_status": "device_status",
    "last_updated": "last_updated"
    }

class ITMAC(altolib.AltoHVACDevice, altolib.AltoDeviceSensor):

    def __init__(self, controller, devid, port, ac_addr, itm_handler):
        super().__init__(controller, devid, 1)
        self.port = port
        self.ac_addr = ac_addr
        self.capabilities = {
            "mode": ["off", "cool", "fan", "dry"],
            "set_temperature": [16.0, 32.0],
            "fan": ["auto", "high", "medium", "low"],
            "louver": ["swing", "position_0", "position_1", "position_2", "position_3", "position_4"],
            "room_temperature": [0.0, 100.0],
            "read_lock": True,
            "source": ["ac_remote", "c2d", "rl_correction", "rl_action", "web", "trivial"],
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
        self._itm_fcu = ITM.ITMFCU(self.port, self.ac_addr, itm_handler)
        self.datapoint_supported["device"] = [x for x in ITMDEVICE.keys()]
        self._sample_init()
        self._is_commanded = False
        self.was_updated = False

        self.last_source = "ac_remote"

    def _sample_init(self):
        self.data_map.update(ITMDEVICE)
        self.initialise_data("device", ITMDEVICE.keys())

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

    def command_set_all(self, all_command):
        pass

    def command_set_mode(self, mode):
        self._is_commanded = True
        on_off = "off"
        if mode != "off":
            on_off = "on"
        if mode == "off":
            ret = self._itm_fcu.set_on_off(mode)
        else:
            ret = self._itm_fcu.set_mode(mode)
        if not ret:
            return
        self.update_mode(mode, on_off)
        _log.debug(f"ITMAC command_set_mode: Success {self.port}:{self.ac_addr}")

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
        ret = self._itm_fcu.set_temperature(set_point=value)
        if not ret:
            return False
        self.update_set_temperature(value)
        _log.debug(f"ITMAC command_set_temperature: Success {self.port}:{self.ac_addr}")

    def command_set_fan(self, mode):
        self._is_commanded = True
        ret = self._itm_fcu.set_fan(mode)
        if not ret:
            return False
        self.update_fan(mode)
        _log.debug(f"ITMAC command_set_fan: Success {self.port}:{self.ac_addr}")
    
    def command_set_louver(self, mode):
        self._is_commanded = True
        ret = self._itm_fcu.set_fan_direction(mode)
        if not ret:
            return False
        self.update_fan_direction(mode)
        _log.debug(f"ITMAC command_set_fan_direction: Success {self.port}:{self.ac_addr}")
    
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
        ret = self._itm_fcu.get_status()
        if not ret:
            return
        self.update_status_code(ret["status"])
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
            ret = self._itm_fcu.get_status()
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


class ITMOAUAC(altolib.AltoHVACDevice, altolib.AltoDeviceSensor):

    def __init__(self, controller, devid, port, ac_addr, itm_handler):
        super().__init__(controller, devid, 1)
        self.port = port
        self.ac_addr = ac_addr
        self.capabilities = {
            "mode": ["off", "on"],
            "read_lock": True,
            "source": ["ac_remote", "c2d", "rl_correction", "rl_action", "web", "trivial"]
        }
        self.current_state[0]["hvac"] = {
            "on": False,
            "read_lock": [],
            "source": "ac_remote"
            }

        self._itm_oau = ITM.ITMOAU(self.port, self.ac_addr, itm_handler)
        self.datapoint_supported["device"] = [x for x in ITMDEVICE.keys()]
        self._sample_init()
        self._is_commanded = False
        self.was_updated = False

    def _sample_init(self):
        self.data_map.update(ITMDEVICE)
        self.initialise_data("device", ITMDEVICE.keys())
    
    @property
    def current_state_mode(self):
        if not self.current_state[0]["hvac"]["on"]:
            return "off"
        return "on"
    
    def command_set_mode(self, mode):
        self._is_commanded = True
        ret = self._itm_oau.set_mode(mode)
        if not ret:
            return False
        self.update_mode(mode)
        _log.debug(f"ITMOAUAC command_set_mode: Success {self.port}:{self.ac_addr}")
    
    def command_set_source(self, source):
        self.update_source(source)
    
    def update_source(self, value):
        res = self._update_generic("source", value)
    
    def to_schema(self, prop, value):
        return value

    def update_mode(self, mode):
        if mode == "on":
            res = self._update_generic("on", True)
            if res:
                self.was_updated = True
        else:
            res = self._update_generic("on", False)
            if res:
                self.was_updated = True

    def update_state(self):
        if not self._is_commanded:
            ret = self._itm_oau.get_status()
            self.update_mode(ret["on_off"])
            self.emit_event_state()
        else:
            self._is_commanded = False
    
    def get_data(self):
        ret = self._itm_oau.get_status()
        if not ret:
            return
        self.update_status_code(ret["status"])
        self.update_error_code(ret["malfunction_code"])

    def update_error_code(self, value):
        self.set_sensor_data({"error_code": value}, subdevice=0, sensor_type="device")
        
    def update_status_code(self, value):
        if value == 'normal':
            self.set_sensor_data({
                "status_code": value,
                "device_status": "online"
                }, 
                subdevice=0, 
                sensor_type="device")
        else:
            self.set_sensor_data({
                "status_code": value,
                "device_status": "offline"
                },
                subdevice=0, 
                sensor_type="device")
    
    def force_emit_state(self):
        pass

    def emit_event_state(self, val=None):
        if self.was_updated:
            self.was_updated = False
            self.controller.emit_event_state(self.device_id)
            self.update_source("ac_remote")
    
    def get_device_status(self):
        state = self.current_state[0]['sensor']['device']['status_code']
        if state == 'normal':
            return True
        return False

def itmagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Itmagent
    :rtype: Itmagent
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
        "itm_credential",
        "itm_ip",
        "itm_port",
        "devices",
        "default_timezone"
    ],["itm", 60, {}, "", "", {}, "Asia/Bangkok"]):
        kwargs[x] = config.get(x, y)

    return Itmagent(topic, **kwargs)


class Itmagent(altolib.AltoBridgeAgent, altolib.AltoHVAC, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Itmagent, self).__init__(topic, **kwargs)
        self._sampling_rate_cd = 15
        self.auto_send =True
        self.sample_lock = {}

        self.itm_handler = None
        self.use_cmd_set_all = False # pls update this flag from config file
        _log.debug("vip_identity: " + self.core.identity)

    def _build_device(self, dev_type, dev_id, ac_port, ac_addr):
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, ac_port, ac_addr, self.itm_handler)
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
        self.itm_handler = ITM.ITMHandler(self.itm_credential["username"],
                                        self.itm_credential["password"],
                                        self.itm_ip,
                                        self.itm_port)
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, v[1], v[2])

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

        if len(topic) != 2:
            raise altolib.AltoSchemaError("HVAC command handler cannot parse topic")

        devid, func = topic
        # if func == "set":
        if func == "command":
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev != 0:
                _log.warning(f"HVAC subdevice_idx can be 0 only")
                return
            targetdev = self.device_list[devid]
            donotify = False
            _log.debug(f'''handle command hvac message {message}''')
            pre_command = {}
            for prop in targetdev.capabilities.keys():
                if prop in message:
                    pre_command[prop] = message[prop]
            targetdev.command_set_all(pre_command)
            # targetdev.command_was_sent()
            if donotify:
                _log.debug("handle command hvac donotify")
                self.emit_event_state(devid)
        else:
            _log.warning(f"HVAC cannot handle command {func}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(itmagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
    