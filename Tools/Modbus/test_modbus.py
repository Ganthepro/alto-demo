from pymodbus.client.sync import ModbusTcpClient as ModbusClient

from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from time import sleep


# client = ModbusClient('192.168.1.11', port = 502, baudrate=9600)
client = ModbusClient('192.168.2.101', port = 502)
# client = ModbusClient('192.168.1.10', port = 502)
try:
    # client.strict = False
    print(client.connect())
    # r=client.read_holding_registers(4799, 8, unit=1) # 4800 40562 32260, 1836 year, 4800 - 1 = 4799
    r=client.read_holding_registers(2999, 2, unit=2) # 4800 40562 32260, 1836 year, 4800 - 1 = 4799
    # https://docs.google.com/spreadsheets/d/1sfOjHcURdB0riruMj9MuDxMfHUtfpU-r/edit#gid=216354813
    print(r)
    # r=client.write_register(0x2B, 65, unit=1)
    print(r.registers)
except Exception as er:
    print(f" X:{er}")
else:
    print("Unit: ")
    # break
finally:
    client.close()

# client = ModbusClient('192.168.1.10', port = 502)
# for i in range(160):
#     try:
#         # client.strict = False
#         print(client.connect())
#         r=client.read_holding_registers(40525, 2, unit=i) # 4800
#         print(r.registers)
#         # r=client.write_register(0x2B, 65, unit=1)
#         print(r.registers)
#     except:
#         print(" X")
#     else:
#         print("Unit: ", i)
#         break
#     finally:
#         client.close()
#     sleep(0.25)
