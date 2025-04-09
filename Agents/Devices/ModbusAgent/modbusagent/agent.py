"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import sys
import altolib
import getmac
import subprocess
from threading import Thread, Lock
from queue import Queue
from math import acos, tan
import gevent
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from volttron.platform.agent import utils


MODBUSMAP = {
    "current": "current",
    "voltage": "voltage",
    "frequency": "frequency",
    "power": "power",
    "power_reactive": "power_reactive",
    "power_apparent":"power_apparent",
    "power_to_grid": "power_to_grid",
    "energy": "energy",
    "energy_apparent":"energy_apparent",
    "energy_reactive": "energy_reactive",
    "energy_reactive_net":"energy_reactive_net",
    "energy_reactive_total":"energy_reactive_total",
    "energy_reactive_to_grid":"energy_reactive_to_grid",
    "energy_to_grid": "energy_to_grid",
    # "energy_reactive_to_grid": "energy_reactive_to_grid",
    "power_factor":"power_factor",
    "input_power":"input_power",
    "co2_reduction": "co2_reduction",
    "energy_total":"energy_total",
    "energy_daily": "energy_daily",
    "energy_net":"energy_net",
    "pv": "pv",

    # PM5560
    "active_energy_delivered_into_load": "active_energy_delivered_into_load",
    "active_energy_delivered_outoff_load": "active_energy_delivered_outoff_load",
    "active_energy_delivered_plus_received": "active_energy_delivered_plus_received",
    "active_energy_delivered_minus_received": "active_energy_delivered_minus_received",

    "active_energy_delivered_rate_1": "active_energy_delivered_rate_1",
    "active_energy_delivered_rate_2": "active_energy_delivered_rate_2",
    "active_energy_delivered_rate_3": "active_energy_delivered_rate_3",
    "active_energy_delivered_rate_4": "active_energy_delivered_rate_4",
    "active_energy_received_rate_1": "active_energy_received_rate_1",
    "active_energy_received_rate_2": "active_energy_received_rate_2",
    "active_energy_received_rate_3": "active_energy_received_rate_3",
    "active_energy_received_rate_4": "active_energy_received_rate_4",

    # Huawei solar logger (Power meter)
    "total_active_electricity": "total_active_electricity",
    "total_reactive_electricity": "total_reactive_electricity",
    "negative_active_electricity": "negative_active_electricity",
    "negative_reactive_electricity": "negative_reactive_electricity",
    "positive_active_electricity": "positive_active_electricity",
    "positive_reactive_electricity": "positive_reactive_electricity",
}

MODBUSENVMAP = {
    "wind_speed": "wind_speed",
    "wind_direction": "wind_direction",
    "pv_module_temperature": "pv_module_temperature",
    "ambient_temperature": "ambient_temperature",
    "total_irradiance": "total_irradiance",
    "daily_irradiation_amount": "daily_irradiation_amount"
}

MBPORT = 502


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def device_factory(devtype):
    if devtype == "schneider":
        return SchneiderSensor
    elif devtype == "circutor":
        return CircutorSensor
    elif devtype == "circutor3phases":
        return CircutorSensor3P
    elif devtype == "circutorcemmrs485":
        return CircutorCEMMRS485
    elif devtype == "pzem016":
        return PZEM016Sensor
    elif devtype == "socomec":
        return Socomec3P
    elif devtype == "huaweisolar":
        return HuaweiSolarLogger
    elif devtype == "rtr":
        return RTR
    elif devtype == "pm5560":
        return SchneiderPM5560
    elif devtype == "umg96rm":
        return UMG96RM
    elif devtype == "sun2000":
        return SUN2000
    elif devtype == "sun2000_emi":
        return SUN2000EMI
    elif devtype == "enerium_30":
        return ENERIUM30
    elif devtype == "epr_04s":
        return EPR04S
    elif devtype == "circutorcem_c12":
        return CircutorCEMC12

    raise Exception(f"Unknown device type {devtype}")

def decoder_factory(regval, data_type):
    if data_type == "U16":
        return regval.decode_16bit_uint()
    elif data_type == "U32":
        return regval.decode_32bit_uint()
    elif data_type == "U64":
        return regval.decode_64bit_uint()
    elif data_type == "I8":
        return regval.decode_8bit_int()
    elif data_type == "I64":
        return regval.decode_64bit_int()
    elif data_type == "I32":
        return regval.decode_32bit_int()
    elif data_type == "I16":
        return regval.decode_16bit_int()
    elif data_type == "F32":
        return regval.decode_32bit_float()


