"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import pyrebase 
import json
import time

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.3"

def rlcorrection(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Rlcorrection
    :rtype: Rlcorrection
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    building = config.get("building", "")
    zone = config.get("zone", {})
    firebase_config = config.get("firebase_config", {})

    return Rlcorrection(building, zone, firebase_config, **kwargs)


class Rlcorrection(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, building, zone, firebase_config, **kwargs):
        super(Rlcorrection, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.building = building
        self.zone = zone
        self.firebase_config = firebase_config
        
        self.firebase_client = None
        self.firebase_databse = None
        self.map_ac = {}
        self.zone_updated_time = {}

        self.default_config = {
            "building": building,
            "zone": zone,
            "firebase_config": firebase_config
            }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
    
    def initialize_firebase(self):
        self.firebase_client = pyrebase.initialize_app(self.firebase_config)
        self.firebase_database = self.firebase_client.database()

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
            building = config.get("building", "")
            zone = config.get("zone", {})
            firebase_config = config.get("firebase_config", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.building = building
        self.zone = zone
        self.firebase_config = firebase_config
        
        self.initialize_firebase()
        
        for zone_name in zone:
            self.zone_updated_time[zone_name] = None
        
        self._create_subscriptions()  # sub subiot

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """

        self.vip.pubsub.unsubscribe("pubsub", None, None)
        
        self.vip.pubsub.subscribe(peer='pubsub',
                                prefix="rl_correct/subiot/example/command",
                                callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        step0 : check msg type: Subiot or HVAC
        step1 : Map zone to ac
        step2 : Get that ac info
        step3 : Take action
        """

        # payload = {
        #     "feedback": "Too Hot", 
        #     "building": "BGrimm", 
        #     "zone": "Floor 1 Creative Arena Room", 
        #     "lineId": "U87d0284d6b783f8fbb4af8bd050ba1e6", 
        #     "feedbackId": "406",
        #     "topic": "human_feedback"
        #     }
        
        if isinstance(message, str):
            message = json.loads(message)
        feedback = message["feedback"] # Too Hot, Too Cold
        zone = message["zone"] # Floor 1 Creative Arena Room
        building = message["building"] # BGrimm
        _log.info(f"Got feedback: {feedback}, zone: {zone}, building: {building}")

        # Step 2: get data from firebase
        # Step 3: take action
        try:
            if zone in self.default_config["zone"]:
                zone_time = self.zone_updated_time.get(zone, None)
                _log.debug(f"zone_time: {zone_time}")
                if zone_time is None:
                    self.take_action(feedback, zone)
                    self.zone_updated_time[zone] = time.time()
                    _log.debug(f"Zone: {zone}, update time: {self.zone_updated_time[zone]}")
                else:
                    if time.time() - zone_time <= 900:
                        _log.debug(f"Time not exceed 10 minutes at zone: {zone}")
                    else:
                        self.take_action(feedback, zone)
                        self.zone_updated_time[zone] = time.time()
                        _log.debug(f"Zone: {zone}, update time: {self.zone_updated_time[zone]}")
            else:
                _log.debug(f"Unknown zone: {zone}")
        except Exception as e:
            _log.error(f"_handle_publish: Exception {e}")

    def take_action(self, feedback, zone):
        ac_map = self.firebase_database.child('buildings').child('synergy').child('iot_devices').get().val()
        if feedback == "Too Cold":
            for ac in self.default_config['zone'][zone]:
                if ac_map[ac]['ac']['subdev_0']['mode'] == "cool":
                    topic2p = f"mqtt/rl_correction/{ac}/command"
                    message = {
                        "mode": 1,
                        "source": "rl_correction",
                        "set_temperature": ac_map[ac]['ac']['subdev_0']["set_temperature"] + 1
                    }
        elif feedback == "Too Hot":
            for ac in self.default_config['zone'][zone]:
                if ac_map[ac]['ac']['subdev_0']['mode'] == "off":
                    topic2p = f"mqtt/rl_correction/{ac}/command"
                    message = {
                        "source": "rl_correction",
                        "mode": 1,
                        "set_temperature": ac_map[ac]['ac']['subdev_0']['set_temperature']}
                else:
                    topic2p = f"mqtt/rl_correction/{ac}/command"
                    message = {
                        "mode": 1,
                        "source": "rl_correction",
                        "set_temperature": ac_map[ac]['ac']['subdev_0']["set_temperature"] - 1}
        self.emit_ac_temperature(topic2p, message)

    def emit_ac_temperature(self, topic, message):
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            headers={
                "requesterID": self.core.identity,
                "message_type": "command",
            },
            message=message
            )
        _log.info(f"RLCorrection Successfully published: {topic} and {message}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(rlcorrection, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass