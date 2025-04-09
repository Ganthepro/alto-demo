#
# A charging station
import logging
import time
import sys
import serial
import altolib
from threading import Thread
from queue import Queue
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, RPC, Core

UNIT = 0x01

ELECMAP = {
    # "current": "current",
    "voltage": "voltage",
    "state_of_charge": "state_of_charge",
    "remaining_capacity": "remaining_capacity",
    "charging_current": "charging_current",
    
    "voltage0": "voltage0",
    "voltage1": "voltage1",
    "voltage2": "voltage2",
    "voltage3": "voltage3",
    "voltage4": "voltage4",
    "voltage5": "voltage5",
    "voltage6": "voltage6",
    "voltage7": "voltage7",
    "voltage8": "voltage8",
    "voltage9": "voltage9",
    "voltage10": "voltage10",
    "voltage11": "voltage11",
    "voltage12": "voltage12",
    "voltage13": "voltage13",
    "voltage14": "voltage14",
    "voltage15": "voltage15",
    "voltage16": "voltage16",
    "voltage17": "voltage17",
    "voltage18": "voltage18",
    "voltage19": "voltage19",
}

DEVMAP = {
    "battery_id": "battery_id",
    "count": "count",
    "state_of_health": "state_of_health",
    "temperature_zone1": "temperature_zone1",
    "temperature_zone2": "temperature_zone2",
    "temperature_zone3": "temperature_zone3",

    "error_condition": "error_condition",
    
    "cell_volttage_different": "cell_volttage_different",
    "overcurrent_charge": "overcurrent_charge",
    "overcurrent_discharge": "overcurrent_discharge",
    "short_circuit_protection": "short_circuit_protection",
    "high_temperature_protection_charge": "high_temperature_protection_charge",
    "high_temperature_protection_discharge": "high_temperature_protection_discharge",
    "low_temperature_protection_charge": "low_temperature_protection_charge",
    "low_temperature_protection_discharge": "low_temperature_protection_discharge",
    "MOS_damage_charge": "MOS_damage_charge",
    "MOS_damage_discharge": "MOS_damage_discharge",
    "communication_abnormal": "communication_abnormal",
    "overcharge_protection_0": "overcharge_protection_0",
    "overcharge_protection_1": "overcharge_protection_1",
    "overcharge_protection_2": "overcharge_protection_2",
    "overcharge_protection_3": "overcharge_protection_3",
    "overcharge_protection_4": "overcharge_protection_4",
    "overcharge_protection_5": "overcharge_protection_5",
    "overcharge_protection_6": "overcharge_protection_6",
    "overcharge_protection_7": "overcharge_protection_7",
    "overcharge_protection_8": "overcharge_protection_8",
    "overcharge_protection_9": "overcharge_protection_9",
    "overcharge_protection_10": "overcharge_protection_10",
    "overcharge_protection_11": "overcharge_protection_11",
    "overcharge_protection_12": "overcharge_protection_12",
    "overcharge_protection_13": "overcharge_protection_13",
    "overcharge_protection_14": "overcharge_protection_14",
    "overcharge_protection_15": "overcharge_protection_15",
    "overcharge_protection_16": "overcharge_protection_16",
    "overcharge_protection_17": "overcharge_protection_17",
    "overcharge_protection_18": "overcharge_protection_18",
    "overcharge_protection_19": "overcharge_protection_19",
    "overdischarge_protection_0": "overdischarge_protection_0",
    "overdischarge_protection_1": "overdischarge_protection_1",
    "overdischarge_protection_2": "overdischarge_protection_2",
    "overdischarge_protection_3": "overdischarge_protection_3",
    "overdischarge_protection_4": "overdischarge_protection_4",
    "overdischarge_protection_5": "overdischarge_protection_5",
    "overdischarge_protection_6": "overdischarge_protection_6",
    "overdischarge_protection_7": "overdischarge_protection_7",
    "overdischarge_protection_8": "overdischarge_protection_8",
    "overdischarge_protection_9": "overdischarge_protection_9",
    "overdischarge_protection_10": "overdischarge_protection_10",
    "overdischarge_protection_11": "overdischarge_protection_11",
    "overdischarge_protection_12": "overdischarge_protection_12",
    "overdischarge_protection_13": "overdischarge_protection_13",
    "overdischarge_protection_14": "overdischarge_protection_14",
    "overdischarge_protection_15": "overdischarge_protection_15",
    "overdischarge_protection_16": "overdischarge_protection_16",
    "overdischarge_protection_17": "overdischarge_protection_17",
    "overdischarge_protection_18": "overdischarge_protection_18",
    "overdischarge_protection_19": "overdischarge_protection_19",
}