class MBDevice(altolib.AltoElectricSensor, altolib.AltoEnvironSensor):
    """
    This is the Circutor 1 phase device

    Here the map must be saet by every class subclassing this one.
    The map is a list of 3-uples.  The 3-uples consist in
        - An address, where to start reading registers.
        - A number, the number of registers to read
        - A list of 4-uples:
            + A data point name
            + An offset in the list of registers read
            + A size, the number of registers to read
            + An index, the subdevice index

    """

    def __init__(
        self, controller, unit, mac_addr, ip_addr, nb_subdev, lock, port=MBPORT
    ):
        devid = f"{mac_addr}:{unit}"
        super().__init__(controller, devid, nb_subdev)

        # change the datapoint_supported, we need pf and etc.
        self.datapoint_supported["electric"] = [
            "type",
            "voltage",
            "current",
            "frequency",
            "power",
            "energy",
            "power_reactive",
            "power_apparent",
            "energy_to_grid",
            "energy_reactive",
            "energy_reactive_to_grid",
            "energy_reactive_total",
            "energy_reactive_net",
            "energy_apparent",
            "power_factor",
            "input_power",
            "co2_reduction",
            "energy_total",
            "energy_daily",
            "pv",
            "power_apparent",
            "energy_net",

            # PM5560
            "active_energy_delivered_into_load",
            "active_energy_delivered_outoff_load",
            "active_energy_delivered_plus_received",
            "active_energy_delivered_minus_received",
            
            "active_energy_delivered_rate_1",
            "active_energy_delivered_rate_2",
            "active_energy_delivered_rate_3",
            "active_energy_delivered_rate_4",
            "active_energy_received_rate_1",
            "active_energy_received_rate_2",
            "active_energy_received_rate_3",
            "active_energy_received_rate_4",

            # Huawei solar logger (Power meter)
            "total_active_electricity",
            "total_reactive_electricity",
            "negative_active_electricity",
            "negative_reactive_electricity",
            "positive_active_electricity",
            "positive_reactive_electricity",
        ]

        self.datapoint_supported["environment"] = [x for x in MODBUSENVMAP.keys()]

        # Now setup the map
        self.data_map.update(MODBUSMAP)
        self.data_map.update(MODBUSENVMAP)
        self.initialise_data("electric", MODBUSMAP.keys())
        self.initialise_data("environment", MODBUSENVMAP.keys())
        self.ip_addr = ip_addr
        self.thread_lock = lock
        self.port = port
        self.map = []
        self.endian = "big"
        self.newvals = []

    @property
    def unit(self):
        return int(self.device_id.split(":")[-1])

    def func_aggregate(self, func, data):
        if func == "sum":
            aggr_data = sum(data)
        else:
            aggr_data = sum(data)/len(data)
        return aggr_data

    def send_sample_thread(self):
        # with self.thread_lock:
        try:
            mbc = self.controller.get_connector(self.ip_addr, self.port)
            self.newvals = []
            # _log.debug(f"modbus 1")
            for subdev_idx in range(self.number_subdevices):
                self.newvals.append({"type": "ac"})
            # _log.debug(f"modbus 2")
            for addr, nb_reg, lovalues in self.map:
                # _log.debug(f"modbus 3")
                val = mbc.read_holding_registers(addr, nb_reg, slave=self.unit)
                gevent.sleep(0.5)
                # _log.debug(f"modbus 4")
                if not val.isError():
                    if self.endian not in ["schneider"]:
                        for dp, idx, dl, sdidx, data_type in lovalues:
                            _log.debug(f"datapoint: {dp}")
                            self.newvals[sdidx][dp] = 0
                            if self.endian:
                                regval = BinaryPayloadDecoder.fromRegisters(
                                    val.registers[idx: idx + dl],
                                    Endian.Big,
                                    wordorder=Endian.Big,
                                )
                                regval = decoder_factory(regval, data_type)
                                self.newvals[sdidx][dp] = regval
                            else:
                                _log.debug(f"endian not schneider")
                                if self.endian == "big":
                                    myrange = range(dl)
                                else:
                                    myrange = range(dl, -1, -1)

                                ## aggregate the data that cannot poll.
                                if "sum_" in dp or "avg_" in dp:
                                    _log.debug("in sum or avf aggregate function modbus")
                                    dp = dp.split("_")
                                    func = dp[0]
                                    num = int(dp[1])
                                    dp = "_".join(dp[2:])

                                    temp = 0
                                    data = []
                                    for x in myrange:
                                        temp <<= 16
                                        temp += val.registers[idx + x]
                                        if x % (dl/num) == 1 and x != 0:
                                            data.append(temp)
                                            temp =0
                                    aggreg_data = self.func_aggregate(func, data)
                                    self.newvals[sdidx][dp] = aggreg_data
                                else:
                                    for x in myrange:
                                        self.newvals[sdidx][dp] <<= 16
                                        self.newvals[sdidx][dp] += val.registers[idx + x]
                    else:
                        for dp, idx, dl, sdidx in lovalues:
                            _log.debug(f"datapoint: {dp}")
                            self.newvals[sdidx][dp] = 0
                            if self.endian == "schneider":
                                regval = BinaryPayloadDecoder.fromRegisters(
                                    val.registers[idx: idx + dl],
                                    Endian.Big,
                                    wordorder=Endian.Big,
                                )
                                regval = regval.decode_32bit_float()
                                self.newvals[sdidx][dp] = regval
        except Exception as e:
            _log.debug(f"Problem with {self.ip_addr}, unit {self.unit}: {e}")
            self.controller.reset_connector(self.ip_addr, self.port)

        else:
            try:
                if self.newvals:
                    for subdev_idx in range(self.number_subdevices):
                        self.set_sensor_data(self.newvals[subdev_idx], subdev_idx)
            except Exception as e:
                _log.debug(f"Modbus we have a problem for {self.ip_addr}: {e}")
        # finally:
        # mbc.close()


