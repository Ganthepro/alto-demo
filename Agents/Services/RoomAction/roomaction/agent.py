"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread
from queue import Queue
from time import time

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

import pyrebase
import requests
import json


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


##authentication configuration
FBSECRET = "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM"
FBDATABASEURL = "https://altohotel-b6ae5.firebaseio.com/"
FBTARGET="hotel/alto_demo"
FBAPIKEY = "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM"
FBAUTHDOMAIN = "altohotel-b6ae5.firebaseapp.com"
FBSTORAGEBUCKGET = "altohotel-b6ae5.appspot.com"
config = {
  "apiKey": FBAPIKEY,
  "authDomain": FBAUTHDOMAIN,
  "databaseURL": FBDATABASEURL,
  "storageBucket": FBSTORAGEBUCKGET
  }
firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
db = firebase.database()


class Line:

    def __init__(self, username, password, rest_url_login, rest_url_notify):
        self.rest_url_login = rest_url_login
        self.rest_url_notify = rest_url_notify
        self.username = username
        self.password = password
        self.token = "Token"
        self._auth_line(self.username, self.password)

    def _send_to_line(self, message):
        try:
            response = requests.post(
                # url="https://altoiotbackendprod.azurewebsites.net/api/v2.0/push_to_line",
                url=self.rest_url_notify,
                headers={
                    "Authorization": self.token,
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps({
                    "RequestId": "1234",
                    "stickerPackageId": "",
                    "image_url": "",
                    "stickerId": "",
                    "message": message,
                    "notificationDisabled": "False",
                    "to": "maid"
                })
            )
            print('Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            print('Response HTTP Response Body: {content}'.format(
                content=response.content))
            if response.status_code == 401:
                self.token = self._auth_line(self.username, self.password)
        except requests.exceptions.RequestException:
            print('HTTP Request failed')
            self.token = self._auth_line(self.username, self.password)

    def _auth_line(self, l_user, l_psswd):
        try:
            response = requests.post(
                # url="https://altoiotbackendprod.azurewebsites.net/api/v2.0/login",
                url=self.rest_url_login,
                headers={
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "username": l_user,
                    "password": l_psswd
                })
            )
            self.token = "Token " + json.loads(response.content.decode("UTF-8"))["token"]
            print('Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            print('Response HTTP Response Body: {content}'.format(
                content=response.content))
        except:
            print('Authentication Request failed')

    def update_credential(self, username, password, rest_url_login, rest_url_notify):
        self.rest_url_login = rest_url_login
        self.rest_url_notify = rest_url_notify
        self.username = username
        self.password = password
        self._auth_line(self.username, self.password)


class TasmotaDevice():

    def __init__(self, parent_room, in_room, tas_id, device_id, subdevice_idx, init_count):
        self.parent_room = parent_room
        self.in_room = in_room
        self.tas_id = tas_id
        self.device_id = device_id
        self.subdevice_idx = subdevice_idx

        self._count = init_count

        _log.debug(f"TasmotaDevice __init__ {self.device_id} {self.subdevice_idx}")
        self.parent_room.add_send_data_job({
            "msg": f"off tasmota light, there are intruder, in room {self.in_room}",
            "line": f"someone turn on light in room {self.in_room}"
        })

    def countdown(self):
        self._count -= 1
        if self._count <= 0:
            _log.debug(f"TasmotaDevice turn off {self.device_id} {self.subdevice_idx}")
            self.parent_room.add_send_data_job({
                "msg": f"off tasmota light, there are intruder, device_id {self.device_id} subdevice_idx {self.subdevice_idx}",
                "off_tasmota": [self.device_id, self.subdevice_idx]
            })
            self.parent_room.push_to_destroy(self.tas_id)


