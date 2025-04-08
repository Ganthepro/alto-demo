"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'
import json
import logging
import sys
import random
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron, periodic
import pyrebase
from datetime import datetime
from threading import Thread, Lock
import time

FBSECRET = "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM"
FBDATABASEURL = "https://altohotel-b6ae5.firebaseio.com/"
FBTARGET="hotel/alto_demo"
FBAPIKEY = "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM"
FBAUTHDOMAIN = "altohotel-b6ae5.firebaseapp.com"
FBSTORAGEBUCKGET = "altohotel-b6ae5.appspot.com"
config = {
  "apiKey": FBAPIKEY,
  "authDomain": FBAUTHDOMAIN,
  "databaseURL": FBDATABASEURL,
  "storageBucket": FBSTORAGEBUCKGET
  }

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
db = firebase.database()



_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def tester(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Tester
    :rtype: Tester
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Tester(setting1,
                          setting2,
                          **kwargs)


class Tester(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic",
                 **kwargs):
        super(Tester, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.y = 1
        self.setting1 = setting1
        self.setting2 = setting2

        self.default_config = {"setting1": setting1,
                               "setting2": setting2}
        # thread = Thread(target=self.get_fb_data, name="get_firebase_data", daemon=True)
        # thread.start()

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
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
            setting1 = int(config["setting1"])
            setting2 = str(config["setting2"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.setting1 = setting1
        self.setting2 = setting2

        self._create_subscriptions(self.setting2)

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix='rooms/*',
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        print(f"topic: {topic}")
        print(f"headers {headers}")
        print(f"message {message}")
        print(f"----------------------------")

    @Core.schedule(periodic(5))
    def periodic_function(self):
        try:
            print("in periodic")
            data = db.child("hotel").child("mintel").child("building main").get()
            res = {"ac": {"off": 0, "on": 0},
                   "front_switch": {"off": 0, "on": 0},
                   "back_switch": {"off": 0, "on": 0},
                   "exfan": {"off": 0, "on": 0}}
            res = self.count_ons(data, res)
            now = datetime.now()  # current date and time
            date_time = now.strftime("%Y-%m-%d, %H:%M:%S")
            print("date and time:", date_time)
            to_fb = {}
            to_fb["updated_at"] = date_time
            to_fb["items"] = res
            db.child("hotel").child("mintel").child("dashboard").child("devices_status").update(to_fb)
        except Exception as e:
            _log.debug("error in getting count devices")

    # def get_fb_data(self):
    #     while True:
    #         time.sleep(5)
    #         self.data = db.child("hotel").child("mintel").child("building main").get()

    def count_ons(self, data, res):

        def count_switches(type):
            if k.startswith(type):
                have_on = False
                for sub_dev in v["relay"].values():
                    if sub_dev["state"] == "on":
                        have_on = True
                if have_on == False:
                    res[type]["off"] += 1
                else:
                    res[type]["on"] += 1

        for dat in data.each():
            if dat.key().startswith("room_"):
                for k, v in dat.val()["iot_devices"].items():

                    ##count acs
                    if k.startswith("ac_"):
                        # res[dat.key()]= (v["ac"]["ac"]["mode"])
                        if v["ac"]["ac"]["mode"] == "off":
                            res["ac"]["off"] += 1
                        else:
                            res["ac"]["on"] += 1

                    ##count front switches
                    count_switches("front_switch")

                    ##count back switches
                    count_switches("back_switch")

                    ##count fans
                    count_switches("exfan")
                    if k.startswith("exfan"):
                        if v["relay"]["fan"]["state"] == "on":
                            print(dat.key())
        return res

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        #Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        #Exmaple RPC call
        #self.vip.rpc.call("some_agent", "some_method", arg1, arg2)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export  # expose RPC interface for other agents, can alto define capability
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method
        May be called from another agent via self.core.rpc.call """
        _log.debug('get called from another agent via RPC')
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(tester, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