class CircutorCEMC12(MBDevice):
    """
    This is the Circutor 1 phase model CEM-C12
    """
    
    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 1, lock, port)
        self.map = [
            [
                0x00,
                16,
                [
                    ["voltage", 0x00, 2, 0,"I32"],
                    ["current", 0x02, 2, 0, "I32"],
                    ["power", 0x04, 2, 0, "I32"],
                    ["power_reactive", 0x06, 2, 0, "I32"],
                    ["power_apparent", 0x0C, 2, 0, "I32"],
                    ["power_factor", 0x0E, 2, 0, "I32"]
                ]
            ],
            [
                0x12,
                8,
                [
                    ["energy", 0, 2, 0, "I32"],
                    ["energy_reactive", 6, 2, 0, "I32"]
                ]
            ],
            [
                0x22,
                8,
                [
                    ["energy_to_grid", 0, 2, 0, "I32"],
                    ["energy_reactive_to_grid", 6, 2, 0, "I32"]
                ]
            ],
            [
                0x5A,
                1,
                [
                    ["frequency", 0, 1, 0, "I16"]
                ]
            ]
        ]
    
    def to_electric_voltage(self, val):
        return val/10

    def to_electric_current(self, val):
        return val/100
    
    def to_electric_power(self, val):
        return val/100
    
    def to_electric_power_apparent(self, val):
        return val/100
    
    def to_electric_power_reactive(self, val):
        return val/100
    
    def to_electric_power_factor(self, val):
        return val/100
    
    def to_electric_energy(self, val):
        return val/100

    def to_electric_energy_reactive(self, val):
        return val/100
    
    def to_electric_energy_to_grid(self, val):
        return val/100
    
    def to_electric_energy_reactive_to_grid(self, val):
        return val/100

    def to_electric_frequency(self, val):
        return val/100


class CircutorSensor(MBDevice):
    """
    This is the Circutor 1 phase device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 1, lock, port)
        # Now setup the map
        self.map = [
            [
                0,
                9,
                [
                    ["voltage", 0, 1, 0, "I16"],
                    ["current", 1, 1, 0, "I16"],
                    ["frequency", 2, 1, 0, "I16"],
                    ["power", 3, 1, 0, "I16"],
                    ["power_reactive", 4, 1, 0, "I16"],
                    ["energy", 7, 2, 0, "I32"]
                ],
            ],
            [
                17,
                2,
                [
                    ["energy_reactive", 0, 2, 0, "I32"],
                ],
            ],
            [
                37,
                2,
                [
                    ["energy_to_grid", 0, 2, 0, "I32"],
                ],
            ],
            [
                0x4B,
                2,
                [
                    ["energy_reactive_to_grid", 0, 2, 0, "I32"],
                ],
            ]
        ]

    def to_electric_current(self, val):
        return val / 10

    def to_electric_voltage(self, val):
        return val / 10

    def to_electric_frequency(self, val):
        return val / 10

    def to_electric_power(self, val):
        # return val / 1000
        return val / 1

    def to_electric_power_reactive(self, val):
        # return val / 1000
        return val / 1

    def to_electric_energy(self, val):
        return val / 1000

    def to_electric_energy_to_grid(self, val):
        return val / 1000

    def to_electric_energy_reactive(self, val):
        return val / 1000

    def to_electric_energy_reactive_to_grid(self, val):
        return val / 1000


class CircutorSensor3P(MBDevice):
    """
    This is the Circutor 3 phase device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                0x00,
                0x04,
                [
                    ["energy", 0, 2, 3],
                    ["energy_to_grid", 2, 2, 3]

                ],
            ],
            [
                0x0732,
                0x12,
                [
                    ["voltage", 0, 2, 0],
                    ["voltage", 2, 2, 1],
                    ["voltage", 4, 2, 2],
                    ["avg_3_voltage", 0, 6, 3],
                    ["current", 6, 2, 0],
                    ["current", 8, 2, 1],
                    ["current", 10, 2, 2],
                    ["sum_3_current", 6, 6, 3],
                    ["power_factor", 12, 2, 0],
                    ["power_factor", 14, 2, 1],
                    ["power_factor", 16, 2, 2],
                    ["avg_3_power_factor", 12, 6, 3]
                ],
            ],
            [
                0x0746,
                0x10,
                [
                    ["power", 0, 2, 0],
                    ["power", 2, 2, 1],
                    ["power", 4, 2, 2],
                    ["power", 6, 2, 3],
                    ["power_reactive", 8, 2, 0],
                    ["power_reactive", 10, 2, 1],
                    ["power_reactive", 12, 2, 2],
                    ["power_reactive", 14, 2 ,3]
                ],
            ],
        ]
        self.name_subdevices = [f"phase_{i}" for i in range(1, 4)] +["total"]

    def to_electric_current(self, val):
        return val / 100

    def to_electric_voltage(self, val):
        return val / 10

    def to_electric_frequency(self, val):
        return val / 10

    def to_electric_power(self, val):
        return val / 1000

    def to_electric_power_reactive(self, val):
        return val / 1000

    def to_electric_energy(self, val):
        return val / 1000

    def to_electric_energy_to_grid(self, val):
        return val / 1000

    def to_electric_energy_reactive(self, val):
        return val / 1000

    def to_electric_energy_reactive_to_grid(self, val):
        return val / 1000

    def to_electric_power_factor(self, val):
        return val / 100


