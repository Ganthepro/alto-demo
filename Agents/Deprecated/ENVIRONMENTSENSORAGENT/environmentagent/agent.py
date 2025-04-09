"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, \
    PubSub  # @PubSub.subscribe('pubsub', 'devices/mintel/room1/aircon/all')
import importlib
from volttron.platform.scheduling import periodic
import random

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def environmentagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Environmentagent
    :rtype: Environmentagent
    """
    try:
        config = utils.load_config(config_path)
        print("load_config\n", config)       #xxxxxxxxxxx
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    hotel_name = config.get('hotel_name', "mintel")
    building_name = config.get("building_name", "mintel_1")
    room_no = int(config.get('room_no', 50))
    device_name = config.get('device_name', "ligh")
    api = config.get('api', "classAPI_broadlink_envsensor")
    mac_address = config.get('mac_address', "b4:43:0d:fb:f7:51")
    ip_address = config.get("ip_address", "192.168.1.34")
    topic_head = config.get('topic_head', "alto")
    device_monitor_time = int(config.get("device_monitor_time", 12))
    message_agent = config.get("message_agent", None)

    return Environmentagent(hotel_name, building_name, room_no, device_name, api
                            , mac_address, ip_address, topic_head, device_monitor_time
                            , message_agent, **kwargs)


class Environmentagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, hotel_name, building_name, room_no, device_name, api
                 , mac_address, ip_address, topic_head, device_monitor_time,
                 message_agent, **kwargs):
        super(Environmentagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.hotel_name = hotel_name
        self.building_name = building_name
        self.room_no = room_no
        self.device_name = device_name
        self.api = api
        self.mac_address = mac_address
        self.ip_address = ip_address
        self.topic_head = topic_head
        self.poll_cd = self.device_monitor_time = device_monitor_time
        self.message_agent = message_agent
        # alto/mintel/mintel1/50/fan/mac
        self.topic_sub = "{}/{}/{}/{}/{}/{}".format(self.topic_head, self.hotel_name,
                                                    self.building_name, self.room_no,
                                                    self.device_name, self.mac_address)

        self.topic_room = "{}/{}/{}/{}".format(self.topic_head, self.hotel_name,
                                               self.building_name, self.room_no)

        self.offline_count = 0
        self.new_dev_ip = None
        self.timeproofmacip = random.randint(600, 900)

        self.apiLib = importlib.import_module("DeviceAPI.classAPI." + self.api)
        self.device = self.apiLib.API(model='A1', type=self.device_name, api=self.api, agent_id='A1sensor',
                                      address=self.ip_address, macaddr=self.mac_address)
        self.sensor_dataget = ""

        self.default_config = {}
        self.default_config["hotel_name"] = self.hotel_name
        self.default_config["building_name"] = self.building_name
        self.default_config["room_no"] = self.room_no
        self.default_config["device_name"] = self.device_name
        self.default_config["api"] = self.api
        self.default_config["mac_address"] = self.mac_address
        self.default_config["ip_address"] = self.ip_address
        self.default_config["topic_head"] = self.topic_head
        self.default_config["device_monitor_time"] = self.device_monitor_time
        self.default_config["message_agent"] = self.message_agent
        print("after self.default_config\n", self.default_config)
        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        print("after cofig.set_default\n", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
        print("after config.subscribe\n", self.default_config)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        print("parameter that send to def configure\n", config_name, action, contents)
        config = self.default_config.copy()
        print("config in def configure\n", config)
        config.update(contents)
        print("config after .update(contents)\n", config)
        _log.debug("Configuring Agent")

        try:
            hotel_name = config['hotel_name']
            building_name = config["building_name"]
            room_no = int(config['room_no'])
            device_name = config['device_name']
            api = config['api']
            mac_address = config['mac_address']
            ip_address = config['ip_address']
            topic_head = config['topic_head']
            device_monitor_time = int(config['device_monitor_time'])
            message_agent = config["message_agent"]

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.hotel_name = hotel_name
        self.building_name = building_name
        self.room_no = room_no
        self.device_name = device_name
        self.api = api
        self.topic_head = topic_head
        self.message_agent = message_agent
        self.ip_address = ip_address
        self.mac_address = mac_address
        self.poll_cd = self.device_monitor_time = device_monitor_time

        # alto/mintel/mintel1/50/sensor_environment/mac
        self.topic_sub = "{}/{}/{}/{}/{}/{}".format(self.topic_head, self.hotel_name,
                                                    self.building_name, self.room_no,
                                                    self.device_name, self.mac_address)
        # alto/mintel/mintel1/50
        self.topic_room = "{}/{}/{}/{}".format(self.topic_head, self.hotel_name,
                                               self.building_name, self.room_no)

        _log.debug("topic for subscribe {}".format(self.topic_sub))
        print("self.topic_sub --> ".format(self.topic_sub))

        self.importDeviceAPI()

        self._create_subscriptions(self.topic_sub)

    def importDeviceAPI(self):
        self.apiLib = importlib.import_module("DeviceAPI.classAPI." + self.api)
        self.device = self.apiLib.API(model='A1', type='environment sensor', api=self.api, agent_id='A1sensor',
                                      address=self.ip_address, macaddr=self.mac_address)

    def _create_subscriptions(self, topic):
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self.envcmd)

    def envcmd(self, peer, sender, bus, topic, headers, message):
        _log.debug("Print from subscribe envcmd :{}, sender:{}, bus:{}, topic:{},headers:{} , message:{}"
                   .format(peer, sender, bus, topic, headers, message))
        _log.debug("{}-->{}".format(headers["request"], type(headers["request"])))

        if "configuration" in headers["request"]:  # message ={"configuration": {key:value, key2:value2 , keyn: valuen}}
            self.updateconfig(message["configuration"])

        if "setupenv" in headers["request"]:  # message = {"setupenv": {key:value, key2:value2 , keyn: valuen}}
            self.updateconfig(message["setupenv"])

        if "agentinfo" in headers["request"]:
            # Capabilites requested
            # self.message_agent
            pass

    def updateconfig(self, message):
        try:
            newconfig = self.vip.config.get("config")
            for configkey, configval in message["index_status"].items():
                newconfig[configkey] = configval
            self.vip.config.set("config", newconfig, trigger_callback=True)
        except Exception as e:
            print("Error: Something went wrong when updateconfig. Error was: {}".format(e))

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        # Example publish to pubsub
        # self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # Exmaple RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    @Core.schedule(periodic(1))
    def period_poll(self):
        # Todo self.timeofline
        '''
        time for raise error is about 10 sec --> so you can set self.device_monitor_time < 10 sec
        '''
        self.poll_cd -= 1

        if self.poll_cd <= 0 and (self.offline_count > int(20 / self.device_monitor_time)):
            self.poll_cd = self.device_monitor_time
            self.poll_cd -= (self.device_monitor_time / 3)
            self.checkip()

        if self.poll_cd <= 0:
            self.poll_cd = self.device_monitor_time
            self.checksensor()  # call method checksensor

    @Core.schedule(periodic(10))
    def proofmacip(self):
        if self.timeproofmacip < 0:                         # it's the time to proofmacip
            self.offline_count = 100                        # set offline count
            self.timeproofmacip = random.randint(600, 900)  # renew time delay for proofmacip
        else:
            self.timeproofmacip -= 10                       # decrease time delay

    def checkip(self):
        self.new_dev_ip = self.device.discoveryDevices(macdev=self.mac_address, timeout=5)
        print("self.new_dev_ip in agent = ", self.new_dev_ip)
        if self.new_dev_ip[self.mac_address] == "ip_not_found":
            _log.debug("Env discovery ip_not_found : {}".format(self.new_dev_ip))

        elif self.new_dev_ip[self.mac_address] == self.ip_address:
            _log.debug("Env discovery  Not change : {} ".format(self.new_dev_ip))
            self.offline_count = 0

        elif self.new_dev_ip[self.mac_address] != self.ip_address:
            _log.debug("Env discovery IP change : {} ".format(self.new_dev_ip))
            self.updateconfig({"index_status": {"ip_address": self.new_dev_ip[self.mac_address]}})
            self.offline_count = 0

    def checksensor(self):
        print("\ndebug in checksensor")
        self.sensor_dataget = self.device.getDeviceStatus()
        print(self.sensor_dataget)
        print("debug in checksensor after get sensor_dataget")
        if self.sensor_dataget == "timed out":
            self.offline_count += 1
            print(" Publish offline_count {} peer:{} Topic:{} header:{} message:{} "
                  .format(self.offline_count, 'pubsub', self.topic_room, self.core.identity, self.sensor_dataget))
            self.vip.pubsub.publish(peer='pubsub',
                                    topic=self.topic_room,
                                    message=self.sensor_dataget,
                                    headers={'requesterID': self.core.identity,
                                             "request": "status"})
            # import again for init device
            self.importDeviceAPI()

        else:
            self.offline_count = 0
            print(" Publish --> peer:{} Topic:{} header:{} message:{} "
                  .format('pubsub', self.topic_room, self.core.identity, self.sensor_dataget))
            self.vip.pubsub.publish(peer='pubsub',
                                    topic=self.topic_room,
                                    message=self.sensor_dataget,
                                    headers={'requesterID': self.core.identity,
                                             "request": "status"})

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
    utils.vip_main(environmentagent,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
