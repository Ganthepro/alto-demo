#@title Latest ModbusSerial (24/02/2023)
"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
from queue import PriorityQueue
from threading import Thread

import pendulum
from pymodbus.client import ModbusSerialClient
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.exceptions import ConnectionException

from altolib import AltoHealth
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"

WRITEPRIORITY = 1
READPRIORITY = 5

def device_factory(devtype: str):
    if devtype == "schneider_pm3255":
        return SchneiderPM3255
    elif devtype == "btu_dataindustrial_3050":
        return BTUDataIndustrial3050
    elif devtype == "vsd_ach550":
        return VSDACH550
    elif devtype == "vsd_sako_ski600":
        return VSDSAKOSKI600

    raise ValueError(f"Unknown device type: {devtype}")


def decode_factory(val, decode_type):
    if decode_type == "U16":
        return val.decode_16bit_uint()
    elif decode_type == "U32":
        return val.decode_32bit_uint()
    elif decode_type == "U64":
        return val.decode_64bit_uint()
    elif decode_type == "I8":
        return val.decode_8bit_int()
    elif decode_type == "I16":
        return val.decode_16bit_int()
    elif decode_type == "I32":
        return val.decode_32bit_int()
    elif decode_type == "I64":
        return val.decode_64bit_int()
    elif decode_type == "F32":
        return val.decode_32bit_float()

    raise ValueError(f"Unknown decode type: {decode_type}")


class PqElement(object):
    def __init__(self, priority: int, device_id: str, args: str):
        self._priority = priority
        self._device_id = device_id
        self._args = args

    def __lt__(self, other):
        return self.priority < other.priority

    @property
    def priority(self):
        return self._priority
    
    @property
    def device_id(self):
        return self._device_id

    @property
    def args(self):
        return self._args