class CircutorCEMMRS485(MBDevice):
    """
    This is the Circutor 3 phase device, packed with CEM C30
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                0x00,
                4,
                [
                    ["energy", 0, 2, 3, "I32"],
                    ["energy_to_grid", 2, 2, 3, "I32"]

                ],
            ],
            [
                0x0732,
                18,
                [
                    ["voltage", 0, 2, 0, "I32"],
                    ["voltage", 2, 2, 1, "I32"],
                    ["voltage", 4, 2, 2, "I32"],
                    # ["avg_3_voltage", 0, 6, 3, "I32"],
                    ["current", 6, 2, 0, "I32"],
                    ["current", 8, 2, 1, "I32"],
                    ["current", 10, 2, 2, "I32"],
                    # ["sum_3_current", 6, 6, 3, "I32"],
                    ["power_factor", 12, 2, 0, "I32"],
                    ["power_factor", 14, 2, 1, "I32"],
                    ["power_factor", 16, 2, 2, "I32"],
                    # ["avg_3_power_factor", 12, 6, 3, "I32"]
                ],
            ],
            [
                0x0746,
                16,
                [
                    ["power", 0, 2, 0, "I32"],
                    ["power", 2, 2, 1, "I32"],
                    ["power", 4, 2, 2, "I32"],
                    ["power", 6, 2, 3, "I32"],
                    ["power_reactive", 8, 2, 0, "I32"],
                    ["power_reactive", 10, 2, 1, "I32"],
                    ["power_reactive", 12, 2, 2, "I32"],
                    ["power_reactive", 14, 2 ,3, "I32"]
                ],
            ],
        ]
        self.name_subdevices = [f"phase_{i}" for i in range(1, 4)] +["total"]

    def to_electric_current(self, val):
        return val / 100

    def to_electric_voltage(self, val):
        return val / 10

    def to_electric_power(self, val):
        return val / 1000

    def to_electric_power_reactive(self, val):
        return val / 1000

    def to_electric_energy(self, val):
        return val / 1000

    def to_electric_energy_to_grid(self, val):
        return val / 1000

    def to_electric_power_factor(self, val):
        return val / 100


class Socomec3P(MBDevice):
    """
    This is the Socomec 3 phases device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                0xC652,
                10,
                [
                    ["energy", 0, 2, 3],
                    ["reactive_energy", 2, 2, 3],
                    ["energy_to_grid", 6, 2, 3]
                ],
            ],
            [
                0xC552,
                20,
                [
                    ["voltage", 0, 2, 0],
                    ["voltage", 2, 2, 1],
                    ["voltage", 4, 2, 2],
                    ["avg_3_voltage", 0, 6, 3],
                    ["frequency", 12, 2, 3],
                    ["current", 14, 2, 0],
                    ["current", 16, 2, 1],
                    ["current", 18, 2, 2],
                    ["sum_3_current", 14, 6, 3]
                ],
            ],
            [
                0xC568,
                32,
                [

                    ["power", 8, 2, 0],
                    ["power", 10, 2, 1],
                    ["power", 12, 2, 2],
                    ["power", 0, 2, 3],
                    ["power_reactive", 14, 2, 0],
                    ["power_reactive", 16, 2, 1],
                    ["power_reactive", 18, 2, 2],
                    ["power_reactive", 2, 2 ,3],
                    ["power_factor", 26, 2, 0],
                    ["power_factor", 28, 2, 1],
                    ["power_factor", 30, 2, 2],
                    ["power_factor", 6, 2, 3]
                ],
            ],
        ]
        self.name_subdevices = [f"phase_{i}" for i in range(1, 4)] +["total"]

    def to_electric_current(self, val):
        return val / 1000

    def to_electric_voltage(self, val):
        return val / 100

    def to_electric_frequency(self, val):
        return val / 100

    def to_electric_power(self, val):
        return val

    def to_electric_power_reactive(self, val):
        return val

    def to_electric_energy(self, val):
        return val

    def to_electric_energy_to_grid(self, val):
        return val

    def to_electric_energy_reactive(self, val):
        return val

    def to_electric_energy_reactive_to_grid(self, val):
        return val

    def to_electric_power_factor(self, val):
        return val / 1000


