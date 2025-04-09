"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from altolib import (
    AltoSwitchDevice,
    AltoSwitch,
    AltoElectricSensor,
    AltoDeviceSensor,
    AltoSensor,
    AltoBridgeAgent,
)
from altoutils.tuya.local import LocalTuya

from gevent import spawn, joinall
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.1"


def device_factory(devtype):
    if devtype == "tuya_plug_elec":
        return TuyaPlugElectric
    elif devtype == "tuya_wall_socket":
        return WallSocketDevice
    
    raise f"TuyaLocalPlug Device Factory Error, No {devtype} in device factory found"


class TuyaPlugElectric(AltoElectricSensor, AltoDeviceSensor, AltoSwitchDevice):

    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        for idx in range(self.number_subdevices):
            self.current_state[idx]['switch'].update({
                "event_status": "success"
            })

        self.TUYAELECTRICMAP = {
            "current": "18",
            "power": "19",
            "voltage": "20",
            "energy": "17"
        }
        self.TUYADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
        }
        self._device_name = device_name
        self.offline_count = 0

        self.datapoint_supported['device'] = [x for x in self.TUYADEVICEMAP.keys()]
        self.datapoint_supported['electric'] = [y for y in self.TUYAELECTRICMAP.keys()]

        self._tuya = LocalTuya(devid, ip_address, local_key)
        self._sample_init()

    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.data_map.update(self.TUYAELECTRICMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
        self.initialise_data("electric", self.TUYAELECTRICMAP.keys())

    def get_status(self):
        was_update = False
        vals_elec = {}
        vals_read = {}
        rev_map = {}
        for k, v in self.TUYAELECTRICMAP.items():
            rev_map[v] = k

        ret = self._tuya.get_status()
        if "Err" in ret:
            if self.offline_count == 18:
                self._emit_device_data({
                    "device_name": self._device_name,
                    "online_status": False,
                    "device_status": "offline"
                })
                _log.warning(f"TuyaPlugElectric get_status Failed: {self._device_name}, return: {ret}")
                self.offline_count = 0
                return
            self.offline_count += 1
            return

        self.offline_count = 0
        for data, value in ret['dps'].items():
            if data == "1":
                state = "on" if ret['dps'][data] else "off"
                was_update = self.update_switch_state(0, state)
                if was_update:
                    self._emit_event_relay(0)
                    _log.info(f"TuyaPlugElectric get_status: {self._device_name}, Switch State Changed to {state}")
                vals_read['state'] = state
            if data in self.TUYAELECTRICMAP.values():
                vals_elec[data] = value
                vals_read[rev_map[data]] = value
        self._emit_electric_data(vals_elec)
        self._emit_device_data({
            "online_status": True,
            "device_status": "online"
        })
        _log.info(f"TuyaPlugElectric get_status: {self._device_name}, data: {vals_read}")

    def turn_on(self, subdev):
        _log.debug(
            f"TuyaPlugElectric Received Turn On Request: {self._device_name}, subdev: {subdev}")
        ret = self._tuya.set_command("1", True)
        if "Err" in ret:
            self.update_event_status(subdev, "failed")
            _log.warning(
                f"TuyaPlugElectric Turn On Failed: {self._device_name}, return: {ret}")
        else:
            self.update_event_status(subdev, "success")
            self.update_switch_state(subdev, "on")
            _log.info(
                f"TuyaPlugElectric Turn On Success: {self._device_name}, subdev: {subdev}")
        self._emit_event_relay(subdev)

    def turn_off(self, subdev):
        _log.debug(
            f"TuyaPlugElectric Received Turn Off Request: {self._device_name}, subdev: {subdev}")
        ret = self._tuya.set_command("1", False)
        if "Err" in ret:
            self.update_event_status(subdev, "failed")
            _log.warning(
                f"TuyaPlugElectric Turn Off Failed: {self._device_name}, return: {ret}")
        else:
            self.update_event_status(subdev, "success")
            self.update_switch_state(subdev, "off")
            _log.info(
                f"TuyaPlugElectric Turn Off Success: {self._device_name}, subdev: {subdev}")
        self._emit_event_relay(subdev)

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as err:
            _log.error(f"TuyaPlugElectric _emit_device_data Error: {err}")

    def _emit_electric_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYAELECTRICMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="electric")
        except Exception as err:
            _log.error(f"TuyaPlugElectric _emit_electric_data Error: {err}")

    def update_event_status(self, subdev, event):
        self.current_state[subdev]['switch']['event_status'] = event

    def update_switch_state(self, subdevice, state):
        """
        Method to be invoked whenever a switch state information is received.
        This method will check if a change is detected and will broadcast the
        'relay' event if needed.
        :param subdevice: The name or index of the subdevice
        :type subdevice: int or string
        :param state: The state, "on" or "off"
        :type state: str
        """
        subdevice_idx = self.subdevice_name_to_idx(subdevice)
        # _log.debug(f"\n\nSwitch current state {self.current_state[subdevice_idx]}")
        if self.current_state[subdevice_idx]["switch"]["state"] != state:
            _log.debug(
                f"Switch from {self.current_state[subdevice_idx]['switch']['state']} to {state}"
            )
            self.current_state[subdevice_idx]["switch"]["state"] = state
            # self.event_switch_state_change(subdevice_idx)
            return True
        return False

    def _emit_event_relay(self, subdevice_idx: int) -> None:
        """
        Method used to signal on the Volttron bus that a relay state change has
        been detected. In most cases, this should nopt be called directly, :func: update_switch_state
        should be used.
        """
        self.controller.emit_event_relay(self, subdevice_idx)

    def switch_event_status(self, subdev):
        return self.current_state[subdev]['switch']['event_status']

    def switch_state(self, subdev):
        return self.current_state[subdev]['switch']['state']
    
    def to_electric_voltage(self, val):
        return round(float(val/10), 2)

    def to_electric_current(self, val):
        return round(float(val/1000), 2)

    def to_electric_power(self, val):
        return round(float(val/1000), 2)

    def to_electric_energy(self, val):
        return round(float(val/1000), 2)


