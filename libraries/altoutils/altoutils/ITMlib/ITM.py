import requests
import base64
import struct
import logging

_log = logging.getLogger(__name__)

GET_RESPONSEMAP = {
                    "command_size":"command_size",
                    "command_id":"command_id",
                    "reserved1":"reserved1",
                    "reserved2":"reserved2",
                    "reserved3":"reserved3",
                    "reserved4":"reserved4",
                    "reserved5":"reserved5",
                    "number_a/c":"number_a/c",
                    "a/c_address":"a/c_address",
                    "status":"status",
                    "malfunction_code":"malfunction_code",
                    "on_off":"on_off",
                    "operation_mode":"operation_mode",
                    "ventilation_mode":"ventilation_mode",
                    "ventilation_amount":"ventilation_amount",
                    "enable/disable_temp":"enable/disable_temp",
                    "room_temp":"room_temp",
                    "set_temp":"set_temp",
                    "fan_speed":"fan_speed",
                    "fan_direction":"fan_direction",
                    "filter_sign":"filter_sign",
                    "defrost/hotstart":"defrost/hotstart"
                }
SET_RESPONSEMAP = {
                    "command_size":"command_size",
                    "command_id":"command_id",
                    "reserved_1":"reserved_1",
                    "reserved_2":"reserved_2",
                    "reserved_3":"reserved_3",
                }
for i in range(1, 65):
    SET_RESPONSEMAP[f"address_{i}"] = f"address_{i}"

