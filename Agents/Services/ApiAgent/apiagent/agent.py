"""
Agent documentation goes here.

TOPIC_LOAD_BAT_ID = "datalogger/station/station_1/station_1/load"
{'timestamp': '2021-04-21T13:25:37.297972+00:00', 'device_id': 'station_1', 'subdevice_idx': 4, 'subdevice_name': '', 'location': 'station/station_1/iot_devices', 'loaded_device_id': 'ML60200718HCA1B0094', 'type': 'load'}
subdevice_idx 4 = slot_5
TOPIC_SAMPLE = "sensor/charger/station_1/sample"
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import requests
import json
from threading import Thread
from queue import Queue
import time

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


TYPE_DEVICE = "device"
TYPE_ELECTRIC = "electric"

PAYMENTS_ERROR = "rider not exist"
EVTRANSACTION_ERROR = "not occupied by rider"


def api_factory(apitype):
    if apitype == "api_unit":
        return ApiUnit
    if apitype == "api_eject":
        return ApiEject
    if apitype == "battery_updator":
        return BatteryUpdator

    raise Exception(f"Unknown api type {apitype}")


class AltoAPI:

    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.token = "Token"
        self.username = username
        self.password = password
        self.restict_time_request = None

    def update_self(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        
    def alto_post(self, param_in, data_in, endpoint):
        _log.info(f"apiagent alto_post: {param_in} {data_in}")
        _log.info(f"apiagent alto_post: {self.base_url + endpoint}")

        self.restict_request()
        resc_dict = None

        try:
            response = requests.post(
                url=self.base_url + endpoint,
                params=param_in,
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps(data_in),
                timeout=9
            )
            _log.info('apiagent Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            resc = response.content
            _log.info('apiagent Response HTTP Response Body: {content}'.format(
                content=resc))
            resc_dict = json.loads((resc).decode())
            resc_error = resc_dict.get("error", None)
            if response.status_code != 200:
                if response.status_code == 401:
                    self.get_token()
                    return self.alto_post(param_in, data_in, endpoint)
        except Exception as e:
            _log.error(f'apiagent {e}')
        except requests.exceptions.RequestException:
            _log.error('apiagent HTTP Request failed')
        return resc_dict

    def alto_put(self, param_in, data_in, endpoint):
        _log.info(f"apiagent alto_put: {param_in} {data_in}")
        _log.info(f"apiagent alto_put: {self.base_url + endpoint}")

        self.restict_request()
        resc_dict = None

        try:
            response = requests.put(
                url=self.base_url + endpoint,
                params=param_in,
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps(data_in),
                timeout=9
            )
            _log.info('apiagent Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            resc = response.content
            _log.info('apiagent Response HTTP Response Body: {content}'.format(
                content=resc))
            resc_dict = json.loads((resc).decode())
            resc_error = resc_dict.get("error", None)
            if response.status_code != 200:
                if response.status_code == 401:
                    self.get_token()
                    return self.alto_put(param_in, data_in, endpoint)
        except Exception as e:
            _log.error(f'apiagent {e}')
        except requests.exceptions.RequestException:
            _log.error('apiagent HTTP Request failed')
        return resc_dict

    def alto_get(self, param_in, endpoint):
        _log.info(f"apiagent alto_get: {param_in}")
        _log.info(f"apiagent alto_get: {self.base_url + endpoint}")

        self.restict_request()
        resc_dict = None

        try:
            response = requests.get(
                url=self.base_url + endpoint,
                params=param_in,
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps({}),
                timeout=9
            )
            _log.info('apiagent Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            resc = response.content
            resc_dict = json.loads((resc).decode())
            resc_error = resc_dict.get("error", None)
            if response.status_code != 200:
                if response.status_code == 401:
                    self.get_token()
                    return self.alto_get(param_in, endpoint)
        except Exception as e:
            _log.error(f'apiagent {e}')
        except requests.exceptions.RequestException:
            _log.error('apiagent HTTP Request failed')
        return resc_dict

    def send_payment(self, data_in):
        endpoint = "/api/v2.0/payments"
        _ = self.alto_post({}, data_in, endpoint)

    def send_evtransaction(self, data_in):
        endpoint = "/api/v2.0/evtransactions"
        _ = self.alto_post({}, data_in, endpoint)

    def get_device_by_type(self, param_in):
        endpoint = "/api/v2.0/devices"
        return self.alto_get(param_in, endpoint)

    def put_device(self, data_in):
        endpoint = "/api/v2.0/devices"
        _ = self.alto_put({}, data_in, endpoint)
    
    def get_token(self):
        self.restict_request()
        
        try:
            response = requests.post(
                url=self.base_url + "/api/v2.0/login",
                headers={
                    "content-type": "application/json",
                },
                data=json.dumps({
                    "username": self.username,
                    "password": self.password
                }),
                timeout=9
            )
            _log.info('Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            if response.status_code != 200:
                self.get_token()
            token = json.loads((response.content).decode())
            self.token = token['token']
        except Exception as e:
            _log.error(f'apiagent {e}')
        except requests.exceptions.RequestException:
            _log.error('apiagent HTTP Request failed')

    def restict_request(self):
        if self.restict_time_request:
            while time.time() - self.restict_time_request < 0.15:
                pass
        self.restict_time_request = time.time()


class ApiEject:

    def __init__(self, controller, api_id, alto_api, topic):
        self.controller = controller
        self.api_id = api_id

        # self.alto_api = AltoAPI(rest_url_login, rest_url, username, password)
        self.alto_api = alto_api
        self.topic = topic

        self.controller.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self.subscribe_callback)

    def __str__(self):
        return f"{self.topic} {self.api_id}"

    def update_self(self, controller, api_id, alto_api, topic):
        self.controller = controller
        self.api_id = api_id
        self.topic = topic

        # self.alto_api.update_self(rest_url_login, rest_url, username, password)

        self.controller.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self.subscribe_callback)

    def subscribe_callback(self, 
                            peer, 
                            sender, 
                            bus, 
                            topic, 
                            headers,
                            message):
        _log.debug(f"apiagent eject {message}")
        try:
            # if (
            #     message["inserted_battery_id"] != "" and 
            #     message["inserted_battery_id"] is not None
            # ):
            if message["inserted_battery_id"] is None:
                message["inserted_battery_id"] = ""
            message["status"] = "success"
            _log.debug(f'''apiagent eject pass {message["inserted_battery_id"]}''')

            self.controller.add_job({
                "instance": self,
                "msg": message
            })

        except Exception as e:
            _log.error(f"apiagent self.controller.add_job eject {e}")

    def send_message(self, message):
        self.alto_api.send_evtransaction(message)


class ApiUnit:

    def __init__(self, controller, api_id, alto_api, topic, rpc_device_id, gateway_name):
        self.controller = controller
        self.api_id = api_id
        
        # self.alto_api = AltoAPI(rest_url_login, rest_url, username, password)
        self.alto_api = alto_api
        self.topic = topic

        self._rpc_device_id = rpc_device_id
        self.gateway_name = gateway_name

        self.controller.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self.subscribe_callback)

    def __str__(self):

        return f"{self.topic} {self.api_id}"

    def update_self(self, controller, api_id, alto_api, topic, rpc_device_id, gateway_name):
        self.controller = controller
        self.api_id = api_id
        self.topic = topic

        # self.alto_api.update_self(rest_url_login, rest_url, username, password)

        self._rpc_device_id = rpc_device_id
        self.gateway_name = gateway_name

        self.controller.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self.subscribe_callback)

    def subscribe_callback(self, 
                            peer, 
                            sender, 
                            bus, 
                            topic, 
                            headers,
                            message):
        # _log.debug(f"apiagent loaded_device_id {message}")
        try:
            data = self.controller.vip.rpc.call('charger', 'get_current_state', self._rpc_device_id).get(9) # 10 seconds for timeout
            # _log.debug(f"apiagent rpc call {data}")

            battery_id_array = []
            state_of_charge = []
            for i in range(9):
                if data[str(i)]["sensor"]["electric"]["state_of_charge"]:
                    state_of_charge.append(data[str(i)]["sensor"]["electric"]["state_of_charge"])
                    battery_id_array.append(data[str(i)]["sensor"]["device"]["battery_id"])
                else:
                    state_of_charge.append(0)
                    battery_id_array.append("")
                    
            pre_message = {
                "battery_id": message["loaded_device_id"],
                "battery_id_array": battery_id_array,
                "state_of_charge": state_of_charge,
                # "gateway_id": "ev_tower_001",
                "gateway_name": self.gateway_name,
                "slot_idx": message["subdevice_idx"]
            }

            _log.debug(f"apiagent {pre_message}")

            self.controller.add_job({
                "instance": self,
                "msg": pre_message
            })

        except Exception as e:
            _log.error(f"apiagent self.controller.add_job except {e}")

    def send_message(self, message):
        self.alto_api.send_payment(message)


class BatteryUpdator:

    def __init__(self, controller, api_id, alto_api, rpc_device_id, room_name, room_id, gateway_id):
        self.controller = controller
        self.api_id = api_id
        self.alto_api = alto_api
        self._rpc_device_id = rpc_device_id
        self.room_name = room_name
        self.room_id = room_id
        self.gateway_id = gateway_id

    def __str__(self):

        return f"{self.api_id}"

    def update_self(self, controller, api_id, alto_api, rpc_device_id, room_name, room_id, gateway_id):
        self.controller = controller
        self.api_id = api_id
        self.alto_api = alto_api
        self._rpc_device_id = rpc_device_id
        self.room_name = room_name
        self.room_id = room_id
        self.gateway_id = gateway_id

    @property
    def rpc_device_id(self):
        return self._rpc_device_id

    def send_message(self, message):
        bat_in_tower = {}
        for k, v in message.items():
            if v["sensor"]["device"]['battery_id'] not in bat_in_tower and v["sensor"]["device"]['battery_id'] is not None:
                bat_in_tower[v["sensor"]["device"]['battery_id']] = k
        param_in = {
            "type": "battery"
        }
        battery_list = self.alto_api.get_device_by_type(param_in)
        # _log.debug(f"battery_list {battery_list}")
        bat_in_room = {}
        for i in battery_list["devices"]:
            if i["room"] is not None:
                if i["room"] == self.room_id:
                    d_id = i["device_id"].rstrip()
                    for k, v in i["subdevices"].items():
                        if v["schema"] == "charger":
                            device_number = v["device_number"]
                    if d_id in bat_in_tower:
                        bat_in_room[d_id] = {
                            "exists": True,
                            "device_number": str(device_number)
                        }
                    else:
                        bat_in_room[d_id] = {
                            "exists": False,
                            "device_number": str(device_number)
                        }
        for k, v in bat_in_room.items():
            if not v["exists"]:
                data_in = {
                    "room_name": None,
                    "device_id": k
                }
                self.alto_api.put_device(data_in)
        for k, v in bat_in_tower.items():
            if k in bat_in_room:
                if v == bat_in_room[k]["device_number"]:
                    continue
            data_in = {
                "subdevices": {
                    v: {
                        "nickname": k,
                        "schema": [
                            "charger"
                        ]
                    }
                },
                "room_name": self.room_name,
                "device_id": k,
                "device_name": k
            }
            self.alto_api.put_device(data_in)
        _log.debug(f"bat_in_tower {bat_in_tower}")
        # _log.debug(f"bat_in_room {bat_in_room}")


def apiagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Apiagent
    :rtype: Apiagent
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    # setting1 = int(config.get('setting1', 1))
    # setting2 = config.get('setting2', "some/random/topic")
    alto_apis = config.get("alto_apis", [])
    v2apis = config.get("v2apis", [])

    return Apiagent(alto_apis, v2apis, **kwargs)


class Apiagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, alto_apis=None, v2apis=None, **kwargs):
        super(Apiagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.alto_apis = alto_apis
        self.v2apis = v2apis

        # self.apiunit = {}
        self.alto_apis_ins = {}
        self.v2apis_ins = {}
        self.batupdator_ins = {}
        self.queue = Queue()

        self.default_config = {
            "alto_apis": alto_apis,
            "v2apis": v2apis,
        }

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.getsample_thread = Thread(target=self._rest_api_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

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
            alto_apis = config["alto_apis"]
            v2apis = config["v2apis"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.alto_apis = alto_apis
        self.v2apis = v2apis

        self._create_subscriptions()

    def _create_subscriptions(self):
        _log.debug("apiagent Unsubscribe from everything")
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self._build_api()

    def _build_api(self):
        _log.debug("apiagent begin build")
        self.alto_apis_ins = {}
        self.v2apis_ins = {}
        self.batupdator_ins = {}

        for i in self.alto_apis:
            # if i["alto_api_id"] not in self.alto_apis_ins:
            self.alto_apis_ins[i["alto_api_id"]] = AltoAPI(i["base_url"], i["username"], i["password"])
        for i in self.v2apis:
            # if i["api_id"] not in self.v2apis_ins:
            ApiClass = api_factory(i["api_type"])
            if i["api_type"] == "api_unit":
                newapi = ApiClass(self, i["api_id"], self.alto_apis_ins[i["alto_api"]], i["topic"], i["rpc_device_id"], i["gateway_name"])
                self.v2apis_ins[i["api_id"]] = newapi
            elif i["api_type"] == "api_eject":
                newapi = ApiClass(self, i["api_id"], self.alto_apis_ins[i["alto_api"]], i["topic"])
                self.v2apis_ins[i["api_id"]] = newapi
            elif i["api_type"] == "battery_updator":
                newapi = ApiClass(self, i["api_id"], self.alto_apis_ins[i["alto_api"]], i["rpc_device_id"], i["room_name"], i["room_id"], i["gateway_id"])
                self.batupdator_ins[i["api_id"]] = newapi
                
    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """

        self.core.periodic(90, self._period_signal)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        
        self.add_job("Die")

    def add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _period_signal(self):
        try:
            for k, v in self.batupdator_ins.items():
                message = self.vip.rpc.call('charger', 'get_current_state', v.rpc_device_id).get(7)
                self.add_job({
                    "instance": v,
                    "msg": message
                })
        except Exception as e:
            _log.debug(f"th {e}")

    def _rest_api_thread(self):
        _log.debug("_rest_api_thread")
        # please comment out debugpy when install and run
        # import debugpy
        # debugpy.debug_this_thread()

        while True:
            try:
                job = self.queue.get()
                self.queue.task_done()
                if isinstance(job, str):
                    if job == "Die":
                        return
                job["instance"].send_message(job["msg"])
            except Exception as e:
                _log.debug(f"th {e}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(apiagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
