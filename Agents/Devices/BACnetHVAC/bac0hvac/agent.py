"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

from distutils import command
from itertools import count
import re
import BAC0
import logging
import sys
import time
import altolib
from threading import Thread, Lock
from time import sleep
from typing import Any, List, Mapping, Union, Callable, Optional
from queue import PriorityQueue, Queue
from random import randint

from gevent.lock import BoundedSemaphore

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Core
from volttron.platform.scheduling import periodic
from bacpypes.pdu import PDU, Address
from bacpypes.bvll import BVLPDU, bvl_pdu_types
from bacpypes.npdu import NPDU
from bacpypes.apdu import APDU, apdu_types, unconfirmed_request_types
from socket import socket, AF_INET, SOCK_DGRAM

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

bounded_sem = BoundedSemaphore(1)

CARRIERMAP = {"temperature": "temperature"}
CHENSENMAP = {"temperature": "temperature"}
DAIKINDBACSMAP = {"temperature": "temperature"}
# DAIKINDBACSMAP = {
#     "temperature": "temperature",
#     "room_temperature": "room_temperature"
# }
RPRIORITY = 10
WPRIORITY = 5


def device_factory(devtype):
    if devtype == "fast_carrier":
        return FastCarrierAC
    if devtype == "carrier":
        return CarrierAC
    if devtype == "chensen":
        return ChenSen
    if devtype == "daikinDBACS":
        return DaikinDBACS
    raise Exception(f"Unknown device type {devtype}")


