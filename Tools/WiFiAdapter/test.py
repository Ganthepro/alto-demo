import requests
import json
import time


class DaikinWiFiAdapterHandler:

    def __init__(self, ip_addr):
        self._ip_addr = ip_addr

    def get_status(self):
        try:
            r_control_info = requests.get(("http://" + self._ip_addr + "/aircon/get_control_info"), timeout=9)
            r_json = r_control_info.json()
            print(f"status {r_control_info.status_code} {r_json}")

            r_sensor_info = requests.get(("http://" + self._ip_addr + "/aircon/get_sensor_info"), timeout=9)
            rs_json = r_sensor_info.json()
            print(f"status {r_sensor_info.status_code} {rs_json}")

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
            print(f"DaikinWiFiAdapterHandler get_status error {er}")

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
            print(f"set_on_off status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            print(f"DaikinWiFiAdapterHandler set_on_off error {er}")
        
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
            print(f"set_mode status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            print(f"DaikinWiFiAdapterHandler set_mode error {er}")
        
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
            print(f"set_fan status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            print(f"DaikinWiFiAdapterHandler set_fan error {er}")
        
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
            print(f"set_fan_direction status {mode} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            print(f"DaikinWiFiAdapterHandler set_fan_direction error {er}")
        
        return False
    
    def set_temperature(self, set_point):
        set_point = int(set_point)
        if set_point < 18 or set_point > 32:
            return False

        try:
            r_control_info = requests.get((f"http://{self._ip_addr}/aircon/set_control_info?stemp={set_point}"), timeout=9)
            r_json = r_control_info.json()
            print(f"set_temperature {set_point} {r_control_info.status_code} {r_json}")

            if r_control_info.status_code == 200:
                if r_json["ret"] == "OK":
                    return True

        except Exception as er:
            print(f"DaikinWiFiAdapterHandler set_temperature error {er}")


a = DaikinWiFiAdapterHandler("192.168.1.201")
print(a.get_status())
# print(a.set_on_off("on"))
# print(a.set_fan("medium"))
# print(a.set_fan_direction("position_0"))
# print(a.set_mode("cool"))
print(a.set_temperature(25))
