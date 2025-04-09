""" Platform Agent
Monitor the heartbeat of the agents along with the status of the functions and devices.
These status information will be uploaded to Database through `observe/` topic
If the agent is not sending the heartbeat for a certain period of time, the agent will be restarted.
Alert message will be published to the message bus when the agent is restarted or the function/device is in unhealthy condition.

To start the agent, run the following commands:
```
vctl remove --tag platform_agent
python ~/volttron/scripts/install-agent.py -s ~/alto_os/Agents/Platforms/PlatformAgent -t platform_agent -i platform_agent
# install with config: python ~/volttron/scripts/install-agent.py -s ~/alto_os/Agents/Platforms/PlatformAgent -t platform_agent -i platform_agent --agent-config ~/site_configs/cero_staging.yaml
vctl config store platform_agent config ~/site_configs/cero_staging.yaml --raw
vctl enable --tag platform_agent
vctl start --tag platform_agent
```

Example agent config in `~/site_configs/cero_staging.yaml`
platform_agent:
    agent_ids:
      - cratedb
      - bacnet
    agent_heartbeat_topic: "heartbeat/"
    custom_heartbeat_topic: "altoheartbeat/"
    topic_to_crate: "observe_data"
    status_checking_frequency: 30
    agent_offline_duration: 180
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
import yaml
import pendulum

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic, cron
from .agent_control import AgentControl


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def platformagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: PlatformAgent
    :rtype: PlatformAgent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    # Get the data from config, otherwise use defaults (2nd argument)
    agent_config = config.get("volttron_agents", dict()).get('platform_agent', dict())
    location = config.get("location", "default_location")
    
    agent_ids = agent_config.get("agent_ids", list())
    agent_heartbeat_topic = agent_config.get("agent_heartbeat_topic", "heartbeat/")
    custom_heartbeat_topic = agent_config.get("custom_heartbeat_topic", "altoheartbeat/")
    topic_to_crate = agent_config.get("topic_to_crate", "observe_data")
    status_checking_frequency = int(agent_config.get("status_checking_frequency", 30))
    agent_offline_duration = int(agent_config.get("agent_offline_duration", 120))

    return PlatformAgent(location, agent_ids, agent_heartbeat_topic, custom_heartbeat_topic, topic_to_crate, status_checking_frequency, agent_offline_duration, **kwargs)


class PlatformAgent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, location: str, agent_ids: list(), agent_heartbeat_topic: str, custom_heartbeat_topic: str, topic_to_crate: str, status_checking_frequency=30, agent_offline_duration=120, **kwargs):
        super(PlatformAgent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.location = location
        self.agent_ids = agent_ids
        self.agent_heartbeat_topic = agent_heartbeat_topic
        self.custom_heartbeat_topic = custom_heartbeat_topic
        self.topic_to_crate = topic_to_crate
        self.status_checking_frequency = status_checking_frequency
        self.agent_offline_duration = agent_offline_duration

        self.default_config = {
            "location": self.location,
            "agent_ids": self.agent_ids,
            "agent_heartbeat_topic": self.agent_heartbeat_topic,
            "custom_heartbeat_topic": self.custom_heartbeat_topic,
            "topic_to_crate": self.topic_to_crate,
            "status_checking_frequency": self.status_checking_frequency,
            "agent_offline_duration": self.agent_offline_duration
        }
        
        self.agent_control = AgentControl()
        
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
                _log.error(f"{self.core.identity}: Error parsing YAML: ", e)
                return None

        _log.debug("Configuring Agent")

        try:
            agent_config = config.get("volttron_agents", dict()).get('platform_agent', dict())
            location = config.get("location", "default_location")
            agent_ids = agent_config.get("agent_ids", list())
            agent_heartbeat_topic = agent_config.get("agent_heartbeat_topic", "heartbeat/")
            custom_heartbeat_topic = agent_config.get("custom_heartbeat_topic", "altoheartbeat/")
            topic_to_crate = agent_config.get("topic_to_crate", "observe_data")
            status_checking_frequency = int(agent_config.get("status_checking_frequency", 30))
            agent_offline_duration = int(agent_config.get("agent_offline_duration", 120))
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.location = location
        self.agent_ids = agent_ids
        self.agent_heartbeat_topic = agent_heartbeat_topic
        self.custom_heartbeat_topic = custom_heartbeat_topic
        self.topic_to_crate = topic_to_crate
        self.status_checking_frequency = status_checking_frequency
        self.agent_offline_duration = agent_offline_duration

        # state of the agent to store the heartbeat information for comparing with the latest heartbeat
        self.agent_states = dict()
        for agent_id in self.agent_ids:
            _initial_payload = {
                "setup_timestamp": pendulum.now().timestamp(),  # unix_timestamp (float)
                "latest_heartbeat": None,  # option: [None, unix_timestamp (float)]
            }
            self.agent_states.update({str(agent_id): _initial_payload})

        # set up periodic checking on heartbeat status
        self.core.schedule(periodic(self.status_checking_frequency), self.check_heartbeat_status)

        self._create_subscriptions()

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=self.agent_heartbeat_topic,
                                  callback=self._handle_heartbeat)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=self.custom_heartbeat_topic,
                                  callback=self._handle_custom_heartbeat)

    def _handle_heartbeat(self, peer, sender, bus, topic, headers, message: str):
        """Handle default heartbeat message from defined Volttron agents
        `topic` = "heartbeat/{agent_id}"
        `message` = STRING options: ["GOOD", "BAD", "DEAD"]
        """
        # validate agent_id
        _log.debug(f"{self.core.identity}: topic-{topic}, message-{message}")
        agent_id = topic.split('/')[1]
        if agent_id not in self.agent_ids:
            return
        
        # validate message: format=STRING ["GOOD", "BAD", "DEAD"]
        if not isinstance(message, str):
            return

        # update agent state
        _agent_state = self.agent_states.get(str(agent_id), None)
        if _agent_state is None:
            return
        _agent_state["latest_heartbeat"] = pendulum.now().timestamp()
        self.agent_states[str(agent_id)] = _agent_state
        
        # construct payload to upload database
        timestamp = int(pendulum.now().timestamp())
        datetime = pendulum.from_timestamp(timestamp, tz='Asia/Bangkok').isoformat()
        
        headers = {
            "requesterID": self.core.identity,
            "message_type": "event",
            "TimeStamp": datetime
        }
        
        _payload = {
            "location": self.location,
            "timestamp": timestamp,
            "datetime": datetime,
            "device_id": agent_id,
            "type": "agent",
            "datapoint": "agent_status",
            "value": message,
            "message": ""
        }
        
        # publish payload to the message bus to store in database
        _topic_name = f"{self.topic_to_crate}/{self.core.identity}"
        self.vip.pubsub.publish('pubsub', _topic_name, headers=headers, message=_payload)
        _log.debug(f"{self.core.identity}: publish to {_topic_name} with payload: {_payload}")

    def _handle_custom_heartbeat(self, peer, sender, bus, topic, headers, message):
        """Handle custom heartbeat message from defined Volttron agents where the message can be for any devices or functions
        `topic` = "altoheartbeat/{agent_id}"
        payload = {
            "type": string, # options: ["device", "function"]
            "datapoint": string, # device_name or function_name
            "value": string,  # options: ["GOOD", "BAD"]
            "timestamp": float,  # unix_timestamp
            "message": string,  # context of the status ex. error message
        }
        """
        # validate topic and agent_id
        agent_id = topic.split('/')[1]
        if agent_id not in self.agent_ids:
            return

        # validate payload
        if isinstance(message, str):
            message = json.loads(message)
        _type = message.get("type", None)
        _datapoint = message.get("datapoint", None)
        _value = message.get("value", None)
        _timestamp = message.get("timestamp", None)
        _message = message.get("message", "")
        if not all([_type, _datapoint, _value, _timestamp]):
            return

        # construct payload to upload database
        datetime = pendulum.from_timestamp(_timestamp, tz='Asia/Bangkok').isoformat()
        
        headers = {
            "requesterID": self.core.identity,
            "message_type": "event",
            "TimeStamp": datetime
        }
        
        _payload = {
            "location": self.location,
            "timestamp": _timestamp,
            "datetime": datetime,
            "device_id": agent_id,
            "type": _type,
            "datapoint": _datapoint,
            "value": _value,
            "message": _message
        }
        
        # publish payload to the message bus to store in database
        _topic_name = f"{self.topic_to_crate}/{self.core.identity}"
        self.vip.pubsub.publish('pubsub', _topic_name, headers=headers, message=_payload)

    def check_heartbeat_status(self):
        """Periodic checking on agent running status
        If the agent is not sending the heartbeat for a certain period of time, the agent will be restarted.
        """
        _now = pendulum.now(tz='Asia/Bangkok')
        unix_timestamp = _now.timestamp()
        
        for agent_id in self.agent_ids:
            agent_state = self.agent_states.get(agent_id, None)
            if not agent_state:
                continue
            
            setup_timestamp = agent_state['setup_timestamp']
            latest_heartbeat = agent_state['latest_heartbeat']
            
            
            # Case 1: initial case - no heartbeat received yet
            if latest_heartbeat is None:
                if (unix_timestamp - setup_timestamp) > self.agent_offline_duration:
                    # restart agent
                    _ = self._restart_agent(agent_tag=agent_id)
            
            # Case 2: normal case - check if the latest heartbeat is older than the offline duration
            else:
                if (unix_timestamp - latest_heartbeat) > self.agent_offline_duration:
                    # restart agent
                    _ = self._restart_agent(agent_tag=agent_id)

    def _restart_agent(self, agent_tag: str):
        # REMARK: consider on `agent_id` instead of `agent_tag` (current: agent_id and agent_tag need to be the same)
        response_status = self.agent_control.control_agent(
            agent_tag=agent_tag, 
            method_name="restart", 
            retry_count=3
        )
        _log.debug(f"{self.core.identity}: restarting agent-{agent_tag}, response_status-{response_status}")
        return response_status

def main():
    """Main method called to start the agent."""
    utils.vip_main(platformagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
