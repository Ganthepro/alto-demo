"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron

import json
import yaml
from pymongo import MongoClient

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def mongodb(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Mongodb
    :rtype: Mongodb
    """
    config = utils.load_config(config_path)
    if not config:
        raise "Configuration for MongoDB Agent not found."

    # Get the data from config, otherwise use defaults (2nd argument)
    agent_config = config['volttron_agents']['mongodb']
    location = config["location"]

    mongodb_host = agent_config.get("host", "localhost")
    mongodb_port = agent_config.get("port", 27017)
    mongodb_db_name = agent_config.get("db_name", "realtime_data")
    mongodb_config = agent_config.get("config", {})

    return Mongodb(location, mongodb_host, mongodb_port, mongodb_db_name, mongodb_config, **kwargs)


class Mongodb(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, location, mongodb_host, mongodb_port, mongodb_db_name, mongodb_config, **kwargs):
        super(Mongodb, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.location = location
        self.mongodb_host = mongodb_host
        self.mongodb_port = mongodb_port
        self.mongodb_db_name = mongodb_db_name
        self.mongodb_config = mongodb_config

        self.default_config = {"location": self.location,
                               "mongodb_host": self.mongodb_host,
                               "mongodb_port": self.mongodb_port,
                               "mongodb_db_name": self.mongodb_db_name,
                               "mongodb_config": self.mongodb_config}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """

        if isinstance(contents, dict):
            config = contents
        else:
            try:
                config = yaml.safe_load(contents)
            except yaml.YAMLError as e:
                _log.error("Error parsing YAML:", e)
                return None

        _log.debug("Configuring Agent")

        try:
            agent_config = config['volttron_agents']['mongodb']
            location = config["location"]
            mongodb_host = agent_config["host"]
            mongodb_port = agent_config["port"]
            mongodb_db_name = agent_config["db_name"]
            mongodb_config = agent_config["config"]
            mongodb_client = MongoClient(mongodb_host, mongodb_port)
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.location = location
        self.mongodb_host = mongodb_host
        self.mongodb_port = mongodb_port
        self.mongodb_db_name = mongodb_db_name
        self.mongodb_config = mongodb_config
        self.mongodb_client = mongodb_client

        self._create_subscriptions()
        
        # Reset today_data everyday at midnight
        self.core.schedule(cron("0 0 * * *"), self._reset_today_data)

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="datalogger",
                                  callback=self._handle_publish_datalogger)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="bacnet",
                                  callback=self._handle_publish_suggestion)
        
    def _reset_today_data(self):
        """
        Reset the today_data collection
        """
        db = self.mongodb_client[self.mongodb_db_name]
        collection = db[self.location]
        collection.update_one({}, {"$set": {"today_data": {}}})



    def _handle_publish_datalogger(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        _log.debug(f"RECEIVE DATALOGGER BACNET FROM TOPIC : {topic}, MESSAGE: {message}")

        # Step 1: If topic is not in the format of /bacnet/{agent_name}/{device_id}/command
        if len(topic.split("/")) != 4:
            _log.error(f"Invalid topic format: {topic}")
            return

        # Step 2: Split the topic to get the "device_id" and "message_type"
        schema, agent_name, device_id, message_type = topic.split("/")

        if isinstance(message, str):
            message = json.loads(message)

        if message_type == "event":

            db = self.mongodb_client[self.mongodb_db_name]
            collection = db[self.location]

            update_payload = {
                "$set": {
                    f"raw_data.{device_id}": message
                }
            }
            collection.update_one({}, update_payload, upsert=True)

            if device_id in self.mongodb_config['today_data']:
                for device_id, dp_list in self.mongodb_config['today_data'].items():
                    new_message = {k: v for k, v in message.items() if k in dp_list + ['timestamp']}

                push_payload = {
                    "$push": {
                        f"today_data.{device_id}": new_message
                    }
                }

                collection.update_one({}, push_payload, upsert=True)

    def _handle_publish_suggestion(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        _log.info(f"RECEIVE SUGGESTION BACNET FROM TOPIC : {topic}, MESSAGE: {message}")

        # Step 1: If topic is not in the format of /bacnet/{agent_name}/{device_id}/command
        if len(topic.split("/")) != 4:
            _log.error(f"Invalid topic format: {topic}")
            return

        # Step 2: Split the topic to get the "device_id" and "message_type"
        schema, agent_name, device_id, message_type = topic.split("/")

        if isinstance(message, str):
            message = json.loads(message)

        if agent_name == "optimization" and message_type == "command":

            # MongDB client setup
            db = self.mongodb_client[self.mongodb_db_name]
            collection = db[self.location]
            update_payload = {
                "$set": {
                    "alto_cero_mode": {"mode": message['mode']},
                    f"copilot_suggestion": {key: value for key, value in message.items() if key not in ['mode']} # Get every data except mode
                }
            }

            collection.update_one({}, update_payload, upsert=True)


def main():
    """Main method called to start the agent."""
    utils.vip_main(mongodb,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
