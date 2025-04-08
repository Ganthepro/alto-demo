import time
import datetime as dt

import pandas as pd
import numpy as np

# from stable_baselines3 import PPO

from rlaction import (_log,
                      AltoNotImpl,
                      PMVCalculation)


def output_device_factory(dtype):
    if dtype == "hvac_output":
        return HVACOutput
    if dtype == "ahu_output":
        return AHUOutput
    if dtype == "itm_oau_output":
        return ITMOAUOutput

    raise Exception(f"Unknown output_device {dtype}")


class OutputDevice:

    def __init__(self, controller, input_rl, output_id, output_enable: bool):
        """
        input_rl: [base_rl_1, rl_output_index]
        """

        self._controller = controller
        self._input_rl = input_rl
        self._output_id = output_id
        self._output_device_id = output_id.split(":;")[0]
        self._subdev_number = int(output_id.split(":;")[1])

        self._output_enable = output_enable

        _log.debug(f"OutputDevice init {self._output_id} {self._input_rl} {self._output_enable}")

    def __str__(self):
        return "output_device"

    # @property
    # def output_device_id(self):
    #     return self._output_device_id

    # @property
    # def subdev_number(self):
    #     return self._subdev_number

    def enable_output(self):
        self._output_enable = True
        # self.emit_rl_output_state()
        self._controller.update_output_devices_enable(self._output_id, self._output_enable)

    def disable_output(self):
        self._output_enable = False
        # self.emit_rl_output_state()
        self._controller.update_output_devices_enable(self._output_id, self._output_enable)

    @property
    def output_enable(self):
        return self._output_enable

    def _is_rl_updated(self):
        is_rl_updated = True
        if not self._input_rl:
            return False
        if not self._input_rl[0].is_updated:
            is_rl_updated = False
        if is_rl_updated:
            return True
        return False

    def process_output(self):
        """
        Method that MUST be overridden to receive the actual data
        """

        raise AltoNotImpl("data_in method must be implemented")

    def emit_rl_output(self, is_data_updated):
        """
        Method that MUST be overridden to emit rl_output
        """

        raise AltoNotImpl("emit_rl_output method must be implemented")

    def emit_rl_output_state(self):
        output_topic = f'''rein_output/{self._controller.core.identity}/{self._output_id}/event'''
        data = {
            "device_id": self._output_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_output_state",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "output_enable": self._output_enable,
        }
        _log.debug(f"BaseRL emit_rl_output_state {self._output_id} {data}")
        self._controller.publish(output_topic, data, "event")


class HVACOutput(OutputDevice):

    def __init__(self, controller, input_rl, output_id, output_enable):
        super().__init__(controller, input_rl, output_id, output_enable)
        self._output_temperature = None

    def __str__(self):
        return "hvac_output"

    def process_output(self):
        """
        process output from rl input data
        """
        
        try:
            if self._is_rl_updated():
                if len(self._input_rl[0].rl_output)>self._input_rl[1]:
                    self._output_temperature = self._input_rl[0].rl_output[self._input_rl[1]]
                    if self._output_temperature is not None:
                        if isinstance(self._output_temperature, (float, int)):
                            if self._output_temperature < 18.0:
                                self._output_temperature = 18.0
                            if self._output_temperature > 29.0:
                                self._output_temperature = 29.0
                            if self._output_temperature >= 18.0 and self._output_temperature <= 29.0:
                                self.emit_output()
                self.emit_rl_output(True)
            else:
                if len(self._input_rl[0].rl_output)>self._input_rl[1]:
                    self._output_temperature = self._input_rl[0].rl_output[self._input_rl[1]]
                    if self._output_temperature is not None:
                        self._output_temperature = 27.0 # default temp
                        self.emit_output()
                self.emit_rl_output(False)
            self.emit_rl_output_state()
        except Exception as e:
            _log.error(f"HVACOutput process_output {self._output_id} {e}")

    def emit_output(self):
        if self._output_enable:
            self._controller.emit_ac_temperature(self._output_device_id, self._output_temperature)

    def emit_rl_output(self, is_data_updated):
        output_topic = f'''rein_output/{self._controller.core.identity}/{self._output_id}/event'''
        data = {
            "device_id": self._output_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_output",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "is_data_updated": is_data_updated,
            "output_temperature": self._output_temperature,
        }
        _log.debug(f"HVACOutput process_output {self._output_id} {data}")
        self._controller.publish(output_topic, data, "event")


class AHUOutput(OutputDevice):

    def __init__(self, controller, input_rl, output_id, output_enable):
        super().__init__(controller, input_rl, output_id, output_enable)
        self._output_state = None

    def __str__(self):
        return "ahu_output"

    def process_output(self):
        """
        process output from rl input data
        """

        try:
            if self._is_rl_updated() and len(self._input_rl[0].rl_output)>0:
                self._output_state =  self._input_rl[0].rl_output[self._input_rl[1]]
                if isinstance(self._output_state, str):
                    if self._output_state == "on" or self._output_state == "off":
                        self.emit_output()
                self.emit_rl_output(True)
            else:
                self._output_state = "on" # default on
                self.emit_output()
                self.emit_rl_output(False)
            self.emit_rl_output_state()
        except Exception as e:
            _log.error(f"AHUOutput process_output {self._output_id} {e}")

    def emit_output(self):
        if self._output_enable:
            self._controller.emit_relay_state(self._output_device_id, self._subdev_number, self._output_state)

    def emit_rl_output(self, is_data_updated):
        output_topic = f'''rein_output/{self._controller.core.identity}/{self._output_id}/event'''
        data = {
            "device_id": self._output_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_output",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "is_data_updated": is_data_updated,
            "output_state": self._output_state,
        }
        _log.debug(f"AHUOutput process_output {self._output_id} {data}")
        self._controller.publish(output_topic, data, "event")


class ITMOAUOutput(OutputDevice):

    def __init__(self, controller, input_rl, output_id, output_enable):
        super().__init__(controller, input_rl, output_id, output_enable)
        self._output_state = None

    def __str__(self):
        return "itm_oau_output"

    def process_output(self):
        """
        process output from rl input data
        """
        try:
            if self._is_rl_updated() and len(self._input_rl[0].rl_output)>0:
                self._output_state =  self._input_rl[0].rl_output[self._input_rl[1]]
                if isinstance(self._output_state, str):
                    if self._output_state == "on" or self._output_state == "off":
                        self.emit_output()
                self.emit_rl_output(True)
            else:
                self._output_state = "on" # default on
                self.emit_output()
                self.emit_rl_output(False)
            self.emit_rl_output_state()
        except Exception as e:
            _log.error(f"ITMOAUOutput process_output {self._output_id} {e}")

    def emit_output(self):
        if self._output_enable:
            self._controller.emit_itm_oau_state(self._output_device_id, self._subdev_number, self._output_state)

    def emit_rl_output(self, is_data_updated):
        output_topic = f'''rein_output/{self._controller.core.identity}/{self._output_id}/event'''
        data = {
            "device_id": self._output_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_output",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "is_data_updated": is_data_updated,
            "output_state": self._output_state,
        }
        _log.debug(f"ITMOAUOutput process_output {self._output_id} {data}")
        self._controller.publish(output_topic, data, "event")

