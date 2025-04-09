import time
import uuid
import hmac
from hashlib import sha256
import requests
import json
import logging
from typing import Optional, Union

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)
__version__ = "1.5"

BASE_URL = "https://openapi.tuyaus.com"
REFREST_TOKEN_END_POINT = ""

class BaseTuyaAuth:

    def __init__(self, client_id: str, client_secret: str):
        """
        An Abstract Class that define Tuya Authentication

        :param client_id: The Tuya Credential define user Id
        :param client_secret: The Tuya Credential define user secret
    
        """
        self._client_id = client_id 
        self._client_secret = client_secret
        self.ac_token = None
        self.rf_token = None
    
    @property
    def access_token(self):
        return self.ac_token
    
    @property
    def refresh_token(self):
        return self.refresh_token
    
    @property
    def client_id(self):
        return self._client_id
    
    @property
    def client_secret(self):
        return self._client_secret


class TuyaAuth(BaseTuyaAuth):
    """
    A Class for Authenticate Tuya Account for using API or other

    Inherit from BaseTuyaAuth that are Abstract class
    """

    def __init__(self, client_id: str, client_secret: str):
        super().__init__(client_id, client_secret)
        self.last_time = 0
        self.ac_token = None
        self._connect()
    
    def update_self(self, client_id: str, client_secret: str):
        """Update Credential of Tuya Account"""
        self._client_id = client_id
        self._client_secret = client_secret
    
    def _connect(self):
        """Connect to Tuya to getting Access Token"""
        try:
            url = "https://buildingapimgmt.azure-api.net/tuya-auth/http_tuya_auth"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                res = r.json()
                self.ac_token = res["access_token"]
                self.last_time = res["last_time"]
                _log.debug(f"Connect to Tuya and got Token: {self.ac_token}")
            else:
                _log.error(f"Can't Connect: {r}")
        except Exception as e:
            _log.error(f"_connect: Exception {e}")
    
    @property
    def access_token(self):
        t = time.time()
        if t - self.last_time >= 3600:
            self._connect()
            return self.ac_token
        return self.ac_token
    
    @property
    def client_id(self):
        return super().client_id
    
    @property
    def client_secret(self):
        return super().client_secret


class NormalTuyaAuth(BaseTuyaAuth):

    def __init__(self, client_id: str, client_secret: str):
        super().__init__(client_id, client_secret)
        self._get_access_token()

    def update_self(self, client_id, client_secret):
        self._client_id = client_id
        self._client_secret = client_secret

    def _get_access_token(self) -> dict:
        try:
            r = TuyaRequests._connect(self._client_id, self._client_secret)
            if r == None:
                _log.error(f"TuyaAuth _get_access_token: {r}")
                return None
            self.time = time.time()
            self.ac_token = r["result"]["access_token"]
            self.rf_token = r["result"]["refresh_token"]
            _log.debug(f"TuyaAuth _get_access_token: {r}")
            return r
        except Exception as e:
            _log.error(f'TuyaAuth _get_access_token: Error from exception "{e}"')
            return None

    @property
    def access_token(self):
        """
        This method is to return access_token
        Normally, OAuth time of tuya is 2 hours (7200 secs)
        """
        t = time.time()
        if t - self.time >= 7200/2:
            self.ac_token = TuyaRequests._connect()
            return self.ac_token
        return self.ac_token