R1VALUES = [
    "voltage",
    "count",
    "state_of_charge",
    "remaining_capacity",
    "state_of_health",
    "charging_current",
    "temperature_zone1",
    "temperature_zone2",
    "temperature_zone3",
    "voltage0",
    "voltage1",
    "voltage2",
    "voltage3",
    "voltage4",
    "voltage5",
    "voltage6",
    "voltage7",
    "voltage8",
    "voltage9",
    "voltage10",
    "voltage11",
    "voltage12",
    "voltage13",
    "voltage14",
    "voltage15",
    "voltage16",
    "voltage17",
    "voltage18",
    "voltage19",
]

R2VALUES = [
    "online",
    "cell_volttage_different",
    "overcurrent_charge",
    "overcurrent_discharge",
    "short_circuit_protection",
    "high_temperature_protection_charge",
    "high_temperature_protection_discharge",
    "low_temperature_protection_charge",
    "low_temperature_protection_discharge",
    "MOS_damage_charge",
    "MOS_damage_discharge",
    "communication_abnormal",
    "overcharge_protection_0",
    "overcharge_protection_1",
    "overcharge_protection_2",
    "overcharge_protection_3",
    "overcharge_protection_4",
    "overcharge_protection_5",
    "overcharge_protection_6",
    "overcharge_protection_7",
    "overcharge_protection_8",
    "overcharge_protection_9",
    "overcharge_protection_10",
    "overcharge_protection_11",
    "overcharge_protection_12",
    "overcharge_protection_13",
    "overcharge_protection_14",
    "overcharge_protection_15",
    "overcharge_protection_16",
    "overcharge_protection_17",
    "overcharge_protection_18",
    "overcharge_protection_19",
    "overdischarge_protection_0",
    "overdischarge_protection_1",
    "overdischarge_protection_2",
    "overdischarge_protection_3",
    "overdischarge_protection_4",
    "overdischarge_protection_5",
    "overdischarge_protection_6",
    "overdischarge_protection_7",
    "overdischarge_protection_8",
    "overdischarge_protection_9",
    "overdischarge_protection_10",
    "overdischarge_protection_11",
    "overdischarge_protection_12",
    "overdischarge_protection_13",
    "overdischarge_protection_14",
    "overdischarge_protection_15",
    "overdischarge_protection_16",
    "overdischarge_protection_17",
    "overdischarge_protection_18",
    "overdischarge_protection_19",
]

