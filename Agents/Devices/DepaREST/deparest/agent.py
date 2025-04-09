"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import requests
import json
import time
import datetime as dt

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

class WellFineAuth:

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._base_url = "http://energyz.wellfinetech.co.th"
        self._get_access_token()

    def _get_access_token(self) -> dict:
        url = "/api/v1/user/login"
        header = {
            "Content-Type": "application/json"
        }
        body = {
            "username": self._username,
            "password": self._password
        }
        try:
            response = requests.post(self._base_url + url, headers=header, data=json.dumps(body))
            if response.ok:
                r = response.json()
                self._access_token = r["data"]["token"] 
                _log.debug(f"WellfineAuth _get_access_token: Success")
                return r
            return False
        except Exception as e:
            _log.error(f"WellFineAuth _get_access_token: Exception {e}")
        
    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def base_url(self) -> str :
        return self._base_url

class WellFineAPI:

    def __init__(self, wellfine_auth: object):
        self._wellfine_auth = wellfine_auth
    
    def get_placelist(self) -> dict:
        url = "/api/v1/place/placelist"
        header = {
            "Content-type": "application/x-www-form-urlencoded",
            "token": self._wellfine_auth.access_token
        }
        try:
            response = requests.get(self._wellfine_auth.base_url + url, headers=header)
            if response.ok:
                r = response.json()
                _log.debug(f"WellfineAPI get_placelist: Success")
                return r
            return False
        except Exception as e:
            _log.error(f"WellFine API get_placelist: Exception {e}")

    def get_meter_data(self, place_id: str) -> dict:
        url = f"/api/v1/place/places/{place_id}/meters"
        header = {
            "Content-type": "application/x-www-form-urlencoded",
            "token": self._wellfine_auth.access_token
        }
        try:
            response = requests.get(self._wellfine_auth.base_url + url, headers=header)
            if response.ok:
                r = response.json()
                _log.debug(f"WellfineAPI get_meter_data: Success")
                return r
            return False
        except Exception as e:
            _log.error(f"WellFine API get_meter_data: Exception {e}")