class TuyaRequests:

    def __init__(self, client_id: str, client_secret: str):
        """
        A Class that use to send HTTP request to Tuya

        Attributes
        ----------
        client_id: tuya client Id
        client_secret: tuya client secret

        Methods
        ----------
        _connect: connected to tuya to get a token
        _request: send HTTP request to get data or command devices
        get: send HTTP request GET
        post: send HTTP request POST
        _calc_sign: calculate tuya signature for requesting 

        """
        self.client_id = client_id
        self.client_secret = client_secret

    def _connect(self) -> str:
        end_point = "/v1.0/token?grant_type=1"
        response = self.get(end_point)
        return response["result"].get("access_token", None)

    def _request(self, method: str, end_point: str, token: str = None, body: str = None, params: dict = None) -> dict:
        if method == "GET":
            if token is None:
                sign, t, nonce = self._calc_sign(method, end_point, params=params)
                try:
                    response = requests.get(BASE_URL+end_point, headers={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "sign": sign,
                    "sign_method": "HMAC-SHA256",
                    "t": t,
                    "nonce": nonce
                    }, params=params, timeout=30)
                    if response.ok:
                        # print(f"Response: {response.json()}")
                        return response.json()
                    else:
                        print(f"Response error: {response}")
                        print(f"Response: {response.json()}")
                        return None
                except Exception as e:
                    print(f"HTTP requests Error {e}")
            else:
                sign, t, nonce = self._calc_sign("GET", end_point, token, params=params)
                try:
                    response = requests.get(BASE_URL+end_point, headers={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "sign": sign,
                        "sign_method": "HMAC-SHA256",
                        "access_token": token,
                        "t": t,
                        "nonce": nonce
                    }, params=params, timeout=30)
                    if response.ok:
                        # print(f"Response: {response.json()}")
                        return response.json()
                    else:
                        print(f"Response error: {response}")
                        print(f"Response: {response.json()}")
                        return None
                except Exception as e:
                    print("HTTP requests Error")
        elif method == "POST":
            if body is None:
                print(f"This Method need body")
                return
            sign, t, nonce = self._calc_sign("POST", end_point, token, body, params=params)
            try:
                response = requests.post(BASE_URL+end_point, headers={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "sign": sign,
                    "sign_method": "HMAC-SHA256",
                    "access_token": token,
                    "t": t,
                    "nonce": nonce
                },data=body, timeout=30)
                if response.ok:
                    print(f"Response: {response.json()}")
                    return response.json()
                else:
                    print(f"Response error: {response}")
                    print(f"Response {response.json()}")
                    return None
            except Exception as e:
                print("HTTP requests Error")

    def get(self, end_point: str, token: str = None, params: dict = None):
        return self._request("GET", end_point, token, None, params)

    def post(self, end_point: str, token: str, body: str):
        return self._request("POST", end_point, token, body)

    def _calc_sign(self, method: str, end_point: str, token: str = None, body: str = None, params: dict = None):
        if body is None:
            body = ""
        content_sha256 = sha256(body.encode("utf-8")).hexdigest()
        str_to_sign = method + "\n" + content_sha256 + "\n" + "" + "\n" + end_point

        if params is not None and len(params.keys()) > 0:
            str_to_sign += "?"

            params_keys = sorted(params.keys())
            query_builder = "".join(f"{key}={params[key]}&" for key in params_keys)
            str_to_sign += query_builder[:-1]

        t = str(int(time.time()*1000))
        nonce = str(uuid.uuid4())
        if token is None:
            message = self.client_id + t + nonce + str_to_sign
        else:
            message = self.client_id + token + t + nonce + str_to_sign
        sign = hmac.new(msg=message.encode("utf-8"), key=self.client_secret.encode("utf-8"), digestmod=sha256).hexdigest().upper()
        return sign, t, nonce