class ModbusSerialDevice:
    """
    This is an abstract class for Modbus Serial devices.
    
    """

    def __init__(self, controller: object, device_id: str, port: int | str, unit: int, nb_subdev: int):
        self._controller = controller
        self._device_id = device_id
        self.port = port
        self.unit = unit
        self.number_subdevices = nb_subdev
        self.byteorder = Endian.Big
        self.wordorder = Endian.Big
        self.current_state = dict()
        for idx in range(nb_subdev):
            self.current_state[idx] = dict()
        self.device_state = "DISCONNECTED"
        self.newvals = list()

        # Must Implement this in child class
        self.sensor_type = None
        self.subdevice_name = list()
        self.data_map = dict()
        self.map = dict()

    def _initialise_data(self):
        try:
            for idx in range(self.number_subdevices):
                self.current_state[idx][self.sensor_type] = dict()
                for datapoint in self.data_map:
                    self.current_state[idx][self.sensor_type][datapoint] = None
            _log.debug(f"Initialised data: {self.current_state}")
        except Exception as e:
            _log.exception(f"Error initialising data: {e}")

    def send_sample_thread(self):
        self.newvals = [{} for _ in range(self.number_subdevices)]
        # Get Connector of Modbus RTU from Serial Port ('/dev/ttySx')
        mb_serial = self._controller.get_connector(self.port)
        if mb_serial is None:
            self.device_state = "DISCONNECTED"
            self._controller.custom_health.update_status_payload(
                name=self._device_id,
                type_label="device",
                status=self.device_state,
                context=f"Modbus Serial Disconnected"
            )
            _log.warning(f"Modbus Serial Disconnected: {self._device_id}")
            return

        # Get Modbus Data by Function
        for func, func_values in self.map.items():
            try:
                if func == "0x01":
                    self.read_coils(mb_serial, func_values)
                elif func == "0x02":
                    self.read_discrete_inputs(mb_serial, func_values)
                elif func == "0x03":
                    self.read_holding_registers(mb_serial, func_values)
                elif func == "0x04":
                    self.read_input_registers(mb_serial, func_values)
            except ConnectionException as e:
                _log.exception(f"{self.__class__.__name__ } Connection Error: {e}")
                self.device_state = "DISCONNECTED"
                self._controller.custom_health.update_status_payload(
                    name=self._device_id,
                    type_label="device",
                    status="DISCONNECTED",
                    context=f"Error, Device Disconnected"
                )
            except Exception as err:
                _log.exception(f"{self.__class__.__name__} send_sample_thread Error: {err}")

    def read_coils(self, modbus_client, function_values: list):
        newvals = [{} for _ in range(self.number_subdevices)]
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_colis(addr, nb_reg, slave=self.unit)

            if not val.isError():
                for datapoint, address, size, subdev_idx in values:
                    _log.debug(f"datapoint: {datapoint}")
                    ret = val.bits[address: address + size]
                    newvals[subdev_idx][datapoint] = ret[0]
                    _log.debug(f"{datapoint}: {ret}")
            else:
                _log.warning(f"Error reading {self._device_id} at address {addr}")
                self._controller.custom_health.update_status_payload(
                    name=self._device_id, 
                    type_label="device", 
                    status="DISCONNECT", 
                    context=f"Error Reading Data"
                )
                
        for idx, data in enumerate(newvals):
            if data:
                self.format_data(data, idx, self.sensor_type)
            else:
                _log.warning(f"No data in {self._device_id} subdevice: {idx}")

    def read_discrete_inputs(self, modbus_client, function_values: list):
        newvals = [{} for _ in range(self.number_subdevices)]
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_discrete_registers(addr, nb_reg, slave=self.unit)

            if not val.isError():
                for datapoint, address, size, subdev_idx in values:
                    _log.debug(f"datapoint: {datapoint}")
                    ret = val.bits[address: address + size]
                    newvals[subdev_idx][datapoint] = ret[0]
                    _log.debug(f"{datapoint}: {ret}")
            else:
                _log.warning(f"Error reading {self._device_id} at address {addr}")
                self._controller.custom_health.update_status_payload(
                    name=self._device_id, 
                    type_label="device",
                    status="DISCONNECT",
                    context=f"Error Reading Data"
                )
                
        for idx, data in enumerate(newvals):
            if data:
                self.format_data(data, idx, self.sensor_type)
            else:
                _log.warning(f"No data in {self._device_id} subdevice: {idx}")

    def read_holding_registers(self, modbus_client, function_values: list):
        newvals = [{} for _ in range(self.number_subdevices)]
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_holding_registers(addr, nb_reg, slave=self.unit)

            if not val.isError():
                for datapoint, address, size, subdev_idx, decode_type in values:
                    _log.debug(f"datapoint: {datapoint}")
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        val.registers[address: address + size],
                        byteorder=self.byteorder,
                        wordorder=self.wordorder
                    )
                    decode_value = decode_factory(decoder, decode_type)
                    if decode_value is not None:
                        newvals[subdev_idx][datapoint] = decode_value
                        _log.debug(f"{datapoint}: {decode_value}")
            else:
                _log.warning(f"Error reading {self._device_id} at address {addr}")
                self._controller.custom_health.update_status_payload(
                    name=self._device_id, 
                    type_label="device", 
                    status="DISCONNECT", 
                    context=f"Error Reading Data"
                )
        
        for idx, data in enumerate(newvals):
            if data:
                self.format_data(data, idx, self.sensor_type)
            else:
                _log.warning(f"No data in {self._device_id} subdevice: {idx}")

    def read_input_registers(self, modbus_client, function_values: list):
        newvals = [{} for _ in range(self.number_subdevices)]
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_input_registers(addr, nb_reg, slave=self.unit)

            if not val.isError():
                for datapoint, address, size, subdev_idx, decode_type in values:
                    _log.debug(f"datapoint: {datapoint}")
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        val.registers[address: address + size],
                        byteorder=self.byteorder,
                        wordorder=self.wordorder
                    )
                    decode_value = decode_factory(decoder, decode_type)
                    if decode_value is not None:
                        newvals[subdev_idx][datapoint] = decode_value
                        _log.debug(f"{datapoint}: {decode_value}")
            else:
                _log.warning(f"Error reading {self._device_id} at address {addr}")
                self._controller.custom_health.update_status_payload(
                    name=self._device_id, 
                    type_label="device", 
                    status="DISCONNECT", 
                    context=f"Error Reading Data"
                )

        for idx, data in enumerate(newvals):
            if data:
                self.format_data(data, idx, self.sensor_type)
            else:
                _log.warning(f"No data in {self._device_id} subdevice: {idx}")

    def format_data(self, data: dict, subdevice_idx: int, sensor_type: str):
        _log.debug(f"Set data: {data}, subdevice_idx: {subdevice_idx}, sensor_type: {sensor_type}")
        try:
            for datapoint, value in data.items():
                if datapoint in self.data_map:
                    if value is not None:
                        convert_unit = getattr(
                            self,
                            f"to_{sensor_type}_{datapoint}",
                            lambda x: x
                        )
                        value = convert_unit(value)
                        self.current_state[subdevice_idx][sensor_type][datapoint] = value
                        data[datapoint] = value
                    else:
                        self.current_state[subdevice_idx][sensor_type][datapoint] = "NaN"
                        data[datapoint] = "NaN"
            data.update({
                "device_id": self._device_id,
                "type": sensor_type,
                "subdevice_idx": subdevice_idx,
                "subdevice_name": self.subdevice_name[subdevice_idx]
            })
            self.device_state = "GOOD"
            self._controller.custom_health.update_status_payload(
                        name=self._device_id, 
                        type_label="device", 
                        status="GOOD", 
                        context=""
                    )
            self._emit_data(data)
        except Exception as e:
            _log.exception(f"Error formatting data: {e}")

    def _emit_data(self, data):
        _log.debug(f"Emit data: {data}")
        self._controller.publish(data, 'event')
    
    @property
    def status(self) -> list[str, str]:
        return [self._device_id, self.device_state]


