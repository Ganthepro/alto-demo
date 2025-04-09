"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import requests
import pendulum
import time
import json

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def linenotify(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Linenotify
    :rtype: Linenotify
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    line_token = config.get('line_token', '')
    sampling_rate = config.get('sampling_rate', 0)
    topic = config.get('topic', )


    return Linenotify(line_token, sampling_rate, topic, **kwargs)


class Linenotify(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, line_token, sampling_rate, topic, **kwargs):
        super(Linenotify, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.line_token = line_token
        self.sampling_rate = sampling_rate
        self.topic = topic

        self.default_config = {"line_token": line_token,
                               "sampling_rate": sampling_rate,
                               "topic": topic}

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
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        try:
            self.line_token = config["line_token"]
            self.sampling_rate = config["sampling_rate"]
            self.topic = config["topic"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        
        self._create_subscriptions(self.topic)
        dt = pendulum.now(tz="Asia/Bangkok")
        self.send_line_notify(f"Start Line notify Agent at {dt.format('HH:mm DD-MM-YYYY')}")

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)
        
        try:
            schema, agent, dev_id, mtype = topic.split("/")
            if schema == "line_notify" and mtype == "command":
                self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=topic,
                                    callback=self._handle_publish)
                _log.debug(f"Subscribe Topic: {topic}")
        except Exception as e:
            _log.error(f"Subscribe Error")

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        if isinstance(message, str):
            message = json.loads(message)
        msg = message.get('message', None)
        self.send_line_notify(msg)

    def send_line_notify(self, message: str) -> None:
        _log.debug(f"send_line_notify recieved message: {message}")
        url = "https://notify-api.line.me/api/notify"
        header = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self.line_token}"
            }
        body = {"message": message}
        try:
            response = requests.post(url, headers=header, data=body)
            if response.status_code == 200:
                _log.debug(f"Send message: {message}")
            else:
                _log.debug(f"Not success, code: {response.status_code}, response: {response.json()}")
        except Exception as e:
            _log.error(f"send_line_notify Exception: {e}")
    

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        dt = pendulum.now(tz='Asia/Bangkok')
        self.send_line_notify(f"Stoping Line notify Agent at {dt.format('HH:mm DD-MM-YYYY')}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(linenotify, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