class SchneiderSensor(MBDevice):
    """
    This is the SchneiderSensor device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                0x0BB7,
                12,
                [["current", 0, 2, 0], ["current", 2, 2, 1], ["current", 4, 2, 2], ["current", 10, 2, 3]],
            ],
            [
                # 0x0BCB,
                3027,
                8,
                [["voltage", 0, 2, 0], ["voltage", 2, 2, 1], ["voltage", 4, 2, 2], ["voltage", 6, 2, 3]],
            ],
            [
                0x0BED,
                16,
                [
                    ["power", 0, 2, 0],
                    ["power", 2, 2, 1],
                    ["power", 4, 2, 2],
                    ["power", 6, 2, 3],
                    ["power_reactive", 8, 2, 0],
                    ["power_reactive", 10, 2, 1],
                    ["power_reactive", 12, 2, 2],
                    ["power_reactive", 14, 2, 3]
                ],
            ],
            [
                0x0A8B,
                12,
                [
                    ["energy", 0, 2, 3],
                    ["energy_reactive", 8, 2, 3],
                    ["energy_to_grid", 2, 2, 3],
                    ["energy_reactive_to_grid", 10, 2, 3],
                ],
            ],
            [
                0x0C05,
                8,
                [
                    ["power_factor", 0, 2, 0],
                    ["power_factor", 2, 2, 1],
                    ["power_factor", 4, 2, 2],
                    ["power_factor", 6, 2, 3]
                ],
            ]

        ]
        # self.name_subdevices = [f"phase_{i}" for i in range(1, 4)] +["total"]
        self.name_subdevices = [f"phase_{i}" for i in ["A", "B", "C"]] + ["total"]
        self.endian = "schneider"

    # def to_electric_energy(self, val):
    #     return val / 1000
    #
    # def to_electric_energy_to_grid(self, val):
    #     return val / 1000
    #
    # def to_electric_energy_reactive(self, val):
    #     return val / 1000
    #
    # def to_electric_energy_reactive_to_grid(self, val):
    #     return val / 1000

    def to_electric_power_factor(self, val):
        if val > 1:
            val = 2 - val
        elif val < -1:
            val = -2 - val
        return val


class HuaweiSolarLogger(MBDevice):
    """
    This is the HuaweiSolarLogger device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                40521,
                6,
                [
                    ["input_power", 0, 2, 3, "U32"],
                    ["co2_reduction", 2, 2, 3, "U32"],
                    ["power", 4, 2, 3, "I32"]
                ],
            ],
            [
                40532,
                1,
                [
                    ["power_factor", 0, 1, 3, "I16"]
                ]
            ],
            [
                40560,
                4,
                [
                    ["energy_total", 0, 2, 3, "U32"],
                    ["energy_daily", 2, 2, 3, "U32"]

                ],
            ],
            [
                41934,
                2,
                [
                    ["pv", 0, 2, 3, "U32"]
                ]
            ]
        ]
        self.name_subdevices = [f"phase_{i}" for i in ["A", "B", "C"]] +["total"]

    def to_electric_input_power(self, val):
        return val / 1000

    def to_electric_co2_reduction(self, val):
        return val / 10

    def to_electric_power(self, val):
        return val / 1000

    def to_electric_power_factor(self, val):
        return val / 1000

    def to_electric_energy_total(self, val):
        return val / 10

    def to_electric_energy_daily(self, val):
        return val / 10

    def to_electric_pv(self, val):
        return val / 1000


class UMG96RM(MBDevice):
    """
    This is the UMG96RM 3 phase device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                32260,
                25,
                [
                    ["voltage", 0, 2, 0, "U32"],
                    ["voltage", 2, 2, 1, "U32"],
                    ["voltage", 4, 2, 2, "U32"],
                    ["current", 12, 2, 0, "I32"],
                    ["current", 14, 2, 1, "I32"],
                    ["current", 16, 2 ,2, "I32"],
                    ["power", 18, 2, 3, "I32"],
                    ["power_reactive", 20, 2, 3, "I32"],
                    ["power_factor", 24, 1, 3, "I16"]
                ]
            ],
            [
                32341,
                24,
                [
                    ["total_active_electricity", 0, 4, 3, "I64"],
                    ["total_reactive_electricity", 4, 4, 3, "I64"],
                    ["negative_active_electricity", 8, 4, 3, "I64"],
                    ["negative_reactive_electricity", 12, 4, 3, "I64"],
                    ["positive_active_electricity", 16, 4, 3, "I64"],
                    ["positive_reactive_electricity", 20, 4, 3, "I64"],
                ]
            ]
        ]
        self.name_subdevices = [f"phase_{i}" for i in ["A", "B", "C"]] +["total"]

    def to_electric_voltage(self, val):
        return val / 100

    def to_electric_current(self, val):
        return val / 10

    def to_electric_power(self, val):
        return val / 1000

    def to_electric_power_reactive(self, val):
        return val / 1000

    def to_electric_power_factor(self, val):
        return val / 1000

    def to_electric_total_active_electricity(self, val):
        return val / 100

    def to_electric_total_reactive_electricity(self, val):
        return val / 100

    def to_electric_negative_active_electricity(self, val):
        return val / 100

    def to_electric_negative_reactive_electricity(self, val):
        return val / 100

    def to_electric_positive_active_electricity(self, val):
        return val / 100

    def to_electric_positive_reactive_electricity(self, val):
        return val / 100


class SUN2000(MBDevice):
    """
    This is the SUN2000 device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                32080,
                5,
                [
                    ["power", 0, 2, 3, "I32"],
                    ["power_reactive", 2, 2, 3, "I32"],
                    ["power_factor", 4, 1, 3, "I16"]
                ],
            ]
        ]
        self.name_subdevices = [f"phase_{i}" for i in ["A", "B", "C"]] +["total"]

    def to_electric_power(self, val):
        return val / 1000

    def to_electric_power_reactive(self, val):
        return val / 1000

    def to_electric_power_factor(self, val):
        return val / 1000