class AirConditionerDevice():

    def __init__(self, parent_room, in_room, device_id, status):
        self.parent_room = parent_room
        self.in_room = in_room
        self.device_id = device_id

        self._status = status

        self._turn_on_off_count = 0
        self._count_to_noti = 1

        self._turn_on_time = 0
        self._time_to_normal_noti = 12
        self._time_to_anormal_noti = 2

        _log.debug(f"AirConditionerDevice __init__ {self.in_room} {self.device_id}")
    
    def get_status(self):
        return self._status
    
    def update_status(self, val):
        if self._status != "off" and val == "off":
            self.reset_turn_on_time()
            self._turn_on_off_count += 1
        elif self._status == "off" and val != "off":
            if self._turn_on_off_count >= self._count_to_noti:
                self.parent_room.noti_from_ac_count(self.device_id, self._turn_on_off_count+1)
        self._status = val

    def update_time_to_normal_noti(self, t_time):
        self._time_to_normal_noti = t_time

    def update_time_to_anormal_noti(self, t_time):
        self._time_to_anormal_noti = t_time

    def reset_turn_on_time(self):
        self._turn_on_time = 0

    def update_count_to_noti(self, t_count):
        self._count_to_noti = t_count

    def reset_turn_on_off_count(self):
        self._turn_on_off_count = 0

    def update_and_reset_all(self, t_ntime):
        self.reset_turn_on_time()
        self.reset_turn_on_off_count()
        self.update_count_to_noti(1)
        self.update_time_to_anormal_noti(2)
        self.update_time_to_normal_noti(t_ntime)

    def period_signal(self):
        if self._status != "off":
            self._turn_on_time += 1
            if self._turn_on_off_count >= self._count_to_noti:
                if self._turn_on_time == self._time_to_anormal_noti:
                    self.parent_room.noti_from_ac_time_anormal(self.device_id)
            else:
                if self._turn_on_time == self._time_to_normal_noti:
                    self.parent_room.noti_from_ac_time_normal(self.device_id)
            

