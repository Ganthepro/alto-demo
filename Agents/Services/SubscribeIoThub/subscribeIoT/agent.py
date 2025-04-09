# -*- coding: utf-8 -*-
from __future__ import absolute_import
import sys
from pprint import pformat
import gevent
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub, compat
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.scheduling import periodic

from queue import Queue
from threading import Thread
import logging
from volttron.platform.agent import utils, matching
from os.path import expanduser
import time
import sys
# import iothub_client
# from iothub_client import IoTHubClient, IoTHubClientError, IoTHubTransportProvider, IoTHubClientResult
# from iothub_client import IoTHubMessage, IoTHubMessageDispositionResult, IoTHubError
import json
import logging
from pprint import pprint

import threading
import time
from azure.iot.device import IoTHubDeviceClient
RECEIVED_MESSAGES = 0

RECEIVE_CONTEXT = 0
WAIT_COUNT = 10
RECEIVED_COUNT = 0
RECEIVE_CALLBACKS = 0
# choose AMQP or AMQP_WS as transport protocol
# PROTOCOL = IoTHubTransportProvider.MQTT
# CONNECTION_STRING = "HostName=altoiothubprod.azure-devices.net;DeviceId=newaltonucmintelcontrol;SharedAccessKey=BAdlAeP2KucjwKMGoVRNss5IPKoMqVDw0vgbHdxuh74="
IS_WATCHER_CHECK = False
MARK = "GENERAL" # BETA, for tower as room, BETA for beta vm. GENERAL, for normal hotel structure, BGRIMM, SYN
# CONNECTION_STRING = "HostName=altominttower.azure-devices.net;DeviceId=altolenovominttowercontrol;SharedAccessKey=jxqOyfr95CFlFg9BAXLsQhnGeEbw9umdxBU9KxG13bo="
CONNECTION_STRING = "HostName=altoiothubprod.azure-devices.net;DeviceId=altonucsyncontrol;SharedAccessKey=phOWPw5AsLxBlHNTqMr6DjayFHtAQcmZQAEj3dvh5ak="
LINE_NOTI_TOPIC = "line_notify/line_notify_subiot/line_mintel/command"
LINE_STARTED_MSG = "Syn: subiot started"
LINE_RECONNECTED_MSG = "Syn: subiot re-connected"
# CONNECTION_STRING = "HostName=AltoIoTHUB.azure-devices.net;DeviceId=armubuntu16;SharedAccessKey=kLP50RT7fOitzLz7nWIxkQHcZ74bF6lmG4R325Mggz8="
TOPICHEAD = "/hiveos"
utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '3.2'
DEFAULT_MESSAGE = 'HELLO'


# TODO
'''
Problem every time ading
Solution 
'''

class Action:
    def __init__(self, actions_backendformat):
        self.actions_backendformat = actions_backendformat

    def backend_to_volttron(self, **kwargs):
        ## actions
        action_tasks = self.actions_backendformat
        actions = []
        for action in action_tasks:
            if "command" in action:
                act = "command"
            elif "config" in action:
                act = "config"
            elif "learn" in action:
                act = "learn"
            elif "custom_action" in action:
                act = "custom_action"
            else:
                raise Exception("Action that send from iothub is not supported.")
            if MARK == "BETA_VM": # should make this configurable
                inmsg_topic = [action["schema"], action["agent_id"], act]
                action[act]["ca_id"] = action["rider_id"]
                action[act]["transaction_id"] = action["transaction_id"]
            elif MARK == "BETA": # should make this configable
                # action["room_name"] = "beta_ev_tower_001" # for debug
                inmsg_topic = [action["schema"], action["agent_id"], action["room_name"], act]
                commsg = kwargs.get("commsg", None)
                if commsg is not None:
                    action[act]["source"] = commsg.get("source", "")
            elif MARK == "BGRIMM": # should make this configable
                inmsg_topic = [action["schema"], action["agent_id"], action["device_id"], act]
                commsg = kwargs.get("commsg", None)
                if commsg is not None and action["schema"]=="hvac":
                    action[act]["source"] = commsg.get("source", "web")
            else:
                inmsg_topic = [action["schema"], action["agent_id"], action["device_id"], act]
            if MARK == "SYN" and act == "command":
                tmp_cmd = action[act]
                if "mode" in tmp_cmd:
                    if tmp_cmd["mode"] == "off":
                        tmp_cmd["mode"] = "cool"
                        tmp_cmd["status"] = "off"
                    else:
                        tmp_cmd["status"] = "on"
                payload = tmp_cmd
            else:
                payload = action[act]
            if MARK != "BETA_VM":
                if "subdevice_idx" in action:
                    payload["subdevice_idx"] = action["subdevice_idx"]
                else:
                    raise Exception("You need to specify 'subdevice_idx' in the action")
            inmsg_action = [inmsg_topic, payload]
            actions.append(inmsg_action)

        return actions

        