class SUN2000EMI(MBDevice):
    """
    This is the SUN2000EMI device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 1, lock, port)
        # del self.datapoint_supported["electric"]
        # Now setup the map
        self.map = [
            [
                40031,
                7,
                [
                    ["wind_speed", 0, 1, 0, "I16"],
                    ["wind_direction", 1, 1, 0, "I16"],
                    ["pv_module_temperature", 2, 1, 0, "I16"],
                    ["ambient_temperature", 3, 1, 0, "I16"],
                    ["total_irradiance", 4, 1, 0, "I16"],
                    ["daily_irradiation_amount", 5, 2, 0, "U32"],
                ],
            ]
        ]
        self.name_subdevices = [f"subdev_{i}" for i in ["0"]]

    def to_environment_wind_speed(self, val):
        return val / 10

    def to_environment_wind_direction(self, val):
        return val / 1

    def to_environment_pv_module_temperature(self, val):
        return val / 10

    def to_environment_ambient_temperature(self, val):
        return val / 10

    def to_environment_total_irradiance(self, val):
        return val / 10

    def to_environment_daily_irradiation_amount(self, val):
        return val / 1000


class RTR(MBDevice):
    """
    This is the Circutor 3 phase device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 1, lock, port)
        # Now setup the map
        self.map = [
            [
                0,
                14,
                [
                    ["voltage", 0, 2, 0, "F32"],
                    ["current", 2, 2, 0, "F32"],
                    ["power", 4, 2, 0, "F32"],
                    ["power_reactive", 6, 2, 0, "F32"],
                    ["power_apparent", 8, 2, 0, "F32"],
                    ["power_factor", 10, 2, 0, "F32"],
                    ["frequency", 12, 2, 0, "F32"]
                ]
            ],
            [
                40,
                18,
                [
                    ["energy", 0, 2, 0, "I32"],
                    ["energy_to_grid", 2, 2, 0, "I32"],
                    ["energy_net", 4, 2, 0, "I32"],
                    ["energy_total", 6, 2, 0, "I32"],
                    ["energy_reactive", 8, 2, 0, "I32"],
                    ["energy_reactive_to_grid", 10, 2, 0, "I32"],
                    ["energy_reactive_net", 12, 2, 0, "I32"],
                    ["energy_reactive_total", 14, 2, 0, "I32"],
                    ["energy_apparent", 16, 2, 0, "I32"]
                ]
            ]
        ]
        self.name_subdevices = ["phase_1"]

    def to_electric_voltage(self, val):
        return val

    def to_electric_current(self, val):
        return val

    def to_electric_power(self, val):
        return val

    def to_electric_power_reactive(self, val):
        return val

    def to_electric_power_apparent(self, val):
        return val

    def to_electric_power_factor(self, val):
        return val

    def to_electric_frequency(self, val):
        return val

    # def to_electric_pv(self, val):
    #     return val / 1000

    # def to_electric_input_power(self, val):
    #     return val / 1000

    def to_electric_energy(self, val):
        return val / 100

    def to_electric_energy_to_grid(self, val):
        return val / 100

    def to_electric_energy_net(self, val):
        return val / 100

    def to_electric_energy_total(self, val):
        return val / 100

    def to_electric_energy_reactive(self, val):
        return val / 100

    def to_electric_energy_reactive_to_grid(self, val):
        return val / 100

    def to_electric_energy_reactive_net(self, val):
        return val / 100

    def to_electric_energy_reactive_total(self, val):
        return val / 100

    def to_electric_energy_apparent(self, val):
        return val / 100


