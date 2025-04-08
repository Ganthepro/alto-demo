"""
Agent documentation goes here.
"""
__docformat__ = 'reStructuredText'
import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub
import pytz
from datetime import datetime
from ISStreamer.Streamer import Streamer
_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

tz = pytz.timezone('Asia/Bangkok')

def initial(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Initial
    :rtype: Initial
    """
    try:
        config = utils.load_config(config_path)
        _log.debug(config)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    print(kwargs)
    topics = config.get('topics', )
    gatewayid = config.get('gatewayid', )
    # ----InitialState Config----
    BUCKET_NAME = config.get('BUCKET_NAME', )
    BUCKET_KEY = config.get('BUCKET_KEY', )
    ACCESS_KEY = config.get('ACCESS_KEY', )

    print(BUCKET_NAME, BUCKET_KEY, ACCESS_KEY, gatewayid, topics)

    return Initial(topics, gatewayid, BUCKET_NAME, BUCKET_KEY, ACCESS_KEY,
                        **kwargs)


class Initial(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, topics, gatewayid, BUCKET_NAME, BUCKET_KEY, ACCESS_KEY, **kwargs):
        super(Initial, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.topics = topics
        self.gatewayid = gatewayid
        self.BUCKET_NAME = BUCKET_NAME
        self.BUCKET_KEY = BUCKET_KEY
        self.ACCESS_KEY = ACCESS_KEY

        self.default_config = {"topics": topics,
                               "gatewayid": gatewayid,
                               "BUCKET_NAME": BUCKET_NAME,
                               "BUCKET_KEY": BUCKET_KEY,
                               "ACCESS_KEY": ACCESS_KEY}
        # Initialize Initial State Streamer
        self.streamer = Streamer(bucket_name=self.BUCKET_NAME, bucket_key=self.BUCKET_KEY, access_key=self.ACCESS_KEY)

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
            topics = dict((config["topics"]))
            gatewayid = str(config["gatewayid"])
            BUCKET_NAME = str(config["BUCKET_NAME"])
            BUCKET_KEY = str(config["BUCKET_KEY"])
            ACCESS_KEY = str(config["ACCESS_KEY"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        self.topics = topics
        self.gatewayid = gatewayid
        self.BUCKET_NAME = BUCKET_NAME
        self.BUCKET_KEY = BUCKET_KEY
        self.ACCESS_KEY = ACCESS_KEY



    #     self._create_subscriptions(self.setting2)
    #
    # def _create_subscriptions(self, topic):
    #     #Unsubscribe from everything.
    #     self.vip.pubsub.unsubscribe("pubsub", None, None)
    #
    #     self.vip.pubsub.subscribe(peer='pubsub',
    #                               prefix=topic,
    #                               callback=self._handle_publish)
    #
    # def _handle_publish(self, peer, sender, bus, topic, headers,
    #                             message):
    #     pass

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

    @PubSub.subscribe(peer='pubsub', prefix='devices')
    def subscribe_device(self, peer, sender, bus, topic, headers, message):
        _log.warning("initialstate subscribe prefix -devices- :{}, sender:{}, bus:{}, topic:{}, message:{}"
                     .format(peer, sender, bus, topic, message))
        try :
            topic = topic.split('/')
        except Exception as er:
            _log.debug(" error topic cannot split(/) {}".format(er))

        # ----> check toppic
        if topic[0] == "devices" and topic[1][:7] == 'sensor_':
            self.envInit(topic, message)
        elif topic[0] == "devices" and topic[1][:8] == 'airconet':
            self.airconetInit(topic, message)
        else:
            _log.debug("Cannot catch the toppic--------> {}".format(topic))

    def envInit(self, topic, message):
        _log.warning("Print initialstate subscribe ENV :{} {}".format(topic,message))
        try:  # ----->
            self.streamer.log("Last update: {}".format(message['mac']), message['data']['datetime'])
            self.streamer.log(":computer:air_quality {}".format(message['mac']), message['data']['air_quality'])
            self.streamer.log(":computer:light {}".format(message['mac']), message['data']['light'])
            self.streamer.log(":computer:noise {}".format(message['mac']), message['data']['noise'])
            self.streamer.log(":computer:temperature {}".format(message['mac']), message['data']['temperature'])
            self.streamer.log(":computer:humidity {}".format(message['mac']), message['data']['humidity'])
            _log.debug("done publishing to initialstate ENV   {}".format(message['mac']))
            self.streamer.flush()
        except Exception as er:
            _log.debug(" error sending data to initialstate ENV   {}".format(er))

    def airconetInit(self, topic, message):
        _log.warning("Print initialstate subscribe airconet :{} {}".format(topic, message))
        try:
            self.streamer.log("Last update: {}".format(message['mac']), message["data"]['datetime'])
            self.streamer.log(":computer:status {}".format(message['mac']), message["data"]['status'])
            self.streamer.log(":computer:mode {}".format(message['mac']),"mode:" + message["data"]['mode'])
            self.streamer.log(":computer:fansp {}".format(message['mac']),"fan:" +  message["data"]['fansp'])
            self.streamer.log(":computer:settemp {}".format(message['mac']), message["data"]['settemp'])
            self.streamer.log(":computer:roomtemp {}".format(message['mac']), message["data"]['temperature'])
            self.streamer.log(":computer:error {}".format(message['mac']), message["data"]['error'])
            self.streamer.log(":computer:room {}".format(message['mac']), message["data"]['room'])
            self.streamer.log(":computer:registered {}".format(message['mac']), message["data"]['registered'])
            self.streamer.log(":computer:presence {}".format(message['mac']), message["data"]['presence'])
            _log.debug("done publishing to initialstate airconet state")
            self.streamer.flush()
        except Exception as er:
            _log.debug(" error sending data to initialstate airconet state {}".format(er))

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(initial, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass

# Example data for subscribe
#  topic devices/sensor_" + str(mac).replace(":", "") + "/state  {'ip': '192.168.1.104', 'mac': 'e7f5fb0d43b4', 'data': {'temperature': 21.7, 'humidity': 64.3, 'light': 'normal', 'air_quality': 'excellent', 'noise': 'normal'}}


# Example data for subscribe
                        # Publishing devices/airconet_cc50e33b11aa/state
                        # {'hotel': 'naplabcu', 'building': 'naplabcu', 'type': 'airconet', 'room': None, 'registered': None,
                        #  'addr': ('192.168.1.115', 1540), 'mac': 'cc50e33b11aa', 'Action': 'control from remote',
                        #  'data': {'status': 'on', 'mode': 'auto', 'fansp': 'fan auto', 'error': 'No error', 'roomtemp': '23.0',
                        #           'settemp': '24.0'}}

                        # Publishing devices/airconet/heartbeat
                        # {'hotel': 'naplabcu', 'building': 'naplabcu', 'type': 'airconet', 'addr': None, 'mac': None, 'Action': 'heartbeat',
                        #  'data': {'no': 1, 'cc50e33b11aa': {'addr': ('192.168.1.115', 1540), 'room': None}}}
