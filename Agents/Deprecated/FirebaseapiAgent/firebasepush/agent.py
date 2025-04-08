"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub
import requests
import json
import pytz
import time
from datetime import datetime

tz = pytz.timezone('Asia/Bangkok')
_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

localserver = True


def firebasepush(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Firebasepush
    :rtype: Firebasepush
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    url = str(config.get('url'))
    urlcloudapi = str(config.get('urlcloudapi'))
    Authorization = str(config.get('Authorization'))
    Content = str(config.get('Content'))

    return Firebasepush(url, urlcloudapi, Authorization, Content, **kwargs)


class Firebasepush(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, url, urlcloudapi, Authorization, Content, **kwargs):
        super(Firebasepush, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.url = url
        self.urlcloudapi = urlcloudapi
        self.Authorization = Authorization
        self.Content = Content
        self.default_config = {"url": url, "urlcloudapi": urlcloudapi,
                               "Authorization": Authorization, "Content": Content}

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
            url = str(config["url"])
            urlcloudapi = str(config.get('urlcloudapi'))
            Authorization = str(config.get('Authorization'))
            Content = str(config.get('Content'))
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.url = url
        self.urlcloudapi = urlcloudapi
        self.Authorization = Authorization
        self.Content = Content

    #     self._create_subscriptions(self.setting2)
    #
    # def _create_subscriptions(self, topic):
    #     #Unsubscribe from everything.
    #     self.vip.pubsub.unsubscribe("pubsub", None, None)
    #
    #     self.vip.pubsub.subscribe(peer='pubsub',
    #                               prefix=topic,
    #                               callback=self._handle_publish)
    #
    # def _handle_publish(self, peer, sender, bus, topic, headers,
    #                             message):
    #     pass

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

        # Exmaple RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @PubSub.subscribe(peer='pubsub', prefix='alto')
    def subscribe_device(self, peer, sender, bus, topic, headers, message):
        #_log.debug("firebaseapi subscribe prefix -devices- :{}, sender:{}, bus:{}, topic:{}, message:{}"
                     .format(peer, sender, bus, topic, message))
        try:
            topic = topic.split('/')
        except Exception as er:
            _log.debug(" error topic cannot split(/) {}".format(er))

        # ----> check toppic
        if topic[1] == "device" and topic[3] == "state":
            try:
                self.fire(topic, message)
            except Exception as e:
                _log.debug("Error: Could not save data to firebase: {}".format(e))
        else:
            _log.debug("Cannot catch the topic--------> {}".format(topic))

    def fire(self, topic, message):
        if localserver:
            _log.debug("Firebase local server :{} {}".format(topic, message))
            try:
                mydata = {"target": message["target"]} if "target" in message.keys() else {}
                mydata["mac address"] = message['mac']
                mydata['data'] = dict([(x, y) for x, y in message['data'].items()])
                response = requests.post(self.url, json=mydata)

                _log.debug('Response HTTP Status Code: {status_code}'.format(
                    status_code=response.status_code))
                _log.debug('Response HTTP Response Body: {content}'.format(
                    content=response.content))

            except requests.exceptions.RequestException:
                _log.debug('HTTP Request failed')

        else:
            _log.warning("FirebaseCloudAPI :{} {}".format(topic, message))
            try:
                mydata = {"topic": str(message["target"])+ "/" + str(message['mac'])} if "target" in message.keys() else {}
                mydata["requestId"] = str(int(time.time()))
                mydata['data'] = dict([(x, y) for x, y in message['data'].items()])
                _log.debug("---->{}  ---->{} ".format(self.Authorization, self.Content))
                _log.debug(json.dumps(mydata))
                response = requests.post(
                    url=self.urlcloudapi,
                    headers={
                        "Authorization": self.Authorization,
                        "Content-Type": self.Content,
                    },
                    data=json.dumps(mydata)
                )

                _log.debug('Response HTTP Status Code: {status_code}'.format(
                    status_code=response.status_code))
                _log.debug('Response HTTP Response Body: {content}'.format(
                    content=response.content))

            except requests.exceptions.RequestException:
                _log.debug('HTTP Request failed')

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method
        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(firebasepush,
                   version=__version__)

if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