class FastCarrierAC(altolib.AltoHVACDevice, altolib.AltoEnvironSensor):
    """
    Defines a single AC unit behing a Carrier BACnet bridge
    """

    def __init__(self, controller, devid, ip, unit):
        """
        Here devid is of the form <ip address>:<unit>
        """
        super().__init__(controller, devid, 1)
        # Now setup the map
        self.ip_address = ip
        self.unit = int(unit)
        self.data_map.update(CARRIERMAP)
        self.initialise_data("environment", CARRIERMAP.keys())
        self.capabilities = {
            "mode": ["off", "cool", "fan", "dry"],
            "temperature": [18.0, 29.0, 1.0],  # Min, Max, Increment
            "set_temperature": [18.0, 29.0, 1.0],  # Min, Max, Increment
            # "fan": ["auto", "high", "median", "low", "off"],
            "fan": ["auto", "high", "medium", "low", "off"],
            # "lock": True,
            "read_lock": True,
            "alarm": ["filter", "device"],
            # "env_temperature": 25.0,
            "room_temperature": 25.0,
            "source": ["ac_remote", "web", "c2d", "rl_action", "trivial", "rl_correction"],
            "event_status": ["success", "pending", "failed"],
            "total_waiting_command": 0,
            "update_type": ["normal", "force"],
        }
        self.current_state[0]["hvac"] = {
            "on": False,
            "oper": "cool",
            "temperature": 25.0,
            "set_temperature": 25.0,
            "fan": "off",
            "flow": "off",
            # "lock": {},
            "read_lock": [],
            "alert": False,
            "filter": False,
            "alert_code": 1,
            # "env_temperature": 25.0,
            "room_temperature": 25.0,
            "source": "ac_remote",
            "event_status": "success",
            "total_waiting_command": 0,
            "update_type": "normal",
        }
        self.unit_zero = 2
        self.unit_offset = 256
        self.output_offset = 128
        self.prop_defs = {}
        self.prop_defs["alert_code"] = (-1, "multiState", False)  # False is read-only
        self.prop_defs["on"] = (0, "binary", True)  # True is Read/write
        self.prop_defs["oper"] = (1, "multiState", True)
        # self.prop_defs["temperature"] = (2, "analog", True)
        self.prop_defs["set_temperature"] = (2, "analog", True)
        self.prop_defs["fan"] = (3, "multiState", True)
        self.prop_defs["flow"] = (5, "multiState", True)
        # self.prop_defs["env_temperature"] = (6, "analog", False)
        self.prop_defs["room_temperature"] = (6, "analog", False)
        # self.prop_defs["lock"] = (7, "multiState", True)
        self.prop_defs["filter"] = (18, "binary", True)
        self.prop_defs["alert"] = (62, "binary", False)
        self.was_updated = False
        self.is_normal_updated = False
        
        self.sec_cdown = 0
        self.sec_cnt = lambda: randint(2, 3)  # Spread around
        self.ter_cdown = randint(0, 30)  # Spread around
        self.ter_cnt = lambda: randint(2, 3)  # Spread around

        self.command_queue = Queue()
        self.last_command_queue_size = self.command_queue.qsize()
        self.last_command = {}

        self._current_read_part = 0 # 0 need send part 1, 1 nothing, 2 need send part 2, 3 nothing
        self.read_part_timestamp = 0

        self.emit_event_count = 0

    def send_read_command(self):
        if self.command_queue.empty() and not self.last_command and time.time() - self.read_part_timestamp > 5:
            if self._current_read_part == 0:
                self.read_part_timestamp = time.time()
                self.send_read_part(send_part=0)
                self._current_read_part = 1
                _log.debug(f"FastCarrierAC send_read_command {self.device_id} {self._current_read_part}")
            elif self._current_read_part == 2:
                self.read_part_timestamp = time.time()
                self.send_read_part(send_part=1)
                self._current_read_part = 3
                _log.debug(f"FastCarrierAC send_read_command {self.device_id} {self._current_read_part}")

    @property
    def current_read_part(self):
        return self._current_read_part

    @current_read_part.setter
    def current_read_part(self, val):
        self._current_read_part = val # val = 0 for reset

    def immediate_notice_event(self, data):
        pre_command = {}
        for k, v in data.items():
            pre_command[k] = v

        # if not all(kn in data for kn in ["mode", "temperature", "fan", "source"]) and False:
        if not all(kn in data for kn in ["mode", "temperature", "set_temperature", "fan", "source"]) and False:
            return
        if "mode" in data:
            if data["mode"] not in ["off", "cool", "fan", "dry"]:
                return

        if "fan" in data:
            # if data["fan"] not in ["auto", "high", "median", "low"]:
            if data["fan"] not in ["auto", "high", "medium", "low"]:
                return
        if "temperature" in data:
            if data["temperature"] < 18.0:
                data["temperature"] = 18.0
                pre_command["temperature"] = 18.0
            if data["temperature"] > 29.0:
                data["temperature"] = 29.0
                pre_command["temperature"] = 29.0
        if "set_temperature" in data:
            if data["set_temperature"] < 18.0:
                data["set_temperature"] = 18.0
                pre_command["set_temperature"] = 18.0
            if data["set_temperature"] > 29.0:
                data["set_temperature"] = 29.0
                pre_command["set_temperature"] = 29.0
        
        res = self._update_generic("event_status", "pending")
        res = self._update_generic("total_waiting_command", self.last_command_queue_size + 1)
        self.controller.emit_last_command(self.device_id, data) # do emit_event_state first time for pending status
        
        self.add_to_command_queue(pre_command)
        self.last_command_queue_size = self.command_queue.qsize()

    def add_to_command_queue(self, data):
        try:
            self.command_queue.put_nowait(data)
        except Exception as e:
            _log.debug(f"FastCarrierAC put command_queue {e}")

    def execute_command_queue(self):
        if not self.command_queue.empty() and not self.last_command and time.time() - self.read_part_timestamp > 5:
            data = self.command_queue.get()
            self.last_command_queue_size = self.command_queue.qsize()
            res = self._update_generic("total_waiting_command", self.last_command_queue_size)
            if "mode" in data:
                on_oper = {}
                if data["mode"] == "off":
                    on_oper = {
                        "on": False
                    }
                else:
                    on_oper = {
                        "on": False,
                        "oper": "cool"
                    }
                data.update(on_oper)
            self.last_command["set_to"] = {}
            self.last_command["is_write"] = {}
            self.last_command["is_read"] = {}
            self.last_command["is_recv"] = {}
            self.last_command["cov_timeout"] = {}
            self.last_command["read_timeout"] = {}
            self.last_command["is_success"] = {}
            for k, v in data.items():
                if k == "source":
                    self.last_command["set_to"][k] = v
                    self.last_command["is_write"][k] = True
                    self.last_command["is_read"][k] = True
                    self.last_command["is_recv"][k] = True
                    self.last_command["cov_timeout"][k] = 0
                    self.last_command["read_timeout"][k] = 0
                    self.last_command["is_success"][k] = True

                    getattr(self, "_command_set_" + k)(v)
                else:
                    self.last_command["set_to"][k] = v
                    self.last_command["is_write"][k] = False
                    self.last_command["is_read"][k] = False
                    self.last_command["is_recv"][k] = False
                    self.last_command["cov_timeout"][k] = 0
                    self.last_command["read_timeout"][k] = 0
                    self.last_command["is_success"][k] = False

        if self.last_command:
            _log.debug(f"FastCarrierAC {self.device_id} last_command {self.last_command}")
            for k, v in self.last_command["set_to"].items():
                if not self.last_command["is_write"][k]:
                    if k not in ["on", "oper"]:
                        getattr(self, "_command_set_" + k)(v)
                    self.last_command["is_write"][k] = True

            for k, v in self.last_command["cov_timeout"].items():
                if self.last_command["is_write"][k] and not self.last_command["is_recv"][k]:
                    self.last_command["cov_timeout"][k] += 1
                    if self.last_command["cov_timeout"][k] >= 12:
                        self.last_command["cov_timeout"][k] = 12
                        if not self.last_command["is_read"][k]:
                            if k != "mode":
                                # activate bac0.read
                                prop = k
                                if prop in ["on", "oper"]:
                                    ino, outo, dtype = self.registers(prop)
                                    cb = self.update_mode
                                    self.controller.send(
                                        f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                                    )
                                # if prop in ["temperature", "fan"]:
                                if prop in ["set_temperature", "fan"]:
                                    ino, outo, dtype = self.registers(prop)
                                    cb = getattr(self, "update_" + prop)
                                    self.controller.send(
                                        f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                                    )
                            self.last_command["is_read"][k] = True

            read_timeout = False # one of reading timeout
            for k, v in self.last_command["read_timeout"].items():
                if self.last_command["is_read"][k] and not self.last_command["is_recv"][k]:
                    self.last_command["read_timeout"][k] += 1
                    if self.last_command["read_timeout"][k] >= 15:
                        self.last_command["read_timeout"][k] = 15
                        read_timeout = True
            if read_timeout:
                _log.debug(f"FastCarrierAC {self.device_id} read timeout")
                if "on" in self.last_command["is_success"]:
                    del self.last_command["is_success"]["on"]
                if "oper" in self.last_command["is_success"]:
                    del self.last_command["is_success"]["oper"]
                if "source" in self.last_command["set_to"]:
                    self.command_set_source(self.last_command["set_to"]["source"])
                    # self.command_set_source("ac_remote") # force source for test
                for k, v in self.last_command["is_success"].items():
                    self.last_command["is_success"][k] = False
                    if self.last_command["set_to"][k] == getattr(self, "current_state_" + k):
                        self.last_command["is_success"][k] = True
                
                _log.debug(f"FastCarrierAC {self.device_id} final state")
                # prepare message for noti
                noti_msg = ""
                for k, v in self.last_command["is_success"].items():
                    if not v:
                        noti_msg += f"Set {k} to {v} failed\n"
                if noti_msg:
                    _log.debug(f"FastCarrierAC {self.device_id} noti {noti_msg}") # send noti to line
                    res = self._update_generic("event_status", "failed")
                    self.emit_event_state() # do emit_event_state for success
                else:
                    _log.debug(f"FastCarrierAC {self.device_id} no noti {noti_msg}") # send noti to line
                    res = self._update_generic("event_status", "success")
                    self.emit_event_state() # do emit_event_state for success

                # clear last command for starting new command_queue
                _log.debug(f"FastCarrierAC read timeout {self.device_id} last_command {self.last_command}")
                self.last_command = {}
                res = self._update_generic("event_status", "success") # set default to success for event from remote
                return
            
            is_recv_all = True
            for k, v in self.last_command["is_recv"].items():
                if k == "mode":
                    if self.last_command["set_to"][k] == "off":
                        if self.last_command["is_recv"]["on"]:
                            self.last_command["is_recv"]["mode"] = True
                            v = True
                    else:
                        if self.last_command["is_recv"]["on"] and self.last_command["is_recv"]["oper"]:
                            self.last_command["is_recv"]["mode"] = True
                            v = True
                if not v:
                    is_recv_all = False
            if "on" in self.last_command["is_success"]:
                del self.last_command["is_success"]["on"]
            if "oper" in self.last_command["is_success"]:
                del self.last_command["is_success"]["oper"]
            if is_recv_all:
                if "source" in self.last_command["set_to"]:
                    self.command_set_source(self.last_command["set_to"]["source"])
                    # self.command_set_source("ac_remote") # force source for test
                for k, v in self.last_command["is_success"].items():
                    self.last_command["is_success"][k] = False
                    if self.last_command["set_to"][k] == getattr(self, "current_state_" + k):
                        self.last_command["is_success"][k] = True
                
                _log.debug(f"FastCarrierAC {self.device_id} final state")
                # prepare message for noti
                noti_msg = ""
                for k, v in self.last_command["is_success"].items():
                    if not v:
                        noti_msg += f"Set {k} to {v} failed\n"
                if noti_msg:
                    _log.debug(f"FastCarrierAC {self.device_id} noti {noti_msg}") # send noti to line
                    res = self._update_generic("event_status", "failed")
                    self.emit_event_state() # do emit_event_state for success
                else:
                    _log.debug(f"FastCarrierAC {self.device_id} no noti {noti_msg}") # send noti to line
                    res = self._update_generic("event_status", "success")
                    self.emit_event_state() # do emit_event_state for success

                # clear last command for starting new command_queue
                _log.debug(f"FastCarrierAC is_recv_all {self.device_id} last_command {self.last_command}")
                self.last_command = {}
                res = self._update_generic("event_status", "success") # set default to success for event from remote
    
    def update_last_command_is_recv(self, prop):
        if self.last_command:
            if prop in self.last_command["is_recv"]:
                self.last_command["is_recv"][prop] = True
        
    def registers(self, prop):
        in_off = self.unit_zero + self.unit * self.unit_offset
        reg, dtype, rw = self.prop_defs[prop]
        in_off += reg
        out_off = (in_off + self.output_offset) if rw else False
        return (in_off, out_off, dtype)

    @property
    def current_state_mode(self):
        if not self.current_state[0]["hvac"]["on"]:
            return "off"
        return self.current_state[0]["hvac"]["oper"]

    @property
    def current_state_alarm(self):
        res = {}
        if self.current_state[0]["hvac"]["filter"]:
            res["filter"] = {
                "level": "maintenance",
                "msg": "Filter needs cleaning/replacement",
            }

        if self.current_state[0]["hvac"]["alert"]:
            res["device"] = {
                "level": "warning",
                "msg": f"Error code is {self.current_state[0]['hvac']['alert_code']}",
            }
        if res:
            return res
        return False

    def to_schema(self, prop, value):
        """
        Translate values from the device into schema defined values
        """

        if prop == "mode":
            if value in ["active", "inactive"]:
                if value == "inactive":
                    return "off"
                return self.current_state[0]["hvac"]["oper"]
            return value[:4]
        if prop == "fan":
            # return ["", "", "auto", "high", "median", "low", "off"][int(value)]
            return ["", "", "auto", "high", "medium", "low", "off"][int(value)]

        if prop == "filter":
            return value == "active"

        if prop == "alert":
            return value == "active"

        if prop == "lock": # after we have set_temperature, lock is not support
            lattr = []
            if value == 2:
                lattr = ["mode"]
            elif value == 3:
                lattr = ["temperature"]
            elif value == 4:
                lattr = ["on"]
            elif value == 5:
                lattr = ["mode", "temperature"]
            elif value == 6:
                lattr = ["mode", "on"]
            elif value == 7:
                lattr = ["temperature", "on"]
            elif value == 8:
                lattr = ["mode", "temperature", "on"]
            res = {}
            if "temperature" in lattr:
                res["temperature"] = [self.current_state[0]["hvac"]["temperature"]] * 2
            if "on" in lattr:
                if "mode" in lattr:
                    res["mode"] = []
                else:
                    if self.current_state[0]["hvac"]["on"]:
                        res["mode"] = ["cool", "fan", "dry"]
                    else:
                        res["mode"] = []
            elif "mode" in lattr:
                res["mode"] = ["off", self.current_state[0]["hvac"]["oper"]]

            return res
        return value

    def _update_generic(self, prop: str, dvalue: Any) -> bool:
        """
        Update the current value of prop if needed. Return True if actually updated and can be notified,
        False otherwise. This modifies the current_state[0]["hvac"] attribute

        The value is not checked against allowed values.
        """

        _log.debug(f"FastCarrierAC _update_generic {prop} {dvalue}")
        acquire_ret = False
        try:
            acquire_ret = bounded_sem.acquire(blocking=True, timeout=9)
        except Exception as e:
            _log.error(f"FastCarrierAC _update_generic acquire {e}")
        if_prop_in_rlock = False
        if acquire_ret:
            _log.debug(f"FastCarrierAC _update_generic acquire_ret {acquire_ret}")
            value = self.to_schema(prop, dvalue)
            if self.current_state[0]["hvac"][prop] != value:
                self.current_state[0]["hvac"][prop] = value
                if prop not in self.current_hvac_state["read_lock"]:
                    # return True
                    if_prop_in_rlock = True
            try:
                bounded_sem.release()
            except ValueError:
                _log.error("FastCarrierAC _update_generic, the semaphore is being over-released")
            except Exception as e:
                _log.error(f"FastCarrierAC _update_generic release {e}")
        # return False
        return if_prop_in_rlock

    def command_set_mode(self, mode: str) -> None:
        """
        Set the mode
        """
        mymodes = ["cool", "fan", "dry"]
        if mode == "off":
            ino, outo, dtype = self.registers("on")
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue inactive",
                self.update_mode,
            )
        else:  # Must be on then
            if not self.current_state[0]["hvac"]["on"]:
                ino, outo, dtype = self.registers("on")
                self.controller.send(
                    f"{self.ip_address} {dtype}Output {outo} presentValue active",
                    self.update_mode,
                )
            ino, outo, dtype = self.registers("oper")
            value = mymodes.index(mode) + 2
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue {value}",
                self.update_mode,
            )

    def command_set_temperature(self, value: Union[int, float]) -> None:
        pass
        # self.command_set_set_temperature(value)
        # ino, outo, dtype = self.registers("temperature")
        # self.controller.send(
        #     f"{self.ip_address} {dtype}Output {outo} presentValue {value*1.0}",
        #     self.update_temperature,
        # )

    def command_set_set_temperature(self, value: Union[int, float]) -> None:
        ino, outo, dtype = self.registers("set_temperature")
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {value*1.0}",
            self.update_set_temperature,
        )

    def command_set_fan(self, value: str) -> None:
        ino, outo, dtype = self.registers("fan")
        # cvalue = ["", "", "auto", "high", "median", "low", "off"].index(value)
        cvalue = ["", "", "auto", "high", "medium", "low", "off"].index(value)
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {cvalue}",
            self.update_fan,
        )

    def command_set_lock(self, value: dict) -> None: # after we have set_temperature, lock is not support
        lol = []
        if "temperature" in value:
            lol.append("temperature")

        if "mode" in value:
            if "off" in value["mode"]:
                if len(value["mode"]) < 3:
                    lol.append("oper")
            else:
                lol.append("on")
                if value["mode"] == []:
                    lol.append("oper")
        svalue = 1
        if len(lol) == 3:
            svalue = 8
        elif "on" in lol:
            if "temperature" in lol:
                svalue = 7
            elif "oper" in lol:
                svalue = 6
            else:
                svalue = 4
        elif "temperature" in lol:
            if "oper" in lol:
                svalue = 5
            else:
                svalue = 3
        elif "oper" in lol:
            svalue = 2
        ino, outo, dtype = self.registers("lock")
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {svalue}",
            self.update_lock,
        )

    def command_set_alarm(self, value: dict) -> None:
        """
        Only reset filter alarm here
        """
        if "filter" in value:
            ino, outo, dtype = self.registers("filter")
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue inactive"
            )

    def command_set_source(self, value: str) -> None:
        """
        Set event source here
        """
        
        self.update_source(value)

    def command_set_event_status(self, value: str) -> None:
        """
        Set event event_status here
        """
        
        self.update_event_status(value)

    def command_set_total_waiting_command(self, value: str) -> None:
        """
        Set event total_waiting_command here
        """
        
        self.update_total_waiting_command(value)

    # pls move to altolib
    def _command_set_total_waiting_command(self, value: dict) -> None:
        """
        The value is application dependent.
        """
        self._command_set_free_generic("total_waiting_command", value)

    # pls move to altolib
    def _command_set_event_status(self, value: dict) -> None:
        """
        The value is application dependent.
        """
        self._command_set_free_generic("event_status", value)

    # pls move to altolib
    def _command_set_set_temperature(self, temp: Union[int, float]) -> None:
        """
        Set the set_temperature. Make sure it is valid and is not locked.

        We are not using _command_set_generic because the testes are differents

        """
        if "set_temperature" not in self.capabilities:
            _log.error("Mode is not supported.")

        if (
            temp < self.capabilities["set_temperature"][0]
            or temp > self.capabilities["set_temperature"][1]
        ):
            _log.error(
                f"Temperature {temp} is out of range. Must be between {self.capabilities['set_temperature'][0]} and {self.capabilities['set_temperature'][1]}."
            )

        if (
            "lock" in self.capabilities
            and "set_temperature" in self.current_hvac_state["lock"]
        ):
            if (
                temp < self.current_hvac_state["lock"]["set_temperature"][0]
                and temp > self.current_hvac_state["lock"]["set_temperature"][1]
            ):
                _log.warning(f"Temperature is locked and cannot be set to {temp}")

        # TODO Check the steps

        try:
            self.command_set_set_temperature(temp)
        except Exception as e:
            _log.error("Could not set set_temperature")
            _log.exception(e)

    # pls move to altolib
    @property
    def current_state_total_waiting_command(self):
        return self.current_state[0]["hvac"]["total_waiting_command"]

    # pls move to altolib
    @property
    def current_state_event_status(self):
        return self.current_state[0]["hvac"]["event_status"]

    # pls move to altolib
    @property
    def current_state_update_type(self):
        return self.current_state[0]["hvac"]["update_type"]

    # pls move to altolib
    @property
    # def current_state_env_temperature(self):
    def current_state_room_temperature(self):
        # return self.current_state[0]["hvac"]["env_temperature"]
        return self.current_state[0]["hvac"]["room_temperature"]

    # pls move to altolib
    @property
    def current_state_set_temperature(self):
        return self.current_state[0]["hvac"]["set_temperature"]

    def update_source(self, value: str) -> bool:
        """
        Update the current value of source
        """

        res = self._update_generic("source", value)

    def update_event_status(self, value: str) -> bool:
        """
        Update the current value of event_status
        """

        res = self._update_generic("event_status", value)

    def update_total_waiting_command(self, value: str) -> bool:
        """
        Update the current value of total_waiting_command
        """

        res = self._update_generic("total_waiting_command", value)

    def update_mode(self, mode: Union[int, str]) -> bool:
        """
        Update the current value of mode,  with info from the device
        """
        mymodes = ["", "", "cool", "fan", "dry"]
        res = False
        if mode in ["active", "inactive"]:
            self.update_last_command_is_recv("on")
            res = self._update_generic("on", mode == "active")
            if res:
                # self.sec_cdown = 0
                self.was_updated = True

        else:
            imode = int(mode)
            if imode >= 2 and imode <= 4:
                cmode = mymodes[imode]  # To the schema defined values
                self.update_last_command_is_recv("oper")
                res = self._update_generic("oper", cmode)

        if "mode" in self.current_hvac_state["read_lock"]:
            return False
        if res:
            self.was_updated = True
        return res

    def update_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of purifier
        """
        res = False
        if isinstance(value, (int, float)):
            if value >= self.capabilities["temperature"][0] and value <= self.capabilities["temperature"][1]:
                self.update_last_command_is_recv("temperature")
                res = super().update_temperature(value)
                if res:
                    self.was_updated = True
        return res

    def update_set_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of purifier
        """
        res = False
        if isinstance(value, (int, float)):
            if value >= self.capabilities["set_temperature"][0] and value <= self.capabilities["set_temperature"][1]:
                self.update_last_command_is_recv("set_temperature")
                res = self._update_generic("set_temperature", value)
                if res:
                    self.was_updated = True
                self.update_temperature(value) # duplicate temperature value
        return res

    def update_fan(self, value: str) -> bool:
        """
        Update the current value of fan
        """
        res = False
        ivalue = int(value)
        if ivalue >= 2 and ivalue <= 5:
            self.update_last_command_is_recv("fan")
            res = super().update_fan(value)
            if res:
                self.was_updated = True
        return res

    # def update_env_temperature(self, temp: Union[int, float]) -> bool:
    def update_room_temperature(self, temp: Union[int, float]) -> bool:
        if isinstance(temp, (int, float)):
            if temp > 10 and temp < 60:
                # res = self._update_generic("env_temperature", temp)
                res = self._update_generic("room_temperature", temp)
        # if res:
        #     self.was_updated = True
        # self.set_sensor_data({"temperature": temp})

    def update_filter(self, value: str) -> bool:
        """
        Update the current value of filter
        """
        res = False
        if value in ["active", "inactive"]:
            res = self._update_generic("filter", value)
            if res:
                # self.was_updated = True
                pass
        return res

    def update_alert(self, value: str) -> bool:
        res = False
        if value in ["active", "inactive"]:
            res = self._update_generic("alert", value)
            if res:
                # self.was_updated = True
                pass
        return res

    def update_alert_code(self, value: int) -> bool:
        res = False
        if isinstance(value, int):
            res = self._update_generic("alert_code", value)
            if res:
                # self.was_updated = True
                pass
        return res

    def to_environment_temperature(self, val):
        return val

    def get_data(self):
        """
        Get the data for the device and send the info
        """

        return
        ino, outo, dtype = self.registers("env_temperature")
        self.controller.send(
            f"{self.ip_address} {dtype}Input {ino} presentValue",
            self.update_env_temperature,
        )
        _log.debug(f"State for {self.device_id} is {self.current_state}")

    def update_device(self, device):
        if self.ip_address == device.ip_address and self.unit == device.unit:
            return self
        return device

    def send_read_part(self, send_part):
        _log.debug(f'''FastCarrierAC send_read_part {self.device_id} {send_part}''')
        if send_part == 0:
            for prop in ["on", "oper"]:
                ino, outo, dtype = self.registers(prop)
                cb = self.update_mode
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )
            # for prop in ["temperature", "fan", "env_temperature"]:
            # for prop in ["temperature", "set_temperature", "fan", "room_temperature"]:
            for prop in ["set_temperature", "fan", "room_temperature"]:
                ino, outo, dtype = self.registers(prop)
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )
        else:
            # for prop in ["lock", "filter", "alert", "alert_code"]:
            for prop in ["filter", "alert", "alert_code"]:
                ino, outo, dtype = self.registers(prop)
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )

    def update_state(self):
        pass

    def process_cov(self, register, value):
        """
        Process a COV info. The COV is a 2uple
            register the 'address" that changed
            value the new value

        return True if the COV was for this device. False otherwise.
        """
        for prop in self.prop_defs:
            ino, outo, _ = self.registers(prop)
            if register == ino:
                _log.debug(f"COV for {prop} on {self.device_id}")
                try:
                    if prop in ["on", "oper"]:
                        self.update_mode(value)
                    else:
                        getattr(self, "update_" + prop)(value)
                except Exception as e:
                    _log.debug(f"Problem with COV: {e}")
                return True
            elif register == outo:
                _log.debug(f"COV was for {prop} Output on {self.device_id}")
                # We don't care
                return True
        return False

    def check_emit_event(self):
        if self.command_queue.empty() and not self.last_command:
            if self.emit_event_count < 60: # 30*5 = 150, ~ 2.5 min
                if self.was_updated:
                    # self.is_normal_updated = True
                    self.command_set_source("ac_remote")
                    self.emit_event_state()
                    _log.debug(f"FastCarrierAC check_emit_event {self.device_id} {self.emit_event_count}")
                self.emit_event_count += 1
            else:
                if not self.was_updated:
                    if not self.is_normal_updated:
                        res = self._update_generic("update_type", "force")
                        self.emit_event_state()
                    self.emit_event_count = 0
                else:
                    self.command_set_source("ac_remote")
                    self.emit_event_state()
                    self.emit_event_count = 0
                _log.debug(f"FastCarrierAC check_emit_event {self.device_id} {self.emit_event_count} {self.is_normal_updated}")
                self.is_normal_updated = False

    def emit_event_state(self, val=None):
        self.is_normal_updated = True
        self.was_updated = False
        self.controller.emit_event_state(self.device_id)
        # self.command_set_source("ac_remote")
        res = self._update_generic("update_type", "normal")

    def subscribe_cov(self, bacnet):
        return


