"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import json
import logging
import sys
from flask import Flask, request
from threading import Thread
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic
from queue import Queue


_log = logging.getLogger(__name__)
utils.setup_logging()

_nolog = logging.getLogger("werkzeug")
_nolog.setLevel(logging.ERROR)
__version__ = "0.1"


def trivialagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Trivialagent
    :rtype: Trivialagent
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    host = config.get("host", "0.0.0.0")
    port = int(config.get("port", 5000))

    return Trivialagent(host, port, **kwargs)


class Trivialagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, host="0.0.0.0", port=5000, **kwargs):
        super(Trivialagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.host = host
        self.port = port
        self.msg = Queue()

        self.default_config = {"host": host, "port": port}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(
            self.configure, actions=["NEW", "UPDATE"], pattern="config"
        )

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
            host = str(config["host"])
            port = int(config["port"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        if "listen_to" in config:
            self.listen_to = config["listen_to"]
        else:
            self.listen_to = []
            
        if "command" in config:
            if "topic" in config["command"]:
                try:
                    topic = config["command"]["topic"]
                    payload = config["command"]["payload"]
                    header = config["command"]["header"]
                    self.msg.put_nowait([topic, payload, header])
                except Exception as e:
                    _log.debug(f"Command error {e}")

        self.host = host
        self.port = port
        self._create_subscriptions("")

    def _create_subscriptions(self, topic):
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(
            peer="pubsub", prefix=topic, callback=self._handle_publish
        )

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        # if sender in self.listen_to:
        _log.debug(
            f"Received message from {sender}:\n\tTopic: {topic},\n\tHeaders:{headers}\n\tMessage: {message}"
        )

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
        self.flask = Thread(target=self._flask_thread)
        self.flask.setDaemon(True)
        self.flask.start()

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

        May be called from another agent via self.core.rpc.call """
        return self.host + arg1 - arg2

    def _flask_thread(self):

        app = Flask("TrivialAgent")
        TAG = "<!-- REPLACE ME -->"
        MyForm = """
        <html>
        <body>
            <!-- REPLACE ME -->
            <form action = "/broadcast" method = "post">
                <label for="topic">Topic:</label>
                <input type="text" id="topic" name="topic"><br><br>
                <label for="header">Type:</label>
                <select id="header" name="header">
                <option value="command">Command</option>
                <option value="event">Event</option>
                <option value="request">Request</option>
                <option value="response">Response</option>
                </select><br><br>
                <label for="value">JSON Value:</label>
                <input type="text" id="value" name="value"><br><br>
                <input type="submit" value="Submit">
            </form>
        </body>
        </html>
        """

        @app.route("/broadcast/", methods=["POST", "GET"])
        def do_broadcast():
            if request.method == "POST":
                try:
                    val = json.loads(request.form["value"])
                    _log.debug("Topic: {}".format(request.form["topic"]))
                    _log.debug("Type: {}".format(request.form["header"]))
                    _log.debug("Value: {}".format(val))
                    msg = "<p>Data was sent</p>"
                    self.msg.put_nowait([request.form["topic"],val,request.form["header"]])
                    #self.vip.pubsub.publish(
                        #peer="pubsub",
                        #topic=request.form["topic"],
                        #message=val,
                        #headers={
                            #"requesterID": self.core.identity,
                            #"message_type": request.form["header"],
                        #},
                    #)
                except:
                    msg = "<p>Error: {} is not properly formated for JSON.</p>".format(
                        request.form["value"]
                    )
                return MyForm.replace(TAG, msg)
            return MyForm

        @app.route("/")
        def send_form():
            return MyForm

        app.run(
            host=self.default_config["host"],
            port=self.default_config["port"],
            debug=False,
        )

    @Core.schedule(periodic(2))
    def _send_stuffs(self,):

        if not self.msg.empty():
            try:
                topic, msg, head = self.msg.get_nowait()
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=topic,
                    message=msg,
                    headers={
                        "requesterID": self.core.identity,
                        "message_type": head,
                    },
                )
                self.msg.task_done()
            except:
                pass

def main():
    """Main method called to start the agent."""
    utils.vip_main(trivialagent, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