MBPORT = 502

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class BatteryDevice(
    altolib.AltoBattery, altolib.AltoElectricSensor, altolib.AltoDeviceSensor
):
    """
    This is the device that will handle one battery, sub devices will be batterys
    """

    def __init__(
            self, controller, devid="station_1", slots={}, nb_subdev=9, eject_slot_map = None, read_slot_map = None
    ):

        super().__init__(controller, devid, nb_subdev)
        self.eject_slot_map = eject_slot_map
        self.read_slot_map = read_slot_map
        self.slots = slots
        self._suboi = 0  # Sub device of interest
        self.battery_id = ["Empty" for i in range(self.number_subdevices)]
        self.serial = [v for v in slots.values()]
        self.relay_port = "/dev/ttyS0"
        self.slot_online_status = [False for i in range(self.number_subdevices)]
        self.charging = [False for i in range(self.number_subdevices)]
        self.in_slot = [False for i in range(self.number_subdevices)]
        # self.loaded = False
        self.loaded = [False for i in range(self.number_subdevices)]
        self.is_booting = True
        # Now setup the map
        self.datapoint_supported["device"] = [x for x in DEVMAP.keys()]
        self.datapoint_supported["electric"] = [x for x in ELECMAP.keys()]
        # if self.battery_id != "Empty":
        self._sample_init()

        # self.fake_put_bat = False

    def _sample_init(self):
        for idx in range(0, self.number_subdevices):
            self.current_state[idx] = {"sensor": {"device": {}, "electric": {}}}
            # setattr(self, f"to_electric _voltage{0}", self.to_electric_voltage)
        self.initialise_data("electric", ELECMAP.keys())
        self.initialise_data("device", DEVMAP.keys())
        self.name_subdevices = [f"slot_{i + 1}" for i in range(0, self.number_subdevices)]
        
        self.restict_time_eject = None
        self._init_confirm_ejected_body()

    def _init_confirm_ejected_body(self):
        self.number_of_try_to_eject = 0
        self.confirm_ejected_body = {
            "ejected_battery_id": "",
            "ejected_battery_percent": -1,
            "ejected_slot_idx": -1,
            # "gateway_name": "beta_ev_tower_001",
            "gateway_name": self.device_id,
            "payment_type": "QR",
            "inserted_battery_id": "",
            "inserted_battery_percent": -1,
            "inserted_slot_idx": -1
        }

    def _emit_event_confirm_ejected(self, devid, payload):
        """
        Emit the event through the controller
        """
        _log.info("ejecting _emit_event_confirm_ejected")

        if payload:
            topic = self.controller.topic + "charger/" + self.controller.agent_name + "/" + devid + "/confirm_ejected"
            self.controller.publish(topic, payload, "event")

    def _emit_event_ejected_failed(self, devid, payload):
        """
        Emit the event through the controller
        """
        _log.info("ejecting _emit_event_ejected_failed")

        if payload:
            topic = self.controller.topic + "charger/" + self.controller.agent_name + "/" + devid + "/ejected_failed"
            self.controller.publish(topic, payload, "event")

    @property
    def data_map(self):
        """
        use self._suboi to generate the current map
        """

        nmap = {}
        for k, v in {**ELECMAP, **DEVMAP}.items():
            v = v.format(self._suboi)
            if k not in nmap:
                nmap[k] = v
        return nmap

    @data_map.setter
    def data_map(self, x):
        return

    def reset(self, subdev_id):
        """
        Go back to nothing
        """
        self.number_subdevices = 9
        # self.battery_id = ["Empty" for i in range(self.number_subdevices)]
        self.battery_id[subdev_id] = "Empty"
        # self.current_state[str(subdev_id)] =  {"sensor": {"device": {}, "electric": {}}}
        # self.current_state[subdev_id] =  {"sensor": {"device": {}, "electric": {}}}
        self.reset_datapoints(subdev_id)

    def reset_datapoints(self, subdev_id):
        sensor_types = {
            "device": DEVMAP.keys(),
            "electric": ELECMAP.keys()
        }
        for sensor_type, datapoints in sensor_types.items():
            thissd = self.current_state[subdev_id]["sensor"][sensor_type]
            for attr in set(self.datapoint_supported[sensor_type]).intersection(
                set(datapoints)
            ):
                thissd[attr] = None
            if "timestamp" not in thissd:
                thissd["timestamp"] = None

    def send_sample_thread(self):
        for slot, port in self.slots.items():
            self.subdev_send_sample_thread(self.name_subdevices.index(slot), port)
        self.is_booting = False

    def subdev_send_sample_thread(self, subdev_id, port):
        # with self.thread_lock:
        try:
            client = ModbusClient(
                method="rtu", port=port, timeout=2, baudrate=9600
            )
            _log.debug(f"Read registers for slot {port}")
            nbtries = 2
            bat_id = ""
            for _ in range(0, nbtries):
                try:
                    rr = client.read_holding_registers(1000, 13, unit=UNIT)
                    for c2 in rr.registers:
                        # c2 is a 16 bits quantity, 2 characters
                        if c2 == 0:
                            break
                        c = chr(c2 >> 8)  # First byte
                        if c != "\x00":
                            bat_id += c
                        c = chr(c2 & 0x00FF)  # First byte
                        if c != "\x00":
                            bat_id += c

                    break
                except:
                    bat_id = ""
                    pass

            self.in_slot[subdev_id] = self.check_slot_state(subdev_id)

            if not self.charging[subdev_id] and self.in_slot[subdev_id]:
                self.charge_slot(subdev_id)

            if self.charging[subdev_id]:
                self.trigger_charge(subdev_id)

            if bat_id == "":
                self.slot_online_status[subdev_id] = False
                self.controller.emit_event_online(
                    self.device_id, self._command_online(subdev_id)
                )
                if self.battery_id[subdev_id] != "Empty":
                    self.controller.emit_event_eject(
                        self.device_id, self._command_eject(subdev_id)
                    )
                    self.reset(subdev_id)
                client.close()
                return

            _log.debug(f"Device ID is {bat_id}")
            rr = client.read_holding_registers(0, 29, unit=UNIT)
            r1vals = {}
            r1vals["battery_id"] = bat_id
            for v, lbl in zip(rr.registers, R1VALUES):
                _log.debug(f"Set {lbl} to {v}")
                r1vals[lbl] = v
            errcond = []
            rr = client.read_coils(0, 52, unit=UNIT)
            for v, n in zip(rr.bits, R2VALUES):
                if v:
                    errcond.append(n)
            r2vals = {}
            # r2vals["battery_id"] = bat_id
            for v, n in zip(rr.bits, R2VALUES):
                # _log.debug(f"Set {n} to {v}")
                r2vals[n] = v

            if bat_id != self.battery_id[subdev_id]:
                if self.battery_id[subdev_id] != "Empty":
                    self.controller.emit_event_eject(
                        self.device_id, self._command_eject(subdev_id)
                    )
                    self.reset(subdev_id)
                    # _log.debug(f"apiagent reset")
                self.battery_id[subdev_id] = bat_id
                # self.number_subdevices = 2#r1vals["count"]
                # self._sample_init()
                # self.reset(subdev_id)
                if not self.is_booting:
                    self.loaded[subdev_id] = True
                #     self.loaded = True
                # self.loaded = True
                # self.loaded[subdev_id] = True
            # fake put bat
            # if self.fake_put_bat and subdev_id == 6:
            #     # _log.debug(f"apiagent subdev_id {subdev_id}")
            #     self.reset_datapoints(subdev_id)
            #     # _log.debug(f"apiagent self.current_state[{subdev_id}] {self.current_state[subdev_id]}")
            #     self.fake_put_bat = False
            #     if not self.is_booting:
            #         self.loaded[subdev_id] = True
        except Exception as e:
            _log.exception(e)
        else:
            # _log.debug(f"apiagent subdev_id else {subdev_id}")
            try:
                # _log.debug(f"apiagent subdev_id else try {subdev_id}")
                self.slot_online_status[subdev_id] = True
                self.controller.emit_event_online(
                    self.device_id, self._command_online(subdev_id)
                )
                # del r1vals["voltage"]
                # del r1vals["count"]
                if "online" in errcond:
                    _log.debug("device is online")
                    if self.slot_online_status[subdev_id]:
                        self.slot_online_status[subdev_id] = False
                        self.controller.emit_event_online(
                            self.device_id, self._command_online(subdev_id)
                        )
                    errcond.remove("online")
                else:
                    _log.debug(f"device is offline: {self.slot_online_status[subdev_id]}")
                    if not self.slot_online_status[subdev_id]:
                        _log.debug(f"online status: {self.slot_online_status[subdev_id]}")
                        self.slot_online_status[subdev_id] = True
                        self.controller.emit_event_online(
                            self.device_id, self._command_online(subdev_id)
                        )
                    loerrs = []
                    # for subdev_idx in range(self.number_subdevices):
                    #     loerrs = []
                    #     for x in errcond:
                    #         if x.startswith("Overcharge"):
                    #             if x == f"Overcharge Protection {subdev_idx}":
                    #                 loerrs.append("Overcharge Protection")
                    #         elif x.startswith("Overdischarge"):
                    #             if x == f"Overdischarge Protection {subdev_idx}":
                    #                 loerrs.append("Overdischarge Protection")
                    #         else:
                    #             loerrs.append(x)
                    #         loerrs.sort()

                    ##testing until line 286
                    r1vals_elec = {}
                    r1vals_dev = {}
                    for k, v in r1vals.items():
                        if k in ELECMAP:
                            r1vals_elec[k] = v
                        elif k in DEVMAP:
                            r1vals_dev[k] = v
                    for k, v in r2vals.items():
                        if k in ELECMAP:
                            r1vals_elec[k] = v
                        elif k in DEVMAP:
                            r1vals_dev[k] = v
                # _log.debug(f"r1vals_dev {r1vals_dev}")
                # _log.debug(f"""r1vals_dev {self.current_state[subdev_id]["sensor"]["device"]}""")
                    # _log.debug(f"r1vals_elec: {r1vals_elec}")
                    # _log.debug(f"r1vals_dev: {r1vals_dev}")
                # _log.debug(f"apiagent subdev_id else try before set_sen {subdev_id}")
                self.set_sensor_data(
                    {**r1vals_elec, **{"error_condition": loerrs}}, subdev_id, "electric"
                )
                self.set_sensor_data(
                    {**r1vals_dev}, subdev_id, "device"
                )
                # if self.loaded == True :
                if self.loaded[subdev_id] == True:
                    # _log.debug(f"apiagent self.current_state[{subdev_id}] {self.current_state[subdev_id]}")
                    # time.sleep(3)
                    self._init_confirm_ejected_body()
                    self.confirm_ejected_body["inserted_battery_id"] = self.current_state[subdev_id]["sensor"]["device"]["battery_id"]
                    self.confirm_ejected_body["inserted_battery_percent"] = self.current_state[subdev_id]["sensor"]["electric"]["state_of_charge"]
                    self.confirm_ejected_body["inserted_slot_idx"] = subdev_id
                    
                    self.controller.emit_event_load(
                        self.device_id, self._command_load(subdev_id)
                    )
                # self.loaded = False
                self.loaded[subdev_id] = False
            except Exception as e:
                _log.debug(f"Modbus we have a problem for {port}: {e}")
        finally:
            client.close()

    #    def event_sensor_sample(self, subdevice_idx, sensor_type, datapoint ) :
    #        """
    #        Needs to be overloaded to set self._suboi
    #        """
    #        if subdevice_idx == "all":
    #            for idx in range(0, self.number_subdevices):
    #                self._suboi = idx
    #                super().event_sensor_sample(idx, sensor_type,  datapoint )
    #        else:
    #            self._suboi = self.subdevice_name_to_idx(subdevice_idx)
    #            super().event_sensor_sample(subdevice_idx, sensor_type,  datapoint )

    def set_sensor_data(self, data, subdevice, sensor_type=None):
        """
        Needs to be overloaded to set self._suboi
        """
        if subdevice == "all":
            for idx in range(0, self.number_subdevices):
                self._suboi = idx
                super().set_sensor_data(data, idx, sensor_type)
        else:
            self._suboi = self.subdevice_name_to_idx(subdevice)
            super().set_sensor_data(data, subdevice, sensor_type)

    def to_electric_voltage(self, val):
        return round(val / 100, 2)

    def to_electric_state_of_charge(self, val):
        return round(val * 1.0, 2)

    def to_electric_remaining_capacity(self, val):
        return round(val * 0.01, 2)

    def to_electric_state_of_health(self, val):
        return round(val * 1.0, 2)

    def to_electric_charging_current(self, val):
        return round(val * 0.01, 2)

    def to_electric_temperature_zone1(self, val):
        return round(val * 1.0, 2)

    def to_electric_temperature_zone2(self, val):
        return round(val * 1.0, 2)

    def to_electric_temperature_zone3(self, val):
        return round(val * 1.0, 2)

    def to_electric_voltage0(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage1(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage2(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage3(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage4(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage5(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage6(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage7(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage8(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage9(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage10(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage11(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage12(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage13(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage14(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage15(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage16(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage17(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage18(self, val):
        return round(val * 0.001, 2)

    def to_electric_voltage19(self, val):
        return round(val * 0.001, 2)

    def to_electric_remaining_capacity(self, val):
        return round(val / 100, 2)

    def to_electric_charging_current(self, val):
        return round(val / 100, 2)

    def to_electric_current(self, val):
        return round(val / 100, 2)

    def _command_eject(self, subdev_id, doit=True):
        msg = {
            "device_id": self.device_id,
            "subdevice_idx": subdev_id,
            "loaded_device_id": self.battery_id[subdev_id],
        }
        return msg

    def _command_load(self, subdev_id, doit=True):
        if self.battery_id[subdev_id] != "Empty":
            msg = {
                "device_id": self.device_id,
                "subdevice_idx": subdev_id,
                "loaded_device_id": self.battery_id[subdev_id],
            }
        else:
            msg = {
                "device_id": self.device_id,
                "subdevice_idx": subdev_id,
                "loaded_device_id": False,
            }
        # _log.debug(f"apiagent {msg}")
        return msg

    def _command_online(self, subdev_id, doit=True):
        msg = {
            "device_id": self.device_id,
            "subdevice_idx": subdev_id,
            "online": self.slot_online_status[subdev_id],
        }
        return msg

    # def eject(self, subdev_id):
    #     # fake put bat
    #     # if subdev_id == 2:
    #     #     self.fake_put_bat = True

    #     _log.debug(f"start ejecting {self.device_id} {subdev_id}")
    #     self.disable_charge(subdev_id)
    #     self.eject_battery(subdev_id)
    #     time.sleep(0.1)
    #     self.eject_battery(subdev_id)
    #     time.sleep(0.1)
    #     self.eject_battery(subdev_id)
    #     time.sleep(0.1)
    #     self.eject_battery(subdev_id)

    def eject(self, subdev_id, **kwargs):
        # fake put bat
        # if subdev_id == 2:
        #     self.fake_put_bat = True
        
        cmd_source = "rider"
        message = kwargs.get("message", None)
        if message is not None:
            _log.info(f"ejecting message {message}")
            cmd_source = message.get("source", cmd_source)
        _log.info(f"start ejecting {self.device_id} {subdev_id}, trying number {self.number_of_try_to_eject}")
        if self.restict_time_eject:
            while time.time() - self.restict_time_eject < 0.1:
                pass
        self.restict_time_eject = time.time()

        self.disable_charge(subdev_id) # after we have checked, we found that this Modbus is synced
        # _log.debug(f"start ejecting disable_charge")
        while time.time() - self.restict_time_eject < 0.1:
            pass
        self.restict_time_eject = time.time()
        self.eject_battery(subdev_id) # subdev_id
        # _log.debug(f"start ejecting eject_battery")
        while time.time() - self.restict_time_eject < 0.1:
            pass
        self.restict_time_eject = time.time()
        # _log.debug(f"start ejecting restict_time_eject")
        if self.check_slot_state(subdev_id): # subdev_id
            if self.number_of_try_to_eject < 10:
                self.number_of_try_to_eject += 1
                self.eject(subdev_id, **kwargs)
            else:
                self.number_of_try_to_eject = 0
                self.confirm_ejected_body["ejected_battery_id"] = self.current_state[subdev_id]["sensor"]["device"]["battery_id"]
                self.confirm_ejected_body["ejected_battery_percent"] = self.current_state[subdev_id]["sensor"]["electric"]["state_of_charge"]
                self.confirm_ejected_body["ejected_slot_idx"] = subdev_id
                self.confirm_ejected_body["source"] = cmd_source
                self._emit_event_ejected_failed(self.device_id, self.confirm_ejected_body)
                self._init_confirm_ejected_body()
        else:
            self.number_of_try_to_eject = 0
            self.confirm_ejected_body["ejected_battery_id"] = self.current_state[subdev_id]["sensor"]["device"]["battery_id"]
            self.confirm_ejected_body["ejected_battery_percent"] = self.current_state[subdev_id]["sensor"]["electric"]["state_of_charge"]
            self.confirm_ejected_body["ejected_slot_idx"] = subdev_id
            self.confirm_ejected_body["source"] = cmd_source
            self._emit_event_confirm_ejected(self.device_id, self.confirm_ejected_body)
            self._init_confirm_ejected_body()
        
    def charge_slot(self, subdev_id):
        """

        :param port: serial port to connect: eg. "/dev/ttyS0"
        :return: self.charging
        """
        slot_state = self.check_slot_state(subdev_id)
        if slot_state:
            self.disable_charge(subdev_id)
            self.init_config_charge(subdev_id)
            self.trigger_charge(subdev_id)
            self.charging[subdev_id] = True

        return self.charging

    def check_slot_state(self, subdev_id, buad=9600, timeout=1.0):
        """
        Check, is there any battery in slot?
        """

        # Sync hardware slot with software slot
        read_slot_map = subdev_id
        if self.read_slot_map is not None:
            if str(subdev_id) in self.read_slot_map:
                read_slot_map = self.read_slot_map[str(subdev_id)]
                _log.info(f"read_slot_map {subdev_id} {read_slot_map}")
                subdev_id = read_slot_map

        slot = subdev_id + 1
        try:
            section1 = [1, 2, 3, 4, 5, 6]
            section2 = [7, 8, 9]
            ser = serial.Serial(self.relay_port, buad, timeout=timeout)
            if slot in section1:
                ser.write(b'Read SW@001')
            elif slot in section2:
                ser.write(b'Read SW@002')
            else:
                raise NotImplementedError('Not implemented yet')
            res = ser.read(6)
            ser.close()
            res = res.decode("utf-8")
            if res.find("@") != -1:
                get_slot_state = res.split("@")
                if len(get_slot_state) >= 2:
                    slot_state = "0x" + get_slot_state[0]
                    state_binary = int(slot_state, 0)
                    state_bi_string = f"{state_binary:0>16b}"
                    if slot in section1:
                        if state_bi_string[len(state_bi_string) - slot] == "0":
                            return False
                        else:
                            return True
                    elif slot in section2:
                        if state_bi_string[len(state_bi_string) - (slot - 6)] == "0":
                            return False
                        else:
                            return True
                else:
                    return False
        except:
            pass
        return False

    def eject_battery(self, subdev_id, buad=9600, timeout=1.0):
        """
        Eject one slot
        """

        # Sync hardware slot with software slot
        eject_slot_map = subdev_id
        if self.eject_slot_map is not None:
            if str(subdev_id) in self.eject_slot_map:
                eject_slot_map = self.eject_slot_map[str(subdev_id)]
                _log.info(f"eject_slot_map {subdev_id} {eject_slot_map}")
                subdev_id = eject_slot_map

        EJECT_COMMAND_MAP = {
            "send": [
                "Set LOCK1@001",
                "Set LOCK2@001",
                "Set LOCK3@001",
                "Set LOCK4@001",
                "Set LOCK5@001",
                "Set LOCK6@001",
                "Set LOCK1@002",
                "Set LOCK2@002",
                "Set LOCK3@002",
            ],
            "response": [
                "Set LOCK1 OK@001",
                "Set LOCK2 OK@001",
                "Set LOCK3 OK@001",
                "Set LOCK4 OK@001",
                "Set LOCK5 OK@001",
                "Set LOCK6 OK@001",
                "Set LOCK1 OK@002",
                "Set LOCK2 OK@002",
                "Set LOCK3 OK@002",
            ]
        }

        slot = subdev_id + 1
        try:
            ser = serial.Serial(self.relay_port, buad, timeout=timeout)
            ser.write(EJECT_COMMAND_MAP["send"][slot - 1].encode("utf-8"))
            res = ser.read(len(EJECT_COMMAND_MAP["response"][slot - 1]))
            ser.close()
            res = res.decode("utf-8")
            if res == EJECT_COMMAND_MAP["response"][slot - 1]:
                return True
            else:
                return False
        except:
            pass
        return False

    def disable_charge(self, subdev_id, unit=0, buad=9600, timeout=1.0):
        try:
            client = ModbusClient(
                method="rtu", port=self.serial[subdev_id], timeout=timeout, baudrate=buad
            )
            rq = client.write_register(0, 0, unit=unit)
            client.close()
            # print(rq)
            return True
        except:
            pass
        return False

    def init_config_charge(self, subdev_id, baudrate=9600, timeout=3.0):
        MAYBESETTING = b'\x00\x0F\x00\x01\x00\x02\x02\xCA\x03\xE8\x79\xCF'
        try:
            client = serial.Serial(self.serial[subdev_id], baudrate, timeout=timeout)
            client.write(MAYBESETTING)
            print(client.read(8))
            client.close()
            return True
        except Exception as e:
            print(e)
            pass
        return False

    # TODO error
    def trigger_charge(self, subdev_id, unit=0, buad=9600, timeout=1.0):
        try:
            client = ModbusClient(
                method="rtu", port=self.serial[subdev_id], timeout=timeout, baudrate=buad
            )
            rq = client.write_register(0, 0xff, unit=unit)
            client.close()
            # print(rq)
            return True
        except:
            pass
        return False


def charger(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Blremote
    :rtype: Blremote
    """
    try:
        config = utils.load_config(config_path)
    except:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "charger")
    # Key is slot number and value serial device string
    kwargs["slots"] = config.get("slots", {})
    kwargs["eject_slot_map"] = config.get("eject_slot_map", {})
    kwargs["read_slot_map"] = config.get("read_slot_map", {})

    return Charger(topic, **kwargs)


class Charger(altolib.AltoSensor, altolib.AltoCharger):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        self._sampling_rate_cd = 60 # overlide default start polling time
        self.auto_send = True  # We update regularly or when we get a command
        self.is_bridge = True
        self.queue = Queue()
        _log.debug("vip_identity: " + self.core.identity)
        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

    def build_devices(self):
        print("self.slots", self.slots)
        # for sl, dev in self.slots.items():
        self.register_new_device(BatteryDevice(self, self.dev_id, self.slots, 9, self.eject_slot_map, self.read_slot_map))

    def send_samples(self):

        for device in self.device_list.values():
            self.queue.put_nowait(device)
            # getsample = Thread(target=device.send_sample_thread)
            # getsample.setDaemon(True)
            # getsample.start()

    def _send_samples_thread(self):
        while True:
            adev = self.queue.get()
            self.queue.task_done()
            if adev == "Die":
                return
            adev.send_sample_thread()

    def last_rites(self):
        self.queue.put_nowait("Die")

    @RPC.export
    def get_current_state(self, dev_id):
        """
        you can call this function from other agents by this
        line of code

        self.vip.rpc.call('charger', 'get_current_state').get()

        :return: current state of the tower station data
        """
        # tmp = self.device_list[dev_id].current_state.copy()
        # for i in range(9):
        #     try:
        #         tmp.pop(str(i))
        #     except:
        #         pass
        # return tmp
        return self.device_list[dev_id].current_state


def main():
    """Main method called to start the agent."""
    utils.vip_main(charger, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