class TuyaAPI:
    
    def __init__(self, tuya_auth: TuyaAuth):
        """
        A Class that call Tuya API for get and set devices information

        Attributes
        ----------
        tuya_auth: TuyaAuth class

        Methods
        ----------
        get_status: get devices status
        get_specification: get devices specification
        get_function: get devices function
        get_information: get devices information
        set_command: set devices control by commanding code
        """
        self._tuya_auth = tuya_auth
        self._tuya_request = TuyaRequests(self._tuya_auth.client_id, self._tuya_auth.client_secret)
        
    def get_status(self, device_id: str) -> dict:
        """Get Tuya Devices Status"""
        url = f"/v1.0/iot-03/devices/{device_id}/status"
        r = self._tuya_request.get(url, self._tuya_auth.access_token)
        return r 
    
    def get_multi_status(self, device_ids: list) -> dict:
        """Get the status of multiple Tuya Devices"""
        url = "/v1.0/iot-03/devices/status"
        params = {'device_ids': ','.join(device_ids)}
        r = self._tuya_request.get(url, self._tuya_auth.access_token, params=params)
        return r
    
    def get_specification(self, device_id: str) -> dict:
        """Get Tuya Devices Specifications"""
        url = f"/v1.0/iot-03/devices/{device_id}/specification"
        r = self._tuya_request.get(url, self._tuya_auth.access_token)
        return r
    
    def get_function(self, device_id: str) -> dict:
        """Get Tuya Devices Functions"""
        url = f"/v1.0/iot-03/devices/{device_id}/functions"
        r = self._tuya_request.get(url, self._tuya_auth.access_token)
        return r
    
    def get_information(self, device_id: str) -> dict:
        """Get Tuya Devices Information"""
        url = f"/v1.0/iot-03/devices/{device_id}"
        r = self._tuya_request.get(url, self._tuya_auth.access_token)
        return r
    
    def get_multi_information(self, device_ids: list) -> dict:
        """Get the information of multiple Tuya Devices"""
        url = "/v1.0/iot-03/devices"
        params = {'device_ids': ','.join(device_ids)}
        r = self._tuya_request.get(url, self._tuya_auth.access_token, params=params)
        return r

    def set_command(self, device_id: str, body: Union[str, dict]):
        url = f"/v1.0/iot-03/devices/{device_id}/commands"
        r = self._tuya_request.post(url, self._tuya_auth.access_token, body)
        return r


class TuyaMonitorDevice:

    def __init__(self, device_id: str, tuya_api: TuyaAPI):
        """
        Abstract Class of Tuya Device class. When ever integrated new device type with Tuya device
        please inherit this class.

        param device_id: device identity of device
        type device_id: string
        param tuya_api: TuyaAPI Class 
        type tuya_api: TuyaAPI class
        """
        self._device_id = device_id
        self._tuya_api = tuya_api
    
    def get_status(self):
        """
        Get Tuya device data by using REST API.
        """
        return self._tuya_api.get_status(self._device_id)
    
    def get_information(self):
        """
        Get Tuya device information by using REST API.
        """
        return self._tuya_api.get_information(self._device_id)


class TuyaControlDevice:

    def __init__(self, device_id: str, tuya_api: TuyaAPI):
        """
        Abstract Class of Tuya Device class. When ever integrated new device type with Tuya device
        please inherit this class.

        param device_id: device identity of device
        type device_id: string
        param tuya_api: TuyaAPI Class 
        type tuya_api: TuyaAPI class
        """
        self._device_id = device_id
        self._tuya_api = tuya_api
    
    def turn_on(self, command: Union[str, dict]):
        """
        Turn on Tuya device by using REST API.
        """
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)
    
    def turn_off(self, command: Union[str, dict]):
        """
        Turn off Tuya device by using REST API.
        """
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)


class TuyaCurtain(TuyaMonitorDevice):

    def __init__(self, device_id, tuya_api):
        super().__init__(device_id, tuya_api)

    def open_curtain(self, command: Union[str, dict]) -> dict:
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)
            
    def close_curtain(self, command: Union[str, dict]) -> dict:
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)

    def stop_curtain(self, command: Union[str, dict]) -> dict:
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)
    
    def set_percent_position(self, command: Union[str, dict]):
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)

    def read_percent(self) -> dict:
        r = self._tuya_api.request_get(self._deivce_id)
        display = r["result"][1]
        _log.debug(f"TuyaCurtain read_percent: {display}")
        return display


class TuyaEnvSensor(TuyaMonitorDevice):

    def __init__(self, device_id, tuya_api):
        super().__init__(device_id, tuya_api)


class TuyaSocket(TuyaMonitorDevice, TuyaControlDevice):

    def __init__(self, device_id, tuya_api):
        super().__init__(device_id, tuya_api)


class TuyaMeter(TuyaMonitorDevice, TuyaControlDevice):

    def __init__(self, device_id, tuya_api):
        super().__init__(device_id, tuya_api)


class TuyaSwitch(TuyaMonitorDevice, TuyaControlDevice):

    def __init__(self, device_id, tuya_api):
        super().__init__(device_id, tuya_api)
    
    def set_bright_value(self, command: Union[str, dict]) -> None:
        if isinstance(command, dict):
            command = json.dumps(command)
        return self._tuya_api.set_command(self._device_id, command)
