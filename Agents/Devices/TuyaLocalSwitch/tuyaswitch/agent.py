"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from gevent import spawn, joinall
from gevent.queue import Queue
from gevent.lock import BoundedSemaphore

from altolib import (AltoSwitchDevice, 
                     AltoSwitch, 
                     AltoDeviceSensor, 
                     AltoSensor, 
                     AltoBridgeAgent,
                     AltoSchemaError)
from altoutils.tuya.local import LocalTuya

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def device_factory(devtype):
    if devtype == "tuya_switch":
        return TuyaSwitchDevice

    raise Exception(f"Unknown device type: {devtype}")


class TuyaSwitchDevice(AltoSwitchDevice, AltoDeviceSensor):

    def __init__(self, controller, devid, nb_subdev, ip_address, local_key, device_name, **kwargs):
        super().__init__(controller, devid, nb_subdev)
        for idx in range(self.number_subdevices):
            self.current_state[idx]["switch"].update({
                "event_status": "success"
            }) # # event_status: ["success", "failed"]
        self.TUYADEVICEMAP = {
            "online_status": "online_status",
            "device_status": "device_status",
            "device_name": "device_name"
        }
        self.device_name = device_name
        self.datapoint_supported['device'] = [x for x in self.TUYADEVICEMAP.keys()]
        self._sample_init()
        self.offline_count = 0
        self.queue = Queue()
        self.bounded_sem = BoundedSemaphore(1)

        self._tuya = LocalTuya(devid, ip_address, local_key)

    def _sample_init(self):
        self.data_map.update(self.TUYADEVICEMAP)
        self.initialise_data("device", self.TUYADEVICEMAP.keys())
    
    def get_status(self):
        was_updated = False
        ret = self._tuya.get_status()
        if "Err" in ret:
            if self.offline_count == 18:
                self._emit_device_data({
                    "device_name": self.device_name,
                    "online_status": False,
                    "device_status": "offline"
                })
                _log.warning(f"TuyaSwitchDevice get_status Failed: {self.device_name}, return: {ret}")
                self.offline_count = 0
                return
            self.offline_count += 1
            return
        
        self.offline_count = 0
        if self.number_subdevices == 1:
            if "1" in ret['dps']:
                states = "on" if ret['dps']["1"] == True else "off"
                was_updated = self.update_switch_state(0, states)
                if was_updated:
                    self._emit_event_relay(0)
                _log.info(f"TuyaSwitchDevice get_status: {self.device_name}, state_1: {states}")
            else:
                _log.warning(f"TuyaSwitchDevice get_status: {self.device_name}, data lost")
                return
        elif self.number_subdevices == 2:
            if ("1" in ret['dps']) and ("2" in ret['dps']):
                states = {
                    0: "on" if ret['dps']["1"] == True else "off",
                    1: "on" if ret['dps']["2"] == True else "off"
                }
                for sub_dev, state in states.items():
                    was_updated = self.update_switch_state(sub_dev, state)
                    if was_updated:
                        self._emit_event_relay(sub_dev)
                _log.info(f"TuyaSwitchDevice get_status: {self.device_name}, state_1: {states[0]}")
                _log.info(f"TuyaSwitchDevice get_status: {self.device_name}, state_2: {states[1]}")
            else:
                _log.warning(f"TuyaSwitchDevice get_status: {self.device_name}, data lost")
                return
        elif self.number_subdevices == 3:
            if ("1" in ret['dps']) and ("2" in ret['dps']) and ("3" in ret['dps']):
                states = {
                    0: "on" if ret['dps']["1"] == True else "off",
                    1: "on" if ret['dps']["2"] == True else "off",
                    2: "on" if ret['dps']["3"] == True else "off"
                }
                for sub_dev, state in states.items():
                    was_updated = self.update_switch_state(sub_dev, state)
                    if was_updated:
                        self._emit_event_relay(sub_dev)
                _log.info(f"TuyaSwitchDevice get_status: {self.device_name}, state_1: {states[0]}")
                _log.info(f"TuyaSwitchDevice get_status: {self.device_name}, state_2: {states[1]}")
                _log.info(f"TuyaSwitchDevice get_status: {self.device_name}, state_3: {states[2]}")
            else:
                _log.warning(f"TuyaSwitchDevice get_status: {self.device_name}, data lost")
                return
        self._emit_device_data({
            "device_name": self.device_name,
            "online_status": True,
            "device_status": "online"
        })
    
    def turn_on_off_queue(self, command, subdev):
        acquire_ret = False
        try:
            acquire_ret = self.bounded_sem.acquire(blocking=True, timeout=9)
        except Exception as e:
            _log.error(f"_process_derived_and_manipulations_data acquire {e}")
        if acquire_ret:
            if self.queue.empty():
                try:
                    self.queue.put_nowait({"command": command, "subdev": subdev})
                    self.execute_command_queue()
                except Exception as e:
                    _log.error(f"TuyaSwitchDevice turn_on_queue Error: {e} ")
            else:
                try:
                    self.queue.put_nowait({"command": command, "subdev": subdev})
                except:
                    _log.error(f"TuyaSwitchDevice turn_on_queue Error: {e}")
        try:
            self.bounded_sem.release()
        except ValueError:
            _log.error("_process_derived_and_manipulations_data, the semaphore is being over-released")
        except Exception as e:
            _log.error(f"_process_derived_and_manipulations_data release {e}")
    
    def execute_command_queue(self):
        try:
            cmd = self.queue.get_nowait()
            if cmd['command'] == "on":
                self.turn_on(cmd['subdev'])
            elif cmd['command'] == "off":
                self.turn_off(cmd['subdev'])
            self.execute_command_queue()
        except Exception as e:
            _log.error(e)

    def turn_on(self, subdev):
        _log.debug(f"TuyaSwitchDevice turn_on: {self.device_name}, subdev: {subdev}")
        ret = self._tuya.set_command(str(subdev+1), True)
        if "Err" in ret:
            self.update_event_status(subdev, "failed")
            _log.warning(f"TuyaSwitchDevice turn_on Failed: {self.device_name}, subdev: {subdev}, return: {ret}, event_status: failed")
        else:
            self.update_event_status(subdev, "success")
            self.update_switch_state(subdev, "on")
            _log.info(f"TuyaSwitchDevice turn_on: {self.device_name}, subdev: {subdev}, event_status: success")
        self._emit_event_relay(subdev)
    
    def turn_off(self, subdev):
        _log.debug(f"TuyaSwitchDevice turn_off: {self.device_name}, subdev: {subdev}")
        ret = self._tuya.set_command(str(subdev+1), False)
        if "Err" in ret:
            self.update_event_status(subdev, "failed")
            _log.warning(f"TuyaSwitchDevice turn_off Failed: {self.device_name}, subdev: {subdev}, return: {ret}, event_status: failed")
        else:
            self.update_event_status(subdev, "success")
            self.update_switch_state(subdev, "off")
            _log.info(f"TuyaSwitchDevice turn_off: {self.device_name}, subdev: {subdev}, event_status: success")
        self._emit_event_relay(subdev)
        
    def update_event_status(self, subdev, event):
        self.current_state[subdev]['switch']['event_status'] = event

    def update_switch_state(self, subdevice, state):
        """
        Method to be invoked whenever a switch state information is received.
        This method will check if a change is detected and will broadcast the
        'relay' event if needed.
        :param subdevice: The name or index of the subdevice
        :type subevice: int or string
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

    def _emit_device_data(self, data):
        try:
            vals = {}
            for k, v in data.items():
                if k in self.TUYADEVICEMAP.values():
                    vals[k] = v
            self.set_sensor_data({**vals}, subdevice=0, sensor_type="device")
        except Exception as e:
            _log.error(f"TuyaOneGangSwitch _emit_device_data Error: {e}")
    
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

    topic = config.get("topic", "")
    for x, y in zip([
        "devices",
        "agent_name",
        "timezone",
        "default_timezone",
        "sampling_rate"
    ],
    [{}, "tuya_switch", "Asia/Bangkok", "", 120]
    ):
        kwargs[x] = config.get(x, y)

    return Tuyaswitch(topic, **kwargs)


class Tuyaswitch(AltoBridgeAgent, AltoSwitch, AltoSensor):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Tuyaswitch, self).__init__(topic, **kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._sampling_rate_cd = 15
        self.auto_send = True
        self.sample_lock = {}

    def _build_device(self, devtype, dev_id, nb_subdev, ip_address, local_key, dev_name):
        if dev_id not in self.device_list:
            Sensor = device_factory(devtype)
            newdev = Sensor(self, dev_id, nb_subdev, ip_address, local_key, dev_name)
            self.register_new_device(newdev)

    def send_samples(self):
        spawn_list = []
        for k, v in self.device_list.items():
            try:
                spawn_list.append(spawn(v.get_status))
            except Exception as e:
                _log.error(f"Tuyaswitch send_samples Error: {e}")
        joinall(spawn_list)
    
    def handle_command_switch(self, topic, message) -> None:
        """
             Handle the commands meant for the switch schema. Essentially the 'relay' command.
        """
        if len(topic) != 2:
            raise AltoSchemaError("Switch command handler cannot parse topic")

        devid, func = topic
        if func == "command":
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev == "all":
                losubdev = range(0, self.device_list[devid].number_subdevices)
            else:
                losubdev = [self.device_list[devid].subdevice_name_to_idx(subdev)]
                # _log.debug(f"Switch {losubdev}")
            if message["state"].lower() == "on":
                for subdev in losubdev:
                    # _log.debug(f"Switch on {subdev}")
                    # self.device_list[devid].turn_on(subdev)
                    self.device_list[devid].turn_on_off_queue("on", subdev)
            elif message["state"].lower() == "off":
                for subdev in losubdev:
                    # self.device_list[devid].turn_off(subdev)
                    self.device_list[devid].turn_on_off_queue("off", subdev)
            else:
                raise AltoSchemaError(
                    f"Error: {message['state']} is not a valid value for a switch state"
                )
        else:
            _log.warning(f"Command {func} is not know to the switch schema")

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
    
    def emit_event_relay(
        self, dev: AltoSwitchDevice, subdevice_idx: int
    ) -> None:

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

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def get_device_status(self):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return [{dev, instance.get_device_status()} for dev, instance in self.device_list.items()]


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