class SchneiderPM3255(ModbusSerialDevice):

    def __init__(self, controller, device_id, port, unit, nb_subdev):
        super().__init__(controller, device_id, port, unit, nb_subdev)
        self.sensor_type = "electric"
        self.subdevice_name = [
            "total",
            "phase_1",
            "phase_2",
            "phase_3",
            "L1-L2",
            "L2-L3",
            "L3-L1"
        ]
        self.data_map = {
            "voltage": "voltage",
            "current": "current",
            "power": "power",
            "power_apparent": "power_apparent",
            "power_factor": "power_factor",
            "frequency": "frequency",
            "energy": "energy"
        }
        self.map = {
            "0x03": [
                [
                    0x0BB7,  # 2999
                    6,
                    [
                        # name, addr, num_reg, subdev_idx, data_type
                        ["current", 0, 2, 1, "F32"],
                        ["current", 2, 2, 2, "F32"],
                        ["current", 4, 2, 3, "F32"]
                    ]
                ],
                [
                    0x0BCB,  # 3019
                    14,
                    [
                        ["voltage", 0, 2, 4, "F32"],  # 3019
                        ["voltage", 2, 2, 5, "F32"],  # 3021
                        ["voltage", 4, 2, 6, "F32"],  # 3023
                        ["voltage", 8, 2, 1, "F32"],  # 3027
                        ["voltage", 10, 2, 2, "F32"],  # 3029
                        ["voltage", 12, 2, 3, "F32"]  # 3031
                    ]
                ],
                [
                    0x0BED,  # 3053
                    24,
                    [
                        ["power", 0, 2, 1, "F32"],  # 3053
                        ["power", 2, 2, 2, "F32"],  # 3055
                        ["power", 4, 2, 3, "F32"],  # 3057
                        ["power", 6, 2, 0, "F32"],  # 3059
                        ["power_apparent", 16, 2, 1, "F32"],  # 3069
                        ["power_apparent", 18, 2, 2, "F32"],  # 3071
                        ["power_apparent", 20, 2, 3, "F32"],  # 3073
                        ["power_apparent", 22, 2, 0, "F32"],  # 30
                    ]
                ],
                [
                    0x0C0B,  # 3083
                    2,
                    [
                        ["power_factor", 0, 2, 0, "F32"],  # 3083
                    ]
                ],
                [
                    0x0C25,  # 3109
                    2,
                    [
                        ["frequency", 0, 2, 0, "F32"],  # 3109
                    ]
                ],
                [
                    0xB06D,  # 45165
                    2,
                    [
                        ["energy", 0, 2, 0, "F32"],  # 45165
                    ]
                ]
            ]
        }
        self._initialise_data()

    def to_electric_voltage(self, val):
        return val

    def to_electric_current(self, val):
        return val

    def to_electric_power_factor(self, val):
        return val

    def to_electric_power(self, val):
        return val

    def to_electric_power_reactive(self, val):
        return val

    def to_electric_power_apparent(self, val):
        return val

    def to_electric_energy(self, val):
        return val

    def to_electric_frequency(self, val):
        return val


