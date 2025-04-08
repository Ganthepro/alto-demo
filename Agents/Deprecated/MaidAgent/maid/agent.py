"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'
import json
import logging
import sys
import random
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron, periodic
from threading import Thread
import sched
import time
import requests

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"
class Line:

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self._auth_line(self.username, self.password)


    def _send_to_line(self, message):
        try:
            response = requests.post(
                url="https://altoiotbackendprod.azurewebsites.net/api/v2.0/push_to_line",
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
                url="https://altoiotbackendprod.azurewebsites.net/api/v2.0/login",
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

def tester(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Tester
    :rtype: Tester
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Tester(setting1,
                          setting2,
                          **kwargs)


class Tester(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic",
                 **kwargs):
        super(Tester, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.rooms = {}
        self.setting1 = setting1
        self.setting2 = setting2
        self.threads = []
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.line_api = Line(username="minteladmin", password="minteladmin")
        self.default_config = {"setting1": setting1,
                               "setting2": setting2}
        self.no_acon_rooms = {}
        self.checkin_rooms = {}
        self.rooms_countstat = {}
        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
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
            setting1 = int(config["setting1"])
            setting2 = str(config["setting2"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.setting1 = setting1
        self.setting2 = setting2

        self._create_subscriptions(self.setting2)

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="app/maidapp/10minsac/event",
                                  callback=self._handle_publish)

    def _volttron_subscribe(self, topic: str, callback):
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=callback)
        _log.debug(f"subscribe to topic: {topic}")

    def _volttron_unsubscribe(self, topic: str):
        self.vip.pubsub.unsubscribe("pubsub", topic, None)
        _log.debug(f"unsubscribe to topic: {topic}")

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        if message["message"]["room_status"].startswith("v"):

            room = message["message"]["location"]
            clean_status = message["message"]["clean_status"]
            _log.debug(f"in _handle_publish with atopic: {topic},message: {message}")
            if clean_status == "startclean":
                self.rooms_countstat["room_"+room] = 0
                self.no_acon_rooms["room_"+room] = False
                self._volttron_subscribe(topic=f"datalogger/room_{room}/ac_{room}", callback=self._is_maid_turnon)
            elif clean_status == "endclean":
                self.no_acon_rooms.pop(room, None)
                self.checkin_rooms.pop(f"room_{room}",None)
                self._close_everything(room)
                self.vip.pubsub.unsubscribe("pubsub", f"datalogger/room_{room}/ac_{room}", None)
                # self._volttron_unsubscribe(f"datalogger/room_{room}/ac_{room}")
            else:
                raise Exception("clean_status is not either startclean or endclean, We don't support that!")

    def _close_everything(self, room):
        topic = f"location/mintel/room_{room}/check_out"
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message={})
        self.checkin_rooms.pop(f"room_{room}", None)
        _log.debug(f"close everything topic {topic}")

    def _is_maid_turnon(self, peer, sender, bus, topic, headers,
                        message):
        '''
        to be implemented
        :param peer:
        :param sender:
        :param bus:
        :param topic:
        :param headers:
        :param message:
        :return:
        '''

        # check if maid turn on the ac.
        # def _is_maid_turnon(self):
        #     if maid turn on the ac # check from subscribe to the room topic if payload mode != "off"
        #         schedule the task to turn off the ac in next 10 mins # should be implemented by while True.
        #     if maid finish cleaning
        #         unsubscribe to the topic # room

        message.pop("room_temperature", None)
        message.pop("timestamp", None)

        _log.debug(f"topic {topic}, message {message}")
        room = topic.split('/')[1]
        if "temperature" in message:
            message["temperature"] = float(message["temperature"])

        _log.debug(f" rooms_countstat message {self.rooms_countstat}")
        # if (message["mode"] != "off" and message["mode"] != self.rooms_countstat[room]) :
        if message["mode"] != self.rooms_countstat[room]:
            _log.debug(f"starting _schedule_ac to turn off ")
            device_id = topic.split("/")[2]  # or message["device_id"]
            # schedule_time = time.time() + 600
            # self._schedule_ac(schedule_time, device_id)
            # _log.debug(f"finish _schedule_ac to turn off at {schedule_time}")
            _log.debug(f"check in rooms {self.checkin_rooms}")
            self.rooms_countstat[room] = message["mode"]
            # if room not in self.checkin_rooms:
            if self.no_acon_rooms[room] == False:
                _log.debug(f"maid turn on")
                # self.rooms_countstat[room] = message["mode"]
                self.no_acon_rooms[room] = True
                self.checkin_rooms[room] = time.time()
                # self._schedule_ac(time.time() + 600, device_id)
            else:
                if message["mode"] != "off":
                    _log.debug("maid intruder noti")
                    # self.rooms_countstat[room] = message["mode"]
                    # self.checkin_rooms[room] = time.time()
                    # self._schedule_ac(time.time() + 60, device_id)
                    self.line_api._send_to_line(f"maid turn on the ac in {room.replace('_', ' ')}")
                    self._schedule_ac(time.time()+10, "ac_"+room.split('_')[1])
        else:
            if message["mode"] == "off" and message != self.rooms_countstat[room]:
                self.rooms_countstat[room] = message
                self.checkin_rooms.pop(room, None)


    def _schedule_ac(self, time, device_id):
        self.scheduler.enterabs(time, 1, self._turnoff_ac, argument=(device_id,))
        self.scheduler.run()

    def _turnoff_ac(self,device_id: str):
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

    @Core.schedule(periodic(5))
    def check_intruders(self):
        # Update if needed
        now = time.time()
        _log.debug(f"check checkin_rooms: {len(self.checkin_rooms)}")
        self.finished_check = []
        for room, t in self.checkin_rooms.items():
            if now - t > 600:
                # self._send_to_line("you stay too long in the room bro!")
                subdevice_idx = 0
                device_id = "ac_" + room.split('_')[1]
                self._control_ac(device_id, subdevice_idx, mode="off")
                self.finished_check.append(room)
        for room in self.finished_check:
            self.checkin_rooms.pop(room, None)
            # self.vip.pubsub.unsubscribe("pubsub",f"datalogger/{room}/ac_{room.split('_')[1]}",None)
        _log.debug(self.checkin_rooms)

    def _control_ac(self, device_id: str, subdevice_idx: int, **kwargs):
        _log.debug("in _control ac")
        message = {}
        for k, v in kwargs.items():
            message[k] = v
        message["subdevice_idx"] = subdevice_idx
        topic = f"hvac/carrierac/{device_id}/command"
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={"requesterID": self.core.identity,
                                         "message_type": "command"},
                                message=message)
        _log.debug(f"topic {topic}, msg {message}")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        #Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        #Exmaple RPC call
        #self.vip.rpc.call("some_agent", "some_method", arg1, arg2)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """

    @RPC.export  # expose RPC interface for other agents, can alto define capability
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method
        May be called from another agent via self.core.rpc.call """
        _log.debug('get called from another agent via RPC')
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(tester, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
