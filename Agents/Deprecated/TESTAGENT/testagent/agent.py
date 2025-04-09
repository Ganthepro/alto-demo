"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic

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

        self._create_subscriptions("alto/mintel/mintel1/50")

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        print(" Sub topic --> {} +++headers --> {}  message --> {}".format(topic, headers, message) )

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
        print("onstart 123123123123123121231231254*31*/2*3/1*/2/3")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        print("onstop 123123123123123121231231254*31*/2*3/1*/2/3")

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

    # @Core.schedule(periodic(5))
    # def printconfig(self):
    #     print(f"you config self.topic = {self.topic}  self.message = {self.message} self.hotel = {self.hotel}")
    #
    # @Core.schedule(periodic(10))
    # def newconfig(self):
    #     global no
    #     newconfig = self.vip.config.get("config")
    #     newconfig["message"] = f"this is new config --> {no}"
    #     self.vip.config.set("config", newconfig, trigger_callback=True)
    #     print(f"you new config self.topic = {self.topic}  self.message = {self.message} self.hotel = [self.hotel")
    #     no += 1
    #
    # # @Core.schedule(periodic(30))
    # def changeme(self, tasstate):
    #     # global tasstate
    #     print("pub")
    #     # tasstate = tasstate == "on" and "off" or "on"
    #     for i in range(3):
    #         print("pub", i)
    #         self.vip.pubsub.publish("pubsub", "alto/devices/switch_d8df25/power",
    #                                 headers={'requesterID': self.core.identity},
    #                                 message={"gang": int(i), "power": tasstate})

    # @Core.schedule(periodic(10))
    # def lighttest(self):
    #     global tasstate
    #     print("pub")
    #     tasstate = tasstate == "on" and "off" or "on"
    #     if tasstate is 'on':
    #         self.vip.pubsub.publish("pubsub", "alto/mintel/mintel1/50/light/600194D8DF25",
    #                                 headers={'requesterID': self.core.identity, "request": "controllight"},
    #                                 message={"index_status":{1:'on',2:'on',3:'on'}})
    #
    #         self.vip.pubsub.publish("pubsub", "alto/mintel/mintel1/50/fan/DC4F22AB5747",
    #                                 headers={'requesterID': self.core.identity, "request": "controlfan"},
    #                                 message={"index_status": {1: 'on'}})
    #     else:
    #         self.vip.pubsub.publish("pubsub", "alto/mintel/mintel1/50/light/600194D8DF25",
    #                                 headers={'requesterID': self.core.identity, "request": "controllight"},
    #                                 message={"index_status":{1:'off',2:'off',3:'off'}})
    #
    #         self.vip.pubsub.publish("pubsub", "alto/mintel/mintel1/50/fan/DC4F22AB5747",
    #                                 headers={'requesterID': self.core.identity, "request": "controlfan"},
    #                                 message={"index_status": {1: 'off'}})

    @Core.schedule(periodic(300))
    def lighttest(self):
        global tasstate
        print("pub")
        tasstate = tasstate == "on" and "off" or "on"
        if tasstate is 'on':
            self.vip.pubsub.publish("pubsub", "alto/mintel/mintel1/50",
                                    headers={'requesterID': self.core.identity, "request": "room_check_in"},
                                    message={})

        else:
            self.vip.pubsub.publish("pubsub", "alto/mintel/mintel1/50",
                                    headers={'requesterID': self.core.identity, "request": "room_check_out"},
                                    message={})

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
