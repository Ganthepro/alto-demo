"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic
import time

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "10"

global tasstate,no
tasstate = "off"
no = 1
print('0.area import')

def testagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Testagent
    :rtype: Testagent
    """
    print("2.in def testagent configpath --> {} kwargs --> {}".format(config_path,kwargs))

    try:
        config = utils.load_config(config_path)
        print("3. try load config from {} and show config --> {}".format(config_path ,config))
    except StandardError:
        config = {}

    if not config:
        print("3.5.1if not config -->Using Agent defaults for starting configuration.")

    topic = config.get('topic', "alto/defaultconfig")
    message = config.get('message', "Room 111 hello")
    hotel = config.get('hotel', "chaweng")

    print("topic (default = alto/defaultconfig) -> {}".format(topic))
    print("message (default = Room 111 hello) -> {}".format(message))
    print("hotel (default = chaweng) -> {}".format(hotel))

    return Testagent(topic,
                     message,
                     hotel,
                     **kwargs)

class Testagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, topic="init alto/defaultconfig", message="init Room 111 hello", hotel="init chaweng" ,
                 **kwargs):

        print("init topic (default = alto/defaultconfig) -> {}".format(topic))
        print("init message (default = Room 111 hello) -> {}".format(message))
        print("init hotel (default = chaweng) -> {}".format(hotel))
        print("init kwargs --> {}".format(kwargs))

        super(Testagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.topic = topic
        self.message = message
        self.hotel = hotel
        self.lights_in_room = {}
        self.rooms_countstat = {}
        print("set default_config for config store")
        self.default_config = {"topic": topic,
                               "message": message,
                                "hotel": hotel}

        print("look at self.default_config --> {}".format(self.default_config))

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        --> Called after the Agent has connected to the message bus.
        --> If a configuration exists at startup.this will be called before onstart.
        --> Is called every time the configuration in the store changes.
        """
        print("!@#@#@!#@#@#@!#!@#!@# call def configure !@#@#@!#@#@#@!#!@#!@#")

        config = self.default_config.copy()
        config.update(contents)
        _log.debug("Configuring Agent")
        print(config)
        try:
            topic = config.get('topic', "alto/defaultconfig")
            message = config.get('message', "Room 111 hello")
            hotel = config.get('hotel', "chaweng")
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.topic = topic
        self.message = message
        self.hotel = hotel
        self.checkin_rooms = {}
        self._create_subscriptions("pms")

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_pms)
    def _handle_pms(self, peer, sender,bus, topic, headers,
                                message):
        topic = topic.split('/')
        room = topic[2] # eg. room_201
        event = topic[3]
        _log.debug(f"check in to topic {topic}")
        if event == "check_in":
            self.checkin_rooms[room] = time.time()
            _log.debug(f"self.checkin_rooms ===={self.checkin_rooms}")
            self.rooms_countstat[room] = 0
            # time.sleep(15)
            self.vip.pubsub.subscribe(peer="pubsub",
                                      prefix=f"datalogger/{room}",
                                      callback=self._handle_room)

    def _handle_room(self, peer, sender, bus, topic, headers,
                                message):
        _log.debug(f"in _handle_room topic: {topic}, message {message}")
        message.pop("room_temperature", None)
        message.pop("timestamp", None)
        if "temperature" in message:
            message["temperature"] = float(message["temperature"])
        room = topic.split('/')[1]
        _log.debug(f"message {self.rooms_countstat}")
        if self.rooms_countstat[room] == 0 and message["type"] == "ac" and message["mode"] != "off" and message["temperature"] == 25.0:
            _log.debug(f"first message {self.rooms_countstat}")
            self.rooms_countstat[room] = message
        if message["type"] in ["ac", "relay"] and message["subdevice_name"] != "fan":
            if message["type"] == "ac" and self.rooms_countstat[room] !=message:
                _log.debug(f"message that met condition: {message}")
                # self.finished_check.append(room)
                self.checkin_rooms.pop(room, None)
                self.lights_in_room.pop(room, None)
                self.rooms_countstat.pop(room, None)
                try:
                    self.vip.pubsub.unsubscribe("pubsub", f"datalogger/{room}", None)
                except Exception as e:
                    _log.debug(f"error in unsubscribe to the topic {room}")

            if message["type"] == "relay":
                if room not in self.lights_in_room:
                    self.lights_in_room[room] = 1
                else:
                    self.lights_in_room[room] += 1
                if self.lights_in_room[room] >= 2:
                    # self.finished_check.append(room)
                    self.checkin_rooms.pop(room, None)
                    self.lights_in_room.pop(room, None)
                    self.rooms_countstat.pop(room, None)
                    try:
                        self.vip.pubsub.unsubscribe("pubsub", f"datalogger/{room}", self._handle_room)
                    except Exception as e:
                        _log.debug(f"error in unsubscribe to the topic {room}")

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        print(" Sub topic --> {} +++headers --> {}  message --> {}".format(topic, headers, message) )

    @Core.schedule(periodic(5))
    def check_intruders(self):
        # Update if needed
        _log.debug(self.checkin_rooms)
        now = time.time()
        _log.debug(f"check checkin_rooms: {len(self.checkin_rooms)}")
        self.finished_check = []
        for room, t in self.checkin_rooms.items():
            if now - t > 3600:
                # self._send_to_line("you stay too long in the room bro!")
                subdevice_idx = 0
                device_id = "ac_"+room.split('_')[1]
                self._control_ac(device_id, subdevice_idx, temperature=27)
                self.finished_check.append(room)
        for room in self.finished_check:
            self.checkin_rooms.pop(room,None)
            self.lights_in_room.pop(room,None)
            self.rooms_countstat.pop(room,None)
            try:
                self.vip.pubsub.unsubscribe("pubsub", f"datalogger/{room}",self._handle_room)
            except Exception as e:
                _log.debug(f"error in unsubscribe to the topic {room}")
        _log.debug(self.checkin_rooms)

    def _control_ac(self, device_id: str, subdevice_idx: int, **kwargs):
        message = {}
        for k, v in kwargs.items():
            message[k] = v
        message["subdevice_idx"] = subdevice_idx
        topic = f"hvac/carrierac/{device_id}/command"
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={"requesterID": self.core.identity,
                                         "message_type":"command"},
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

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    print("1.5 in main function before cal utils.vip to testagent ")
    utils.vip_main(testagent, 
                   version=__version__)


if __name__ == '__main__':
    print("1 . in if name == main")
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