class BTUDataIndustrial3050(ModbusSerialDevice):

    def __init__(self, controller, port, device_name, unit, nb_subdev):
        super().__init__(controller, port, device_name, unit, nb_subdev)
        self.wordorder = Endian.Little
        self.subdevice_name = ["btu_meter"]
        self.sensor_type = "btu_meter"
        self.data_map = {
            "flow_rate": "flow_rate",
            "total_flow": "total_flow",
            "energy_rate": "energy_rate",
            "energy_total": "energy_total",
            "temp_1": "temp_1",
            "temp_2": "temp_2",
            "temp_delta": "temp_delta"
        }
        self.map = {
            "0x04": [
                [
                    1,
                    22,
                    [
                        ["flow_rate", 0, 2, 0, "F32"],
                        ["total_flow", 4, 2, 0, "F32"],
                        ["energy_rate", 8, 2, 0, "F32"],
                        ["energy_total", 10, 2, 0, "F32"],
                        ["temp_1", 16, 2, 0, "F32"],
                        ["temp_2", 18, 2, 0, "F32"],
                        ["temp_delta", 20, 2, 0, "F32"]
                    ]
                ]
            ]
        }
        self._initialise_data()


class VSDACH550(ModbusSerialDevice):

    def __init__(self, controller, device_id, port, unit, nb_subdev):
        super().__init__(controller, device_id, port, unit, nb_subdev)
        self.sensor_type = "vsd"
        self.subdevice_name = ["vsd"]
        self.byteorder = Endian.Big
        self.wordorder = Endian.Big
        self.data_map = {
            "speed": "speed",
            "frequency": "frequency",
            "alarm": "alarm",
            "mode": "mode",
            "power": "power"
        }
        self.map = {
            "0x03": [
                [
                    101,
                    2,
                    [
                        ["speed", 0, 1, 0, "I16"],
                        ["frequency", 1, 1, 0, "I16"],
                        ["power", 4, 1, 0, "I16"]
                    ]
                ]
            ],
            "0x02": [
                [
                    0,
                    16,
                    [
                        # ["ready", 0, 1, 0],
                        # ["enable", 1, 1, 0],
                        # ["started", 2, 1, 0],
                        ["mode", 3, 1, 0],
                        # ["zero_speed", 4, 1, 0],
                        # ["run_at_setpoint", 7, 1, 0],
                        # ["panel_local", 12, 1, 0],
                        ["alarm", 15, 1, 0]
                    ]
                ]
            ]
        }
        self.retry_count = 0
        self._initialise_data()
    
    def send_sample_thread(self):
        self.newvals = [{} for _ in range(self.number_subdevices)]
        # Get Connector of Modbus
        mb_serial = self._controller.get_connector(self.port)
        if mb_serial is None:
            self.device_state = "DISCONNECTED"
            self._controller.custom_health.update_status_payload(
                name=self._device_id,
                type_label="device",
                status=self.device_state,
                context=f"Modbus Serial Disconnected"
            )
            _log.warning(f"Modbus Serial Disconnected: {self._device_id}")
            return

        # Get Modbus Data
        try:
            if "0x02" in self.map:
                self.read_discrete_inputs(mb_serial, self.map["0x02"])
            if "0x03" in self.map:
                self.read_holding_registers(mb_serial, self.map["0x03"])
        except ConnectionException as err:
            _log.exception(f"{self.__class__.__name__} Connection Error: {err}")
            self.device_state = "DISCONNECTED"
            self._controller.custom_health.update_status_payload(
                    name=self._device_id, 
                    type_label="device", 
                    status="DISCONNECT", 
                    context=f"Error: Device Disconnected"
                )
        except Exception as e:
            _log.exception(f"{self.__class__.__name__} send_sample_thread Error: {e}")
            
        for idx, data in enumerate(self.newvals):
            if data:
                self.format_data(data, idx, self.sensor_type)
            else:
                _log.warning(f"No data in {self._device_id} subdev: {idx}")
                
    def read_holding_registers(self, modbus_client, function_values: list):
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_holding_registers(addr, nb_reg, slave=self.unit)

            if not val.isError():
                for datapoint, address, size, subdev_idx, decode_type in values:
                    _log.debug(f"datapoint: {datapoint}")
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        val.registers[address: address + size],
                        byteorder=self.byteorder,
                        wordorder=self.wordorder
                    )
                    decode_value = decode_factory(decoder, decode_type)
                    if decode_value is not None:
                        self.newvals[subdev_idx][datapoint] = decode_value
                        _log.debug(f"{datapoint}: {decode_value}")
            else:
                _log.warning(f"Error reading {self._device_id} at address {addr}")

    def read_discrete_inputs(self, modbus_client, function_values: list):
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_discrete_inputs(addr, nb_reg, slave=self.unit)

            if not val.isError():
                for datapoint, address, size, subdev_idx in values:
                    _log.debug(f"datapoint: {datapoint}")
                    ret = val.bits[address: address + size]
                    if datapoint == "mode":
                        self.newvals[subdev_idx][datapoint] = "on" if ret[0] else "off"
                    else:
                        self.newvals[subdev_idx][datapoint] = ret[0]
                    _log.debug(f"{datapoint}: {ret}")
            else:
                _log.warning(f"Error reading {self._device_id} at address {addr}")

    def turn_on(self):
        """
        Turn on the VSD

        Modbus function: 0x0F (write multiple coils)
        STOP bit = 0
        START bit = 1
        turn_on bit = [0, 1]
        """
        mb_serial = self._controller.get_connector(self.port)
        try:
            response = mb_serial.write_coils(address=0, values=[0, 1], slave=self.unit)
            if not response.isError():
                self.retry_count = 0
                _log.info(f"{self.__class__.__name__} unit: {self.unit} turn on success")
                self.update_mode("on")
                return {"device_id": self._device_id, "state": "on", "event": "success"}
            elif self.retry_count == 7:
                self.retry_count = 0
                return {"device_id": self._device_id, "state": "on", "event": "failed"}
            else:
                self.retry_count += 1
                _log.warning(f"VSDACH550 unit: {self.unit} turn on failed, {response}")
                return self.turn_on()
        except Exception as e:
            _log.exception(f"Error turning on VSD unit {self.unit}: {e}")
            return {"device_id": self._device_id, "state": "on", "event": "error"}

    def turn_off(self):
        """
        Turn off the VSD

        Modbus function: 0x0F (write multiple coils)
        STOP bit = 1
        START bit = 0
        turn_off bit = [1, 0]
        """
        mb_serial = self._controller.get_connector(self.port)
        try:
            response = mb_serial.write_coils(address=0, values=[1, 0], slave=self.unit)
            if not response.isError():
                self.retry_count = 0
                _log.info(f"{self.__class__.__name__} unit: {self.unit} turn off success")
                self.update_mode("off")
                return {"device_id": self._device_id, "state": "off", "event": "success"}
            elif self.retry_count == 7:
                self.retry_count = 0
                return {"device_id": self._device_id, "state": "off", "event": "failed"}
            else:
                self.retry_count += 1
                _log.warning(f"VSDACH550 unit: {self.unit} turn off failed, {response}")
                return self.turn_off()
        except Exception as e:
            _log.exception(f"Error turning off VSD unit {self.unit}: {e}")
            return {"device_id": self._device_id, "state": "off", "event": "error"}

    def set_frequency(self, frequency):
        """
        Set the frequency of the VSD

        Modbus function: 0x06 (write register)
        """
        if frequency > 50 or frequency < 35:
            _log.warning(f"unit: {self.unit}, Frequency {frequency} is out of range")
            return {"device_id": self._device_id, "frequency": frequency, "event": "failed"}

        mb_serial = self._controller.get_connector(self.port)
        convert_freq = int((20000/50)*frequency)
        try:
            response = mb_serial.write_register(address=1, value=convert_freq, slave=self.unit)
            if not response.isError():
                self.retry_count = 0
                _log.info(f"{self.__class__.__name__} unit: {self.unit} set frequency {frequency} success")
                self.update_frequency(frequency)
                return {"device_id": self._device_id, "frequency": frequency, "event": "success"}
            elif self.retry_count == 7:
                self.retry_count = 0
                return {"device_id": self._device_id, "frequency": frequency, "event": "failed"}
            else:
                self.retry_count += 1
                _log.warning(f"VSDACH550 unit: {self.unit} set frequency {frequency} failed, {response}")
                return self.set_frequency(frequency)
        except Exception as e:
            _log.exception(f"Error setting frequency of VSD unit {self.unit}: {e}")
            return {"device_id": self._device_id, "frequency": frequency, "event": "error"}
    
    def update_mode(self, mode: str):
        self.current_state[0]['vsd']['mode'] = mode
        self.update_state()
    
    def update_frequency(self, frequency: float):
        self.current_state[0]['vsd']['frequency'] = frequency
        self.update_state()
    
    def update_state(self):
        newvals = {}
        try:
            for idx in range(self.number_subdevices):
                _log.debug(f"update state: {self.current_state[idx]['vsd']}")
                for datapoint, value in self.current_state[idx]['vsd'].items():
                    if value is not None:
                        if datapoint == "frequency":
                            newvals[datapoint] = value*10
                        else:
                            newvals[datapoint] = value
            _log.info(f"update state: {newvals}")
            self.format_data(newvals, 0, self.sensor_type)
        except Exception as e:
            _log.exception(f"Error updating state of VSD unit {self.unit}: {e}")
    
    def to_vsd_frequency(self, val):
        """
        Convert frequency to VSD frequency
        """
        return round(val/10, 2)
    
    