class CarrierAC(altolib.AltoHVACDevice, altolib.AltoEnvironSensor):
    """
    Defines a single AC unit behing a Carrier BACnet bridge
    """

    def __init__(self, controller, devid, ip, unit):
        """
        Here devid is of the form <ip address>:<unit>
        """
        super().__init__(controller, devid, 1)
        # Now setup the map
        self.ip_address = ip
        self.unit = int(unit)
        self.data_map.update(CARRIERMAP)
        self.initialise_data("environment", CARRIERMAP.keys())
        self.capabilities = {
            "mode": ["off", "cool", "fan", "dry"],
            "temperature": [18.0, 29.0, 1.0],  # Min, Max, Increment
            "fan": ["auto", "high", "median", "low", "off"],
            "lock": True,
            "read_lock": True,
            "alarm": ["filter", "device"],
            "source": ["ac_remote", "web", "c2d", "rl_action", "trivial"],
        }
        self.current_state[0]["hvac"] = {
            "on": False,
            "oper": "cool",
            "temperature": 25.0,
            "fan": "off",
            "flow": "off",
            "lock": {},
            "read_lock": [],
            "alert": False,
            "filter": False,
            "alert_code": 1,
            "source": "ac_remote",
        }
        self.unit_zero = 2
        self.unit_offset = 256
        self.output_offset = 128
        self.prop_defs = {}
        self.prop_defs["alert_code"] = (-1, "multiState", False)  # False is read-only
        self.prop_defs["on"] = (0, "binary", True)  # True is Read/write
        self.prop_defs["oper"] = (1, "multiState", True)
        self.prop_defs["temperature"] = (2, "analog", True)
        self.prop_defs["fan"] = (3, "multiState", True)
        self.prop_defs["flow"] = (5, "multiState", True)
        self.prop_defs["env_temperature"] = (6, "analog", False)
        self.prop_defs["lock"] = (7, "multiState", True)
        self.prop_defs["filter"] = (18, "binary", True)
        self.prop_defs["alert"] = (62, "binary", False)
        self.was_updated = False
        self.sec_cdown = 0
        self.sec_cnt = lambda: randint(2, 3)  # Spread around
        self.ter_cdown = randint(0, 30)  # Spread around
        self.ter_cnt = lambda: randint(2, 3)  # Spread around

    def registers(self, prop):
        in_off = self.unit_zero + self.unit * self.unit_offset
        reg, dtype, rw = self.prop_defs[prop]
        in_off += reg
        out_off = (in_off + self.output_offset) if rw else False
        return (in_off, out_off, dtype)

    @property
    def current_state_mode(self):
        if not self.current_state[0]["hvac"]["on"]:
            return "off"
        return self.current_state[0]["hvac"]["oper"]

    @property
    def current_state_alarm(self):
        res = {}
        if self.current_state[0]["hvac"]["filter"]:
            res["filter"] = {
                "level": "maintenance",
                "msg": "Filter needs cleaning/replacement",
            }

        if self.current_state[0]["hvac"]["alert"]:
            res["device"] = {
                "level": "warning",
                "msg": f"Error code is {self.current_state[0]['hvac']['alert_code']}",
            }
        if res:
            return res
        return False

    def to_schema(self, prop, value):
        """
        Translate values from the device into schema defined values
        """

        if prop == "mode":
            if value in ["active", "inactive"]:
                if value == "inactive":
                    return "off"
                return self.current_state[0]["hvac"]["oper"]
            return value[:4]
        if prop == "fan":
            return ["", "", "auto", "high", "median", "low", "off"][int(value)]

        if prop == "filter":
            return value == "active"

        if prop == "alert":
            return value == "active"

        if prop == "lock":
            lattr = []
            if value == 2:
                lattr = ["mode"]
            elif value == 3:
                lattr = ["temperature"]
            elif value == 4:
                lattr = ["on"]
            elif value == 5:
                lattr = ["mode", "temperature"]
            elif value == 6:
                lattr = ["mode", "on"]
            elif value == 7:
                lattr = ["temperature", "on"]
            elif value == 8:
                lattr = ["mode", "temperature", "on"]
            res = {}
            if "temperature" in lattr:
                res["temperature"] = [self.current_state[0]["hvac"]["temperature"]] * 2
            if "on" in lattr:
                if "mode" in lattr:
                    res["mode"] = []
                else:
                    if self.current_state[0]["hvac"]["on"]:
                        res["mode"] = ["cool", "fan", "dry"]
                    else:
                        res["mode"] = []
            elif "mode" in lattr:
                res["mode"] = ["off", self.current_state[0]["hvac"]["oper"]]

            return res
        return value

    def command_set_mode(self, mode: str) -> None:
        """
        Set the mode
        """
        mymodes = ["cool", "fan", "dry"]
        if mode == "off":
            ino, outo, dtype = self.registers("on")
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue inactive",
                self.update_mode,
            )
        else:  # Must be on then
            if not self.current_state[0]["hvac"]["on"]:
                ino, outo, dtype = self.registers("on")
                self.controller.send(
                    f"{self.ip_address} {dtype}Output {outo} presentValue active",
                    self.update_mode,
                )
            ino, outo, dtype = self.registers("oper")
            value = mymodes.index(mode) + 2
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue {value}",
                self.update_mode,
            )

    def command_set_temperature(self, value: Union[int, float]) -> None:
        ino, outo, dtype = self.registers("temperature")
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {value*1.0}",
            self.update_temperature,
        )

    def command_set_fan(self, value: str) -> None:
        ino, outo, dtype = self.registers("fan")
        cvalue = ["", "", "auto", "high", "median", "low", "off"].index(value)
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {cvalue}",
            self.update_fan,
        )

    def command_set_lock(self, value: dict) -> None:
        lol = []
        if "temperature" in value:
            lol.append("temperature")

        if "mode" in value:
            if "off" in value["mode"]:
                if len(value["mode"]) < 3:
                    lol.append("oper")
            else:
                lol.append("on")
                if value["mode"] == []:
                    lol.append("oper")
        svalue = 1
        if len(lol) == 3:
            svalue = 8
        elif "on" in lol:
            if "temperature" in lol:
                svalue = 7
            elif "oper" in lol:
                svalue = 6
            else:
                svalue = 4
        elif "temperature" in lol:
            if "oper" in lol:
                svalue = 5
            else:
                svalue = 3
        elif "oper" in lol:
            svalue = 2
        ino, outo, dtype = self.registers("lock")
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {svalue}",
            self.update_lock,
        )

    def command_set_alarm(self, value: dict) -> None:
        """
        Only reset filter alarm here
        """
        if "filter" in value:
            ino, outo, dtype = self.registers("filter")
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue inactive"
            )

    def command_set_source(self, value: str) -> None:
        """
        Set event source here
        """
        
        self.update_source(value)

    def update_source(self, value: str) -> bool:
        """
        Update the current value of source
        """

        res = self._update_generic("source", value)

    def update_mode(self, mode: Union[int, str]) -> bool:
        """
        Update the current value of mode,  with info from the device
        """
        mymodes = ["", "", "cool", "fan", "dry"]
        res = False
        if mode in ["active", "inactive"]:
            res = self._update_generic("on", mode == "active")
            if res:
                self.sec_cdown = 0

        else:
            cmode = mymodes[int(mode)]  # To the schema defined values
            res = self._update_generic("oper", cmode)

        if "mode" in self.current_hvac_state["read_lock"]:
            return False
        if res:
            self.was_updated = True
        return res

    def update_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of purifier
        """
        res = super().update_temperature(value)
        if res:
            self.was_updated = True
        return res

    def update_fan(self, value: str) -> bool:
        """
        Update the current value of fan
        """
        res = super().update_fan(value)
        if res:
            self.was_updated = True
        return res

    def update_env_temperature(self, temp: Union[int, float]) -> bool:
        # res = self._update_generic("env_temperature", temp)
        # if res:
        self.set_sensor_data({"temperature": temp})

    def update_filter(self, value: str) -> bool:
        """
        Update the current value of filter
        """
        res = self._update_generic("filter", value)
        if res:
            self.was_updated = True
        return res

    def update_alert(self, value: str) -> bool:
        res = self._update_generic("alert", value)
        if res:
            self.was_updated = True
        return res

    def update_alert_code(self, value: int) -> bool:
        res = self._update_generic("alert_code", value)
        if res:
            self.was_updated = True
        return res

    def to_environment_temperature(self, val):
        return val

    def get_data(self):
        """
        Get the data for the device and send the info
        """

        ino, outo, dtype = self.registers("env_temperature")
        self.controller.send(
            f"{self.ip_address} {dtype}Input {ino} presentValue",
            self.update_env_temperature,
        )
        _log.debug(f"State for {self.device_id} is {self.current_state}")

    def update_device(self, device):
        if self.ip_address == device.ip_address and self.unit == device.unit:
            return self
        return device

    def update_state(self):
        
        # _log.debug(f'''sec_cdown {self.sec_cdown}''')
        if self.sec_cdown <= 0:
            # _log.debug(f'''sec_cdown {self.sec_cdown}''')
            self.sec_cdown = self.sec_cnt()
            for prop in ["on", "oper"]:
                ino, outo, dtype = self.registers(prop)
                cb = self.update_mode
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )
            for prop in ["temperature", "fan"]:
                ino, outo, dtype = self.registers(prop)
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )
        else:
            self.sec_cdown -= 1
            if self.current_state[0]["hvac"]["on"]:
                for prop in ["temperature"]:
                    ino, outo, dtype = self.registers(prop)
                    cb = getattr(self, "update_" + prop)
                    self.controller.send(
                        f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                    )
        if self.ter_cdown <= 0:
            self.ter_cdown = self.ter_cnt()
            for prop in ["lock", "filter", "alert", "alert_code"]:
                ino, outo, dtype = self.registers(prop)
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )
        else:
            self.ter_cdown -= 1

    def process_cov(self, register, value):
        """
        Process a COV info. The COV is a 2uple
            register the 'address" that changed
            value the new value

        return True if the COV was for this device. False otherwise.
        """
        for prop in self.prop_defs:
            ino, outo, _ = self.registers(prop)
            if register == ino:
                _log.debug(f"COV for {prop} on {self.device_id}")
                try:
                    if prop in ["on", "oper"]:
                        self.update_mode(value)
                    else:
                        getattr(self, "update_" + prop)(value)
                except Exception as e:
                    _log.debug(f"Problem with COV: {e}")
                return True
            elif register == outo:
                _log.debug(f"COV was for {prop} Output on {self.device_id}")
                # We don't care
                return True
        return False

    def emit_event_state(self, val=None):
        if self.was_updated:
            self.was_updated = False
            self.controller.emit_event_state(self.device_id)
            self.command_set_source("ac_remote")

    def subscribe_cov(self, bacnet):
        return


class ChenSen(altolib.AltoHVACDevice, altolib.AltoEnvironSensor):
    """
    Defines a single AC unit behing a Carrier BACnet bridge
    """

    def __init__(self, controller, devid, ip, unit):
        """
        Here devid is of the form <ip address>:<unit>.
        """
        super().__init__(controller, devid, 1)
        # Now setup the map
        self.ip_address = ip
        self.temp, self.offset = [int(x) for x in unit.split(":")]
        self.data_map.update(CHENSENMAP)
        self.initialise_data("environment", CHENSENMAP.keys())
        self.capabilities = {
            "mode": ["off", "cool", "heat", "fan"],
            "temperature": [18.0, 29.0, 0.1],  # Min, Max, Increment
            "fan": ["high", "median", "low", "auto"],
            "lock": True,
            "read_lock": False,
        }
        self.current_state[0]["hvac"] = {
            "on": False,
            "oper": "cool",
            "temperature": 25.0,
            "fan": "auto",
            "lock": {},
            "read_lock": [],
        }
        self.unit_zero = 2
        self.unit_offset = 256
        self.output_offset = 128
        self.prop_defs = {}
        self.prop_defs["on"] = (self.temp, "binary", True)  # True is Read/write
        self.prop_defs["oper"] = (self.offset, "analog", True)
        self.prop_defs["temperature"] = (self.offset + 2, "analog", True)
        self.prop_defs["fan"] = (self.offset + 1, "analog", True)
        self.prop_defs["env_temperature"] = (self.temp, "analog", False)
        self.prop_defs["lock"] = (self.offset + 3, "analog", True)
        self.was_updated = False
        self.sec_cdown = 0
        self.sec_cnt = lambda: randint(30, 40)  # Spread around
        self.ter_cdown = randint(0, 30)  # Spread around
        self.ter_cnt = lambda: randint(30, 40)  # Spread around

    @property
    def current_state_mode(self):
        if not self.current_state[0]["hvac"]["on"]:
            return "off"
        return self.current_state[0]["hvac"]["oper"]

    def to_schema(self, prop, value):
        """
        Translate values from the device into schema defined values
        """

        if prop == "mode":
            if value in ["active", "inactive"]:
                if value == "inactive":
                    return "off"
                return self.current_state[0]["hvac"]["oper"]
            return "off"
        if prop == "fan":
            return ["high", "median", "low", "auto"][int(value)]

        if prop == "lock":
            if value == 0:
                res = {}
            elif value == 1:
                sres = {
                    "mode": [self.current_state[0]["hvac"]["mode"]],
                    "fan": [self.current_state[0]["hvac"]["fan"]],
                    "temperature": [self.current_state[0]["hvac"]["temperature"]] * 2,
                }
                if not self.current_state[0]["hvac"]["on"]:
                    res["mode"] = ["off"]
            elif value == 2:
                res = {"mode": ["off"]}
                if self.current_state[0]["hvac"]["on"]:
                    res["mode"] = [self.current_state[0]["hvac"]["mode"]]
            elif value == 3:
                if self.current_state[0]["hvac"]["on"]:
                    res["mode"] = ["cool", "heat", "fan"]
                else:
                    res["mode"] = ["off"]

            return res
        return value

    def command_set_mode(self, mode: str) -> None:
        """
        Set the mode
        """
        mymodes = ["", "cool", "heat", "fan"]
        if mode == "off":
            outo, dtype, rw = self.prop_defs["on"]
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue inactive",
                self.update_mode,
            )
        else:  # Must be on then
            if not self.current_state[0]["hvac"]["on"]:
                outo, dtype, rw = self.prop_defs["on"]
                self.controller.send(
                    f"{self.ip_address} {dtype}Output {outo} presentValue active",
                    self.update_mode,
                )
            outo, dtype, rw = self.prop_defs["oper"]
            value = mymodes.index(mode)
            self.controller.send(
                f"{self.ip_address} {dtype}Output {outo} presentValue {value}",
                self.update_mode,
            )

    def command_set_temperature(self, value: Union[int, float]) -> None:
        outo, dtype, rw = self.prop_defs["temperature"]
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {value*1.0}",
            self.update_temperature,
        )

    def command_set_fan(self, value: str) -> None:
        outo, dtype, rw = self.prop_defs["temperature"]
        cvalue = ["high", "median", "low", "auto"].index(value)
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {cvalue}",
            self.update_fan,
        )

    def command_set_lock(self, value: dict) -> None:
        lol = []
        if "temperature" in value:
            lol.append("temperature")

        if "mode" in value:
            if "off" in value["mode"]:
                if len(value["mode"]) < 3:
                    lol.append("oper")
            else:
                lol.append("on")
                if value["mode"] == []:
                    lol.append("oper")
        svalue = 1
        if len(lol) == 3:
            svalue = 8
        elif "on" in lol:
            if "temperature" in lol:
                svalue = 7
            elif "oper" in lol:
                svalue = 6
            else:
                svalue = 4
        elif "temperature" in lol:
            if "oper" in lol:
                svalue = 5
            else:
                svalue = 3
        elif "oper" in lol:
            svalue = 2
        outo, dtype, rw = self.prop_defs["lock"]
        self.controller.send(
            f"{self.ip_address} {dtype}Output {outo} presentValue {svalue}",
            self.update_lock,
        )

    def update_mode(self, mode: Union[int, str]) -> bool:
        """
        Update the current value of mode,  with info from the device
        """
        mymodes = ["", "cool", "heat", "fan"]
        res = False
        if mode in ["active", "inactive"]:
            res = self._update_generic("on", mode == "active")
            if res:
                self.sec_cdown = 0

        else:
            cmode = mymodes[int(mode)]  # To the schema defined values
            res = self._update_generic("oper", cmode)

        if res:
            self.was_updated = True
        return res

    def update_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of purifier
        """
        res = super().update_temperature(value)
        if res:
            self.was_updated = True
        return res

    def update_fan(self, value: str) -> bool:
        """
        Update the current value of fan
        """
        res = super().update_fan(value)
        if res:
            self.was_updated = True
        return res

    def update_env_temperature(self, temp: Union[int, float]) -> bool:
        # res = self._update_generic("env_temperature", temp)
        # if res:
        self.set_sensor_data({"temperature": temp})

    def update_filter(self, value: str) -> bool:
        """
        Update the current value of filter
        """
        res = self._update_generic("filter", value)
        if res:
            self.was_updated = True
        return res

    def to_environment_temperature(self, val):
        return val

    def get_data(self):
        """
        Get the data for the device and send the info
        """

        ino, dtype, rw = self.prop_defs["env_temperature"]
        self.controller.send(
            f"{self.ip_address} {dtype}Input {ino} presentValue",
            self.update_env_temperature,
        )
        _log.debug(f"State for {self.device_id} is {self.current_state}")

    def update_device(self, device):
        if (
            self.ip_address == device.ip_address
            and self.temp == device.temp
            and self.offset == device.offset
        ):
            return self
        return device

    def update_state(self):

        if self.sec_cdown <= 0:
            self.sec_cdown = self.sec_cnt()
            for prop in ["on", "oper"]:
                ino, dtype, rw = self.prop_defs[prop]
                cb = self.update_mode
                self.controller.send(
                    f"{self.ip_address} {dtype}ROutput {ino} presentValue", cb
                )
            for prop in ["temperature", "fan"]:
                ino, dtype, rw = self.prop_defs[prop]
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype}ROutput {ino} presentValue", cb
                )
        else:
            self.sec_cdown -= 1
            if self.current_state[0]["hvac"]["on"]:
                for prop in ["temperature"]:
                    ino, dtype, rw = self.prop_defs[prop]
                    cb = getattr(self, "update_" + prop)
                    self.controller.send(
                        f"{self.ip_address} {dtype}ROutput {ino} presentValue", cb
                    )
        if self.ter_cdown <= 0:
            self.ter_cdown = self.ter_cnt()
            for prop in ["lock"]:
                ino, dtype, rw = self.prop_defs[prop]
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype}Input {ino} presentValue", cb
                )
        else:
            self.ter_cdown -= 1

    def process_cov(self, register, value):
        """
        Process a COV info. The COV is a 2uple
            register the 'address" that changed
            value the new value

        return True if the COV was for this device. False otherwise.
        """
        for prop in self.prop_defs:
            ino, dtype, rw = self.prop_defs[prop]
            if register == ino:
                _log.debug(f"COV for {prop} on {self.device_id}")
                try:
                    if prop in ["on", "oper"]:
                        self.update_mode(value)
                    else:
                        getattr(self, "update_" + prop)(value)
                except Exception as e:
                    _log.debug(f"Problem with COV: {e}")
                return True

        return False

    def emit_event_state(self, val=None):
        if self.was_updated:
            self.was_updated = False
            self.controller.emit_event_state(self.device_id)

    def subscribe_cov(self, bacnet):
        for addr, ptype, rw in self.prop_defs.values():
            if rw:
                ptype += "Output"
            else:
                ptype += "Input"
            bacnet.cov(self.ip_address, (ptype, addr), callback=self.got_cov)

    def got_cov(self, elements=None):
        _log.debug(f"Got cov with {elements}")
        try:
            if elements:
                addr = elements["object_changed"][1]
                for val in self.prop_defs:
                    paddr, type, rw = self.prop_defs[val]
                    if addr == paddr:
                        if val in ["on", "oper"]:
                            uval = "mode"
                        else:
                            uval = val
                        getattr(self, f"update_{uval}")(
                            elements["properties"]["presentValue"]
                        )
                        break
        except Exception as e:
            _log.debug(f"Error from cov: {e}")


