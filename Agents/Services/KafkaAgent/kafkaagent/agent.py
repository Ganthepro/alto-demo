"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from kafka import KafkaProducer

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


class KafkaWrapper:
    def __init__(self, bootstrap_servers='localhost:9094', client_id='kafka-agent', key_serializer=None, value_serializer=None, batch_size=100, retries=5):
        _log.info("Connecting to Kafka")
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            key_serializer=key_serializer,
            value_serializer=value_serializer,
            batch_size=batch_size,  # Set batch size
            retries=retries  # Set retries
        )

    def send_message(self, topic, value=None, key=None, headers=None, partition=None, timestamp_ms=None):
        
        if value is not None and isinstance(value, str):
            value = value.encode('utf-8')

        future = self.producer.send(
            topic,
            value=value,
            key=key,
            headers=headers,
            partition=partition,
            timestamp_ms=timestamp_ms
        )
        # Add callbacks
        future.add_callback(self.on_send_success).add_errback(self.on_send_error)

    def on_send_success(self, record_metadata):
        _log.info("Message produced to Kafka Successfully. Topic: %s, Partition: %s, Offset: %s", record_metadata.topic, record_metadata.partition, record_metadata.offset)

    def on_send_error(self, excp):
        _log.error('I am an errback', exc_info=excp)

    def flush(self, timeout=None):
        self.producer.flush(timeout)
        _log.info("Flushed the producer")

    def close(self, timeout=None):
        self.producer.close(timeout)
        _log.info("Closed the producer")


def kafkaagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: KafkaAgent
    :rtype: KafkaAgent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topics = config.get("topics", [])
    kafka_settings = config.get("kafka", {})

    return KafkaAgent(topics, kafka_settings, **kwargs)


class KafkaAgent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, topics=["sensor/raw_niagara"], kafka_settings={}, **kwargs):
        super(KafkaAgent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.topics = topics
        self.kafka_producer = None

        self.default_config = {"topics": topics, "kafka": kafka_settings}

        self.vip.config.set_default("config", self.default_config)
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
            topics = config["topics"]
            kafka_config = config["kafka"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.topics = topics
        self._create_subscriptions()
        # Create Kafka producer
        self.kafka_producer = KafkaWrapper(**kafka_config)
        if not self.kafka_producer:
            return

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)
        for prefix in self.topics:
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=prefix,
                                    callback=self._handle_publish)
            _log.info(f"Subscribed to prefix: {prefix}")

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        topic = "Niagara" # TODO: Fix this
        _log.info(f"Received message from topic: {topic}, payload: {str(message)}")
        self.kafka_producer.send_message(topic=topic, value=json.dumps(message))

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.info("Disconnecting from Kafka")
        # Disconnect from Kafka
        if self.kafka_producer is not None:
            self.kafka_producer.close()


def main():
    """Main method called to start the agent."""
    utils.vip_main(kafkaagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
