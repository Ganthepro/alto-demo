"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import json
import logging
import requests
import sys
from altolib import AltoAgent
from threading import Thread
from time import sleep
from volttron.platform.agent import utils
from queue import Queue


_log = logging.getLogger(__name__)
utils.setup_logging()

_nolog = logging.getLogger("werkzeug")
_nolog.setLevel(logging.ERROR)
__version__ = "0.1"


def registeragent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Registeragent
    :rtype: Registeragent
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")
    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "registrar")
    kwargs["url"] = config.get("url", "")
    kwargs["user"] = config.get("user", "")
    kwargs["password"] = config.get("password", "")
    kwargs["devices_suburl"] = config.get("devices_suburl", "")
    kwargs["login_suburl"] = config.get("login_suburl", "")

    return Registeragent(topic, **kwargs)


class Registeragent(AltoAgent):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.newdevs = Queue()
        self.needtoken = Queue()
        self.needtoken.put_nowait(True)
        self.known_ids = set()
        self.token = None
        self.time_to_die = False
        self.registration_thread = self.start_registration()
        self.login_thread = self.start_login()

    def _create_subscriptions(self) -> None:
        """
        The schema "datalogger" is treated a tad differently

        """
        # Unsubscribe from everything.
        super()._create_subscriptions()
        _log.debug("Subscribing to newdevice")
        self.vip.pubsub.subscribe(
            peer="pubsub", prefix="newdevice", callback=self._handle_newdev
        )

    def _handle_newdev(self, peer, sender, bus, topic, headers, message):
        try:
            devid = message["device_id"]
            if devid in self.known_ids:
                return
            last_subdev = int(message["subdevice_last_idx"])
            schema = message["schemas"]
        except:
            _log.error(
                f"New device message from {sender} ain't properly formated. Message: {message}"
            )
            return

        self.newdevs.put_nowait((devid, last_subdev, schema))

    def register_self(self):
        """
        Needs to be defined for non-bridge agents

        """
        self.device_list["Stop Bothering Me"] = None

    def last_rites(self):
        self.time_to_die = True
        self.newdevs.put_nowait(("Die", "Die", "Die"))
        self.needtoken.put_nowait(True)

    def start_registration(self):
        _log.debug("Starting registration")
        thread = Thread(target=self._registration_thread, name="bacnet", daemon=True)
        thread.start()
        return thread

    def start_login(self):
        _log.debug("Starting login")
        thread = Thread(target=self._login_thread, name="bacnet", daemon=True)
        thread.start()
        return thread

    def _login_thread(self):
        """
        Attempts to log in and get a token
        """
        while True:
            go = self.needtoken.get()
            self.needtoken.task_done()
            if self.time_to_die:
                return
            confwait = 5
            tries = 3
            while self.token is None and tries:
                if self.url:
                    _log.debug("Attempting to get token")
                    tries -= 1
                    if self.url[-1] != "/":
                        self.url += "/"
                    if self.login_suburl[-1] != "/":
                        self.login_suburl += "/"
                    if self.devices_suburl[-1] != "/":
                        self.devices_suburl += "/"

                    lurl = self.url + self.login_suburl
                    try:
                        response = requests.post(
                            url=lurl,
                            headers={"content-type": "application/json"},
                            data=json.dumps(
                                {"username": self.user, "password": self.password}
                            ),
                        )
                        if response.status_code == 200:
                            res = json.loads(response.content.decode())
                            self.token = res["token"]
                            _log.debug(f"Got new token: {self.token}")
                        else:
                            _log.debug(
                                f"Response to login was {response.status_code}: {response.content}"
                            )
                    except Exception as e:
                        _log.debug(f"Got a problem when login: {e}")
                else:
                    # Waiting for config
                    _log.debug("Waiting for configuration")
                    if confwait:
                        confwait -= 1
                        sleep(2)
                    else:
                        _log.critical("Got not login information")
                        break
            if self.token is None:
                self.time_to_die = True
                return

    def _registration_thread(self):
        """
        Wait for the token, then start registering
        """
        hold = None
        while True:
            if self.token:
                if hold is None:
                    _log.debug("Awaiting new device")
                    hold = self.newdevs.get()
                    self.newdevs.task_done()
                    _log.debug(f"Got new device {hold}")
                if self.time_to_die:
                    _log.debug("Reg thread... time to die")
                    return
                devid, last_sub, schemas = hold
                data = {"device_id": devid, "device_name": devid, "mac_address": ""}
                subdata = {}
                for idx in range(int(last_sub) + 1):
                    subdata[idx] = {"nickname": f"sub_{idx}", "schema": schemas}
                data["subdevices"] = subdata
                try:
                    rurl = self.url + self.devices_suburl
                    headers = {"Content-Type": "application/json; charset=utf-8"}
                    headers["Authorization"] = f"Token {self.token}"
                    data = json.dumps(data)
                    response = requests.post(url=rurl, headers=headers, data=data)
                    _log.debug(
                        f"Got response with status {response.status_code} for {data}"
                    )
                    if response.status_code == 200:

                        hold = None
                        self.known_ids.add(devid)
                    else:
                        rc = json.loads(response.content.decode())
                        if (
                            response.status_code == 400
                            and "error" in rc
                            and rc["error"].startswith("duplicate key")
                        ):
                            self.known_ids.add(devid)
                            hold = None
                        elif response.status_code == 401:
                            # Need new token
                            _log.debug("Need new token")
                            self.token = None
                            self.needtoken.put(True)
                        else:
                            _log.warning(
                                f"Registration was answered with {response.status_code} response: {response.content}"
                            )
                            hold = None
                except Exception as e:
                    _log.error(f"Got a problem whilst registering: {e}")
                    hold = None
            else:
                _log.debug("Registration waiting for a token")
                sleep(2)
                if self.time_to_die:
                    return


def main():
    """Main method called to start the agent."""
    utils.vip_main(registeragent, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