class DaikinDBACS(altolib.AltoHVACDevice, altolib.AltoEnvironSensor):
    """
    Daikin D-BACS, interface for use in BACnet DMS502B51
    """

    def __init__(self, controller, devid, ip, unit):
        """
        Here devid is of the form <ip address>:<unit>. 
        """
        super().__init__(controller, devid, 1)
        # Now setup the map
        self.ip_address = ip

        # FCU-1-01, FCU-x-yy
        # The fomular of Instance Number is: (( 4 -1)*16+ 15 )*256+ 1 or (( x -1)*16+ yy )*256+ zz
        # x is self.offset1, yy is self.offset2, zz is point index in each AC (This value is not continuous, its depends on the model)
        self.offset1, self.offset2 = [int(x) for x in unit.split("-")]

        self.data_map.update(DAIKINDBACSMAP)
        self.initialise_data("environment", DAIKINDBACSMAP.keys())
        self.mode_index = ["", "cool", "", "fan", "", "dry"]
        self.fan_index = ["", "low", "high", "mid", "auto"]
        self.louver_index = ["hor1", "hor2", "hor3", "hor4", "ver", "", "", "swing"]
        self.capabilities = {
            "mode": ["off", "cool", "fan", "dry"],
            "set_temperature": [18.0, 31.0, 1.0],
            "room_temperature": [10.0, 45.0, 1.0],  # Min, Max, Increment
            "fan": ["low", "high", "mid", "auto"],
            "louver": ["hor1", "hor2", "hor3", "hor4", "ver", "swing"], # air direction 0.0 1.0 2.0 3.0 4.0 7.0
            "filter": ["inactive", "active"],
            "alarm": ["inactive", "active"],
            "malfunc": [1, 2, 512], # malfunction code
            "lock": True,
            "read_lock": False,
            "source": ["rl_action", "rl_correction", "web", "ac_remote", "c2d", "trivial"]
        }
        self.current_state[0]["hvac"] = {
            "on": False,
            "oper": "cool",
            "set_temperature": 25.0,
            "room_temperature": 25.0,
            "fan": "auto",
            "louver": "swing",
            "filter": "inactive",
            "alarm": "inactive",
            "malfunc": 1,
            "lock": {},
            "read_lock": [],
            "source": "ac_remote"
        }
        self.unit_zero = 2
        self.unit_offset = 256
        self.output_offset = 128
        self.prop_defs = {}
        self.prop_defs["on"] = (1, "binaryOutput", 2, "binaryInput") # (write address, write type, read address, read type)
        self.prop_defs["oper"] = (5, "multiStateOutput", 6, "multiStateInput")
        self.prop_defs["set_temperature"] = (10, "analogValue", 10, "analogValue")
        self.prop_defs["fan"] = (7, "multiStateOutput", 8, "multiStateInput")
        self.prop_defs["louver"] = (22, "analogValue", 23, "analogInput")
        self.prop_defs["filter"] = (12, "binaryValue", 11, "binaryInput")
        self.prop_defs["alarm"] = (False, False, 3, "binaryInput")
        self.prop_defs["malfunc"] = (False, False, 4, "multiStateInput")
        self.prop_defs["room_temperature"] = (False, False, 9, "analogInput")
        self.prop_defs["lock"] = (17, "binaryValue", 17, "binaryValue")
        self.was_updated = False
        self.cov_force_update = False
        self.sec_cdown = 0
        self.sec_cnt = lambda: randint(30, 40)  # Spread around
        self.ter_cdown = randint(0, 30)  # Spread around
        self.ter_cnt = lambda: randint(30, 40)  # Spread around

    def registers(self, prop):
        local_offset_write, obj_type_write, local_offset_read, obj_type_read = self.prop_defs[prop]
        instance_number_for_write = ((self.offset1 - 1)*16 + self.offset2)*self.unit_offset + local_offset_write
        instance_number_for_read = ((self.offset1 - 1)*16 + self.offset2)*self.unit_offset + local_offset_read
        return (instance_number_for_write, obj_type_write, instance_number_for_read, obj_type_read)

    @property
    def current_state_louver(self):
        return self.current_state[0]["hvac"]["louver"]

    @property
    def current_state_filter(self):
        return self.current_state[0]["hvac"]["filter"]

    @property
    def current_state_malfunc(self):
        return self.current_state[0]["hvac"]["malfunc"]

    @property
    def current_state_room_temperature(self):
        return self.current_state[0]["hvac"]["room_temperature"]

    @property
    def current_state_mode(self):
        if not self.current_state[0]["hvac"]["on"]:
            return "off"
        return self.current_state[0]["hvac"]["oper"]

    def to_schema(self, prop, value):
        """
        Translate values from the device into schema defined values
        """

        if prop == "room_temperature":
            return value

        if prop == "mode":
            if value in ["active", "inactive"]:
                if value == "inactive":
                    return "off"
                return self.current_state[0]["hvac"]["oper"]
            return "off"
        if prop == "fan":
            return self.fan_index[int(value)]

        if prop == "lock":
            res = value

            return res
        return value

    def command_set_mode(self, mode: str) -> None:
        """
        Set the mode
        """

        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }

        if mode == "off":
            outo, dtype, _, __ = self.registers("on")
            self.controller.send(
                f"{self.ip_address} {dtype} {outo} presentValue inactive",
                self.update_mode,
                **options
            )
        else:  # Must be on then
            if not self.current_state[0]["hvac"]["on"]:
                outo, dtype, _, __ = self.registers("on")
                self.controller.send(
                    f"{self.ip_address} {dtype} {outo} presentValue active",
                    self.update_mode,
                    **options
                )
            outo, dtype, _, __ = self.registers("oper")
            value = self.mode_index.index(mode)
            self.controller.send(
                f"{self.ip_address} {dtype} {outo} presentValue {value}",
                self.update_mode,
                **options
            )

    def command_set_temperature(self, value: Union[int, float]) -> None:
        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }

        outo, dtype, _, __ = self.registers("temperature")
        self.controller.send(
            f"{self.ip_address} {dtype} {outo} presentValue {value*1.0}",
            self.update_temperature,
            **options
        )
    
    def command_set_set_temperature(self, value: Union[int, float]) -> None:
        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }
        
        outo, dtype, _, __ = self.registers("set_temperature")
        self.controller.send(
            f"{self.ip_address} {dtype} {outo} presentValue {value*1.0}",
            self.update_set_temperature,
            **options
        )

    def command_set_fan(self, value: str) -> None:
        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }

        outo, dtype, _, __ = self.registers("fan")
        cvalue = self.fan_index.index(value)
        self.controller.send(
            f"{self.ip_address} {dtype} {outo} presentValue {cvalue}",
            self.update_fan,
            **options
        )

    def command_set_louver(self, mode: str) -> None:
        """
        Set the louver
        """

        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }

        outo, dtype, _, __ = self.registers("louver")
        value = round(float(self.louver_index.index(mode)), 1)
        self.controller.send(
            f"{self.ip_address} {dtype} {outo} presentValue {value}",
            self.update_louver,
            **options
        )

    def command_set_filter(self, value: str) -> None:
        """
        Set the filter
        """

        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }

        outo, dtype, _, __ = self.registers("filter")
        if value == "active":
            cvalue = "active"
        else:
            cvalue = "inactive"
        self.controller.send(
            f"{self.ip_address} {dtype} {outo} presentValue {cvalue}",
            self.update_filter,
            **options
        )

    def command_set_lock(self, value: dict) -> None:
        options = {
            "devtype": "daikinDBACS",
            "rw": True
        }

        svalue = "inactive"
        if "all" in value:
            if value["all"]:
                svalue = "active"

        outo, dtype, _, __ = self.registers("lock")
        self.controller.send(
            f"{self.ip_address} {dtype} {outo} presentValue {svalue}",
            self.update_lock,
            **options
        )
    
    def command_set_source(self, source):
        return self.update_source(source)
    
    def update_source(self, value):
        res = self._update_generic("source", value)

    def update_mode(self, mode: Union[int, str]) -> bool:
        """
        Update the current value of mode,  with info from the device
        """

        res = False
        if mode in ["active", "inactive"]:
            res = self._update_generic("on", mode == "active")
            if res:
                self.sec_cdown = 0

        else:
            cmode = self.mode_index[int(mode)]  # To the schema defined values
            res = self._update_generic("oper", cmode)

        if res:
            self.was_updated = True
        return res

    def update_set_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of set temperature
        """
        res = super().update_set_temperature(value)
        if res:
            self.was_updated = True
        return res

    def update_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of temperature
        """
        res = super().update_temperature(value)
        if res:
            self.was_updated = True
        return res

    def update_fan(self, value: str) -> bool:
        """
        Update the current value of fan
        """
        res = super().update_fan(value)
        if res:
            self.was_updated = True
        return res

    def update_louver(self, value: str) -> bool:
        tmp = self.louver_index[int(float(value))]
        res = self._update_generic("louver", tmp)
        if res:
            self.was_updated = True
        return res

    def update_filter(self, value: str) -> bool:
        tmp = value
        res = self._update_generic("filter", tmp)
        if res:
            self.was_updated = True
        return res

    def update_malfunc(self, value: str) -> bool:
        tmp = value
        res = self._update_generic("malfunc", tmp)
        if res:
            self.was_updated = True
        return res

    def update_room_temperature(self, temp: Union[int, float]) -> bool:
        # res = self._update_generic("env_temperature", temp)
        # if res:
        res = self._update_generic("room_temperature", temp)
        if res:
            self.was_updated = True
        return res
        # self.set_sensor_data({"temperature": temp})

    def update_lock(self, value: str) -> bool:
        # _log.debug(f"update_lock {value}")
        tmp = {}
        if value == "active":
            tmp = {
                "mode": [],
                "temperature": self.capabilities["temperature"],
                "fan": []
            }
        res = self._update_generic("lock", tmp)
        # _log.debug(f"update_lock {self.current_state_lock}")
        if res:
            self.was_updated = True
        return res
        
    def to_environment_temperature(self, val):
        return val

    def get_data(self):
        """
        Get the data for the device and send the info
        """

        options = {
            "devtype": "daikinDBACS",
            "rw": False
        }

        _, __, ino, dtype = self.registers("room_temperature")
        self.controller.send(
            f"{self.ip_address} {dtype} {ino} presentValue",
            self.update_room_temperature,
            **options
        )
        _log.debug(f"State for {self.device_id} is {self.current_state}")

    def update_device(self, device):
        if (
            self.ip_address == device.ip_address
            and self.temp == device.temp
            and self.offset1 == device.offset1
            and self.offset2 == device.offset2
        ):
            return self
        return device

    def update_state(self):
        options = {
            "devtype": "daikinDBACS",
            "rw": False
        }

        if self.sec_cdown <= 0:
            self.sec_cdown = self.sec_cnt()
            for prop in ["on", "oper"]:
                _, __, ino, dtype = self.registers(prop)
                cb = self.update_mode
                self.controller.send(
                    f"{self.ip_address} {dtype} {ino} presentValue", cb, **options
                )
            for prop in ["fan", "louver", "filter", "alarm", "malfunc", "set_temperature", "room_temperature"]:
                _, __, ino, dtype = self.registers(prop)
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype} {ino} presentValue", cb, **options
                )
        else:
            self.sec_cdown -= 1
            if self.current_state[0]["hvac"]["on"]:
                for prop in ["set_temperature"]:
                    _, __, ino, dtype = self.registers(prop)
                    cb = getattr(self, "update_" + prop)
                    self.controller.send(
                        f"{self.ip_address} {dtype} {ino} presentValue", cb, **options
                    )
        if self.ter_cdown <= 0:
            self.ter_cdown = self.ter_cnt()
            for prop in ["lock"]:
                _, __, ino, dtype = self.registers(prop)
                cb = getattr(self, "update_" + prop)
                self.controller.send(
                    f"{self.ip_address} {dtype} {ino} presentValue", cb, **options
                )
        else:
            self.ter_cdown -= 1

    def process_cov(self, register, value):
        """
        Process a COV info. The COV is a 2uple
            register the 'address" that changed
            value the new value

        return True if the COV was for this device. False otherwise.
        """
        for prop in self.prop_defs:
            # ino, dtype, rw = self.prop_defs[prop]
            _, __, ino, dtype = self.registers(prop)
            if register == ino:
                _log.debug(f"COV for {prop} on {self.device_id}")
                try:
                    if prop in ["on", "oper"]:
                        self.update_mode(value)
                    else:
                        getattr(self, "update_" + prop)(value)
                except Exception as e:
                    _log.debug(f"Problem with COV: {e}")
                return True

        return False

    def emit_event_state(self, val=None):
        if self.was_updated or self.cov_force_update:
            self.was_updated = False
            self.cov_force_update = False
            self.controller.emit_event_state(self.device_id)
            self.update_source("ac_remote")

    def subscribe_cov(self, bacnet):
        for k in self.prop_defs.keys():
            wa, wt, ra, rt = self.registers(k)
            try:
                if wa != False:
                    bacnet.cov(self.ip_address, (wt, wa), callback=self.got_cov)
                if ra != False:
                    bacnet.cov(self.ip_address, (rt, ra), callback=self.got_cov)
            except Exception as e:
                _log.warning("Problem in subscribe_cov")
                _log.debug(f"Error was {e}")
                _log.exception(e)
    
    def got_cov(self, elements=None):
        _log.debug(f"Got cov with {elements}")
        try:
            if elements:
                addr = elements["object_changed"][1]
                for k, v in self.prop_defs.items():
                    wa, wt, ra, rt = self.registers(k)
                    if addr == wa or addr == ra:
                        if k in ["on", "oper"]:
                            uval = "mode"
                        else:
                            uval = k
                        self.cov_force_update = True
                        getattr(self, f"update_{uval}")(elements["properties"]["presentValue"])
                        break
        except Exception as e:
            _log.debug(f"Error from cov: {e}")
        

