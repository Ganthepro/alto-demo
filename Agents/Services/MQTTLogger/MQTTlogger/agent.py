"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

from gevent import monkey
monkey.patch_all()

import logging
import sys
import json
import time

import pendulum
import paho.mqtt.client as mqtt

from altolib import AltoMQTTAgent

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


def MQTTlogger(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Mqttlogger
    :rtype: Mqttlogger
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get('topic', "")
    for key, value in zip(
        ['agent_name','mqtt_server', 'mqtt_port', 'mqtt_user', 'mqtt_password', 'mqtt_topics'],
        ['mqtt_logger', 'localhost', '1883', '', '', {}]
    ):
        kwargs[key] = config.get(key, value)

    return Mqttlogger(topic, **kwargs)


class Mqttlogger(AltoMQTTAgent):
    """
    Document agent constructor here.
    """

    def __init__(self, topic: str, **kwargs):
        super(Mqttlogger, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.mqtt_client = None
        for attr, attr_type in zip(
            [
                "mqtt_topics",
                "mqtt_server",
                "mqtt_port",
                "mqtt_user",
                "mqtt_password",
                "mqtt_prefix"
            ],
            [
                dict, str, int, str, str, str
            ]
        ):
            self._loattr.add(attr)
            self._attrtypes[attr] = attr_type
            if getattr(self, attr, None) is None:
                if attr == "mqtt_server":
                    setattr(self, attr, "localhost")
                elif attr == "mqtt_port":
                    setattr(self, attr, 1883)
                else:
                    setattr(self, attr, "")
            setattr(self, attr, attr_type())
        
        if self.mqtt_prefix:
            if self.mqtt_prefix[-1] != "/":
                self.mqtt_prefix += "/"
                
        self.publish_topics: list = []
        self.subscribe_topics: list = []
    
    @Core.receiver("onstart")
    def mqttstart(self, sender: str, **kwargs):
        """
        Start the MQTT client only if we actually have data to do something
        
        """
        _log.info("Connecting to MQTT")
        try:
            if self.mqtt_topics and self.mqtt_server:
                self.mqtt_client = mqtt.Client(userdata=self)
                if self.mqtt_user and self.mqtt_password:
                    self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
                self.mqtt_client.on_connect = self.on_mqtt_connect
                self.mqtt_client.on_message = self.process_mqtt_message
                self.mqtt_client.connect_async(self.mqtt_server, self.mqtt_port)
                self.mqtt_client.loop_start()
                _log.info(f"Connected to MQTT: {self.mqtt_server}:{self.mqtt_port}")
            else:
                _log.warning(f"MQTT server or topic or server not configured, not connecting to MQTT")
        except Exception as e:
            _log.exception(f"Error connecting to MQTT: {e}")
    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """
        On connect callback for MQTT client
        
        """
        _log.info(f"Connected to MQTT with connection: {rc}")
        self.set_heartbeat_status("READY")
        self.publish_topics = self.mqtt_topics.get('publish', [])
        self.subscribe_topics = self.mqtt_topics.get('subscribe', {})
        if self.subscribe_topics:
            for topic in self.subscribe_topics:
                client.subscribe(topic)
                _log.info(f"Subscribed to MQTT topic: {topic}")
    
    def process_mqtt_message(self, client, userdata, msg):
        """
        process MQTT message
        
        """
        
        topic = msg.topic
        payload = msg.payload
        _log.debug(f"Got MQTT message topic: {topic}, payload: {payload}")
        
        try:
            if isinstance(payload, bytes):
                payload = json.loads(payload)
            
            if "niagara" in topic:
                # niagara topic: sensor/niagara/<system_name>/event
                message: dict = {}
                volttron_pub_topic = topic.replace("niagara", self.agent_name)
                timestamp_now = time.time()
                datetime_now = pendulum.from_timestamp(timestamp_now).to_atom_string()
                if "currentTime" in payload:
                    message["timestamp"] = pendulum.parse(payload["currentTime"]).to_atom_string()
                else:
                    message["timestamp"] = datetime_now
                
                if "unixTime" in payload:
                    message["unix_timestamp"] = int(payload["unixTime"]/1000)
                else:
                    message["unix_timestamp"] = int(timestamp_now)
                
                for key, values in payload.items():
                    device_message = message.copy()
                    # {"currentTime": xxx, "unixTime": xxx, "device_id1": {"datapoint": "value}, "device_id2": {"datapoint": "value"}
                    if key not in ["currentTime", "unixTime"]:
                        device_id = key
                        device_message['device_id'] = device_id
                        for datapoint, value in values.items():
                            device_message[datapoint] = value
                        _log.debug(f"Forming message: {device_message}")
                        volttron_pub_topic = f"sensor/{self.agent_name}/{device_id}/event"
                        self.publish(volttron_pub_topic, device_message, "event")
        except Exception as e:
            _log.exception(f"Error: {e}")
            
    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        
        super().configure(config_name, action, contents)

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                prefix="datalogger",
                                callback=self._handle_publish)
        
        self.vip.pubsub.subscribe(peer='pubsub',
                                prefix="calculated",
                                callback=self._handle_publish)
        
        self.vip.pubsub.subscribe(peer='pubsub',
                                prefix="mqtt",
                                callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        
        _log.debug(f"MQTTLogger _handle_publish topic: {topic}, message: {message}")
        
        if sender != self.agent_name:
            split_topic = topic.split("/")
            
            if split_topic[0] == "calculated":
                pub_topic = topic.replace(f"calculated/{split_topic[1]}", "pmv/niagara")
                pub_topic = pub_topic.replace(f"event", "command")
                self._publish_mqtt(pub_topic, message)
            
            elif split_topic[0] == "mqtt":
                if split_topic[1] == "rl_correction":
                    pub_topic = topic.replace(f"mqtt/rl_correction", "feedback/niagara")
                    self._publish_mqtt(pub_topic, message)
                elif split_topic[1] == "fcu_control":
                    pub_topic = topic.replace(f"mqtt/fcu_control", "fcu_control/niagara")
                    self._publish_mqtt(pub_topic, message)

    def _publish_mqtt(self, topic: str, message: dict):
        _log.debug(f"MQTTLogger _publish_mqtt topic: {topic}, message: {message}")
        if isinstance(message, dict):
            message = json.dumps(message)
        self.mqtt_client.publish(topic, message)
    
    def publish(self, topic, value, mtype) -> None:
        """
        Publish message into volttron bus
        
        """
        
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            message=value,
            headers={
                "requesterID": self.core.identity,
                "message_type": mtype,
                "Timestamp": pendulum.now('UTC').to_atom_string()
            }
        )
        _log.debug(f"Published to volttron bus topic: {topic}, message: {value}")
        

    @Core.receiver("onstop")
    def mqttstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.info("Disconnecting from MQTT")
        if self.mqtt_client:
            self.mqtt_client.disconnect()
            self.mqtt_client.loop_stop()
            self.mqtt_client = None


def main():
    """Main method called to start the agent."""
    utils.vip_main(MQTTlogger, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