class VSDSAKOSKI600(ModbusSerialDevice):
    
    def __init__(self, controller, device_id, port, unit, nb_subdev):
        super().__init__(controller, device_id, port, unit, nb_subdev)
        self.sensor_type ="vsd"
        self.subdevice_name = ["vsd"]
        self.byteorder = Endian.Big
        self.wordorder = Endian.Big
        self.data_map = {
            "speed": "speed",
            "frequency": "frequency",
            "mode": "mode",
            "current": "current",
            "voltage": "voltage",
            "torque": "torque"
        }
        self.map ={
            "0x03": [
                [
                    7424,
                    23,
                    [
                        ["frequency", 0, 1, 0, "I16"],
                        ["current", 5, 1, 0, "I16"],
                        ["voltage", 6, 1, 0, "I16"],
                        ["torque", 7, 1, 0, "I16"],
                        ["speed", 8, 1, 0, "I16"],
                        ["mode", 23, 1, 0, "I16"]
                    ]
                ]
            ]
        }
        self._initialise_data()
    
    def read_holding_registers(self, modbus_client, function_values: list):
        for addr, nb_reg, values in function_values:
            val = modbus_client.read_holding_registers(addr, nb_reg, slave=self.unit)
            
            if not val.isError():
                for datapoint, address, size, subdev_idx, decode_type in values:
                    _log.debug(f"datapoint: {datapoint}")
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        val.registers[address: address + size],
                        byteorder=self.byteorder,
                        wordorder=self.wordorder
                    )
                    decode_value = decode_factory(decoder, decode_type)
                    if decode_value is not None:
                        if datapoint == "mode":
                            if decode_value == 65 or decode_value == 33:
                                self.newvals[subdev_idx][datapoint] = "on"
                            elif decode_value == 64 or decode_value == 17:
                                self.newvals[subdev_idx][datapoint] = "off"
                        else:
                            self.newvals[subdev_idx][datapoint] = decode_value
                        _log.debug(f"{datapoint}: {decode_value}")
        
    def turn_on(self):
        mb_serial = self._controller.get_connector(self.port)
        try:
            response = mb_serial.write_register(address=0x2000, value=1, slave=self.unit)
            if not response.isError():
                self.update_mode("on")
                return {"device_id": self._device_id, "mode": "on", "event": "success"}
            else:
                _log.warning(f"VSDSAKOSKI600 unit: {self.unit} turn on failed, {response}")
        except Exception as e:
            _log.exception(f"Error turning on VSD Sako unit {self.unit}: {e}")
    
    def turn_off(self):
        mb_serial = self._controller.get_connector(self.port)
        try:
            response = mb_serial.write_register(address=0x2000, value=3, slave=self.unit)
            if not response.isError():
                self.update_mode("off")
                return {"device_id": self._device_id, "mode": "off", "event": "success"}
            else:
                _log.warning(f"VSDSAKOSKI600 unit: {self.unit} turn off failed, {response}")
        except Exception as e:
            _log.exception(f"Error turning off VSD Sako unit {self.unit}: {e}")
    
    def set_frequency(self, frequency):
        """
        Set frequency of the VSD
        
        """
        if frequency > 50 or frequency < 25:
            _log.warning(f"slave: {self.unit}, Frequency {frequency} is out of range")
        mb_serial = self._controller.get_connector(self.port)
        convert_freq = int(frequency*100)
        try:
            response = mb_serial.write_register(address=0x2001, value=convert_freq, slave=self.unit)
            if not response.isError():
                self.update_frequency("frequency")
                return {"device_id": self._device_id, "frequency": frequency, "event": "success"}
            else:
                _log.warning(f"VSDSAKOSKI600 unit: {self.unit} set frequency failed, {response}")
        except Exception as e:
            _log.exception(f"Error setting frequency of VSD Sako unit {self.unit}: {e}")
    
    def update_mode(self, mode: str):
        self.current_state[0]['vsd']['mode'] = mode
        self.update_state()
    
    def update_frequency(self, frequency: float):
        self.current_state[0]['vsd']['frequency'] = frequency
        self.update_state()
    
    def update_state(self):
        newvals = {}
        try:
            for idx in range(self.number_subdevices):
                _log.debug(f"update state: {self.current_state[idx]['vsd']}")
                for datapoint, value in self.current_state[idx]['vsd'].items():
                    if value is not None:
                        if datapoint == "frequency":
                            newvals[datapoint] = value/100
                        else:
                            newvals[datapoint] = value
            _log.info(f"update state: {newvals}")
            self.format_data(newvals, 0, self.sensor_type)
        except Exception as e:
            _log.exception(f"Error updating state of VSD unit {self.unit}: {e}")
    
    def to_vsd_frequency(self, val):
        """
        Convert frequency to readable Hertz
        """
        return round(val/100, 2)

    def to_vsd_current(self, val):
        """
        Convert current to readable Ampere
        """
        return round(val/10, 2)

    def to_vsd_torque(self, val):
        """
        Convert 
        """
        return round(val/10, 2)


