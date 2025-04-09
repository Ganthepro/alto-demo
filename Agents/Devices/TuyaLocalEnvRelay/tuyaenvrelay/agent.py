"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from altolib import (
    AltoEnvironSensor,
    AltoDeviceSensor,
    AltoSwitchDevice,
    AltoSensor,
    AltoSwitch,
    AltoBridgeAgent,
)
from altoutils.tuya.local import LocalTuya

from gevent import spawn, joinall
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from zmq import device

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def device_factory(devtype):
    if devtype == 'tuya_env_relay':
        return
    
    raise Exception(f'Unknown device type: {devtype}')


class TuyaEnvRelay(AltoEnvironSensor, AltoDeviceSensor, AltoSwitchDevice):
    
    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        self._ip_address = ip_address
        self._local_key = local_key
        self._device_name = device_name
        self.TUYAENVMAP = {
            "temperature": "6",
            "probe_switch_state": "1",
            "temperature_calibration": "18"
        }
        self.TUYADEVICEMAP = {
            "device_status": "device_status"
        }
        self.datapoint_supported['device'] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported['environment'] = [x for x in self.TUYAENVMAP.keys()]

        self._tuya = LocalTuya(devid, ip_address, local_key)
        self.offline_count = 0
        self.sample_init()
    
    def sample_init(self):
        self.data_map.update(self.TUYAENVMAP)
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data('device', self.TUYADEVICEMAP.keys())
        self.initialise_data('environment', self.TUYAENVMAP.keys())

    def get_status(self):
        vals_env = {}
        vals_read = {}
        rev_read = {}
        for k, v in self.TUYAENVMAP.items():
            rev_read[v] = k

        try:
            ret = self._tuya.get_status()
            if "Err" in ret:
                if self.offline_count == 5:
                    self._emit_device_data({
                        "device_status": "offline"
                    })
                    _log.warning(f"TuyaEnvRelay {self._device_name} is offline")
                    return
                _log.warning(f"TuyaEnvRelay get_status Failed: {self._device_name}")
                self.offline_count += 1
                return
            
            self.offline_count = 0
            for data, value in ret['dps'].items():
                if data in self.TUYAENVMAP.values():
                    vals_env[data] = value
                    vals_read[rev_read[data]] = value
            self._emit_environment_data(vals_env)
            self._emit_device_data({
                "device_status": "online"
            })
            _log.info(f"TuyaEnvRelay get_status: {self._device_name} {vals_read}")
        except Exception as status_err:
            _log.error(f"TuyaEnvRelay get_status status Exception: {status_err}")

    def turn_on(self, subdev):
        ret = self._tuya.set_command(str(subdev+2), True)
        if "Err" in ret:
            _log.warning(f"TuyaEnvRelay turn_on Failed: {self._device_name}")
        else:
            self.update_switch_state(subdev, "on")
            _log.info(f"TuyaEnvRelay turn_on: {self._device_name} Done")

    def turn_off(self, subdev):
        ret = self._tuya.set_command(str(subdev+2), False)
        if "Err" in ret:
            _log.warning(f"TuyaEnvRelay turn_off Failed: {self._device_name}")
        else:
            self.update_switch_state(subdev, "off")
            _log.info(f"TuyaEnvRelay turn_off: {self._device_name} Done")

    def _emit_environment_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAENVMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="environment")
        except Exception as e:
            _log.error(f"TempHumidBatteryDevice _emit_environment_data: Exception {e}")

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"TempHumidBatteryDevice _emit_device_data: Exception {e}")
        

def tuyaenvrelay(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyaenvrelay
    :rtype: Tuyaenvrelay
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    topic = config.get("topic", "")
    for x, y in zip(
        [
            "devices",
            "agent_name",
            "timezone",
            "default_timezone",
            "sampling_rate"
        ],
        [{}, "", "Asia/Bangkok", "", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyaenvrelay(topic, **kwargs)


class Tuyaenvrelay(AltoBridgeAgent, AltoSwitch, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyaenvrelay, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}
    
    def _build_device(self, devtype, dev_id, nb_subdev, ip_address, local_key, dev_name):
        if dev_id not in self.device_list:
            sensor = device_factory(devtype)
            newdev = sensor(self, dev_id, nb_subdev, ip_address, local_key, dev_name)
            self.register_new_device(newdev)
        
    def send_samples(self):
        spawn_list = []
        for k, v in self.device_list.items():
            try:
                spawn_list.append(spawn(v.get_status))
            except Exception as err:
                _log.error(f"send_samples: Exception {err}")
        joinall(spawn_list)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)
        self.device_list = {}
        for k, v in self.devices.items():
            self._build_device(v[0], k, v[1], v[2], v[3], v[4])

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyaenvrelay, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
