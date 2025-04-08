"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from gevent import subprocess
import requests
import json
import pyrebase
import gevent
import time

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

CMD = ["start", "stop"]

class Firebase:

    def __init__(self, firebase_config):
        _log.debug(f"{firebase_config}")
        self.firebase_config = firebase_config
        self._db = None

        self._firebase_initialize()
    
    def _firebase_initialize(self):
        firebase = pyrebase.initialize_app(self.firebase_config)
        self._db = firebase.database()

    def push_data(self, data):
        if data is not None:
            self._db.child("hotel").child("mintel").child("agents").set({"action_room": {
                                                                        "agent_status": data,
                                                                        "event_status": "success",
                                                                        "unix_timestamp": time.time()
                                                                    }})
        else:
            self._db.child("hotel").child("mintel").child("agents").child("action_room").update({
                                                                        "event_status": "failed",
                                                                        "unix_timestamp": time.time()
                                                                    })

    @property
    def db(self):
        return self._db

def lifecycle(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Lifecycle
    :rtype: Lifecycle
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get("agent_name", "")
    sampling_rate = config.get("sampling_rate", "")
    fb_config = config.get("fb_config", {})

    return Lifecycle(agent_name, sampling_rate, fb_config, **kwargs)


class Lifecycle(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, sampling_rate, fb_config, **kwargs):
        super(Lifecycle, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.agent_name = agent_name
        self._token = None
        self.fb_config = fb_config
        self.agent_check = {}

        self.default_config = {
            "agent_name": agent_name,
            "sampling_rate": sampling_rate,
            "fb_config": fb_config
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
            agent_name = config.get("agent_name", "")
            sampling_rate = config.get("sampling_rate", 1800)
            fb_config = config.get("fb_config", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.sampling_rate = sampling_rate
        self.fb_config = fb_config

        self._initialize_firebase()
        self._create_subscriptions()
        self._login_to_get_token()
        self.core.periodic(180, self._handle_time_check)
    
    def _initialize_firebase(self):
        self.firebase = Firebase(self.fb_config)

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=f"platform/{self.agent_name}",
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        #Step 1 handle message
        if message:
            target_agent = message.get("target_agent", "")
            command = message.get("command", "")
            self.agent_check[target_agent] = {
                "updated_time": time.time(),
                "count": 0
            }
            if command in CMD:
                if command == "start":
                    self.start(target_agent)
                elif command == "stop":
                    self.stop(target_agent)

    def start(self, agent_tag: str) -> None:
        try:
            run = subprocess.run(["vctl", "start", "--tag", agent_tag], stdout=subprocess.PIPE)
            result = run.stdout.decode("utf-8")
            _log.debug(result)
            gevent.sleep(20)
            status = self._check_status(agent_tag)
            _log.debug(f"start: {status}")
            if status is None:
                if self.agent_check[agent_tag]['count'] == 5:
                    del self.agent_check[agent_tag]['count']
                    _log.warning(f"Can't Start Agent: {agent_tag}")
                    return
                self.agent_check[agent_tag]['count'] += 1
                self.start(agent_tag)
                return
            del self.agent_check[agent_tag]['count']
            self.agent_check[agent_tag].update({"agent_status": status})
            self.firebase.push_data(status)
        except Exception as e:
            _log.error(f"start Exception: {e}")

    def stop(self, agent_tag: str) -> None:
        try:
            run = subprocess.run(["vctl", "stop", "--tag", agent_tag], stdout=subprocess.PIPE)
            result = run.stdout.decode("utf-8")
            _log.debug(result)
            gevent.sleep(15)
            status = self._check_status(agent_tag)
            _log.debug(f"stop: {status}")
            self.agent_check[agent_tag].update({"agent_status": status})
            if status is None:
                if self.agent_check[agent_tag]['count'] == 5:
                    del self.agent_check[agent_tag]['count']
                    _log.warning(f"Can't Stop Agent: {agent_tag}")
                    return
                self.agent_check[agent_tag]['count'] += 1
                self.stop(agent_tag)
                return
            del self.agent_check[agent_tag]['count']
            if not status:
                self.send_notification_to_backend()
            self.firebase.push_data(status)
        except Exception as e:
            _log.error(f"stop Exception: {e}")

    def _handle_time_check(self):
        for agent in self.agent_check:
            if time.time() - self.agent_check[agent]["update_time"] >= 180:
                status = self._check_status(agent)
                self.agent_check[agent].update({"agent_status": status})
                self.firebase.push_data(status)
        
    def _check_status(self, agent_tag):
        run = subprocess.run(["vctl", "status"], stdout=subprocess.PIPE)
        result = run.stdout.decode("utf-8")
        _log.debug(result)
        sp_line = result.split("\n")
        _log.debug(sp_line)
        for k in sp_line:
            l = k.split()
            if len(l) > 3:
                if agent_tag == l[3]:
                    if l[4] == "running":
                        return True
                    else:
                        return False
        return None
    
    def _login_to_get_token(self):
        try:
            response = requests.post(
                "https://buildingapimgmt.azure-api.net/auth/api/v2.0/login",
                headers={
                    "content-type": "application/json"
                },
                data=json.dumps({
                    "username": "minteladmin",
                    "password": "minteladmin"
                }))
            if response.ok:
                _log.debug(f"login_to_get_token: {response.json()}")
                self._token = response.json().get("token", "")
        except Exception as e:
            _log.error(f"login_to_get_token: {e}")

    def send_notification_to_backend(self):
        _log.debug("send notification method")
        try:
            response = requests.post(
                "https://buildingapimgmt.azure-api.net/util/api/v2.0/line_notification",
                params={
                    "message": "Mintel intruder detection has already stopped by Front office"
                },
                headers={
                    "Authorization": f"Token {self._token}"
                }, timeout=60)
            if response.ok:
                _log.debug(f"send_notification_to_backend: {response.json()}")
            else:
                self._login_to_get_token()
        except Exception as e:
            _log.error(f"send_notification_to_backend: Exception {e}")

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

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(lifecycle, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
