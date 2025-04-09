"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import altolib
from base64 import b64encode
import datetime as dt
import json
import logging
import pytz
import sys
from threading import Thread
from queue import Queue
from time import sleep
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Core
from volttron.platform.scheduling import periodic
import requests


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

DEVTOPIC = "/device/"
THREADCOUNT = 10
CHECKSSL = True
ENERTALKMAP = {
    "current": "current",
    "voltage": "voltage",
    "power": "activePower",
    "power_reactive": "reactivePower",
    "power_apparent": "apparentPower",
    "energy": "positiveEnergy",
    "energy_to_grid": "negativeEnergy",
    "energy_reactive": "positiveEnergyReactive",
    "energy_reactive_to_grid": "negativeEnergyReactive",
    "timestamp": "timestamp",
}


class EnerTDevice(altolib.AltoElectricSensor):
    def __init__(self, controller, devid, nbsubdev=1):
        super().__init__(controller, devid, nbsubdev)
        # Now setup the map
        self.data_map.update(ENERTALKMAP)
        self.initialise_data("electric", ENERTALKMAP.keys())
        self.site = None
        self.tz = None

    def to_electric_current(self, val):
        return val / 1000

    def to_electric_voltage(self, val):
        return val / 1000

    def to_electric_power(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_power_reactive(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_power_apparent(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_energy(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_energy_to_grid(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_energy_reactive(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_energy_reactive_to_grid(self, val):
        return round((val / 1000) / 1000, 6)

    def to_electric_timestamp(self, val):
        tstmp = self.tz.localize(dt.datetime.fromtimestamp(val / 1000)).astimezone(
            pytz.timezone("UTC")
        )
        return tstmp.isoformat()


def enertalk(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Enertalk
    :rtype: Enertalk
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        [
            "enertalk_user",
            "enertalk_password",
            "site",
            "api_id",
            "api_secret",
            "agent_name",
            "timezones",
            "default_timezone",
        ],
        [
            "altotech.ai@gmail.com_altohoteldev",
            "mib@2015",
            [],
            "",
            "",
            "enertalk",
            {},
            "Asia/Bangkok",
        ],
    ):
        kwargs[x] = config.get(x, y)

    return Enertalk(topic, **kwargs)


class Enertalk(altolib.AltoDiscoverableAgent, altolib.AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super().__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.token = None
        self.refresh_token = None
        self.token_expire = None
        self.refresh_expire = None
        # Should we parametrize the next two?
        self.authUri = "https://enertalk-auth.encoredtech.com/login"
        self.tokenUri = "https://auth.enertalk.com/token"
        self.siteUri = "https://api2.enertalk.com/sites"
        self.devicesUri = "https://api2.enertalk.com/sites/{}/devices"
        self.infoUri = "https://api2.enertalk.com/devices/{}/usages/realtime"

        self.dataqueue = Queue(maxsize=0)
        self.requestqueue = Queue(maxsize=0)
        self.isloggedin = None
        self.skipfirst = True
        self.config_save = False
        self.terminate = False
        self.unauth = {}
        self.discovering = False

        for x in range(THREADCOUNT):
            getter = Thread(target=self._device_thread)
            getter.setDaemon(True)
            getter.start()

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        oldsites = set(self.site)
        super().configure(config_name, action, contents)

        if (
            self.token
            and dt.datetime.strptime(self.token_expire, "%Y-%m-%d %H:%M:%S")
            <= dt.datetime.now()
        ):
            self.token = None

        if oldsites != set(self.site) and self.device_list:
            # If device_list is empty, supper(0 would have started this
            self.start_discovery()

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        self.terminate = True
        for x in range(THREADCOUNT):
            self.requestqueue.put(None)
        sleep(1)

    # Login onto Enertalk
    def et_login(self):
        """
        This method perform authentication to the EnerTalk server and
        request a token. It should only be called when there is no refresh_token.
        nor token.
        """
        self.isloggedin = False
        login_urlparam = {
            "client_id": b64encode(self.api_id.encode()).decode("ascii"),
            "redirect_uri": "http://localhost:8080/callback",
            "response_type": "code",
            "app_version": "web",
            "back_url": "/authorization",
        }

        login_param = {
            "email": self.enertalk_user,
            "password": self.enertalk_password,
            "lang": "en",
        }

        token_param = {
            "client_id": b64encode(self.api_id.encode()).decode("ascii"),
            "client_secret": self.api_secret,
            "code": None,
            "grant_type": "authorization_code",
        }

        postUri = (
            self.authUri
            + "?"
            + "&".join(
                [
                    "{}={}".format(requests.utils.quote(x), requests.utils.quote(y))
                    for x, y in login_urlparam.items()
                ]
            )
        )
        _log.debug(f"Authenticating with {login_param} to {postUri}")
        code = None
        resu = None
        try:
            resu = requests.post(
                postUri, login_param, allow_redirects=True, verify=CHECKSSL
            )
        except Exception as e:
            _log.debug("Error Expected: {}".format(e))
            try:
                code = str(e).split("/callback?code=")[1].split(" ")[0]
            except Exception as e:
                if resu is None:
                    _log.error("Could not get authorisation code: {}".format(e))
                    return

        if code is None and resu is not None:
            try:
                _log.debug("Checking URL: {}".format(resu.url))
                code = resu.url.split("/callback?code=")[1].split(" ")[0]
            except:
                _log.error(
                    "Could not get authorisation code: Error {}, {}".format(
                        resu.status_code, resu.text
                    )
                )
                return

        # Getting token
        token_param["code"] = code
        try:
            resu = requests.post(
                self.tokenUri,
                headers={"Content-Type": "application/json"},
                data=json.dumps(token_param),
                verify=CHECKSSL,
            )
            assert resu.status_code == 200
            resu = json.loads(resu.text)
            _log.debug("Token Info is {}".format(resu))
            self.token = resu["access_token"]
            self.refresh_token = resu["refresh_token"]
            self.token_expire = (
                dt.datetime.now() + dt.timedelta(seconds=resu["expires_in"])
            ).strftime("%Y-%m-%d %H:%M:%S")
            self.refresh_expire = (
                dt.datetime.now() + dt.timedelta(seconds=resu["refresh_expires_in"])
            ).strftime("%Y-%m-%d %H:%M:%S")
            self.config_save = True
        except Exception as e:
            _log.error("Could not get authorisation token: {}".format(e))
            return
        self.isloggedin = True
        self.unauth = {}

    # Login onto Enertalk
    def et_refresh(self):
        if self.refresh_token:
            auth_secret = (
                b64encode(self.api_id.encode()).decode("ascii") + ":" + self.api_secret
            )
            headers = {"Content-Type": "application/json"}
            headers["Authorization"] = "Basic " + b64encode(
                auth_secret.encode()
            ).decode("ascii")
            data = json.dumps(
                {"refresh_token": self.refresh_token, "grant_type": "refresh_token"}
            )
            try:
                resu = requests.post(
                    self.tokenUri, headers=headers, data=data, verify=CHECKSSL
                )
                assert resu.status_code == 200
                resu = json.loads(resu.text)
                _log.debug("Old token is: {}".format(self.token))
                self.token = resu["access_token"]
                _log.debug("New token is: {}".format(resu["access_token"]))
                self.refresh_token = resu["refresh_token"]
                self.token_expire = (
                    dt.datetime.now() + dt.timedelta(seconds=resu["expires_in"])
                ).strftime("%Y-%m-%d %H:%M:%S")
                self.refresh_expire = (
                    dt.datetime.now() + dt.timedelta(seconds=resu["refresh_expires_in"])
                ).strftime("%Y-%m-%d %H:%M:%S")
                self.unauth = {}
                self.config_save = True
            except Exception as e:
                _log.error("Could not refresh authorisation token: {}".format(e))
                return
        else:
            self.et_login()

    # Get all devices associated with the site
    def start_discovery(self):
        # Lets get our sites
        if self.discovering:
            # Already busy
            return
        self.discovering = True
        if self.token is None:
            self.et_login()

        if self.token is None:
            _log.error("Cannot get devices. Token not available.")
            self.discovering = False
            return

        if not self.site:
            # No site configured yet... Bailing out
            self.discovering = False
            return

        headers = {"Authorization": "Bearer " + self.token, "accept-version": "2.0.0"}
        try:
            resu = requests.get(self.siteUri, headers=headers, verify=CHECKSSL)
            assert resu.status_code == 200
            allsites = json.loads(resu.text)
        except Exception as e:
            _log.error("Could not get list of sites. Error: {}".format(e))
            self.discovering = False
            return
        _log.debug("Got site list: {}".format([x["name"] for x in allsites]))
        haderror = False
        old_devices_ids = [x for x in self.device_list.keys()]
        try:
            for asite in allsites:
                if asite["name"] in self.site:
                    # Let's get the devices
                    try:
                        resu = requests.get(
                            self.devicesUri.format(asite["id"]),
                            headers=headers,
                            verify=CHECKSSL,
                        )
                        assert resu.status_code == 200
                        alldevs = json.loads(resu.text)
                    except Exception as e:
                        _log.error(
                            f"Could not get list of devices for {asite['name']}. Error: {e}"
                        )
                        haderror = True
                        continue

                    # _log.debug(f"Got device list for {asite['name']}: {[x['name'] for x in alldevs}")
                    for adev in alldevs:
                        newdev = EnerTDevice(self, adev["id"])
                        newdev.set_subdevice_name(0, adev["name"])
                        newdev.site = asite["name"]
                        try:
                            newdev.tz = pytz.timezone(self.timezones[asite["name"]])
                        except:
                            newdev.tz = pytz.timezone(self.default_timezone)
                        self.register_new_device(newdev)
                        if newdev.device_id in old_devices_ids:
                            old_devices_ids.remove(newdev.device_id)
            for old_dev in old_devices_ids:
                self.unregister_device(old_dev)
        except Exception as e:
            _log.error(f"Problem when retrieving devices. Error: {e}")
            # _log.exception(e)
            haderror = True

        if not haderror:
            self.config_save = True

        self.discovering = False

    #
    def _device_thread(self):
        """Checking and publishing device data for all sensors
        """
        while not self.terminate:
            devid = self.requestqueue.get()
            headers = {
                "Authorization": "Bearer " + self.token,
                "accept-version": "2.0.0",
            }
            if self.terminate:
                # This is the end My Friend
                _log.debug("End of device thread. This is the end my friend.")
                self.requestqueue.task_done()
                return
            _log.debug(
                "Fetching for device {} with token {}".format(
                    self.device_list[devid].name_subdevices, self.token
                )
            )
            try:
                resu = requests.get(
                    self.infoUri.format(devid),
                    headers=headers,
                    timeout=7,
                    verify=CHECKSSL,
                )
                assert resu.status_code == 200
                self.device_list[devid].set_sensor_data(json.loads(resu.text))
                self.device_list[devid].online_status(True)
            except AssertionError:
                _log.error(
                    "Problem getting data for {}. Return code: {}".format(
                        self.device_list[devid].name_subdevices, resu.status_code
                    )
                )
                if resu.status_code == 401:  # What do you mean unauthotrized?
                    if devid in self.unauth:
                        self.unauth[devid] += 1
                    else:
                        self.unauth[devid] = 1
                    val = 0
                    for x in self.unauth.values():
                        val += x
                    if val >= len(self.device_list) + 1:
                        self.refresh_expire = (
                            "2019-11-17 12:00:00"  # First diagnosed COVID-19 case
                        )
                        self.token_expire = "2019-11-17 12:00:00"
            except Exception as e:
                _log.error(
                    "Problem getting data for {}. Error: {}".format(
                        self.device_list[devid].name_subdevices, e
                    )
                )
                _log.exception(e)
                self.device_list[devid].online_status(False)

            self.requestqueue.task_done()

    def send_samples(self):
        for devid in self.device_list:
            self.requestqueue.put(devid)

    @Core.schedule(periodic(60))
    def manage_token(self):
        if not self.skipfirst:
            try:
                if (
                    dt.datetime.strptime(self.refresh_expire, "%Y-%m-%d %H:%M:%S")
                    < dt.datetime.now()
                ):
                    _log.debug(
                        "Refresh Token expired at {}".format(self.refresh_expire)
                    )
                    self.et_login()
                elif (
                    dt.datetime.strptime(self.token_expire, "%Y-%m-%d %H:%M:%S")
                    < dt.datetime.now()
                ):
                    _log.debug("Token expired at {}".format(self.token_expire))
                    self.et_refresh()
                else:
                    _log.debug(
                        "No token expired: Token {}, Refresh {}".format(
                            self.token_expire, self.refresh_expire
                        )
                    )
            except:
                _log.debug("Problem with manage token. Probably not logged in yet")
            if self.isloggedin == False:
                # Try login in
                self.et_login()
        else:
            self.skipfirst = False

        if self.config_save:
            self.config_save = False
            self.save_config()


def main():
    """Main method called to start the agent."""
    utils.vip_main(enertalk, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
