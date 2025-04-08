import logging

_log = logging.getLogger(__name__)

import requests
import json

class Test:
    def fetch_pms_room_status(self):
        try:
            pms_url = "http://10.10.3.200:92/api/roomstatus"

            data = json.dumps({
            "RequestId": "12345678"
            })

            header = {
            "Authorization": "Token bb9ed6f86fcea081953288475ff77a4f0ef9174c1850374c29f423ee8f135cf3",
            "Content-Type": "application/json",
            "Connection": "close"
            }

            # req = requests.session()
            # req.keep_alive = False

            response = requests.post(pms_url, data=data, headers=header, timeout=9)
            if response.status_code == 200:
                res_json = response.json()
                # print(f"Fetch successfully: {res_json}")
                return res_json
            else:
                _log.debug(f"Fetch failed: {response} {response.content}")
        except Exception as e:
            _log.error(f"Fetch Exception: {e}")
        return None

test = Test()
pms_res = test.fetch_pms_room_status()
pms_room_status = {}
if pms_res["Status"] == "Ok":
	for room in pms_res["Data"]:
		room_number = room["room_no"]
		room_status = room["stat_room"].lower()
		pms_room_status[str(room_number)] = room_status
print(pms_room_status)