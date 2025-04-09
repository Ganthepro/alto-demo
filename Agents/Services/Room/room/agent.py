"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import altolib
import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class MyRoom(altolib.AltoLocationDevice):
    pass


def room(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Room
    :rtype: Room
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "mintel")
    kwargs["location_name"] = config.get("location_name", "RoomXX")

    return Room(topic, **kwargs)


class Room(altolib.AltoLocation):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        # self.device_list[self.location_name] = MyRoom(self, self.location_name)

    def register_self(self):
        ndev = MyRoom(self, self.location_name)
        self.register_new_device(ndev)


def main():
    """Main method called to start the agent."""
    utils.vip_main(room, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