class Room():

    def __init__(self, controller, room_number, room_status, **kwargs):
        self.controller = controller
        self.room_number = room_number
        self.room_status = room_status

        room_prop = kwargs.get("room_prop", {})
        self.room_prefix = room_prop.get("room_prefix", "room_")
        self.ac_prefix = room_prop.get("ac_prefix", "ac_")

        self.clean_status = "normal" # startclean, endclean

        # self.ac_status = "off"
        # self.ac_one_time_open = False
        # self.ac_already_send_off = False
        # # self.ac_already_send_line = False
        # self.ac_on_time = 0
        self.ac_on_time_allow = room_prop.get("ac_on_time_allow", 12)
        # self.ac_on_time_anormal = 2

        # self.is_already_sub = False
        _log.debug(f"Room __init__ {self.room_number} {self.room_status}")

        self.tasmota_list = {}
        self.tasmota_list_des = []
        self.tasmota_on_time_anormal = 24

        self.ac_list = {}
    
    def update_room_status(self, status):
        self.room_status = status

        _log.debug(f"Room update_room_status {self.room_status}")

    def update_from_maid(self, room_status, clean_status):
        self.room_status = room_status
        self.clean_status = clean_status

        if self.clean_status == "startclean":
            _log.debug(f"turn on fan in room {self.room_number} by maid check in")
            self.controller.add_send_data_job({
                "instance": self,
                "data": {
                    # "msg": f"turn on fan in room {self.room_number} by maid check in",
                    "on_fan": self.room_number
                }
            })
            for k, v in self.ac_list.items():
                v.update_and_reset_all(self.ac_on_time_allow) # maid turn on ac time allow
            # self.controller.volttron_subscribe(topic=f"datalogger/{self.room_prefix}{self.room_number}/{self.ac_prefix}{self.room_number}", callback=self.handle_datalogger_room_ac)
        elif self.clean_status == "endclean":
            for k, v in self.ac_list.items():
                v.update_and_reset_all(self.ac_on_time_allow)
                v.update_count_to_noti(0) # imediatly noti if some one turn on ac (intruder)
            if self._is_room_status_v_or_a():
                self.controller.close_everything(self.room_number)

    def handle_datalogger(self, device_id, message):
        _log.debug(f"Room handle_datalogger {device_id} {message}")

        if device_id.startswith("ac_"):
            if device_id not in self.ac_list:
                self.ac_list[device_id] = AirConditionerDevice(self, self.room_number, device_id, message["mode"])
                self.ac_list[device_id].update_time_to_normal_noti(self.ac_on_time_allow)
            else:
                self.ac_list[device_id].update_status(message["mode"])
                self.ac_list[device_id].update_time_to_normal_noti(self.ac_on_time_allow)
        elif device_id.startswith("tasmota_"):
            if message["state"] == "on" and message["subdevice_name"] != "fan":
                _log.debug(f"Room handle_datalogger room_status {self.room_status} clean_status {self.clean_status}")
                if self._is_room_status_v_or_a() and self.clean_status != "startclean":
                    if message.get("subdevice_idx", None) is not None:
                        _log.debug(f"Someone turn on the light room {self.room_number} {message}")
                        tas_id = device_id + "_" + str(message["subdevice_idx"])
                        if tas_id not in self.tasmota_list:
                            self.tasmota_list[tas_id] = TasmotaDevice(self, self.room_number, tas_id, device_id, message["subdevice_idx"], self.tasmota_on_time_anormal)

    def handle_pms(self, event):
        if event == "check_in":
            self.room_status = "oc"
            _log.debug(f"Room handle_pms oc")

    def push_to_destroy(self, did):
        self.tasmota_list_des.append(did)

    def noti_from_ac_time_normal(self, device_id):
        if self._is_room_status_v_or_a():
            _log.debug(f"off ac {device_id} {self.room_number}")
            self.controller.add_send_data_job({
                "instance": self,
                "data": {
                    "msg": f"off ac {device_id} {self.room_number}",
                    "off_ac": device_id
                }
            })

    def noti_from_ac_time_anormal(self, device_id):
        if self._is_room_status_v_or_a():
            if self.clean_status == "startclean":
                _log.debug(f"turn off air conditioner in room {self.room_number} {device_id}, > 1 time")
                self.controller.add_send_data_job({
                    "instance": self,
                    "data": {
                        "msg": f"turn off air conditioner in room {self.room_number} {device_id}, > 1 time",
                        "off_ac": device_id
                    }
                })
            else:
                _log.debug(f"turn off air conditioner in room {self.room_number} {device_id}, anormal")
                self.controller.add_send_data_job({
                    "instance": self,
                    "data": {
                        "msg": f"turn off air conditioner in room {self.room_number} {device_id}, anormal",
                        "off_ac": device_id
                    }
                })

    def noti_from_ac_count(self, device_id, turn_on_off_count):
        if self._is_room_status_v_or_a():
            if self.clean_status == "startclean":
                _log.debug(f"maid turn on air conditioner in room {self.room_number} {device_id}, {turn_on_off_count} times")
                self.controller.add_send_data_job({
                    "instance": self,
                    "data": {
                        "msg": f"maid turn on air conditioner in room {self.room_number} {device_id}, {turn_on_off_count} times",
                        "line": f"maid turn on air conditioner in room {self.room_number}, {turn_on_off_count} times"
                    }
                })
            else:
                _log.debug(f"someone turn on air conditioner in room {self.room_number} {device_id}")
                self.controller.add_send_data_job({
                    "instance": self,
                    "data": {
                        "msg": f"someone turn on air conditioner in room {self.room_number} {device_id}",
                        "line": f"someone turn on air conditioner in room {self.room_number}"
                    }
                })

    def _is_room_status_v_or_a(self):
        try:
            self.room_status = self.controller.fetch_one_pms_room_status(self.room_number)
            if self.room_status.lower().startswith("v") or self.room_status.lower().startswith("a"):
                return True
        except Exception as e:
            _log.error(f"Room {e}")
        return False

    def period_signal(self):
        for k, v in self.ac_list.items():
            v.period_signal()

        for k, v in self.tasmota_list.items():
            v.countdown()

        for des_dev in self.tasmota_list_des:
            if des_dev in self.tasmota_list:
                del self.tasmota_list[des_dev]
        self.tasmota_list_des = []

    def add_send_data_job(self, data):
        self.controller.add_send_data_job({
            "instance": self,
            "data": data
        })

    def send_data(self, data):
        _log.debug(f"send_data {data.get('msg', '')}")
        line_data = data.get("line", "")
        if line_data != "":
            self.controller.send_to_line(line_data)
        ac_data = data.get("off_ac", "")
        if ac_data != "":
            self.controller.turnoff_ac(ac_data)
        tasmota_data = data.get("off_tasmota", [])
        if len(tasmota_data) >= 2:
            # _log.debug(f"tasmota_data {tasmota_data}")
            self.controller.turnoff_relay(tasmota_data[0], tasmota_data[1])
        fan_data = data.get("on_fan", "")
        if fan_data != "":
            self.controller.turn_on_fan(fan_data)


