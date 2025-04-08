"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import copy
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.scheduling import cron, periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def devicedataschema(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Devicedataschema
    :rtype: Devicedataschema
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    kwargs["agent_name"] = config.get("agent_name", "device_data_schema")
    kwargs["is_command_only"] = config.get("is_command_only", False)
    kwargs["event_schemas"] = config.get("event_schemas", ["sensor", "hvac"])
    kwargs["target_agent_ids"] = config.get("target_agent_ids", ["modbus", "bac0hvac"])
    kwargs["command_able_devices"] = config.get("command_able_devices", {})
    kwargs["async_apis"] = config.get("async_apis", {})
    kwargs["async_command_apis"] = config.get("async_command_apis", {})

    return Devicedataschema(**kwargs)


class Devicedataschema(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super(Devicedataschema, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)

        self._loattr = set(["agent_name"])  # This will keep the list of attributes in the config
        for k, v in kwargs.items():
            if k not in pskiplist:
                setattr(self, k, v)
                self._loattr.add(k)
        if self.agent_name == "":
            self.agent_name = self.core.identity

        self._async_apis = {}
        self._async_command_apis = {}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.current_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.
        Is called every time the configuration in the store changes.
        """

        _log.debug(f"Configuring Agent ({action}) {config_name} {contents}")
        if config_name == "config":
            for k, v in contents.items():
                self._loattr.add(k)
                setattr(self, k, v)
        else:
            f = getattr(self, "configure_" + config_name, None)
            if f:
                f(action, contents)
            else:
                _log.error(f"Do not know how to handle config {config_name}")

        self._create_subscriptions()

    @property
    def current_config(self):
        """
        Returns the current configuration.
        """

        r = {}
        for x in self._loattr:
            try:
                r[x] = getattr(self, x)
            except Exception as e:
                _log.debug(f"This should not happen. No attribute for {x}")
        return r

    def save_config(self):
        """
        Save the current configuration
        """

        _log.debug(f"New config updated with {self.current_config}")
        try:
            self.vip.config.set("config", self.current_config)
        except Exception as e:
            _log.debug(f"Error: Something went wrong with setting config store Error was: {e}")

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for t in self.event_schemas:
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=t,
                                    callback=self._handle_publish)
        
        self.core.schedule(periodic(60), self._period_signal)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """

        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "event":
                _log.debug(f"Devicedataschema _handle_publish topic {topic}")
                if not self.is_command_only:
                    if agent_id in self.target_agent_ids:
                        if agent_id not in self._async_apis:
                            self._async_apis[agent_id] = {}
                        if device_id not in self._async_apis[agent_id]:
                            self._async_apis[agent_id][device_id] = {}
                        # _log.debug(f"Devicedataschema _handle_publish _async_apis {self._async_apis}")
                        if "subdevice_idx" in message:
                            if message["subdevice_idx"] not in self._async_apis[agent_id][device_id]:
                                self._async_apis[agent_id][device_id][message["subdevice_idx"]] = {}
                        if "type" in message:
                            if message["type"] not in self._async_apis[agent_id][device_id][message["subdevice_idx"]]:
                                self._async_apis[agent_id][device_id][message["subdevice_idx"]][message["type"]] = {}
                        # _log.debug(f"Devicedataschema _handle_publish _async_apis {self._async_apis}")
                        payload = {}
                        for k, v in message.items():
                            payload[k] = str(type(v))
                        self._async_apis[agent_id][device_id][message["subdevice_idx"]][message["type"]] = {
                            "topic": topic,
                            "headers": headers,
                            "payload": payload
                        }
                aids = []
                for eschema, v in self.command_able_devices.items():
                    for aid in v.keys():
                        aids.append(aid)
                if agent_id in aids:
                    if agent_id not in self._async_command_apis:
                        self._async_command_apis[agent_id] = {}
                    if device_id not in self._async_command_apis[agent_id]:
                        self._async_command_apis[agent_id][device_id] = {}
                    # _log.debug(f"Devicedataschema _handle_publish _async_command_apis {self._async_command_apis}")
                    if "subdevice_idx" in message:
                        if message["subdevice_idx"] not in self._async_command_apis[agent_id][device_id]:
                            self._async_command_apis[agent_id][device_id][message["subdevice_idx"]] = {}
                    if "type" in message:
                        if message["type"] not in self._async_command_apis[agent_id][device_id][message["subdevice_idx"]]:
                            self._async_command_apis[agent_id][device_id][message["subdevice_idx"]][message["type"]] = {}
                    # _log.debug(f"Devicedataschema _handle_publish _async_command_apis {self._async_command_apis}")
                    payload = {}
                    for k, v in message.items():
                        payload[k] = str(type(v))
                    headers = {
                        'requesterID': "please_replace_this_with_your_agent_identity",
                        "message_type": "command",
                    }
                    topic = topic.replace("/event", "/command")
                    self._async_command_apis[agent_id][device_id][message["subdevice_idx"]][message["type"]] = {
                        "topic": topic,
                        "headers": headers,
                        "payload": payload
                    }
        except Exception as e:
            _log.error(f"Devicedataschema _handle_publish {e}")
    
    def _period_signal(self):
        _log.debug(f"Devicedataschema _period_signal _async_apis {self._async_apis}")
        self.async_apis = copy.deepcopy(self._async_apis)
        _log.debug(f"Devicedataschema _period_signal _async_command_apis {self._async_command_apis}")
        self.async_command_apis = copy.deepcopy(self._async_command_apis)
        self.save_config()

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

        # Example RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(devicedataschema, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
