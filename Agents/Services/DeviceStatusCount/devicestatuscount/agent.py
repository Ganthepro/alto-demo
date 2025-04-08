#@title DeviceStatusCount Agent Bgrimm
#@markdown tag device_status_rl
"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

from typing import List

import logging
import sys
import pyrebase
import time
import pandas as pd
import pendulum

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class FirebaseHandler:

    def __init__(self, firebase_config):
        self.firebase_config = firebase_config
        self.database = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        self.database = pyrebase.initialize_app(self.firebase_config).database()

    def push_data(self, path, data):
        path_to = ""
        split_path = path.split('/')
        for i, p in enumerate(split_path):
            if i == 0:
                path_to = self.database.child(p)
            else:
                path_to.child(p)
        path_to.update(data)
    
    def get_data(self, path):
        path_to = ""
        split_path = path.split('/')
        for i, p in enumerate(split_path):
            if i == 0:
                path_to = self.database.child(p)
            else:
                path_to.child(p)
        return dict(path_to.get().val())


def devicestatuscount(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Devicestatuscount
    :rtype: Devicestatuscount
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    target = config.get('target', {})
    firebase_config = config.get('firebase_config', {})
    firebase_node_path = config.get('firebase_node_path', "")

    return Devicestatuscount(target, firebase_config, firebase_node_path, **kwargs)


class Devicestatuscount(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, target, firebase_config, firebase_node_path, **kwargs):
        super(Devicestatuscount, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.target = target
        self.firebase_config = firebase_config
        self.firebase_node_path = firebase_node_path
        self.firebase = None

        self.target_status = {}
        self.target_count = {}

        self.default_config = {
            "target": target,
            "firebase_config": firebase_config,
            "firebase_node_path": firebase_node_path
            }

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
            target = config.get('target', {})
            firebase_config = config.get('firebase_config', {})
            firebase_node_path = config.get('firebase_node_path', "")
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.target = target
        self.firebase_config = firebase_config
        self.firebase_node_path = firebase_node_path

        self.firebase = FirebaseHandler(self.firebase_config)
        self._handle_configure()
    
    def _handle_configure(self):
        topic_list = list()
        for schema, schema_prop in self.target.items():
            for agent, agent_prop in schema_prop.items():
                for target_id, target_prop in agent_prop.items():
                    topic_list.append(f"{schema}/{agent}/{target_id}/event")
                    if target_prop:
                        self.target_status[target_id] = {
                            "agent": agent,
                            "node": target_prop[0],
                            "status": None,
                        }
                    else:
                        self.target_status[target_id] = {
                            "agent": agent,
                            "status": None
                        }

        self._create_subscriptions(topic_list)
        for target_id, value in self.target_status.items():
            if 'node' in value:
                self._rpc_device_status(value['agent'], 'get_device_status', value['node'])
            else:
                self._rpc_device_status(value['agent'], 'get_device_status')

        self.core.schedule(cron("*/10 * * * *"), self._count_status)

    def _rpc_device_status(self, agent_identity, method, node=None):
        _log.debug(f"agent identity: {agent_identity}, method: {method}, node: {node}")
        try:
            status_list = self.vip.rpc.call(agent_identity, method).get(timeout=10)
            for dev_status in status_list:
                for dev, status in dev_status.items():
                    self.target_status[dev].update({"status": status})
        except Exception as e:
            _log.error(f"_rpc_device_status: Exception {e}")
        
    def _create_subscriptions(self, topics: list) -> None:
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for topic in topics:
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=topic,
                                    callback=self._handle_publish)
            _log.debug(f"Subscribe to topic: {topic}")

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file

        Args
        """

        _log.debug(f"_handle_publish topic: {topic}, message: {message}")
        schema, agent, target_id, mtye = topic.split("/")

        if message["type"] == "device":
            if target_id in self.target_status:
                if "online_status" in message:
                    self.target_status[target_id].update({
                        'status': message['online_status'],
                        'timestamp': message['unix_timestamp']
                    })
                if "device_status" in message:
                    self.target_status[target_id].update({
                        'status': True if message['device_status'] == "online" else False,
                        'timestamp': message['unix_timestamp']
                    })
                if 'status_code' in message:
                    if message['status_code'] == 'normal':
                        self.target_status[target_id].update({
                            'status': True,
                            'status_code': message['status_code'],
                            'error_code': message['error_code'],
                            'timestamp': message['unix_timestamp']
                        })
                    else:
                        self.target_status[target_id].update({
                            'status': False,
                            'status_code': message['status_code'],
                            'error_code': message['error_code'],
                            'timestamp': message['unix_timestamp']
                        })
                if 'node' in self.target_status[target_id]:
                    self._count_status(self.target_status[target_id]['node'])

        elif message['type'].startswith("rl"):
            self.target_status[target_id] = {"timestamp": message['unix_timestamp']}

    def _publish(self, topic: str, message: str):
        _log.debug(f"_publish: {topic}, message: {message}")
        self.vip.pubsub.publish(
            'pubsub',
            topic=topic,
            headers={
            "requesterID": self.core.identity,
            "message_type": "command",
            "TimeStamp": str(pendulum.now())
            },
            message=message
        )
    
    def _count_status(self, device_type):
        _log.debug(f"Counting status of {device_type}")
        status_list = []
        for device_id, prop in self.target_status.items():
            if 'node' in prop:
                if device_type in prop['node']:
                    status_list.append(prop['status'])
            else:
                continue
        data = {"online": status_list.count(True)}
        _log.debug(f"online {device_type}: {data}")
        self._emit_to_firebase(f"{self.firebase_node_path}/{device_type}", data)
     
    def _emit_to_firebase(self, path, data):
        self.firebase.push_data(path, data)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(devicestatuscount, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
    