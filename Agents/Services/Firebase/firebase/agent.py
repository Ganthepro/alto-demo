"""
Firebase Agent

- This agent is used to publish data to Firebase Realtime Database
- The agent is configured to publish data to a specific Firebase object at a specific path

"""

__docformat__ = 'reStructuredText'

import logging
import sys

import yaml
from .alto_firebase import alto_firebase_object_factory
from volttron.platform.agent import utils
from volttron.platform.scheduling import periodic
from volttron.platform.vip.agent import Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def firebase(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Firebase
    :rtype: Firebase
    """
    config = utils.load_config(config_path)
    if not config:
        raise "Configuration for Firebase Agent not found."

    # Get the data from config
    agent_config = config['volttron_agents']['firebase']
    location = config["location"]

    firebase_config = agent_config['firebase_config']
    firebase_path = agent_config['firebase_path']
    firebase_object_type = agent_config['firebase_object_type']
    custom_config = agent_config['custom_config']

    return Firebase(firebase_config, firebase_path, firebase_object_type, custom_config, config, **kwargs)


class Firebase(Agent):
    """
    Firebase Volttron Agent for publishing data to Firebase

    Args:
        firebase_config (dict): Dictionary containing the Firebase configuration
        firebase_path (str): Path to the Firebase object
        firebase_object_type (str): Type of the Firebase object
        custom_config (dict): Dictionary containing the custom configuration for EACH TYPE OF firebase_object_type
        default_config (dict): Dictionary containing the default configuration in site YAML file

    """

    def __init__(self, firebase_config: dict, firebase_path: str, firebase_object_type: str, custom_config: dict,
                 default_config: dict, **kwargs):
        super(Firebase, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.firebase_config = firebase_config
        self.firebase_path = firebase_path

        self.firebase_object = alto_firebase_object_factory(firebase_object_type)(firebase_config, firebase_path,
                                                                                  custom_config)

        self.default_config = default_config.copy()

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

        try:
            agent_config = config['volttron_agents']['firebase']
            location = config["location"]

            firebase_config = agent_config['firebase_config']
            firebase_path = agent_config['firebase_path']
            firebase_object_type = agent_config['firebase_object_type']
            custom_config = agent_config['custom_config']
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.firebase_config = firebase_config
        self.firebase_path = firebase_path

        self.firebase_object = alto_firebase_object_factory(firebase_object_type)(firebase_config, firebase_path, custom_config)
        self._create_subscriptions(self.firebase_object.subscribed_topics)

        self.core.schedule(periodic(2), self._publish_to_firebase)

    def _create_subscriptions(self, topics):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for topic in topics:
            self.vip.pubsub.subscribe(
                peer='pubsub',
                prefix=topic,
                callback=self._handle_message
            )

    def _handle_message(self, peer, sender, bus, topic, headers, message):
        """
        Callback method for handling incoming messages
        """
        self.firebase_object.update_data(topic, message)

    def _publish_to_firebase(self):
        """
        Publishes data to Firebase
        """
        self.firebase_object.update()


def main():
    """Main method called to start the agent."""
    utils.vip_main(firebase,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