class PZEM016Sensor(MBDevice, altolib.AltoDeviceSensor):
    """
    This is the TPLink device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 1, lock, port)
        self.map = [
            [
                0x0,
                0x0A,
                [
                    ["voltage", 0x0, 1, 0],
                    ["current", 0x1, 2, 0],
                    ["power", 0x3, 2, 0],
                    ["energy", 0x5, 2, 0],
                    ["frequency", 0x7, 1, 0],
                    ["power_reactive", 0x8, 1, 0],
                    ["overload", 0x9, 1, 0],
                ],
            ]
        ]
        self.endian = "little"

    def to_electric_voltage(self, val):
        return val / 10

    def to_electric_frequency(self, val):
        return val / 10

    def to_electric_current(self, val):
        return val / 1000

    def to_electric_energy(self, val):
        return val / 1000

    def to_electric_power(self, val):
        return val / 10000

    def to_electric_power_reactive(self, val):
        return self.newvals[0]["power"] * tan(acos(val / 100))

    def to_device_overload(self, val):
        return val == 0xFFFF


class SchneiderPM5560(MBDevice):
    """
    This is the Circutor 3 phase device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                2999,
                6,
                [
                    ["current", 0, 2, 0, "F32"],
                    ["current", 2, 2, 1, "F32"],
                    ["current", 4, 2, 2, "F32"],
                ]
            ],
            [
                3027,
                6,
                [
                    ["voltage", 0, 2, 0, "F32"],
                    ["voltage", 2, 2, 1, "F32"],
                    ["voltage", 4, 2, 2, "F32"],
                ]
            ],
            [
                2699, # in datasheet it show 2700. it have to subtract with 1 and got 2699
                8,
                [
                    ["active_energy_delivered_into_load", 0, 2, 3, "F32"], # name, addr_idx, len, subdevice_index, type
                    ["active_energy_delivered_outoff_load", 2, 2, 3, "F32"],
                    ["active_energy_delivered_plus_received", 4, 2, 3, "F32"],
                    ["active_energy_delivered_minus_received", 6, 2, 3, "F32"]
                ],
            ],
            [
                4799,
                8,
                [
                    ["active_energy_delivered_rate_1", 0, 2, 3, "F32"], # name, addr_idx, len, subdevice_index, type
                    ["active_energy_delivered_rate_2", 2, 2, 3, "F32"],
                    ["active_energy_delivered_rate_3", 4, 2, 3, "F32"],
                    ["active_energy_delivered_rate_4", 6, 2, 3, "F32"]
                ],
            ],
            [
                4815,
                8,
                [
                    ["active_energy_received_rate_1", 0, 2, 3, "F32"],
                    ["active_energy_received_rate_2", 2, 2, 3, "F32"],
                    ["active_energy_received_rate_3", 4, 2, 3, "F32"],
                    ["active_energy_received_rate_4", 6, 2, 3, "F32"],
                ]
            ]
        ]
        self.name_subdevices = [f"phase_{i}" for i in range(1, 4)] +["total"]

    def to_electric_current(self, val):
        return val / 1
        
    def to_electric_voltage(self, val):
        return val / 1

    def to_electric_active_energy_delivered_into_load(self, val):
        return val / 1

    def to_electric_active_energy_delivered_outoff_load(self, val):
        return val / 1

    def to_electric_active_energy_delivered_plus_received(self, val):
        return val / 1

    def to_electric_active_energy_delivered_minus_received(self, val):
        return val / 1

    def to_electric_active_energy_delivered_rate_1(self, val):
        return val / 1

    def to_electric_active_energy_delivered_rate_2(self, val):
        return val / 1

    def to_electric_active_energy_delivered_rate_3(self, val):
        return val / 1

    def to_electric_active_energy_delivered_rate_4(self, val):
        return val / 1

    def to_electric_active_energy_received_rate_1(self, val):
        return val / 1

    def to_electric_active_energy_received_rate_2(self, val):
        return val / 1

    def to_electric_active_energy_received_rate_3(self, val):
        return val / 1

    def to_electric_active_energy_received_rate_4(self, val):
        return val / 1


