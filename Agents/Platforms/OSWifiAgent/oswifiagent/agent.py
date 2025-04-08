"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import subprocess
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class WifiNetwork:
    "The Singleton Class"

    @staticmethod
    def execute_cmd(cmd, passw=''):
        output = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate(input=(f'{passw}\n').encode('UTF-8'))
        return output[0].decode('UTF-8'), output[1].decode('UTF-8')

    @staticmethod
    def wifi_list():
        return WifiNetwork.execute_cmd(['nmcli', 'dev', 'wifi'])

    @staticmethod
    def check_wifi_ip():
        return WifiNetwork.execute_cmd(['ifconfig'])

    @staticmethod
    def wifi_up(wname, passw):
        return WifiNetwork.execute_cmd(['sudo', '-S', 'nmcli', 'c', 'up', wname], passw)

    @staticmethod
    def wifi_down(wname, passw):
        return WifiNetwork.execute_cmd(['sudo', '-S', 'nmcli', 'c', 'down', wname], passw)


def oswifiagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Oswifiagent
    :rtype: Oswifiagent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get("agent_name", "os_wifi")
    params = config.get("params", {})

    return Oswifiagent(agent_name, params, **kwargs)


class Oswifiagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, params, **kwargs):
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super(Oswifiagent, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)

        self.agent_name = agent_name
        self.params = params

        self.default_config = {"agent_name": agent_name,
                               "params": params}

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
            agent_name = config["agent_name"]
            params = config["params"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.params = params

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        
        self.core.periodic(60, self._period_signal)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        
        _log.info("os_wifi agent stoped.")

    def _period_signal(self):
        try:
            if self.params:
                output, _ = WifiNetwork.check_wifi_ip()
                ifname = self.params["ifname"]
                wifi_name = self.params["wifi_name"]
                os_password = self.params["os_password"]
                ifn_index = output.find(ifname)
                ifn_cut = output[ifn_index:ifn_index + 120]
                if ifn_cut.find("inet") < 0:
                    _log.info(f"os_wifi {ifname} {wifi_name}")
                    tmp = WifiNetwork.wifi_up(wifi_name, os_password)
        except Exception as e:
            _log.error(f'os_wifi {e}')


def main():
    """Main method called to start the agent."""
    utils.vip_main(oswifiagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