class WallSocketDevice(AltoSwitchDevice, AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        for idx in range(self.number_subdevices):
            self.current_state[idx]['switch'].update({
                "event_status": "success"
            })

        self.TUYADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
            "device_name": "device_name",
        }
        self._device_name = device_name
        self.offline_count = 0

        self.datapoint_supported['device'] = [x for x in self.TUYADEVICEMAP.keys()]

        self._tuya = LocalTuya(devid, ip_address, local_key)
        self._sample_init()

    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())

    def get_status(self):
        map_dps_subdev = {
            "1": 0,
            "2": 1
        }
        was_update = False
        vals_read = {}

        ret = self._tuya.get_status()
        if "Err" in ret:
            if self.offline_count == 18:
                self._emit_device_data({
                    "online_status": False,
                    "device_status": "offline"
                })
                _log.warning(
                    f"WallSocketDevice get_status Failed: {self._device_name}, return: {ret}"
                )
                self.offline_count = 0
                return
            self.offline_count += 1
            return

        self.offline_count = 0
        for data, value in ret['dps'].items():
            if data in map_dps_subdev:
                state = "on" if value else "off"
                was_update = self.update_switch_state(map_dps_subdev[data], state)
                if was_update:
                    self._emit_event_relay(map_dps_subdev[data])
                    _log.info(f"WallSocketDevice get_status: {self._device_name}, Switch State Changed to {state}")
                vals_read.update({f'state_{data}': state})
        self._emit_device_data({
            "online_status": True,
            "device_status": "online"
        })
        _log.info(f"WallSocketDevice get_status: {self._device_name} {vals_read}")

    def turn_on(self, subdev):
        _log.debug(f"WallSocketDevice Received Turn On Request: {self._device_name}, subdev: {subdev}")
        ret = self._tuya.set_command(str(subdev + 1), True)
        if "Err" in ret:
            self.update_event_status(subdev, "failed")
            _log.warning(f"WallSocketDevice Turn On Failed: {self._device_name}, return: {ret}")
        else:
            self.update_event_status(subdev, "success")
            self.update_switch_state(subdev, "on")
            _log.info(f"WallSocketDevice Turn On Success: {self._device_name}, subdev: {subdev}")
        self._emit_event_relay(subdev)

    def turn_off(self, subdev):
        _log.debug(f"WallSocketDevice Received Turn Off Request: {self._device_name}, subdev: {subdev}")
        ret = self._tuya.set_command(str(subdev + 1), False)
        if "Err" in ret:
            self.update_event_status(subdev, "failed")
            _log.warning(f"WallSocketDevice Turn Off Failed: {self._device_name}, return: {ret}")
        else:
            self.update_event_status(subdev, "success")
            self.update_switch_state(subdev, "off")
            _log.info(f"WallSocketDevice Turn Off Success: {self._device_name}, subdev: {subdev}")
        self._emit_event_relay(subdev)

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as err:
            _log.error(f"TuyaPlugElectric _emit_device_data Error: {err}")

    def update_event_status(self, subdev, event):
        self.current_state[subdev]['switch']['event_status'] = event

    def update_switch_state(self, subdevice, state):
        """
        Method to be invoked whenever a switch state information is received.
        This method will check if a change is detected and will broadcast the
        'relay' event if needed.
        :param subdevice: The name or index of the subdevice
        :type subdevice: int or string
        :param state: The state, "on" or "off"
        :type state: str
        """
        subdevice_idx = self.subdevice_name_to_idx(subdevice)
        # _log.debug(f"\n\nSwitch current state {self.current_state[subdevice_idx]}")
        if self.current_state[subdevice_idx]["switch"]["state"] != state:
            _log.debug(f"Switch from {self.current_state[subdevice_idx]['switch']['state']} to {state}")
            self.current_state[subdevice_idx]["switch"]["state"] = state
            # self.event_switch_state_change(subdevice_idx)
            return True
        return False

    def _emit_event_relay(self, subdevice_idx: int) -> None:
        """
        Method used to signal on the Volttron bus that a relay state change has
        been detected. In most cases, this should nopt be called directly, :func: update_switch_state
        should be used.
        """
        self.controller.emit_event_relay(self, subdevice_idx)

    def switch_event_status(self, subdev):
        return self.current_state[subdev]['switch']['event_status']

    def switch_state(self, subdev):
        return self.current_state[subdev]['switch']['state']