def bac0hvac(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Bac0Hvac
    :rtype: Bac0Hvac

    We excpect the configuration to have

        topic:: the application namespace
        agent_name
        hvac_units a dicttionary of 2-uples
           the key is the devid
           the valueww a tuple with
               [<ip_address>,<unit number>, device type]
        ip_address: The IP addresss with mask of the agent
        station_id: What offset from 0xbac0 to use  for the port. Must be unbique and > 1
        cov_master: Run the COV thread. Only one agent can do that.
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "bacnet")
    kwargs["hvac_units"] = config.get("hvac_units", {})
    kwargs["ip_address"] = config.get("ip_address", "")
    kwargs["station_id"] = config.get("station_id", 1)
    kwargs["cov_master"] = config.get("cov_master", False)
    kwargs["fast_hvac"] = config.get("fast_hvac", False)

    return Bac0hvac(topic, **kwargs)


class Bac0hvac(altolib.AltoBridgeAgent, altolib.AltoHVAC, altolib.AltoSensor):
    """
    This is the agent for Bacnet devices. It support Carrier/Toshiba, ChenSen (Jetson Control), Daikin devices
    """

    def __init__(self, topic="", **kwargs):
        super().__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.comm_queue = PriorityQueue()
        self.cov_queue = Queue()
        self.cov_proc_queue = Queue()
        # self.build_devices()
        self.comm_tread = self.bacnet_communicate()
        self.cov_thread = None
        self.cov_proc_thread = None
        # Set self.cov_master to False config file to disable cov thread
        # This version can only be selected to one mode only (Using BAC0.cov or _bacnetcov_thread)
        # Because of that mode it might be conflict (Two cov mode run in same system) if your system consist of Carrier + Daikin in the same time
        # So please carefull that and try to avoid that situation
        if self.cov_master and self.cov_thread is None and self.cov_proc_thread is None:
            self.cov_thread = self.bacnet_cov()
            self.cov_proc_thread = self.bacnet_cov_proc()
        self._broadcat_ip = None
        self._dev_ips = set()

    def send_samples(self):
        _log.debug("sending samples")
        for dev in self.device_list.values():
            # dev.get_data()
            pass

    def build_devices(self):
        # First remove
        for devid in self.device_list:
            if devid not in self.hvac_units:
                del self.hvac_units[devid]
        self._dev_ips = set()
        for devid, ipu in self.hvac_units.items():
            dclass = device_factory(ipu[2])
            ndev = dclass(self, devid, ipu[0], ipu[1])
            self.register_new_device(ndev)
            self._dev_ips.add(ipu[0])

    def configure(
        self, config_name: str, action: str, contents: Mapping[str, Any]
    ) -> None:

        super().configure(config_name, action, contents)
        self.build_devices()
        if self.cov_master and self.cov_thread is None and self.cov_proc_thread is None:
            self.cov_thread = self.bacnet_cov()
            self.cov_proc_thread = self.bacnet_cov_proc()
        if self.comm_tread is None:
            self.comm_tread = self.bacnet_communicate()

    def bacnet_communicate(self):
        _log.debug("Starting bacnet")
        thread = Thread(target=self._bacnet_thread, name="bacnet", daemon=True)
        thread.start()
        return thread

    def bacnet_cov(self):
        _log.debug("Starting cov")
        thread = Thread(target=self._bacnetcov_thread, name="cov", daemon=True)
        thread.start()
        return thread

    def bacnet_cov_proc(self):
        _log.debug("Starting cov proc")
        thread = Thread(target=self._bacnetcov_proc_thread, name="cov_proc", daemon=True)
        thread.start()
        return thread

    def send(self, cmd, cb, **kwargs):
        """
            A command to be issued to bacnet. If cb (callback) is defined, run it with the result as parameter
        """
        # _log.debug(f"Putting {cmd} on the queue")
        devtype = kwargs.get("devtype", None)
        rw = kwargs.get("rw", False) # True = Write, False = Read

        if devtype in ["daikinDBACS"]:
            if rw:
                self.comm_queue.put_nowait((WPRIORITY, cmd, cb))
            else:
                self.comm_queue.put_nowait((RPRIORITY, cmd, cb))
        elif "ROutput" in cmd:
            cmd = cmd.replace("ROutput", "Output")
            self.comm_queue.put_nowait((RPRIORITY, cmd, cb))
        elif ("Output" in cmd):
            self.comm_queue.put_nowait((WPRIORITY, cmd, cb))
        else:
            self.comm_queue.put_nowait((RPRIORITY, cmd, cb))

    def _bacnet_thread(self):
        # BAC0.log_level("silence")
        from time import sleep

        sleep(3)
        bacnet = None
        while bacnet is None:
            try:
                if self.ip_address:
                    bacnet = BAC0.lite(
                        ip=self.ip_address, port=0xBAC0 + self.station_id
                    )
                else:
                    bacnet = BAC0.lite(port=0xBAC0 + self.station_id)
            except:
                self.station_id += 1
                if self.station_id > 50:
                    _log.critical("Could not start comunication Thread")
                    self.comm_tread = None
                    return
                bacnet = None
                sleep(2)
        lod = bacnet.whois()
        self._broadcat_ip = bacnet.localIPAddr.addrBroadcastTuple[0]
        _log.debug(f"Whois resulted in {lod}")
        for dev in self.device_list.values():
            dev.subscribe_cov(bacnet)
        while True:
            try:
                pri, cmd, cb = self.comm_queue.get()
                _log.debug(f"Executing {cmd}")
                res = None
                if cmd == "Die":
                    break
                if pri == WPRIORITY:
                    bacnet.write(cmd + " - 1")
                    res = cmd.strip().split(" ")[-1]
                elif cmd:
                    res = bacnet.read(cmd)
                self.comm_queue.task_done()
                # if cb:
                if cb and pri != WPRIORITY: # pri != WPRIORITY, update from read only.
                    cb(res)
                if self.comm_queue.qsize() > 500:
                    _log.debug(f"Queue is growing fast: {self.comm_queue.qsize()}")
            except Exception as e:
                _log.warning("Problem executing BACNet operation")
                _log.debug(f"Error was {e}")
                _log.exception(e)
        bacnet.disconnect()

    def _bacnetcov_thread(self):
        # BAC0.log_level("silence")
        try:
            s = socket(AF_INET, SOCK_DGRAM)
            s.bind(("", 0xBAC0))
        except:
            _log.debug(
                "Could not start COV thread. Is another program listeneing on 0xbac0?"
            )
            return
        while self._broadcat_ip is None:
            sleep(1)

        _log.debug(f'''self._broadcat_ip {self._broadcat_ip}''')
        daddr = Address((self._broadcat_ip, 47808))
        while True:
            msg, addr = s.recvfrom(1024)
            try:
                _log.debug("Got COV")
                predata = {
                    "msg": msg,
                    "addr": addr,
                    "daddr": daddr
                }
                self.cov_proc_queue.put_nowait(predata)
            except Exception as e:
                _log.debug(f"Problem in COV thread: {e}")

    def _bacnetcov_proc_thread(self):
        while True:
            predata = self.cov_proc_queue.get()
            self.cov_proc_queue.task_done()
            if isinstance(predata, str):
                if predata == "Die":
                    return
            try:
                msg = predata["msg"]
                addr = predata["addr"]
                daddr = predata["daddr"]
                _log.debug("COV processing")
                sa = Address(addr)
                pdu = PDU(msg, source=sa, destination=daddr)
                pdu.pduExpectingReply = False
                pdu.pduNetworkPriority = 1
                if pdu.pduData[0] != 0x81:
                    raise Exception
                xpdu = BVLPDU()
                xpdu.decode(pdu)
                pdu = xpdu
                atype = bvl_pdu_types.get(pdu.bvlciFunction)
                xpdu = pdu
                bpdu = atype()
                bpdu.decode(pdu)
                pdu = bpdu
                if pdu.pduData[0] != 0x01:
                    raise Exception
                npdu = NPDU()
                npdu.decode(pdu)
                assert npdu.npduNetMessage is None
                xpdu = APDU()
                xpdu.decode(npdu)
                apdu = xpdu
                apdu.pduSource = npdu.pduSource
                apdu.pduDestination = npdu.pduDestination
                atype = apdu_types.get(apdu.apduType)
                xpdu = apdu
                apdu = atype()
                apdu.decode(xpdu)
                atype = unconfirmed_request_types.get(apdu.apduService)
                xpdu = apdu
                apdu = atype()
                apdu.decode(xpdu)
                cov = apdu.apdu_contents()
                _log.debug(f"COV is {cov}")
                dtype, register = cov["eventObjectIdentifier"]
                if "Input" in dtype:
                    # We are only interested in Input
                    value = [
                        x
                        for x in cov["eventValues"]["changeOfState"][
                            "newState"
                        ].values()
                    ][0]
                    if addr[0] in self._dev_ips:
                        self.cov_queue.put_nowait((register, value))
                    else:
                        payload = {"value": value, "register": register}

                        topic = (
                            self.topic
                            + "hvac/"
                            + self.agent_name
                            + "/"
                            + addr[0]
                            + "/cov"
                        )
                        self.publish(topic, payload, "event")
            except Exception as e:
                _log.debug(f"Problem in COV proc thread: {e}")

    def handle_event_hvac(self, topic, message):

        if len(topic) == 2:
            dev, func = topic
        else:
            _log.debug("This should not have happened")
            return
        if func == "cov":
            loip = set([x[0] for x in self.hvac_units.values()])
            if dev in loip:
                register = message["register"]
                value = message["value"]
                for adev in self.device_list.values():
                    if adev.process_cov(register, value):
                        return

    def handle_command_hvac(self, topic, message):
        """
             Handle the commands meant for the hvac schema. Essentially the 'ac' command.
        """

        if not self.fast_hvac: # if false using old hvac handle
            super().handle_command_hvac(topic, message)
            return

        if len(topic) != 2:
            raise AltoSchemaError("HVAC command handler cannot parse topic")

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
            targetdev.immediate_notice_event(pre_command)
            # targetdev.command_was_sent()
            if donotify:
                _log.debug("handle command hvac donotify")
                self.emit_event_state(devid)
        else:
            _log.warning(f"HVAC cannot handle command {func}")

    def emit_last_command(self, devid, command):
        payload = {"device_id": devid, "subdevice_idx": 0, "type": "ac"}
        sdata = self.device_list[devid].status_data()
        if sdata:
            payload.update(sdata)
            payload.update(command)
            topic = self.topic + "hvac/" + self.agent_name + "/" + devid + "/event"
            self.publish(topic, payload, "event")

    @Core.schedule(periodic(1))
    def poll_command_queue(self):
        if self.fast_hvac:
            # _log.debug(f"FastCarrierAC poll_command_queue")
            for adev in self.device_list.values():
                adev.execute_command_queue()

    @Core.schedule(periodic(10))
    def device_send_read(self):
        if self.fast_hvac:
            # _log.debug(f"FastCarrierAC device_send_read")
            number_device_per_round = 5
            dev_sent_this_round = 0
            dev_sent_total = 0
            send_part = None
            for adev in self.device_list.values():
                if adev.current_read_part == 1:
                    dev_sent_total += 1
                    if dev_sent_total >= len(self.device_list):
                        send_part = 1
                        break
                    continue
                if adev.current_read_part == 3:
                    dev_sent_total += 1
                    if dev_sent_total >= len(self.device_list):
                        send_part = 3
                        break
                    continue
                if dev_sent_this_round < number_device_per_round:
                    # _log.debug(f"FastCarrierAC device_send_read {adev.device_id}")
                    adev.send_read_command()
                    dev_sent_this_round += 1
                else:
                    break
            if send_part is not None:
                if send_part == 1:
                    for adev in self.device_list.values():
                        adev.current_read_part = 2
                elif send_part == 3:
                    for adev in self.device_list.values():
                        adev.current_read_part = 0

    @Core.schedule(periodic(5))
    def device_check_emit_event(self):
        if self.fast_hvac:
            # _log.debug(f"FastCarrierAC device_check_emit_event")
            for adev in self.device_list.values():
                adev.check_emit_event()

    @Core.schedule(periodic(60))
    def poll_state(self):
        if not self.fast_hvac:
            # _log.debug("poll_state")
            for adev in self.device_list.values():
                adev.update_state()

    #@Core.schedule(periodic(10))
    @Core.schedule(periodic(5))
    def inform_state(self):
        if not self.fast_hvac:
            for adev in self.device_list.values():
                adev.emit_event_state()

    @Core.schedule(periodic(2))
    def process_cov(self):
        while not self.cov_queue.empty():
            register, value = self.cov_queue.get()
            for dev in self.device_list.values():
                if dev.process_cov(register, value):
                    break

    def last_rite(self):
        self.comm_queue.put_nowait((0, "Die", None))
        self.cov_proc_queue.put_nowait("Die")


def main():
    """Main method called to start the agent."""
    utils.vip_main(bac0hvac, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
