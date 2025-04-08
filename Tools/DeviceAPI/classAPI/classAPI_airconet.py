# -*- coding: utf-8 -*-

import json
import logging
# import libscrc
import socket
# from volttron.platform.agent import utils

_log = logging.getLogger(__name__)
# utils.setup_logging()

INITIAL_MODBUS = 0xFFFF
INITIAL_DF1 = 0x0000

table = (
0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040)

class API:
    # 1. constructor : gets call every time when create a new class
    # requirements for instantiation1. model, 2.device_type, 3.api, 4. address, 5. port, 6.config (with discovery info)
    def __init__(self, **kwargs):
        # Initialized common attributes
        self.variables = kwargs
        self.debug = True
        self.set_variable('offline_count', 0)   #สร้าง dict เพิ่มให้ variables
        self.set_variable('connection_renew_interval', 6000)
        self.set_variable('last_command', '')

    def set_variable(self, k, v):  # k=key, v=value
        self.variables[k] = v

    def get_variable(self, k):
        return self.variables.get(k, None)  # default of get_variable is none

    # 2. Attributes from Attributes table
    '''
    Attributes:
     ------------------------------------------------------------------------------------------
     status      W R    Write(on,off,set)  Read(last_status)
     MODE        W      cool  hot  auto  fan  dry
     FAN_LV      W      fan1  fan2 fan3  autofan
     TEMP        W      16-32
     ------------------------------------------------------------------------------------------
    '''
    # 3. Capabilites (methods) from Capabilities table
    '''
    API3 available methods:
    1. getDeviceStatus() GET
    '''

    def setDeviceStatus(self, postmsg):
            print("setDeviceStatus get : "+str(postmsg))
            server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            addr = (postmsg["ip"], postmsg["port"])

            POWER_CODE = str(postmsg['status']).upper()
            MODE_CODE = str(postmsg['mode']).lower()
            FAN_CODE = str(postmsg['fan']).lower()
            TEMP_CODE = int(postmsg['settemp'])

            POWER = {"ON": "55", "OFF": "AA"}
            MODE = {"cool": "11", "hot": "22", "auto": "33", "fan": "44", "dry": "55"}
            FAN = {"low": "01", "medium": "02", "high": "03", "auto": "00", "turbo": "03"}
            TEMP = {16: "00A0", 17: "00AA", 18: "00B4", 19: "00BE", 20: "00C8", 21: "00D2", 22: "00DC", 23: "00E6",24: "00F0",25: "00FA", 26: "0104", 27: "010E", 28: "0118", 29: "0122", 30: "012C", 31: "0136", 32: "0140"}

            if POWER_CODE == "OFF":
                command = "01069C4000AA2631"
                print("off" + command)

            # elif POWER_CODE == "on":
            #     command = "01069C4000556671"
            #     print("on" + command)

            elif POWER_CODE == "LAST_STATUS":
                command = "01039C4000086B88"
                print("LAST_STATUS send ---> " + command)

            elif POWER_CODE == "ON":



                command = "01109C4000081000" + POWER[POWER_CODE] + "000000" + MODE[MODE_CODE] + "00" + FAN[FAN_CODE] + "00000000" + TEMP[TEMP_CODE] + "0B01"
                st = "".join([chr(int(command[i:i + 2], 16)) for i in range(0, len(command), 2)])
                print(st)
                crc16 = str(hex(self.calcString(st, INITIAL_MODBUS)))
                # crc16 = str(hex(libscrc.modbus(str(bytearray.fromhex(command)))))  # TODO remove this if we dn't need
                print(crc16)
                crc16 = crc16[2:]
                if len(crc16) < 4:
                    crc16 = "0"*(4-len(crc16)) + crc16
                print(crc16)
                crc16 = crc16[2:] + crc16[0:2]
                command = command + crc16
                print("settemp  " , command)

            print(len(command))
            commanda = bytes(bytearray.fromhex(command))
            print(type(commanda))
            #     # while data!='q':
            # a = b'\x01\x10\x9c@\x00\x08\x10\x00U\x00\x00\x00\x11\x00\x02\x00\x00\x00\x00\x01\x18\x0b\x01\xcd\xff'
            print('a: {}'.format(commanda))
            print(addr)
            server.sendto(commanda, addr)

    def calcByte(self, ch, crc):
       """Given a new Byte and previous CRC, Calc a new CRC-16"""
       if type(ch)==type("c"):
           by = ord(ch)
       else:
           by = ch
       crc = (crc >> 8) ^ table[(crc ^ by) & 0xFF]
       return (crc & 0xFFFF)

    def calcString(self, st, crc):
       """Given a bunary string and starting CRC, Calc a final CRC-16 """
       for ch in st:
           crc = (crc >> 8) ^ table[(crc ^ ord(ch)) & 0xFF]
       return crc


# This main method will not be executed when this class is used as a module
def main():
    # create an object with initialized data from DeviceDiscovery Agent
    # requirements for instantiation1. model, 2.type, 3.api, 4. address
    # Airconet = API(model='airconet', type='aircondiner', api='classAPI_airconet', agent_id='airconet1',
    #                 address='192.168.1.112', port=5380, macaddr=device)

    Airconet = API(model='airconet', type='aircondiner', api='classAPI_airconet', agent_id='airconet1')
    Airconet.setDeviceStatus({"settemp": 17, "mode": "fan", "fan": "high", "status": "on", "mac": "cc50e33b11aa",
                              "ip": "192.168.1.105", "port": 1540 })
    Airconet.setDeviceStatus({"settemp": 17, "mode": "dry", "fan": "low", "status": "on", "mac": "cc50e33b113b1",
                              "ip": "192.168.1.106", "port": 5637})

if __name__ == "__main__":
    main()