def tuyalocalsocket(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tuyalocalplug
    :rtype: Tuyalocalplug
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get('topic', "")
    for x, y in zip([
        "devices", 
        "agent_name", 
        "timezone", 
        "default_timezone", 
        "sampling_rate"
    ],
    [
        {},
        "tuya_plug",
        "Asia/Bangkok",
        "", 
        60
    ]):
        kwargs[x] = config.get(x, y)

    return Tuyalocalsocket(topic, **kwargs)


class Tuyalocalsocket(AltoBridgeAgent, AltoSwitch, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyalocalsocket, self).__init__(topic, **kwargs)
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
        _log.debug(f"TuyaPlug send_sample")
        for k, v in self.device_list.items():
            try:
                spawn_list.append(spawn(v.get_status))
            except Exception as err:
                _log.error(f"Tuyalocalplug send_sample Error: {err}")
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

    def emit_event_relay(self, dev: AltoSwitchDevice, subdevice_idx: int) -> None:
        topic = (
            self.topic + "switch/" + self.agent_name + "/" + dev.device_id + "/event"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "state": dev.switch_state(subdevice_idx),
            "event_status": dev.switch_event_status(subdevice_idx),
            "type": "relay"
        }
        self.publish(topic, payload, "event")


def main():
    """Main method called to start the agent."""
    utils.vip_main(tuyalocalsocket,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
