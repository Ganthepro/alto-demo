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
import pyrebase
from threading import Thread
import sched
import time
import requests

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
            if response.status_code == 400 or response.status_code == 401 :
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
        self.acs_on = {}
        self.line_api = Line(username="minteladmin", password="minteladmin")
        self.default_config = {"setting1": setting1,
                               "setting2": setting2}


        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
        self._main()

    def configure(self, config_name, action, contents):
        """        self.setting1 = setting1

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

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="datalogger",
                                  callback=self._is_sone_turnon)
        self.vip.pubsub.subscribe(peer="pubsub",
                                  prefix="pms",
                                  callback=self._handle_pms)

    def _volttron_subscribe(self, topic: str, callback):
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=callback)
        _log.debug(f"subscribe to topic: {topic}")

    def _volttron_unsubscribe(self, topic: str, callback):
        self.vip.pubsub.unsubscribe("pubsub", topic, None)
        _log.debug(f"unsubscribe to topic: {topic}")

    def _create_unsubscriptions(self, topic: str, _func):
        #unscribe to a specify topic.
        self.vip.pubsub.unsubscribe("pubsub", topic, None)

    def _handle_pms(self, peer, sender, bus, topic, headers, message):
        topic = topic.split('/')
        event = topic[3]
        room = topic[2].split('_')[1]
        if event == "check_in":
            self.rooms[room] = "oc"
        
    def _is_sone_turnon(self, peer, sender, bus, topic, headers, message):
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
        # def _is_sone_turnon(self):
        #     if maid turn on the ac # check from subscribe to the room topic if payload mode != "off"
        #         schedule the task to turn off the ac in next 10 mins # should be implemented by while True.
        #     if maid finish cleaning
        #         unsubscribe to the topic # room
        topic = topic.split("/")
        device_id = topic[2]
        room = topic[1]
        _log.debug(f"Does sone turn on {device_id} in {room}")
        if room.startswith("room_") and self.rooms[room.split('_')[1]] not in ["od","oc","startclean"]:
            if device_id.startswith("ac_"):
                _log.debug(self.rooms[room.split('_')[1]])
                if message["mode"] != "off": # and self.rooms[room.split('_')[1]] not in ["od","oc","startclean"] :
                    _log.debug(f"device_id {device_id}, acs_on {self.acs_on}")
                    if  device_id not in self.acs_on:
                        # add api for sending msg to line.
                        msg = f"someone turn on the ac in {room.replace('_', ' ')}"
                        self.line_api._send_to_line(msg)
                        self.acs_on[device_id] = time.time()
                        self._schedule_dev(time.time() + 60, device_id, 0, "ac")
                else:
                    self.acs_on.pop(device_id, None)
            elif  device_id.startswith("tasmota_"):
                if message["state"] == "on" and message["subdevice_name"] != "fan":
                    msg = f"someone turn on the light in {room.replace('_', ' ')}"
                    self.line_api._send_to_line(msg)
                    self._schedule_dev(time.time() + 60, device_id, message["subdevice_idx"], "relay")

    #subscribe to firebase
    def _firebase_subscribe(self):
        ## listen to firebase node
        self.is_maid_intheroom = db.child("hotel").child("mintel").child("user_info").stream(self._is_maid_intheroom)

    # check if maid get in.
    def _is_maid_intheroom(self, message: dict):
        # check if maid get in.
        # def _is_maid_intheroom(self):
        #
        #     if maid in the room:  ##check from firebase, if status change to "maid_get_in"
        #         subscribe
        #         to
        #         that
        #         room  ##vip subscribe topic from the room. call back function is _is_maid_turnon
        #         example topic: datalogger/room_<no>
        _log.debug("in _is_maid_intheroom")
        path = message["path"]
        # check from firebase, if status change to "maid_get_in"
        try:

            # if callback first time, firebase will send everything in the child to us.
            if path == "/":
                rooms_status = message["data"]["room_status"]  # rooms status in dict
                for room, val in rooms_status.items():
                    try:
                        self.rooms[room] = val["clean_status"]
                    except Exception as e:
                        _log.error(f"error while staring get room status: {e}")
                _log.debug(f"rooms: {self.rooms}")
            else:
                ## if not the first time, it will send only the node that value is changed.
                if path.startswith("/room_status"):
                    ## to be edit
                    clean_status = message["data"]["clean_status"]
                    room = message["path"].split('/')[2]
                    self.rooms[room] = clean_status
                    _log.debug(f"rooms: {room}")
        except Exception as e:
            _log.debug(f"error in stream_handler function: {e}")
    # check
    # func to turn off the ac.

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):

        room = message["message"]["location"]
        clean_status = message["message"]["clean_status"]
        room_status = message["message"]["room_status"]
        if clean_status == "startclean":
            self.rooms[room] = clean_status
        else:
            self.rooms[room] = room_status
        _log.debug(f"in _handle_publish with rooms: {self.rooms}")

    def _schedule_dev(self, time, device_id, subdevice_idx, dev_type):
        if dev_type=="ac":
            _log.debug(f"starting schedule {dev_type}")
            self.scheduler.enterabs(time, 1, self._turnoff_ac, argument=(device_id,subdevice_idx))
            self.scheduler.run()
        if dev_type=="relay" :
            _log.debug(f"starting schedule {dev_type}")
            self.scheduler.enterabs(time, 1, self._turnoff_relay, argument=(device_id,subdevice_idx))
            self.scheduler.run()

    def _turnoff_relay(self,device_id:str,subdevice_idx):
        message = {"subdevice_idx":subdevice_idx, "state":"off"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=f"switch/tasmota/{device_id}/command",
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)

    def _turnoff_ac(self,device_id: str,subdevice_idx):
        '''

        :return:
        '''
        message = {"subdevice_idx":subdevice_idx, "mode": "off"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=f"hvac/carrierac/{device_id}/command",
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)

    def _main(self):
        '''
        1. check _maid_intheroom -> true
        2. check maid turn on the ac -> true
        3. turn off the ac after 10 mins
        :return: publish command to turn off the ac
        '''
        self._firebase_subscribe()


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