class ITMHandler:
    
    def __init__(self, username, password, itm_ip, itm_port):
        self._username = username
        self._password = password
        self._itm_ip = itm_ip
        self._itm_port = itm_port
        self._encode_simple_auth()

    def _update_username_password(self, username, password):
        self._username = username
        self._password = password
        self._encode_simple_auth()

    def _encode_simple_auth(self):
        message = f"{self._username}:{self._password}"
        base64_bytes = base64.b64encode(message.encode("ascii"))
        self._base64_simple_auth = base64_bytes.decode("ascii")

    def request(self, content_length, body):
        # url = "http://<192.168.111.201>:<8081>/cmd/"
        url = f"http://{self._itm_ip}:{self._itm_port}/cmd/"
        header = {
                    "Authorization":f"Basic {self._base64_simple_auth}",
                    "Content-Length": content_length,
                    "Content-Type": "application/octet-stream"
                 }
        r = requests.post(url, headers=header, data=bytes(body))
        try:
            if r.status_code == 200:
                _log.debug(f"request: {r}")
                return r
            _log.debug(f"request: {r}")
            return False
        except Exception as e:
            print(f"request: Exception {e}")
            _log.error(f"request: Exception {e}")

    def _convert_addr_to_int(self, ac_addr: str) -> int:
        ac_bit = ""
        addr = ac_addr.split("-")

        """ calculate bit (ex. 1-04 -> bit=00010000 -> dec=16, hex=10) """
        if int(addr[1]) <= 7:
            for i in range(8):
                if i == 7 - int(addr[1]):
                    ac_bit += "1"
                else : 
                    ac_bit += "0"
        elif int(addr[1]) > 7 and int(addr[1]) <= 15:
            for i in range(8):
                if i == 15 - int(addr[1]):
                    ac_bit += "1"
                else: 
                    ac_bit += "0"
        return int(ac_bit, 2)
    
    def _convert_to_body_idx(self, d_ac: dict) -> int:
        """
        Assign an index to a body list
        index start = 16
        index end = 63
        """
        ret_idx = 0
        map_ac = {}
        doc_port = {"1": 16, "2": 24, "3": 32, "4": 40, "5": 48, "6": 56, "7": 64, "8": 72}
        ind_ac_addr = [
                        {"1":"0"},
                        {"1":"1"}, 
                        {"2":"0"}, 
                        {"2":"1"}, 
                        {"3":"0"}, 
                        {"3":"1"}, 
                        {"4":"0"}, 
                        {"4":"1"}
                    ]
        for k in d_ac:
            map_ac[d_ac[k][0]] = d_ac[k][2]
            for idx, val in enumerate(ind_ac_addr):
                if map_ac == val:
                    ret_idx = doc_port[k] + idx
        return ret_idx
    
    def _convert_bytearrays_to_hex_str(self, byte_array: bytearray, byte_list: list, method: str="SET"):
        res = []
        n = 0
        for i in byte_list:
            if i == 4:
                res.append([byte_array[n], byte_array[n+1], byte_array[n+2], byte_array[n+3]])
                n += i
            elif i == 2:
                res.append([byte_array[n], byte_array[n+1]])
                n += i
            elif i == 1:
                res.append([byte_array[n]])
                n += i

        for idx_li ,li in enumerate(res):
            if method == "GET" and idx_li == 10:
                continue
            else:
                for i, v in enumerate(li):
                    li[i] = hex(v).split("0x")
                    if li[i][1] == "ff":
                        del li[i][1]
                        li[i][0] = "-1"
                    else:
                        del li[i][0]

        for idx_j, l in enumerate(res):
            hex_str = "0x"
            l = l[-1::-1]
            if method == "GET" and idx_j == 10:
                for i, val in enumerate(l):
                    if val in range(0, 8):
                        l[i] = str(val)
                    else:
                        l[i] = chr(val)
                res[idx_j] = l[0] + l[1]
            else:
                for val in l:
                    hex_str += val[0]
                    if hex_str == "0x-1" or hex_str == "0x0-1":
                        res[idx_j] = "-1"
                    else:
                        res[idx_j] = hex_str
        return res

    def _convert_hex_to_float(self, hex_str: str):
        sp_hex_str = hex_str.split("0x") # ['', '41c000']
        if "-1" in sp_hex_str[1]:
            sp_hex_str[1] = sp_hex_str[1].replace("-1", "ff")
        if len(sp_hex_str[1]) < 9:
            for i in range(8 - len(sp_hex_str[1])):
                sp_hex_str[1] += "0"
        ret = struct.unpack("!f", bytes.fromhex(sp_hex_str[1]))[0]
        return ret

    def _idx_of_set(self, port: str, ac_addr: str):
        sp_addr = ac_addr.split("-")
        map_ac_port = {"1": 0, "2": 64, "3": 128, "4": 192, "5": 256, "6": 320, "7": 384, "8": 448}
        map_ac_addr = {"1": 0, "2": 16, "3": 32, "4": 48}
        if port not in map_ac_port:
            _log.error(f"port out of range: {port}")
            return False
        else:
            idx = map_ac_port[port]
            if sp_addr[0] not in map_ac_addr:
                _log.error(f"ac_addr out of range: {ac_addr}")
                return False
            elif int(sp_addr[1]) > 15:
                _log.error(f"ac_addr out of range: {ac_addr}")
                return False
            else:
                idx +=  map_ac_addr[sp_addr[0]] + int(sp_addr[1])
                return idx        
    
    def _check_idx_set(self, port, ac_addr):
        ret_idx = 0
        map_ac = {}
        sp_addr = ac_addr.split("-")
        doc_port = {"1": 20,"2": 28,"3": 36,"4": 44,"5": 52,"6": 60,"7": 68,"8": 76}
        ind_ac_addr = [
                        {"1": "0"}, 
                        {"1": "1"}, 
                        {"2": "0"}, 
                        {"2": "1"}, 
                        {"3": "0"}, 
                        {"3": "1"}, 
                        {"4": "0"}, 
                        {"4": "1"}
                    ]
        d_ac = {port: [sp_addr[0], sp_addr[1], "0"]}
        idx_addr = int(sp_addr[1])
        if idx_addr <= 7:
            d_ac[port][2] = "0"
        elif idx_addr > 7 and idx_addr <= 15:
            d_ac[port][2] = "1"

        for k in d_ac:
            map_ac[d_ac[k][0]] = d_ac[k][2]
            for idx, val in enumerate(ind_ac_addr):
                if map_ac == val:
                    ret_idx = doc_port[port] + idx
        
        return ret_idx

    def get_status(self, port, ac_addr):
        content_length = "80"
        map_response = GET_RESPONSEMAP.copy()
        response_value = {"status":{
                                    1: "normal",
                                    0: "error",
                                    -1: "unconnected"
                                },
                        "on_off":{
                                    0: "off",
                                    1: "on",
                                    2: "unknown"
                                },
                        "operation_mode":{
                                    0x1000: "unknown",
                                    0x0001: "fan",
                                    0x0002: "heat",
                                    0x0004: "cool",
                                    0x0020: "ventilation",
                                    0x0040: "dry",
                                    0x0100: "auto(Heat)",
                                    0x0200: "auto(Cool)"
                                },
                        "ventilation_mode":{
                                    0x100: "unknown",
                                    0x0001: "automatic",
                                    0x0002: "heat_exchange",
                                    0x0004: "bypass"
                                },
                        "ventilation_amount":{
                                    0x100: "unknown",
                                    0x0001: "automatic(normal)",
                                    0x0002: "weak(normal)",
                                    0x0004: "strong(normal)",
                                    0x0008: "automatic(fresh up)",
                                    0x0010: "weak(fresh up)",
                                    0x0020: "strong(fresh up)"
                                },
                        "enable/disable_temp":{
                                    0:"all disable",
                                    1:"set_temp: enable",
                                    2:"room_temp: enable",
                                    3:"all enable"
                                },
                        "fan_speed":{
                                    0:"low",
                                    1:"medium",
                                    2:"high",
                                    100:"auto",
                                    -1:"unknown"
                                },
                        "fan_direction":{
                                    0:"position_0",
                                    1:"position_1",
                                    2:"position_2",
                                    3:"position_3",
                                    4:"position_4",
                                    7:"swing",
                                    -1:"unknown"
                                },
                            }
        body = [0x50,0x00,0x00,0x00, # Command size = 80
                0x74,0x11,0x01,0x00, # Command id = 70004
                0x00,0x00,0x00,0x00, # Reserved 1
                0x00,0x00,0x00,0x00] # Reserved 2

        for _ in range(64):
            body.append(0)
        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx_addr = int(ac_addr[2:])
            d_ac = {port: [
                            ac_addr[0],
                            int_ac,
                            "0"
                        ]
                }
            if idx_addr <= 7:
                d_ac[port][2] = "0"
            elif idx_addr > 7 and idx_addr <= 15:
                d_ac[port][2] = "1"

            idx = self._convert_to_body_idx(d_ac)
            body[idx] = int_ac

            """ request to Daikin HTTP API """
            r = self.request(content_length, body)
            if not r:
                _log.error(f"get_status: {r}")
                return None

            """ format to understanding words/values """
            b2bl = bytearray(r.content)
            data_num = [4, 4, 4, 4, 4, 4, 4, 4, 4, 2, 2, 2, 2, 2, 2, 4, 4, 4, 1, 1, 1, 1]
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num, "GET")
            reserved = ["reserved1", "reserved2", "reserved3", "reserved4", "reserved5"]
            for x, y in zip(map_response, res_map):
                if x in reserved:
                    if "-1" in y:
                        y = y.replace("-1", "ff")
                        map_response[x] = int(y, 16)
                    else:
                        map_response[x] = int(y, 16)
                elif x == "malfunction_code":
                    map_response[x] = y[::-1]
                elif x == "set_temp":
                    f = self._convert_hex_to_float(y)
                    map_response[x] = f
                elif x == "room_temp":
                    f = self._convert_hex_to_float(y)
                    map_response[x] = round(f, 2)
                elif y == "-1":
                    map_response[x] = -1
                else:
                    map_response[x] = int(y, 16)
            
            for k, v in map_response.items():
                if k in response_value:
                    map_response[k] = response_value[k][v]
            _log.debug(f"get_status [{port}:{ac_addr}]: {map_response}")
            return map_response
        except Exception as e:
            print(f"get_status: Exception {e}") 

    def set_on_off(self, port, ac_addr, mode):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        map_mode = {  
                        "off":0x00,
                        "on":0x01
                    }
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x01, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)
        ]
        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_on_off: {idx}")

            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            if mode in map_mode:
                body[40] = map_mode[mode]
            else:
                _log.error(f"Mode out of range: {mode}")
                return False

            # Daikin HTTP request
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_on_off: {r}")
                return None
            
            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_on_off [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_on_off: Exception {e}")

    def set_mode(self, port, ac_addr, mode):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        map_mode = {  
                        "fan":0x01,
                        "cool":0x04,
                        "dry":0x40
                    }
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x03, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)]
        ]
        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_mode: {idx}")
            
            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            if mode in map_mode:
                body[40] = 1
                body[42] = map_mode[mode]
            else:
                _log.error(f"Mode out of range: {mode}")
                return False

            # Daikin HTTP request
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_mode: {r}")
                return None
            
            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_mode: Success {ac_addr}")
                _log.debug(f"set_mode [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_mode: Exception {e}")

    def set_fan(self, port, ac_addr, speed_level):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        map_mode = {  
                            "low":0,
                            "medium":1,
                            "high":2,
                            "auto":100
                        }
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x20, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)]
        ]
        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_fan: {idx}")
            
            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            if speed_level in map_mode:
                body[52] = map_mode[speed_level]
            else:
                _log.error(f"Mode out of range: {speed_level}")
                return False

            # request to Daikin HTTP API
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_fan: {r}")
                return None

            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)

            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_fan [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_fan: Exception {e}")

    def set_fan_direction(self, port, ac_addr, direction):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        map_mode = {  
                        "position_0":0,
                        "position_1":1,
                        "position_2":2,
                        "position_3":3,
                        "position_4":4,
                        "swing":7
                    }
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x40, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)]
        ]

        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_fan_direction: {idx}")
            
            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            if direction in map_mode:        
                body[53] = map_mode[direction]
            else:
                _log.error(f"Mode out of range: {direction}")
                return False

            # request to Daikin HTTP API
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_fan_direction: {r}")
                return None

            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_fan_direction [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_fan_direction: Exception {e}")

    def set_ventilation_mode(self, port, ac_addr, mode):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        map_mode = {  
                        "automatic":1,
                        "heat_exchange":2,
                        "bypass":4,
                    }
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x04, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)]
        ]

        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_ventilation_mode: {idx}")

            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            if mode in map_mode.keys():
                body[44] = map_mode[mode]
            else:
                _log.error(f"Mode out of range: {mode}")
                return False

            # request to Daikin HTTP API
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_ventilation_mode: {r}")
                return None

            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_ventilation_mode [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_ventilation_mode: Exception {e}")

    def set_ventilation_amount(self, port, ac_addr, mode):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        map_mode = {  
                        "automatic_nornal":1,
                        "weak_normal":2,
                        "strong_normal":4,
                        "automatic_fresh_up":8,
                        "weak_fresh_up":0x10,
                        "strong_fresh_up":0x20,
                    }

        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x08, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)]
        ]

        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_ventilation_amount: {idx}")
            
            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            if mode in map_mode.keys():
                body[46] = map_mode[mode]
            else:
                _log.error(f"Mode out of range: {mode}")
                return False

            """ request to Daikin HTTP API """
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_ventilation_amount: {r}")
                return None

            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_ventilation_amount [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_ventilation_amount: Exception {e}")

    def set_temperature(self, port, ac_addr, set_point):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x10, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)
        ]
        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_temperature: {idx}")
            
            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x" + h_ind[1][0], 16)

            # adjust mode
            d_int2hex = {
                            16:[0x00,0x00,0x80,0x41],
                            17:[0x00,0x00,0x88,0x41],
                            18:[0x00,0x00,0x90,0x41],
                            19:[0x00,0x00,0x98,0x41],
                            20:[0x00,0x00,0xa0,0x41],
                            21:[0x00,0x00,0xa8,0x41],
                            22:[0x00,0x00,0xb0,0x41],
                            23:[0x00,0x00,0xb8,0x41],
                            24:[0x00,0x00,0xc0,0x41],
                            25:[0x00,0x00,0xc8,0x41],
                            26:[0x00,0x00,0xd0,0x41],
                            27:[0x00,0x00,0xd8,0x41],
                            28:[0x00,0x00,0xe0,0x41],
                            29:[0x00,0x00,0xe8,0x41],
                            30:[0x00,0x00,0xf0,0x41],
                            31:[0x00,0x00,0xf8,0x41],
                            32:[0x00,0x00,0x00,0x42]
                        }
            if set_point in d_int2hex:
                body[48] = d_int2hex[set_point][0]
                body[49] = d_int2hex[set_point][1]
                body[50] = d_int2hex[set_point][2]
                body[51] = d_int2hex[set_point][3]
            else:
                _log.error(f"temperature out of range: {set_point}")
                return False

            # request to Daikin HTTP API
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_temperature: {r}")
                return None

            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_temperature [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_temperature: Exception {e}")

    def set_filter(self, port, ac_addr, reset):
        content_length = "56"
        map_response = SET_RESPONSEMAP.copy()
        body = [0x40, 0x00, 0x00, 0x00, # Command size
                0x76, 0x11, 0x01, 0x00, # Command id
                0x01, 0x00, 0x00, 0x00, # number of a/c to set status
                0x00, 0x00, 0x00, 0x00, # Reserved 1 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 2 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 3 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 4 (Don't care)
                0x00, 0x00, 0x00, 0x00, # Reserved 5 (Don't care)
                0x00, 0x00, 0x00, 0x00, # A/C Address (1-04, binary = 00010000)
                0x00, 0x00, 0x00, 0x00, # Setting Bit (enable = 1b, disable = 0b)
                0x00, 0x00, # ON/OFF (Off=0, On=1)
                0x00, 0x00, # Operation mode (ex. fan=0x0001, cool=0x0004)
                0x00, 0x00, # Ventilation mode (auto=0x0001)
                0x00, 0x00, # Ventilation amount (auto(normal)=0x0001)
                0x00, 0x00, 0x00, 0x00, # Set temp (degree(float))
                0x00, # Fan speed (low=0, medium=1, high=2, auto=100)
                0x00, # Fan direction (Direction=0-4, swing=7)
                0x00, # Filter Sign reset (Reset=1)
                0x00  # Reserved 6 (Don't care)]
        ]
        try:
            int_ac = self._convert_addr_to_int(ac_addr)
            idx = self._idx_of_set(port, ac_addr)
            if not idx:
                _log.error(f"set_filter: {idx}")
            
            if idx <= 255:
                body[32] = idx
            elif idx > 255:
                h_ind = hex(idx).split("0x")
                body[32] = int("0x" + h_ind[1][1:], 16)
                body[33] = int("0x"+h_ind[1][0], 16)

            # adjust mode 
            if reset == "1":
                body[54] = 1

            # request to Daikin HTTP API
            r = self.request(content_length, body)
            if not r:
                _log.error(f"set_filter: {r}")
                return None

            b2bl = bytearray(r.content)
            data_num = [4,4,4,4,4]
            for _ in range(64):
                data_num.append(1)
            res_map = self._convert_bytearrays_to_hex_str(b2bl, data_num)
            ret_idx = self._check_idx_set(port, ac_addr)
            for i, v in enumerate(res_map):
                res_map[i] = int(v, 16)
            for x, y in zip(map_response, res_map):
                map_response[x] = y
            if res_map[ret_idx - 15] == int(int_ac):
                # print(f"set_on_off: Success {ac_addr}")
                _log.debug(f"set_filter [{port}:{ac_addr}]: Success")
                return True
            else:
                _log.debug(f"False")
                return False
        except Exception as e:
            print(f"set_filter: Exception {e}")
    
class ITMFCU:

    def __init__(self, port, ac_addr, itm_handler):
        self._itm_handler = itm_handler
        self._port = port
        self._ac_addr = ac_addr

    def get_status(self):
        ret = self._itm_handler.get_status(self._port, self._ac_addr)
        if not ret:
            return False
        # _log.debug(f"ITMFCU get_status: {ret}")
        return ret
    
    def set_on_off(self, mode):
        ret = self._itm_handler.set_on_off(self._port, self._ac_addr, mode)
        if not ret:
            return ret
        return ret
    
    def set_mode(self, mode):
        ret = self._itm_handler.set_mode(self._port, self._ac_addr, mode)
        if not ret:
            return False
        # _log.debug(f"ITMFCU set_mode: {ret}")
        return ret
    
    def set_fan(self, mode):
        ret = self._itm_handler.set_fan(self._port, self._ac_addr, mode)
        if not ret:
            return False
        # _log.debug(f"ITMFCU set_fan: {ret}")
        return ret
    
    def set_fan_direction(self, mode):
        ret = self._itm_handler.set_fan_direction(self._port, self._ac_addr, mode)
        if not ret:
            return False
        # _log.debug(f"ITMFCU set_fan_direction: {ret}")
        return ret
    
    def set_temperature(self, set_point):
        ret = self._itm_handler.set_temperature(self._port, self._ac_addr, set_point)
        if not ret:
            return False
        # _log.debug(f"ITMFCU set_temperature: {ret}")
        return ret

class ITMOAU:

    def __init__(self, port, ac_addr, itm_handler):
        self._itm_handler = itm_handler
        self._port = port
        self._ac_addr = ac_addr

    def get_status(self):
        ret = self._itm_handler.get_status(self._port, self._ac_addr)
        if not ret:
            return False
        # _log.debug(f"ITMOAU get_status: {ret}")
        return ret
    
    def set_mode(self, mode):
        ret = self._itm_handler.set_on_off(self._port, self._ac_addr, mode)
        if not ret:
            return False
        # _log.debug(f"ITMOAU set_mode: {ret}") 
        return ret