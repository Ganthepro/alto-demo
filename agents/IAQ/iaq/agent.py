"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic

# import time

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def iaq(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Iaq
    :rtype: Iaq
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    time = int(config.get('time', 5))
    topic = config.get('topic', "iaq/data")
    data = config.get('data', [])
    return Iaq(time, topic, data, **kwargs)


class Iaq(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, time=5, topic="iaq/data", data=[], **kwargs):
        super(Iaq, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.time = time
        self.topic = topic
        self.data = data
        self.default_config = {"time": time,
                               "topic": topic,
                               "data": data}

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
            time = int(config["time"])
            topic = str(config["topic"])
            data = list(config["data"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.time = time
        self.topic = topic
        self.data = data

        self._create_subscriptions(self.topic)
    
    def _read_csv(self, config_name):
        try:
            data: list[dict] = self.vip.config.get(config_name)
                
            _log.info(f"Successfully read {len(data)} rows from {config_name}")
            return config_name, data
            
        except Exception as e:
            _log.error(f"Error reading CSV file: {str(e)}")
            return None, None

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)
                                  

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
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
        # Example publish to pubsub
        self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")        
        for config_name in self.data:
            config, data = self._read_csv(config_name)
            self.core.schedule(periodic(self.time), self._boardcast, config, data[0])

    def _boardcast(self, config_name, data):
        # for data in data:
        payload = {
            "datetime": data["datetime"],
            "temperature": data["temperature"],
            "humidity": data["humidity"],
            "co2": data["co2"],
            "id": config_name
        }
        self.vip.pubsub.publish('pubsub', self.topic, message=payload)
        # _log.info(f"Broadcasting data: {payload}, to topic: {self.topic}")

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

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(iaq, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
