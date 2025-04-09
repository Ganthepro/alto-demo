"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from gevent import spawn, joinall

from altolib import (
    AltoDimmerDevice,
    AltoDimmer,
    AltoDeviceSensor,
    AltoSensor,
    AltoBridgeAgent,
)
from altoutils.tuya.cloud import TuyaAuth, TuyaAPI, TuyaSwitch

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


def device_factory(devtype: str):
    if devtype == "tuya_dimmer":
        return DimmerSwitchDevice

    raise Exception(f"Unknown device type: {devtype}")


class DimmerSwitchDevice(AltoDimmerDevice, AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, tuya_api, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self.TUYADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status"
        }
        self.device_name = device_name
        self._tuya_switch = TuyaSwitch(devid, tuya_api)
        self.datapoint_supported['device'] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()

    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data('device', self.TUYADEVICEMAP.keys())
    
    def get_status(self):
        ret_info = self._tuya_switch.get_information()
        try:
            if ret_info['success']:
                status = "online" if ret_info['result']['online'] else "offline"
                _log.info(f"DimmerSwitchDevice get_status device_status: {status}")
                device_data = {
                    "device_status": status,
                    "online_status": ret_info['result']['online']
                }
                self._emit_device_data(device_data)
                if status == "offline":
                    return
            else:
                _log.warning(f"DimmerSwitchDevice get_status failed: {ret_info['result']}")
        except Exception as err:
            _log.error(f"DimmerSwitchDevice get_status Error: {err}")
        
        vals_read = {}
        ret = self._tuya_switch.get_status()
        try:
            if ret['success']:
                for payload in ret['result']:
                    if payload['code'] == "switch_led":
                        state = "on" if payload['value'] else "off"
                        self.update_switch_state(0, state)
                        vals_read.update({payload['code']: state})
                    elif payload['code'] == "bright_value":
                        self.update_bright_value(0, payload['value'])
                        vals_read.update({payload['code']: payload['value']})
                _log.info(f"DimmerSwitchDevice get_status status: {vals_read}")
        except Exception as err:
            _log.error(f"DimmerSwitchDevice get_status Error: {err}")

    def turn_on(self, subdev):
        body = {
            "commands": [
                {
                    "code": "switch_led",
                    "value": True
                }
            ]
        }
        ret = self._tuya_switch.turn_on(body)
        try: 
            if ret['result']:
                self.update_switch_state(subdev, "on")
                _log.debug(f"DimmerSwithDevice turn_on {self.device_name} success")
            else:
                _log.warning(f"DimmerSwitchDevice turn_on {self.device_name} failed")
        except Exception as err:
            _log.error(f"DimmerSwitchDevice turn_on Error: {self.device_name} {err}")
    
    def turn_off(self, subdev):
        body = {
            "commands": [
                {
                    "code": "switch_led",
                    "value": False
                }
            ]
        }
        ret = self._tuya_switch.turn_on(body)
        try: 
            if ret['result']:
                self.update_switch_state(subdev, "off")
                _log.debug(f"DimmerSwithDevice turn_off {self.device_name} success")
            else:
                _log.warning(f"DimmerSwitchDevice turn_off {self.device_name} failed")
        except Exception as err:
            _log.error(f"DimmerSwitchDevice turn_off Error: {self.device_name} {err}")
    
    def set_dimmer_value(self, subdev, value):
        value_range = [0, 255]
        if value >= value_range[0] and value <= value_range[1]:
            body = {
                "commands": [
                    {
                        "code": "bright_value",
                        "value": value
                    }
                ]
            }
            ret = self._tuya_switch.set_bright_value(body)
            try:
                if ret['result']:
                    self.update_bright_value(subdev, value)
                    _log.debug(f"DimmerSwithDevice set_dimmer_value {self.device_name} success")
                else:
                    _log.warning(f"DimmerSwitchDevice set_dimmer_value {self.device_name} failed")
            except Exception as err:
                _log.error(f"DimmerSwitchDevice set_dimmer_value Error: {self.device_name} {err}")
        else:
            _log.warning(f"Dimmer value out of range!")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"DimmerSwitchDevice _emit_deivce_data: Exception {e}")


def tuyaswitch(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyaswitch
    :rtype: Tuyaswitch
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get('topic', "")

    for x, y in zip(
        [
            "devices",
            "agent_name",
            "timezones",
            "default_timezone",
            "sampling_rate"
        ],
        [
            {},
            "tuya_switch",
            "Asia/Bangkok",
            "Asia/Bangkok",
            60
        ]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyaswitch(topic, **kwargs)


class Tuyaswitch(AltoBridgeAgent, AltoSensor, AltoDimmer):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyaswitch, self).__init__(topic, **kwargs)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

        self.tuya_api = None

        _log.debug("vip_identity: " + self.core.identity)
    
    def _build_device(self, dev_type, dev_id, nb_subdev, device_name):
        if dev_id not in self.device_list:
            Sensor = device_factory(dev_type)
            newdev = Sensor(self, dev_id, nb_subdev, self.tuya_api, device_name)
            self.register_new_device(newdev)
    
    def send_samples(self):
        spawn_list = []
        for k, v in self.device_list.items():
            try:
                spawn_list.append(spawn(v.get_status))
            except Exception as e:
                _log.error(f"Tuyasocketagent send_samples: Exception {e}")
        joinall(spawn_list)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.tuya_api = TuyaAPI(
            TuyaAuth(
                self.tuya_credential["client_id"],
                self.tuya_credential["client_secret"]
                )
            )
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, v[1], v[2])

    
    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyaswitch, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