class ENERIUM30(MBDevice):
    """
    This is the ENERIUM30 device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                0x0500,
                38,
                [
                    ["voltage", 0, 2, 0, "U32"],
                    ["voltage", 2, 2, 1, "U32"],
                    ["voltage", 4, 2, 2, "U32"],
                    # ["avg_3_voltage", 0, 6, 3, "U32"],
                    ["current", 14, 2, 0, "U32"],
                    ["current", 16, 2, 1, "U32"],
                    ["current", 18, 2 ,2, "U32"],
                    ["current", 20, 2 ,3, "U32"],
                    ["power", 22, 2, 0, "I32"],
                    ["power", 24, 2, 1, "I32"],
                    ["power", 26, 2 ,2, "I32"],
                    ["power", 28, 2 ,3, "I32"],
                    ["power_reactive", 30, 2, 0, "I32"],
                    ["power_reactive", 32, 2, 1, "I32"],
                    ["power_reactive", 34, 2, 2, "I32"],
                    ["power_reactive", 36, 2 ,3, "I32"]
                ]
            ],
            [
                0x051C,
                25,
                [
                    ["power_factor", 18, 1, 0, "I16"],
                    ["power_factor", 20, 1, 1, "I16"],
                    ["power_factor", 22, 1, 2, "I16"],
                    ["power_factor", 24, 1, 3, "I16"]
                ]
            ],
            [
                0x0996,
                12,
                [
                    ["energy", 0, 2, 3, "U32"],
                    ["energy_to_grid", 2, 2, 3, "U32"],
                    ["energy_reactive", 10, 2, 3, "U32"] # not checked yet
                ]
            ]
        ]
        self.name_subdevices = [f"phase_{i}" for i in ["A", "B", "C"]] +["total"]

    def to_electric_voltage(self, val):
        return val / 100

    def to_electric_current(self, val):
        return val / 10000

    def to_electric_power(self, val):
        return val / 1000

    def to_electric_power_reactive(self, val):
        return val / 1000

    def to_electric_power_factor(self, val):
        return val / 10000

    def to_electric_energy(self, val):
        return val / 1

    def to_electric_energy_to_grid(self, val):
        return val / 1

    def to_electric_energy_reactive(self, val):
        return val / 1


class EPR04S(MBDevice):
    """
    This is the EPR-04S device
    """

    def __init__(self, controller, unit, mac_addr, ip_addr, lock, port=MBPORT):
        super().__init__(controller, unit, mac_addr, ip_addr, 4, lock, port)
        # Now setup the map
        self.map = [
            [
                20,
                40,
                [
                    ["power", 0, 2, 0, "I16"],
                    ["power", 2, 2, 1, "I16"],
                    ["power", 4, 2 ,2, "I16"],
                    ["power_reactive", 6, 2, 0, "I16"],
                    ["power_reactive", 8, 2, 1, "I16"],
                    ["power_reactive", 10, 2, 2, "I16"],
                    ["power_apparent", 12, 2, 0, "U16"],
                    ["power_apparent", 14, 2, 1, "U16"],
                    ["power_apparent", 16, 2, 2, "U16"],
                    ["power_factor", 18, 2, 0, "I16"],
                    ["power_factor", 20, 2, 1, "I16"],
                    ["power_factor", 22, 2, 2, "I16"],
                    ["power", 24, 2, 3, "I16"],
                    ["power_to_grid", 26, 2, 3, "I16"],
                    ["power_reactive", 28, 2 ,3, "I16"],
                    ["power_apparent", 32, 2, 3, "U16"],
                    ["power_factor", 34, 2, 3, "I16"]
                    ["frequency", 38, 2, 3, "I16"]
                ]
            ],
            [
                86,
                32,
                [
                    ["energy", 0, 4, 3, "I64"],
                    ["energy_to_grid", 4, 4, 3, "I64"],
                    ["energy_reactive", 8, 4, 3, "I64"]
                    # ["energy", 0, 4, 2, "U32"],
                    # ["energy", 0, 4, 3, "U32"],
                    # ["energy_to_grid", 2, 2, 3, "U32"],
                    # ["energy_reactive", 10, 2, 3, "U32"] # not checked yet
                ]
            ]
        ]
        self.name_subdevices = [f"phase_{i}" for i in ["A", "B", "C"]] +["total"]

    def to_electric_power(self, val):
        return val / 10

    def to_electric_power_reactive(self, val):
        return val / 10
    
    def to_electric_power_apparent(self, val):
        return val / 10

    def to_electric_power_factor(self, val):
        return val / 1000
    
    def to_electric_power_to_grid(self, val):
        return val / 10
    
    def to_electric_frequency(self, val):
        return val / 100

    def to_electric_energy(self, val):
        return val / 1

    def to_electric_energy_to_grid(self, val):
        return val / 1
    
    def to_electric_energy_reactive(self, val):
        return val / 1

    # def to_electric_energy_reactive(self, val):
    #     return val / 1


def modbus(config_path, **kwargs):
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
    kwargs["agent_name"] = config.get("agent_name", "modbus")
    kwargs["sampling_rate"] = config.get("sampling_rate", 120)
    # Key is IP address and value a liat of 3-uples (unit numbers
    kwargs["configured_devices"] = config.get("configured_devices", {})

    return Modbus(topic, **kwargs)


class Modbus(altolib.AltoDiscoverableAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        self._sampling_rate_cd = 15
        self.auto_send = True  # We update at high frequecy, let the agent manage
        # self.discovery_lock = Lock()
        self.sample_locks = {}
        self.connectors = {}
        self.queue = Queue()
        _log.debug("vip_identity: " + self.core.identity)
        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

    def start_discovery(self):
        # for ipaddr in self.configured_devices:
        for ipaddr, list_config in self.configured_devices.items():
            try:
                # Ping first
                if ipaddr not in self.sample_locks:
                    self.sample_locks[ipaddr] = Lock()
                ping = subprocess.Popen(
                    ["ping", "-c", "1", ipaddr],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                out, error = ping.communicate()
                # maddr = getmac.get_mac_address(ip=ipaddr)
                # maddr = "9c:a5:25:bb:e2:00" # force mac address
                # for devtype, unit, port in self.configured_devices[ipaddr]:
                for devtype, unit, port, maddr in list_config:
                    Sensor = device_factory(devtype)
                    newdev = Sensor(
                        self, unit, maddr, ipaddr, self.sample_locks[ipaddr], port
                    )
                    self.register_new_device(newdev)
                    if not ipaddr in self.connectors:
                        self.connectors[ipaddr] = {}
                    self.connectors[ipaddr][port] = None
            except Exception as e:
                _log.error(f"Discovery problem: {e}")
                _log.debug(e)

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

    def get_connector(self, ip, port):
        if self.connectors[ip][port] is None:
            self.connectors[ip][port] = ModbusTcpClient(ip, port)
            self.connectors[ip][port].strict = False
            self.connectors[ip][port].connect()
        return self.connectors[ip][port]

    def reset_connector(self, ip, port):
        if not self.connectors[ip][port] is None:
            self.connectors[ip][port].close()
            self.connectors[ip][port] = None

    def last_rites(self):
        self.queue.put_nowait("Die")


def main():
    """Main method called to start the agent."""
    utils.vip_main(modbus, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