def roomaction(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Roomaction
    :rtype: Roomaction
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get("agent_name", "action_room")
    kwargs["altobackend"] = config.get("altobackend", {})
    kwargs["room_prop"] = config.get("room_prop", {})
    kwargs["room_fan_maps"] = config.get("room_fan_maps", {})

    return Roomaction(agent_name, **kwargs)


class Roomaction(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, **kwargs):
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super(Roomaction, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)

        self.agent_name = agent_name
        self.altobackend = kwargs["altobackend"]
        self.room_prop = kwargs["room_prop"]
        self.room_fan_maps = kwargs["room_fan_maps"]

        self.send_queue = Queue()

        self.room_list = {}
        self.line_api = None
        self.last_fb_room_status = {}

        self.default_config = {
            "agent_name": self.agent_name,
            "altobackend": self.altobackend,
            "room_prop": self.room_prop,
            "room_fan_maps": self.room_fan_maps
        }

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.getfirebase_thread = Thread(target=self._firebase_thread)
        self.getfirebase_thread.setDaemon(True)
        self.getfirebase_thread.start()

        self.getsend_thread = Thread(target=self._send_data)
        self.getsend_thread.setDaemon(True)
        self.getsend_thread.start()

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
            agent_name = config["agent_name"]
            altobackend = config["altobackend"]
            room_prop = config["room_prop"]
            room_fan_maps = config["room_fan_maps"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.altobackend = altobackend
        self.room_prop = room_prop
        self.room_fan_maps = room_fan_maps

        if self.line_api is None:
            self.line_api = Line(self.altobackend["username"], self.altobackend["password"], self.altobackend["rest_url_login"], self.altobackend["rest_url_notify"])
        else:
            self.line_api.update_credential(self.altobackend["username"], self.altobackend["password"], self.altobackend["rest_url_login"], self.altobackend["rest_url_notify"])

        self._create_subscriptions()

    def _create_subscriptions(self):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="app/maidapp/10minsac/event",
                                  callback=self._handle_publish)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="datalogger",
                                  callback=self._handle_datalogger)
        
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="pms",
                                  callback=self._handle_pms)

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        room_status = message["message"]["room_status"]
        # if room_status.startswith("v"):

        room = message["message"]["location"]
        clean_status = message["message"]["clean_status"]
        _log.debug(f"in _handle_publish with a topic: {topic}, message: {message} room (type): {type(room)} room: {room}")

        room = str(room)
        room = room.strip()

        if room not in self.room_list:
            conf = {
                "room_prop": self.room_prop
            }
            self.room_list[room] = Room(self, room, room_status, **conf)
            self.room_list[room].update_from_maid(room_status, clean_status)
        else:
            self.room_list[room].update_from_maid(room_status, clean_status)

    def _handle_datalogger(self, peer, sender, bus, topic, headers,
                                message):
        topic = topic.split("/")
        if len(topic) < 3:
            return
        device_id = topic[2]
        room = topic[1]
        if room.startswith("room_"):
            _log.debug(f"_handle_datalogger {room} {device_id}")
            room_number = room.split('_')[1]
            if room_number in self.room_list:
                self.room_list[room_number].handle_datalogger(device_id, message)

    def _handle_pms(self, peer, sender, bus, topic, headers,
                                message):
        topic = topic.split('/')
        if len(topic) < 4:
            return
        event = topic[3]
        room = topic[2]
        if room.startswith("room_"):
            _log.debug(f"_handle_pms {room} {event}")
            room_number = room.split('_')[1]
            if room_number in self.room_list:
                self.room_list[room_number].handle_pms(event)

    def _build_room(self, room_number, room_status):
        _log.debug(f"_build_room {room_number} {room_status}")
        room_number = str(room_number)
        room_number = room_number.strip()

        if room_number not in self.room_list:
            conf = {
                "room_prop": self.room_prop
            }
            self.room_list[room_number] = Room(self, room_number, room_status, **conf)
        else:
            self.room_list[room_number].update_room_status(room_status)

    def volttron_subscribe(self, topic, callback):
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=callback)
        _log.debug(f"subscribe to topic: {topic}")

    def volttron_unsubscribe(self, topic):
        self.vip.pubsub.unsubscribe("pubsub", topic, None)
        _log.debug(f"unsubscribe to topic: {topic}")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        
        self.core.periodic(5, self._period_signal)
        # self.core.periodic(60, self._periodic_get_firebase)
        self.core.periodic(600, self._periodic_fetch_pms)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        
        self.add_send_data_job("Die")
        # self._firebase_response.close()

    def _period_signal(self):
        for k, v in self.room_list.items():
            v.period_signal()

    def fetch_one_pms_room_status(self, rn):
        _log.debug(f"fetch_one_pms_room_status {rn} type {type(rn)}")
        try:
            pms_url = "http://10.10.3.200:92/api/roomstatus"

            data = json.dumps({
                "RequestId": "12345678",
                "RoomNo": str(rn)
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
                room_status = res_json["Data"]["stat_room"].lower()
                return room_status
            else:
                _log.debug(f"Fetch failed: {response} {response.content}")
        except Exception as e:
            _log.error(f"Fetch Exception: {e}")
        return None

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
                _log.debug(f"fetch_pms_room_status Fetch failed: {response} {response.content}")
        except Exception as e:
            _log.error(f"fetch_pms_room_status Fetch Exception: {e}")
        return None

    def _periodic_fetch_pms(self):
        _log.debug(f"_periodic_fetch_pms {self.room_list}")
        try:
            pms_res = self.fetch_pms_room_status()
            if pms_res is None:
                _log.debug(f"_periodic_fetch_pms fetch_pms_room_status is {pms_res}")
                return
            pms_room_status = {}
            if pms_res["Status"] == "Ok":
                for room in pms_res["Data"]:
                    room_number = room["room_no"]
                    room_status = room["stat_room"].lower()
                    pms_room_status[str(room_number)] = room_status
            _log.debug(f"_periodic_fetch_pms pms_room_status {pms_room_status}")
            for k, v in pms_room_status.items():
                self._build_room(k, v)
        except Exception as e:
            _log.error(f"error in _periodic_fetch_pms function: {e}")

    def _periodic_get_firebase(self):
        _log.debug(f"_periodic_get_firebase {self.room_list}")
        try:
            fb_room_status = db.child("hotel").child("mintel").child("user_info").child("room_status").get()
            room_status = fb_room_status.val()
            is_fb_sync = True
            for k, v in room_status.items():
                if "clean_status" in v:
                    # _log.debug(f"_periodic_get_firebase {k} {v['clean_status']}")
                    self._build_room(k, v['clean_status'])
                    # if self.last_fb_room_status[k] != v['clean_status'] and False:
                    #     is_fb_sync = False
                    #     break
            if not is_fb_sync and False:
                _log.debug(f"_periodic_get_firebase fb not sync")
                try:
                    self._firebase_response.close()
                except Exception as e:
                    _log.debug(f"_periodic_get_firebase e {e}")
                finally:
                    # self._firebase_response = db.child("hotel").child("mintel").child("user_info").stream(self._handle_firebase, stream_id="fb_handle")
                    self.getfirebase_thread = Thread(target=self._firebase_thread)
                    self.getfirebase_thread.setDaemon(True)
                    self.getfirebase_thread.start()
        except Exception as e:
            _log.error(f"error in _periodic_get_firebase function: {e}")

    def _firebase_thread(self):
        # self._firebase_response = db.child("hotel").child("mintel").child("user_info").stream(self._handle_firebase)
        # self._firebase_response = db.child("hotel").child("mintel").child("user_info").stream(self._handle_firebase, stream_id="fb_handle")
        # _log.debug(f"_firebase_response {self._firebase_response}")
        pass

    def _handle_firebase(self, message):
        _log.debug("in _handle_firebase")
        # check from firebase, if status change to "maid_get_in"
        try:
            path = message["path"]
            # if callback first time, firebase will send everything in the child to us.
            if path == "/":
                rooms_status = message["data"]["room_status"]  # rooms status in dict
                for room, val in rooms_status.items():
                    try:
                        # self.rooms[room] = val["clean_status"]
                        # if room == '604': # mock
                        #     val["clean_status"] = 'vc'
                        self._build_room(room, val["clean_status"])
                        self.last_fb_room_status[room] = val["clean_status"]
                    except Exception as e:
                        _log.error(f"error while get room status: {e}")
                # _log.debug(f"rooms: {self.rooms}")
            else:
                ## if not the first time, it will send only the node that value is changed.
                if path.startswith("/room_status"):
                    ## to be edit
                    clean_status = message["data"]["clean_status"]
                    room = message["path"].split('/')[2]
                    # self.rooms[room] = clean_status
                    # if room == '604': # mock
                    #     clean_status = 'vc'
                    self._build_room(room, clean_status)
                    self.last_fb_room_status[room] = clean_status
                    _log.debug(f"rooms: {room}")
        except Exception as e:
            _log.debug(f"error in stream_handler function: {e}")

    def add_send_data_job(self, job):
        try:
            self.send_queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _send_data(self):
        _log.debug("_send_data")

        while True:
            job = self.send_queue.get()
            self.send_queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            job["instance"].send_data(job["data"])

    def send_to_line(self, data):
        try:
            # self.line_api._auth_line(self.line_api.username, self.line_api.password)
            if self.line_api is not None:
                self.line_api._send_to_line(data)
        except Exception as e:
            _log.error(f"{e}")

    def turnoff_ac(self, device_id):
        '''

        :return:
        '''
        topic = f"hvac/carrierac/{device_id}/command"
        message = {"subdevice_idx":0, "mode": "off"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"topic: {topic}, message : {message}")
    
    def turnoff_relay(self, device_id, subdevice_idx):
        message = {"subdevice_idx":subdevice_idx, "state":"off"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=f"switch/tasmota/{device_id}/command",
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"message : {message}")

    def turn_on_fan(self, room_nuumber):
        device_id = self.room_fan_maps[str(room_nuumber)]
        message = {"subdevice_idx":0, "state":"on"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=f"switch/tasmota/{device_id}/command",
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"turn_on_fan message : {message}")

    def close_everything(self, room):
        topic = f"location/mintel/room_{room}/check_out"
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message={})
        # self.checkin_rooms.pop(f"room_{room}", None)
        _log.debug(f"close everything topic {topic}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(roomaction, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
