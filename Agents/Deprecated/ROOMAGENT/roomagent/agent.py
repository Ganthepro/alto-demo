"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
import settings
_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

DEBUG = settings.DEBUG

def roomagent(config_path, **kwargs):
    """
        # ** if this agent has been initially configure with config file, it'll use config from config file
        Parses the Agent configuration and returns an instance of
        the agent created using that configuration.
        :param config_path: Path to a configuration file.
        :type config_path: str
        :returns: Roomagent
        :rtype: Roomagent
    """
    try:
        config = utils.load_config(config_path)
    except ValueError as er:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    hotel_name = config.get('hotel_name', "mintel")
    building_name = config.get("building_name", "mintel_1")
    room_no = int(config.get('room_no', 50))
    topic_head = config.get('topic_head', "alto")
    gateway_name = config.get('gateway_name', "nuci7")
    message_agent = config.get("message_agent", None)
    room_device_mac = config.get('room_device_mac', {"fan": "DC4F22AB5747", "light1": "600194D8DF25", "light2": "None", "ac": "None", "sensor_environment": "None"})
    room_rule = config.get('room_rule', {})

    return Roomagent(hotel_name, building_name, room_no, topic_head, gateway_name,
                     message_agent, room_device_mac, room_rule, **kwargs)


class Roomagent(Agent):
    """
    Document agent constructor here.
    """
    def __init__(self, hotel_name, building_name, room_no, topic_head, gateway_name,
                     message_agent, room_device_mac, room_rule, **kwargs):
        super(Roomagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        # TODO define all params for current and historical (crate) room knowledge
        self.hotel_name = hotel_name
        self.building_name = building_name
        self.room_no = room_no
        self.topic_head = topic_head
        self.gateway_name = gateway_name
        self.message_agent = message_agent
        self.room_device_mac = room_device_mac
        self.room_rule = room_rule

        self.default_config = {}
        self.default_config["hotel_name"] = self.hotel_name
        self.default_config["building_name"] = self.building_name
        self.default_config["room_no"] = self.room_no
        self.default_config["topic_head"] = self.topic_head
        self.default_config["gateway_name"] = self.gateway_name
        self.default_config["message_agent"] = self.message_agent
        self.default_config["room_device_mac"] = self.room_device_mac
        self.default_config["room_rule"] = self.room_rule

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        ** refer to AGENT_VIP_IDENTITY, it will load config from config store manager if AGENT_VIP_IDENTITY match
        ** check config stored: vctl config get <AGENT_VIP_IDENTITY> config
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.
        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)
        print(config)
        _log.debug("Configuring Agent")

        try:
            hotel_name = config['hotel_name']
            building_name = config["building_name"]
            room_no = int(config['room_no'])
            topic_head = config['topic_head']
            gateway_name = config['gateway_name']
            message_agent = config["message_agent"]
            room_device_mac = config['room_device_mac']
            room_rule = config['room_rule']

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.hotel_name = hotel_name
        self.building_name = building_name
        self.room_no = room_no
        self.topic_head = topic_head
        self.gateway_name = gateway_name
        self.message_agent = message_agent
        self.room_device_mac = room_device_mac
        self.room_rule = room_rule

        # alto/mintel/mintel1/50  (alto/hotel/building/room)
        self.topic_room = "rooms/{}".format(self.room_no)
        print(f'subscribe to topic {self.topic_room}')
        self._create_subscriptions(self.topic_room)

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("rooms", None, None)

        self.vip.pubsub.subscribe(peer='rooms',
                                  prefix=topic,
                                  callback=self.roomcmd)

    def roomcmd(self, peer, sender, bus, topic, headers, message):
        _log.debug("Print from subscribe roomcmd :{}, sender:{}, bus:{}, topic:{},headers:{} , message:{}"
                   .format(peer, sender, bus, topic, headers, message))
        _log.debug("{}-->{}".format(headers["request"], type(headers["request"])))

        # Room Agent behavior: 1. republish its status update, then it can be trigger by other apps
        # TODO check room status change
        hotel = self.hotel_name
        building = self.building_name
        request = headers['request']
        room_no = self.room_no
        topic = f"room{room_no}/status/{request}/"
        message['status'] = request
        if DEBUG: _log.debug(f"Publishing {topic}")
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity, "request": request},
                                message=message)
        if DEBUG: _log.info(f'publish {topic} room status change for {room_no}')
        if DEBUG: _log.info(f'publish room status change for {message} \n')

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
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(roomagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