class iothubsubAgent(Agent):

    # def __init__(self, config_path, **kwargs):
    def __init__(self, all_config, **kwargs):
        super(iothubsubAgent, self).__init__(**kwargs)
        # self.config = utils.load_config(config_path)

        self.all_config = all_config

        self.azure_queue = Queue()
        self.azure_thread = None

        self._running = True

        self._is_first_time = True
        self._watcher_status = True

        self.default_config = {
            "all_config": all_config,
        }

        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

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
            all_config = config["all_config"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.all_config = all_config

        global IS_WATCHER_CHECK, MARK, CONNECTION_STRING, LINE_NOTI_TOPIC, LINE_STARTED_MSG, LINE_RECONNECTED_MSG
        IS_WATCHER_CHECK = self.all_config["IS_WATCHER_CHECK"]
        MARK = self.all_config["MARK"]
        CONNECTION_STRING = self.all_config["CONNECTION_STRING"]
        LINE_NOTI_TOPIC = self.all_config["LINE_NOTI_TOPIC"]
        LINE_STARTED_MSG = self.all_config["LINE_STARTED_MSG"]
        LINE_RECONNECTED_MSG = self.all_config["LINE_RECONNECTED_MSG"]

        self.start_iot_hub()

    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        # _log.info(self.config.get('message', DEFAULT_MESSAGE))
        # self._agent_id = self.config.get('agentid')
        pass

    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        return
        self.start_iot_hub()

    def start_iot_hub(self):
        if IS_WATCHER_CHECK:
            self.core.schedule(periodic(120), self._check_watcher_status)
        try:
            # self.client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
            # self.message_listener_thread = threading.Thread(target=self.message_listener, args=(self.client,))
            gevent.sleep(40)
            self.message_listener_thread = threading.Thread(target=self.message_listener, args=(None,))
            self.message_listener_thread.daemon = True
            self.message_listener_thread.start()
            self.emit_iot_hub_state(LINE_STARTED_MSG)
            # while True:
            #     time.sleep(1000)
        except KeyboardInterrupt:
            print("IoT Hub C2D Messaging device sample stopped")

    def _check_watcher_status(self):
        if not self._is_first_time:
            if not self._watcher_status:
                _log.debug(f"re-create subiot connection")
                self._running = False
                gevent.sleep(30.0)
                self.message_listener_thread = threading.Thread(target=self.message_listener, args=(None,))
                self.message_listener_thread.daemon = True
                self.message_listener_thread.start()
                self._watcher_status = True
                self.emit_iot_hub_state(LINE_RECONNECTED_MSG)
            else:
                _log.debug(f"reset watcher status")
                self._watcher_status = False
        self._is_first_time = False

    def emit_iot_hub_state(self, msg):
        topic = LINE_NOTI_TOPIC
        message = {"message": msg}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"Subiot emit_iot_hub_state: {topic}, message : {message}")

    def message_listener(self, client):
        global RECEIVED_MESSAGES
        self._running = True
        client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
        client.connect()
        _log.debug(f"start message_listener {client} {self._running}")
        while self._running:
            try:
                message = client.receive_message(block=True, timeout=10.0)
                if message is None:
                    _log.debug(f"receive_message timeout {message}")
                    continue
                RECEIVED_MESSAGES += 1
                print("\nMessage received:")
                # print data and both system and application (custom) properties
                # for property in vars(message).items():
                #     print("    {0}".format(property))
                # print(json.loads(message.data))
                received_data = json.loads(message.data)
                if isinstance(received_data, str):
                    _log.debug(f'received_data type {type(received_data)}')
                    received_data = json.loads(received_data)
                    _log.debug(f'received_data type {type(received_data)}')
                try:
                    if "Topic" in received_data:
                        _log.debug(f"Topic: {received_data}")
                        type_msg = str(received_data.get('Topic', None))
                        _log.debug(f"Topic type_msg {type_msg}")
                        received_data["topic"] = type_msg
                    else:
                        _log.debug(f"topic: {received_data}")
                        _log.debug(f'received_data type {type(received_data)}')
                        type_msg = str(received_data.get('topic', None))
                    print('type message {}'.format(type_msg))
                    print("Total calls received: {}".format(RECEIVED_MESSAGES))
                    _log.debug(f"msg from altoiotbackend: {received_data}")

                    type_msg_list = ["custom_event", "manage_agent", "human_feedback", "watchercheck", "custom_action", "devicecontrol", "guestcheckin", "guestcheckout", "roomstatus", "scene",
                                    "provisioning", "devicediscovery", "lifecycle", "automationcreate",
                                    "automationdelete", "automationupdate"]
                    if type_msg == "custom_event":
                        self.AZD2CPublishCustomEvent(received_data)
                    elif type_msg == "watchercheck":
                        self.AZD2CPublishWatcher(received_data, client)
                    elif type_msg == "custom_action":
                        self.VIPPublishCustomAction(received_data)
                    elif type_msg == "devicecontrol":
                        _log.debug(f"type_msg devicecontrol")
                        self.VIPPublishDevice(received_data)
                    elif type_msg == "guestcheckin" or type_msg == "guestcheckout":
                        print(f"processing API request: {type_msg}")
                        self.VIPPublishGuestActivities(received_data)
                    elif type_msg == "roomstatus" or type_msg == "roomoutoforder" \
                            or type_msg == "roomoutofinventory":
                        print(f"processing API request: {type_msg}")
                        self.VIPPublishRoomActivities(received_data)
                    elif type_msg == "roomtransfer":
                        print(f"processing API request: {type_msg}")
                        self.VIPPublishRoomTransfer(received_data)
                    elif type_msg == "roomreservation":
                        print(f"processing API request: {type_msg}")
                        # TODO implement this
                    elif type_msg == "automation":
                        print(f"processing automation: {type_msg}")
                        self.VIPPublishAutomations(received_data)
                    elif type_msg == "automationcontrol":
                        print(f"processing automation: {type_msg}")
                        self.VIPtriggerAutomations(received_data)
                    elif type_msg == "hivedevhub7":
                        print(f"processing schedule")
                        self.VIPScheduling(received_data)
                    elif type_msg == "automationdelete":
                        print(f"processing automation delete.")
                        self.VIPPublishDeleteAutomation(received_data)
                    elif type_msg == "roomclean_status":
                        print(f"processing roomclean_status.")
                        self.VIPPublishRoomCleanStatus(received_data)
                    elif type_msg == "human_feedback":
                        self.VIPHumanfeedback(received_data)
                    elif type_msg == "manage_agent":
                        self.VIPManageAgent(received_data)
                except Exception as e:
                    _log.error(f'subiot message_listener {e}')
            except Exception as e:
                _log.error(f'subiot receive_message timeout {e}')
        client.disconnect()
        _log.debug(f"end message_listener {client}")

    def VIPManageAgent(self, received_data):
        _log.debug(f"Subiot Manage Agent {received_data}")
        # message = json.dumps(received_data)
        self.vip.pubsub.publish(peer="pubsub",
                                topic=f"platform/{received_data['agent_id']}",
                                headers={'requesterID': self.core.identity},
                                message=received_data["action"])

    # TODO dsadsada
    def VIPHumanfeedback(self, received_data):
        _log.debug(f'''Subiot human feedback {received_data}''')
        message = json.dumps(received_data)
        self.vip.pubsub.publish(peer="pubsub",
                                topic='rl_correct/subiot/example/command',
                                headers={'requesterID': self.core.identity},
                                message=message)

    def AZD2CPublishWatcher(self, received_data, client):
        self._watcher_status = True
        _log.debug(f'''AZD2CPublishWatcher {received_data} {self._watcher_status}''')
        client.connect()
        msg = json.dumps({
            "gatewayid": "newaltonucmintelcontrol",
            "send_index": received_data["send_index"],
            "from_device": True
        })
        client.send_message(msg)

    def VIPPublishRoomStatus(self, commsg):
        topic = str('/pms/agent/update/roomstatus')
        message = json.dumps(commsg)
        _log.debug("topic {}".format(topic))
        _log.debug("message {}".format(message))
        self.vip.pubsub.publish(
            'pubsub', topic,
            {'Type': 'HiVE Application to Gateway'}, message)

    def VIPPublishApplication(self, commsg, type_msg):
        topic = str('/ui/agent/update/hive/999/') + str(type_msg)
        message = json.dumps(commsg)
        _log.debug("topic {}".format(topic))
        _log.debug("message {}".format(message))
        self.vip.pubsub.publish(
            'pubsub', topic,
            {'Type': 'HiVE Application to Gateway'}, message)

    def VIPPublishpro(self, commsg):
        topic = str(TOPICHEAD + '/services/provision')
        # cmdmsg = {"type": "command", "command": "provision", "parameter": {}}
        # for x in ["ssid", "passphrase"]:
        #    cmdmsg["parameter"][x] = commsg[x]
        message = json.dumps(commsg)
        _log.debug("topic {}".format(topic))
        _log.debug("message {}".format(message))
        self.vip.pubsub.publish('pubsub', topic, {'Type': 'HiVE Application to Gateway'}, message)

    def VIPPublishlifecycle(self, commsg):
        topic = str(TOPICHEAD + '/services/lifecycle')
        # cmdmsg = {"type": "command", "command": "provision", "parameter": {}}
        # for x in ["ssid", "passphrase"]:
        #    cmdmsg["parameter"][x] = commsg[x]
        message = json.dumps(commsg)
        _log.debug("topic {}".format(topic))
        _log.debug("message {}".format(message))
        self.vip.pubsub.publish('pubsub', topic,{'Type': 'HiVE Application to Gateway'}, message)

    def VIPPublishdis(self, commsg):
        topic = str(TOPICHEAD + '/service/discover')
        cmdmsg = {"type": "command", "command": "discover", "parameter": {}}
        if "devicetype" in commsg:
            cmdmsg["parameter"]["devicetype"] = commsg["devicetype"]
        message = json.dumps(cmdmsg)
        _log.debug("topic {}".format(topic))
        _log.debug("message {}".format(message))
        self.vip.pubsub.publish(
            'pubsub', topic,
            {'Type': 'HiVE Application to Gateway'}, message)

    def VIPPublishCustomAction(self, commsg):
        _log.debug(commsg["action"])
        action_backend = Action(commsg["action"])
        action_volttron = action_backend.backend_to_volttron()

        for action in action_volttron:

            topic = '/'.join(action[0])
            message = action[1]
            _log.debug(f"topic from iotsub publish device: {topic}, message: {message}")
            self.vip.pubsub.publish(peer="pubsub",
                                    topic=topic,
                                    headers={'requesterID': self.core.identity,"message_type":"request"},
                                    message=message)

    def VIPPublishDevice(self, commsg):
        _log.debug(f'VIPPublishDevice: {commsg["action"]}')
        extras_msg = {
            "commsg": commsg.copy()
        }
        action_backend = Action(commsg["action"])
        action_volttron = action_backend.backend_to_volttron(**extras_msg)


        for action in action_volttron:

            topic = '/'.join(action[0])
            message = action[1]
            _log.debug(f"topic from iotsub publish device: {topic}, message: {message}")
            self.vip.pubsub.publish(peer="pubsub",
                                    topic=topic,
                                    headers={'requesterID': self.core.identity,"message_type":"command"},
                                    message=message)

    def VIPtriggerAutomations(self, commsg):
        # TODO remove statics and need support for multiple checkin call
        hotel = commsg['hotel_name']
        building = 'main'  # TODO fix this to support multiple building
        request = commsg['topic']
        # room = commsg['message'][0]['RoomNo']
        topic = f"alto/Mintel/main/108/test_automation/dev001"
        print(f"Publishing {topic} \n")
        commsg2 = {'OPENCLOSE': 'OPEN'}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity, "request": request},
                                message=commsg2)

    def VIPPublishAutomations(self, commsg):
        topic = f"app/actiontrans/translator/request"
        print(f"Publishing {topic} \n")
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity, "message_type": "request"},
                                message=commsg)

    def AZD2CPublishCustomEvent(self, commsg):
        _log.debug(f"in custom_event: {commsg}")
        request = commsg['topic']
        topic = f"custom_event/{commsg['action'][0]['event_topic']}"
        header = {'requesterID': self.core.identity, "request": request, "message_type": "event"}
        message = {}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers=header,
                                message=message)
        _log.info(f'publish {request} topic {topic}')
        _log.info(f'publish message {message}')

    def VIPPublishGuestActivities(self, commsg):
        _log.debug(f"in checkin and checkout: {commsg}")
        # hotel = commsg['hotel_code']
        building = 'main'  # TODO fix this to support multiple building
        request = commsg['topic']
        hotel = commsg["hotel_name"].lower()
        # room = commsg['Data'][0]['RoomNo']
        room = commsg['Data'][0].get("RoomNo", None)
        if room is None:
            room = commsg.get("RoomNo", None)
            if room is None:
                _log.info(f'RoomNo not found')
                return
        command = "check_in" if request == "guestcheckin" else "check_out"
        topic = f"pms/{hotel}/room_{room}/{command}"
        header = {'requesterID': self.core.identity, "request": request, "message_type": "event"}
        message = {"check": "in"} if request == "guestcheckin" else {"check": "out"}
        _log.debug(f"Publishing topic {topic} \n")
        _log.debug(f"Publishing header {header} \n")
        _log.debug(f"Publishing message {message} \n")
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers=header,
                                message=message)
        _log.info(f'publish {request} for {room}')

    def VIPPublishRoomActivities(self, commsg):
        print(commsg)
        hotel = commsg['hotel_code']
        building = 'main'  # TODO fix this to support multiple building
        request = commsg['topic']
        room = commsg['Data'][0]['RoomNo']
        topic = f"rooms/{room}"
        _log.debug(f"Publishing {topic} \n")
        self.vip.pubsub.publish(peer="rooms",
                                topic=topic,
                                headers={'requesterID': self.core.identity, "request": request},
                                message=commsg['Data'][0])

    def VIPPublishRoomTransfer(self, commsg):
        print(commsg)
        hotel = commsg['hotel_code']
        building = 'main'  # TODO fix this to support multiple building
        request = commsg['topic']
        room = commsg['Data'][0]['FromRoomNo']
        topic = f"rooms/{room}"
        _log.debug(f"Publishing {topic} \n")
        self.vip.pubsub.publish(peer="rooms",
                                topic=topic,
                                headers={'requesterID': self.core.identity, "request": request},
                                message=commsg['Data'][0])

    ## send the schedule to do to action agent
    def VIPScheduling(self, commsg):
        _log.debug(f"in VIPScheduling Publish -> {commsg}")

    def VIPPublishDeleteAutomation(self, commsg):
        list_rules = commsg["automation_id"]
        list_rules = [str(list) for list in list_rules]

        self.vip.pubsub.publish(peer="pubsub",
                                topic='config/automation/del_rules',
                                headers={'requesterID': self.core.identity,
                                         "message_type": "request"},
                                message={"reply_to": "response/automation", "rid": "456", "rules": list_rules})

    def VIPPublishRoomCleanStatus(self, commsg):
        self.vip.pubsub.publish(peer="pubsub",
                                topic='app/maidapp/10minsac/event',
                                headers={'requesterID': self.core.identity,
                                         "message_type": "event"},
                                message=commsg)


# Step1: Agent Initialization
def iothubsub_agent(config_path, **kwargs):
    # config = utils.load_config(config_path)

    # def get_config(name):
    #     try:
    #         kwargs.pop(name)
    #     except KeyError:
    #         return config.get(name, '')


    # Agent.__name__ = 'subscribeIoTAgent'
    # return iothubsubAgent(config_path, **kwargs)
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    all_config = config.get("all_config", {})

    return iothubsubAgent(all_config, **kwargs)


def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(iothubsub_agent, identity='subscribeIoTAgent')
    except Exception as e:
        _log.exception('unhandled exception')

if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