def modbusserial(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Modbusserial
    :rtype: Modbusserial
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get("agent_name", "modbus_serial")
    sampling_rate = config.get("sampling_rate", 30)
    configured_devices = config.get("configured_devices", {})

    return Modbusserial(agent_name, sampling_rate, configured_devices, **kwargs)


class Modbusserial(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, sampling_rate, configured_devices, **kwargs):
        super(Modbusserial, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.agent_name = agent_name
        self.sampling_rate = sampling_rate
        self.configured_devices = configured_devices
        
        self.setup_heartbeat()
        
        self.default_config = {
            "agent_name": agent_name,
            "sampling_rate": sampling_rate,
            "configured_devices": configured_devices
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.connectors = {}
        self.queue = PriorityQueue()
        self.get_sample_thread = Thread(target=self._send_samples_thread, name="modbus", daemon=True)
        self.get_sample_thread.start()
    
    def setup_heartbeat(self):
        try:
            self.custom_health = AltoHealth(self.core, self.vip.pubsub, heartbeat_period=60)

            # set intial status for functions and devices
            self.function_names = [
                "send_samples",
                "get_connector",
                "publish"
            ]
            if "vsd" in self.agent_name:
                self.function_names.append("_handle_command")
                
            self.device_names = [device_id for props in self.configured_devices.values() for device_id in props['device_id']]
            
            self.custom_health.set_pending_status(names=self.function_names, type_label='function')
            self.custom_health.set_pending_status(names=self.device_names, type_label='device')

            # track function status (need to use this approach to pass `self` into decorator function)
            for function_name in self.function_names:
                setattr(self, function_name, AltoHealth.track_status(self.custom_health)(getattr(self, function_name)))
        except Exception as e:
            _log.exception(f"Error setting up heartbeat: {e}")

    def _build_device(self, device_type, device_id, port, unit, nb_subdev):
        try:
            if device_id not in self.device_list:
                device = device_factory(device_type)
                newdev = device(self, device_id, port, unit, nb_subdev)
                self.device_list[device_id] = newdev
                _log.debug(f"Device {device_id} created")

                if port not in self.connectors:
                    self.connectors[port] = None
        except Exception as e:
            _log.exception(f"Error building device {device_id}: {e}")

    def _send_samples_thread(self):
        while True:
            try:
                keep_priority = [1, 4]
                _log.debug(f"{self.__class__.__name__} Queue size: {self.queue.qsize()}")
                if self.queue.qsize() >= 100:
                    self.queue.queue = [x for x in self.queue.queue if x.priority in keep_priority]
                pqobject = self.queue.get()
                priority = pqobject.priority
                dev = pqobject.device_id
                args = pqobject.args
                _log.debug(f"Queue get: {priority}, device_id: {dev}, {args}")
                if dev == "Die":
                    return
                if priority == WRITEPRIORITY:
                    response = None
                    if args == "turn_on":
                        response = self.device_list[dev].turn_on()
                    elif args == "turn_off":
                        response = self.device_list[dev].turn_off()
                    elif args.startswith("set_frequency"):
                        frequency = float(args.split(":")[-1])
                        _log.debug(f"Setting frequency to {frequency}")
                        response = self.device_list[dev].set_frequency(frequency)
                    _log.info(f"Control Response: {response}")
                elif priority == READPRIORITY:
                    self.device_list[dev].send_sample_thread()
                self.queue.task_done()
            except Exception as e:
                _log.exception(f"Error in send_sample_thread: {e}")

    def send_samples(self):
        try:
            for device_id in self.device_list:
                _log.debug(f"Sending samples for device {device_id}")
                self.queue.put_nowait(PqElement(READPRIORITY, device_id, "None"))
        except Exception as e:
            _log.exception(f"Error in send_samples: {e}")

    def get_connector(self, port):
        try:
            if self.connectors[port] is None:
                self.connectors[port] = ModbusSerialClient(
                    method='rtu', 
                    framer=ModbusRtuFramer, 
                    port=port, 
                    baudrate=9600, 
                    timeout=1,
                    retries=1
                )
                connection = self.connectors[port].connect()
                if connection:
                    _log.debug(f"Connected to serial Port {port}")
                else:
                    _log.debug(f"Failed to connect serial port {port}")
                    self.connectors[port] = None
        except ConnectionError as e:
            _log.exception(f"Error connecting to port {port}: {e}")
            self.connectors[port] = None
        return self.connectors[port]

    def reset_connector(self, port):
        try:
            if not self.connectors[port] is None:
                self.connectors[port].close()
                self.connectors[port] = None
        except Exception as e:
            _log.exception(f"Error resetting port {port}: {e}")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        try:
            agent_name = config.get("agent_name", "modbus_serial")
            sampling_rate = config.get("sampling_rate", 30)
            configured_devices = config.get("configured_devices", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.sampling_rate = sampling_rate
        self.configured_devices = configured_devices

        self.device_list = dict()
        for port, devices_list in self.configured_devices.items():
            for device in devices_list:
                self._build_device(
                    device['device_type'],
                    device['device_id'],
                    port,
                    device['unit_id'],
                    device['number_subdevice']
                )
        
        if "vsd" in self.agent_name:
            self._create_subscriptions()
        self.core.schedule(periodic(self.sampling_rate), self.send_samples)

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="modbus",
                                  callback=self._handle_command)

    def _handle_command(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        _log.debug(f"Received message on topic: {topic}, {message}")
        if len(topic.split("/")) != 4:
            _log.warning(f"Invalid topic: {topic}")
            return

        schema, agent_name, device_id, message_type = topic.split("/")
        try:
            if message_type == "command":
                if device_id in self.device_list:
                    if message['action']['schema'] == "vsd":
                        if "mode" in message['action']['command']:
                            if message['action']['command']['mode'] == "on":
                                self.queue.put_nowait(PqElement(WRITEPRIORITY, device_id, "turn_on"))
                            elif message['action']['command']['mode'] == "off":
                                self.queue.put_nowait(PqElement(WRITEPRIORITY, device_id, "turn_off"))
                        if "frequency" in message["action"]['command']:
                            self.queue.put_nowait(PqElement(WRITEPRIORITY, device_id, f"set_frequency:{message['action']['command']['frequency']}"))
                    else:
                        _log.warning(f"This device is not vsd")
                else:
                    _log.warning(f"This device is not configured: {device_id}")
        except Exception as e:
            _log.exception(f"Error in _handle_command: {e}")

    def publish(self, message: dict, message_type: str):
        try:
            timestamp = time.time()
            datetime = pendulum.from_timestamp(timestamp).to_atom_string()
            device_id = message.get("device_id")
            topic = f"sensor/{self.core.identity}/{device_id}/event"
            headers = {
                "requesterID": self.core.identity,
                "message_type": message_type,
                "TimeStamp": datetime
            }
            message.update({
                "timestamp": datetime,
                "unix_timestamp": timestamp,
            })
            self.vip.pubsub.publish("pubsub", topic, headers=headers, message=message)
            _log.info(f"ModbusSerial Publish topic: {topic}, message: {message}")
        except Exception as e:
            _log.exception(f"Error in publish: {e}")

    def last_rites(self):
        self.queue.put_nowait(PqElement(0, "Die", "Die"))
    
    def response_rpc(self, agent_callback, function_callback, payload):
        try:
            self.vip.rpc.call(agent_callback, function_callback, payload)
        except Exception as e:
            _log.exception(f"Error in response_rpc: {e}")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.info("Stopping ModbusSerial Agent")
        self.last_rites()
        for port in self.connectors:
            self.reset_connector(port)


def main():
    """Main method called to start the agent."""
    utils.vip_main(modbusserial,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
