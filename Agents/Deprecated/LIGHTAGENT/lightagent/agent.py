"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
import paho.mqtt.client as mqtt
import json

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

# MQTT bits
def on_mqtt_connect(client, tasmota, flags, rc):
    _log.debug("Connected with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    for topic in tasmota.mqtt_topics:
        client.subscribe(topic)
        _log.debug("MQTT: Subscribe to '{}'".format(topic))


# The callback for when a PUBLISH message is received from the server.
def on_mqtt_message(client, tasmota, msg):
    _log.debug("Got MQTT message {}".format(msg.topic + " " + str(msg.payload)))
    for topic in tasmota.mqtt_topics:
        usetopic = topic.replace("#", "")
        # _log.debug("Checking MQTT {} {} vs {} {}".format(msg.topic.__class__,msg.topic,usetopic,msg.topic.startswith(usetopic)))
        if msg.topic.startswith(usetopic):
            try:
                device, function = [x for x in msg.topic.lower().replace(usetopic, "").split("/") if x]
                if device.startswith("switch") or device.startswith("fan"):
                    if function.startswith("power"):
                        gang = function.replace("power", "")
                        if gang:
                            gang = int(gang) - 1
                        else:
                            gang = 0
                        function = "power"
                        status = {"power": {"gang": gang, "state": msg.payload.decode().lower()}}
                        tasmota.knowndevs.add(device)
                        vtopic = tasmota.topic + "/device/" + device + "/state"
                        vtopic = vtopic.replace("//", "/")
                        _log.debug("Publishing {} {}".format(vtopic, json.dumps(status)))
                        tasmota.vip.pubsub.publish(peer='pubsub',
                                                   topic=vtopic,
                                                   message=json.dumps(status),  # [data, {'source': 'publisher3'}],
                                                   headers={'requesterID': tasmota.core.identity})
                        break
            except Exception as e:
                _log.debug("\n\nOpps: {}".format(e))


def lightagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Lightagent
    :rtype: Lightagent
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    hotel_name = config.get('hotel_name', "mintel")
    building_name = config.get("building_name", "mintel_1")
    room_no = int(config.get('room_no', 50))
    device_name = config.get('device_name', "ligh")
    mac_address = config.get('mac_address', {"light1":"600194D8DF25", "light2": "600194D8DF25"})
    topic_head = config.get('topic_head', "alto")
    mqtt_topics = config.get('mqtt_topics', [])
    mqtt_server = config.get('mqtt_server', 'localhost')
    mqtt_port = int(config.get('mqtt_port', 1883))
    mqtt_user = config.get("mqtt_user", None)
    mqtt_password = config.get("mqtt_password", None)
    message_agent = config.get("message_agent", None)

    return Lightagent(hotel_name, building_name, room_no, device_name, mac_address, topic_head,
                       mqtt_topics, mqtt_server, mqtt_port, mqtt_user, mqtt_password, message_agent, **kwargs)


class Lightagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self,hotel_name, building_name, room_no, device_name, mac_address, topic_head,
                       mqtt_topics, mqtt_server, mqtt_port, mqtt_user, mqtt_password, message_agent, **kwargs):
        super(Lightagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.hotel_name = hotel_name
        self.building_name = building_name
        self.room_no = room_no
        self.device_name = device_name
        self.mac_address = mac_address
        self.topic_head = topic_head
        self.mqtt_topics = mqtt_topics
        self.mqtt_server = mqtt_server
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.message_agent = message_agent

        self.mqtt = None
        self.knowndevs = set()
        # alto/mintel/building1/50/light/mac
        self.topic_sub = "{}/{}/{}/{}/{}/{}".format(self.topic_head, self.hotel_name,
                                                     self.building_name, self.room_no,
                                                     self.device_name, self.mac_address)
        _log.debug("topic for subscribe {}".format(self.topic_sub))

        self.default_config = {}
        self.default_config["hotel_name"] = self.hotel_name
        self.default_config["building_name"] = self.building_name
        self.default_config["room_no"] = self.room_no
        self.default_config["device_name"] = self.device_name
        self.default_config["mac_address"] = self.mac_address
        self.default_config["topic_head"] = self.topic_head
        self.default_config["mqtt_topics"] = self.mqtt_topics
        self.default_config["mqtt_server"] = self.mqtt_server
        self.default_config["mqtt_port"] = self.mqtt_port
        self.default_config["mqtt_user"] = self.mqtt_user
        self.default_config["mqtt_password"] = self.mqtt_password
        self.default_config["message_agent"] = self.message_agent

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)
        _log.debug("Configuring Agent")
        try:
            hotel_name = config['hotel_name']
            building_name = config["building_name"]
            room_no = config['room_no']
            device_name = config['device_name']
            mac_address = config['mac_address']
            topic_head = config['topic_head']
            mqtt_topics = config['mqtt_topics']
            mqtt_server = config['mqtt_server']
            mqtt_port = int(config['mqtt_port'])
            mqtt_user = config["mqtt_user"]
            mqtt_password = config["mqtt_password"]
            message_agent = config["message_agent"]

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.hotel_name = hotel_name
        self.building_name = building_name
        self.room_no = room_no
        self.device_name = device_name
        self.mac_address = mac_address
        self.topic_head = topic_head
        self.message_agent = message_agent
        # alto/mintel/mintel1/50/light/600194D8DF25
        self.topic_sub = "{}/{}/{}/{}/{}/{}".format(self.topic_head, self.hotel_name,
                                                    self.building_name, self.room_no,
                                                    self.device_name, self.mac_address)

        _log.debug("topic for subscribe {}".format(self.topic_sub))

        hard_restart = False
        if self.mqtt_user != mqtt_user:
            self.mqtt_user = mqtt_user
            hard_restart = True

        if self.mqtt_password != mqtt_password:
            self.mqtt_password = mqtt_password
            hard_restart = True

        if self.mqtt_topics != mqtt_topics:
            self.mqtt_topics = mqtt_topics
            hard_restart = True

        if self.mqtt_server != mqtt_server:
            self.mqtt_server = mqtt_server
            hard_restart = True

        if self.mqtt_port != mqtt_port:
            self.mqtt_port = mqtt_port
            hard_restart = True

        if self.mqtt and hard_restart:
            # Do restart
            self.mqtt.disconnect()
            self.mqtt.loop_stop()
            self.mqtt = None

        if self.mqtt is None:
            self.mqtt = mqtt.Client(userdata=self)
            if self.mqtt_user:
                self.mqtt.username_pw_set(self.mqtt_user, self.mqtt_password)
            self.mqtt.on_connect = on_mqtt_connect
            self.mqtt.on_message = on_mqtt_message
            self.mqtt.connect_async(self.mqtt_server, port=self.mqtt_port)  # Should we bind?
            self.mqtt.loop_start()

        self._create_subscriptions(self.topic_sub)

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=self.topic_sub,
                                  callback=self.lightcmd)

    def lightcmd(self, peer, sender, bus, topic, headers, message):
        _log.debug("Print from subscribe lightcmd :{}, sender:{}, bus:{}, topic:{},headers:{} , message:{}".format(peer, sender, bus, topic, headers, message))
        _log.debug("{}-->{}".format(headers["request"], type(headers["request"])))

        if "controllight" in headers["request"]:                 #controllight message = {"index_status":{1:'on',2:'off',3:'on'}}
            for index, val in message["controllight"].items():
                dev = self.device_name + "_" + self.mac_address[6:].upper()
                mqtttopic = "cmnd/tasmota/{}/Power{}".format(dev, index)
                _log.debug("{} --> {}".format(mqtttopic, val))
                self.mqtt.publish(mqtttopic, payload=val)

        if "statuslight" in headers["request"]:                #message = {"index_status":{1:,2:',3:}} not use value just key
            for index in message["statuslight"].keys():
                dev = self.device_name + "_" + self.mac_address[6:].upper()
                mqtttopic = "cmnd/tasmota/{}/Power{}".format(dev, index)
                self.mqtt.publish(mqtttopic, payload=None)

        if "configuration" in headers["request"]:             #message = {key:value, key2:value2 , keyn: valuen}
            newconfig = self.vip.config.get("config")
            for configkey, configval in message["configuration"].items():
                newconfig["configkey"] = configval
            self.vip.config.set("config", newconfig, trigger_callback=True)

        if "agentinfo" in headers["request"]:
            # Capabilites requested
            # self.message_agent
            pass

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
    utils.vip_main(lightagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
