import requests
import json
import time
import logging

_log = logging.getLogger(__name__)

BASE_URL = "https://dashboard.airveda.com/api/"

def AirvedaAuthfactory(auth_type):
    if auth_type == "alto":
        return AltoAirvedaAuth
    elif auth_type == "airveda":
        return AirvedaAuth

class AltoAirvedaAuth:
    pass


class AirvedaAuth:

    def __init__(self, email, password):
        self._email = email
        self._password = password
        self._token = None
        self._refresh_token = None
        self.time = None
        self._connect()
        
    def _connect(self):
        end_point = "token/"
        header = {"Content-Type": "application/json"}
        body = {
            "email": self._email,
            "password": self._password
        }
        response = requests.post(BASE_URL+end_point, headers=header, data=json.dumps(body), timeout=20)
        try:
            if response.ok:
                data = response.json()
                self.time = time.time()
                self._token = data["idToken"]
                self._refresh_token = data["refreshToken"]
                _log.debug(f"connect Success")
            else:
                _log.warning(f"connect fail: {response}")
                _log.warning(f"Response: {response.json()}")
        except Exception as e:
            _log.error(f"AirvedaAuth _connect: Exception {e}")
        
    def _renew_token(self):
        end_point = "token/refresh/"
        header = {"Content-Type": "application/json"}
        body = {"refreshToken": self._refresh_token}
        response = requests.post(BASE_URL+end_point, headers=header, data=json.dumps(body), timeout=20)
        try:
            if response.ok:
                data = response.json()
                self.time = time.time()
                self._token = data["idToken"]
                self._refresh_token = data["refreshToken"]
                _log.debug(f"_renew_token: Success")
            else:
                _log.warning(f"renew token fail: {response}")
                _log.warning(f"Response: {response.json()}")
        except Exception as e:
            _log.error(f"AirvedaAuth _renew_token: Exception {e}")

    @property
    def access_token(self):
        if time.time() - self.time >= 1800:
            self._renew_token()
            return self._token
        return self._token
    

class AirvedaAPI:

    def __init__(self, airveda_auth):
        self._airveda_auth = airveda_auth
    
    def get_status(self, device_id):
        end_point = "data/latest/"
        header = {
                    "Authorization": f"Bearer {self._airveda_auth.access_token}",
                    "Content-Type": "application/json"
                    }
        body = {"deviceIds": device_id}
        response = requests.post(BASE_URL+end_point, headers=header, data=json.dumps(body), timeout=20)
        try:
            if response.ok:
                _log.debug("AirvedaAPI get_status: Success")
                return response.json()
            else:
                _log.warning(f"get_status fail: {response}")
                _log.warning(f"Response: {response.json()}")
                return None
        except Exception as e:
            _log.error(f"AirvedaAPI get_status: Exception {e}")
    
    def get_user_devices_details(self):
        end_point = "data/devices"
        header = {
                    "Authorization": f"Bearer {self._airveda_auth.access_token}",
                    "Content-Type": "application/json"
                    }
        response = requests.get(BASE_URL+end_point, headers=header)
        try:
            if response.ok:
                _log.debug("AirvedaAPI get_user_devices_details: Success")
                return response.json()
            else:
                _log.warning(f"get_user_devices_details fail: {response}")
                _log.warning(f"Response: {response.json()}")
                return None
        except Exception as e:
            _log.error(f"AirvedaAPI get_user_devices_details: Exception {e}")


class AirvedaAQ:

    def __init__(self, device_id, airveda_api):
        self.device_id = device_id
        self.airveda_api = airveda_api
    
    def get_status(self):
        data = {}
        ret = self.airveda_api.get_status(self.device_id)
        if ret is not None:
            for k, v in ret.items():
                data.update({
                    "pm25_value": v["data"][0]["value"],
                    "pm10_value": v["data"][1]["value"],
                    "AQI": v["data"][2]["value"],
                    "co2": v["data"][3]["value"],
                    "temperature": v["data"][4]["value"],
                    "humidity": v["data"][5]["value"],
                    "last_updated": v["lastUpdated"]
                })
            return data
        return None