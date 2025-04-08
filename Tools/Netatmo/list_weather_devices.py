import requests
import json
import time


AUTH_URL = "https://api.netatmo.com/oauth2/token"
WEATHER_STATION_URL = "https://api.netatmo.com/api/getstationsdata"


class NetatmoAuth:

    def __init__(self, grant_type, client_id, client_secret, username, password, scope=None):
        if scope is None:
            scope = "read_homecoach" # read_homecoach for gethomecoachsdata
        self._grant_type = grant_type
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._scope = scope

        self._get_access_token()
    
    def _get_access_token(self):
        datas = {
            "grant_type": self._grant_type,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": self._username,
            "password": self._password,
            "scope": self._scope
        }
        res = requests.post(AUTH_URL, data=datas)
        print(res.status_code)
        # print(res.content)

        if res.status_code == 200:
            res_json = json.loads((res.content).decode())
            print(res_json)
            self._access_token = res_json["access_token"]
            self._refresh_token = res_json["refresh_token"]
            self._expiration = int(res_json['expire_in'] + time.time())

    def _renew_access_token(self):
        datas = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret
        }
        res = requests.post(AUTH_URL, data=datas)
        print(res.status_code)
        # print(res.content)

        if res.status_code == 200:
            res_json = json.loads((res.content).decode())
            print(res_json)
            self._access_token = res_json["access_token"]
            self._refresh_token = res_json["refresh_token"]
            self._expiration = int(res_json['expire_in'] + time.time())
    
    @property
    def access_token(self):
        if time.time() >= self._expiration:
            self._renew_access_token()
        return self._access_token

if __name__ == "__main__":
    netauth = NetatmoAuth(
        "password",
        "60e1f4fee7d31a6b83091198",
        "t3ZtqGRccXmGdQEvzWL9SYObp9Kyj",
        "brown.worawut@altotech.net",
        "Altotech@2021",
        "read_station"
    )

    headers = {
        "Authorization": f'Bearer {netauth.access_token}'
    }
    res = requests.post(WEATHER_STATION_URL, headers=headers)
    print(res.status_code)
    print(res.content)
    if res.status_code == 200:
            res_json = json.loads((res.content).decode())
            for dev in res_json["body"]["devices"]:
                print(f'{dev["_id"]} {dev["type"]}')
                for subd in dev["modules"]:
                    print(f'{subd["_id"]} {subd["type"]}')