def deparest(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Deparest
    :rtype: Deparest
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    sampling_rate = config.get("sampling_rate", 60)
    wellfine_credential = config.get("wellfine_credential", {})
    devices = config.get("devices", {})
    return Deparest(topic, sampling_rate, wellfine_credential, devices, **kwargs)


class Deparest(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, sampling_rate, wellfine_credential, devices, **kwargs):
        super(Deparest, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.topic = topic
        self.sampling_rate = sampling_rate
        self.wellfine_credential = wellfine_credential
        self.devices = devices

        self._wellfine_api = None

        self.default_config = {
                                "topic": topic,
                                "sampling_rate": sampling_rate,
                                "wellfine_credential": wellfine_credential,
                                "devices": devices
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
            topic = config["topic"]
            sampling_rate = config["sampling_rate"]
            wellfine_credential = config["wellfine_credential"]
            devices = config["devices"]

            self.topic = topic
            self.sampling_rate = sampling_rate
            self.wellfine_credential = wellfine_credential
            self.devices = devices
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        
        self._wellfine_api = WellFineAPI(WellFineAuth(self.wellfine_credential["username"], self.wellfine_credential["password"]))
        self.core.periodic(self.sampling_rate, self._get_meter_data)

    def _get_meter_data(self):
        try:
            DEVICE2NAMEMAP = {
                                "08d9b3ba-166c-49c2-8950-60d7df724510": "Khonkaen_NYKN",
                                "08d9b3b9-de0e-4277-8e50-05c9114c53b8": "Khonkaen_D",
                                "08d9b3c9-3dfd-486b-8e48-7fa34cdadb08": "Khonkaen_HNPW"
                            }
            electric_data = {
                                "voltage": "voltage",
                                "current": "current",
                                "power": "power",
                                "energy": "energy",
                                "energy_to_grid": "energy_to_grid",
                                "frequency": "frequency",
                                "power_factor": "power_factor"
                            }
            for k in self.devices.keys():
                ret = self._wellfine_api.get_meter_data(k) # place_id
                if not ret:
                    _log.error(f"Deparest _get_meter_data: Not success")
                    return False
                if ret["data"][0]["isOnline"]:
                    subdev_n = ["phase_A", "phase_B", "phase_C"]
                    meter_id = ret["data"][0]["id"]
                    for d in ret["data"][0]["lastDatas"]: # list of 3 phase meter value
                        subdev = ret["data"][0]["lastDatas"].index(d)
                        subdev_name = subdev_n[subdev]
                        i = 0
                        for k_e in electric_data.keys(): # parameters in single list of 3 phase meter
                            if k_e == "power":
                                electric_data[k_e] = d[i]/1000
                                i += 1
                            else:
                                electric_data[k_e] = d[i]
                                i += 1
                        self.emit_sensor_data(meter_id, subdev, subdev_name, electric_data)
                    t_electric_data = {
                                        "energy": round(ret["data"][0]["lastDatas"][0][3] + ret["data"][0]["lastDatas"][1][3] + ret["data"][0]["lastDatas"][2][3],3),
                                        "power": round((ret["data"][0]["lastDatas"][0][2] + ret["data"][0]["lastDatas"][1][2] + ret["data"][0]["lastDatas"][2][2])/1000,3),
                                        "current": round(ret["data"][0]["lastDatas"][0][1] + ret["data"][0]["lastDatas"][1][1] + ret["data"][0]["lastDatas"][2][1],3),
                                        "energy_to_grid": round(ret["data"][0]["lastDatas"][0][4] + ret["data"][0]["lastDatas"][1][4] + ret["data"][0]["lastDatas"][2][4],3)
                                    }
                    device_data = {
                        "type": "device",
                        "last_update": ret['data'][0]['lastUpdateTime'],
                        "online_status": True
                    }
                    self.emit_sensor_data(meter_id, subdev=0, subdev_name="subdev_0", sensor_data=device_data)
                    self.emit_sensor_data(meter_id, subdev=3, subdev_name="total", sensor_data=t_electric_data)
                else:
                    if ret["data"][0]["id"] in DEVICE2NAMEMAP.keys():
                        if "id" in ret["data"][0]:
                            meter_id = ret["data"][0]["id"]
                            device_data = {
                                "type": "device",
                                "last_update": ret['data'][0]['lastUpdateTime'],
                                "online_status": False
                            }
                            self.emit_sensor_data(meter_id, subdev=0, subdev_name="subdev_0", sensor_data=device_data)
                        _log.debug(f"This Device from {DEVICE2NAMEMAP[ret['data'][0]['id']]} is Offline")
                        _log.debug(f"lastUpdatedTime: {ret['data'][0]['lastUpdateTime']}")
        except Exception as e:
            _log.error(f"Deparest _get_meter_data: Exception {e}")

    def emit_sensor_data(self, meter_id, subdev, subdev_name, sensor_data: dict):
        output_topic = f'''sensor/{self.core.identity}/{meter_id}/event'''
        data = {
            "device_id": meter_id,
            "subdevice_idx": subdev,
            "subdevice_name": subdev_name, # subdev_0: phase_A, subdev_1: phase_B, subdev_2:phase_C
            "type": "electric",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time()
        }
        data.update(sensor_data)
        _log.debug(f"DepaREST emit_sensor_data: {meter_id} {data}")
        self.publish(output_topic, data, "event")

    def publish(self, topic, value, mtype):
        """
        Publish to the Volttron bus
        :param topic: The topic to publish to.
        :type topic: string
        :param value: The message payload
        :type value: as needed
        :param mtype: The type to set in the header, command, evemt, request or response.
        :returns: None
        :rtype: None
        """

        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            message=value,
            headers={
                "requesterID": self.core.identity,
                "message_type": mtype,
                "TimeStamp": dt.datetime.utcnow()
                .replace(tzinfo=dt.timezone.utc)
                .isoformat(),
            },
        )

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        pass

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
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(deparest, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
