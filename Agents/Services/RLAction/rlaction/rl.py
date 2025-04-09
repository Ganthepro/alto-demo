import warnings
import time
import datetime as dt

import pandas as pd
import numpy as np

# from stable_baselines3 import PPO

from rlaction import (_log,
                      AltoNotImpl,
                      PMVCalculation)


def rl_factory(dtype):
    if dtype == "hvac_rl":
        return HVACRL
    if dtype == "ahu_rl":
        return AHURL
    if dtype == "pmv_rl":
        return PMVRL

    raise Exception(f"Unknown rl {dtype}")


class BaseRL:

    def __init__(self, controller, rl_id, rl_en, input_man, rl_en_update):
        """
        rl_id: "ex_rl" # unique identifier for this RL
        input_man: [list of BaseManipulation]
        rl_en: True/False # enable or disable this RL
        """

        self._controller = controller
        self._rl_id = rl_id
        self._rl_en = rl_en
        self._input_man = input_man
        self._rl_en_update = rl_en_update
        self._is_updated = False
        self._rl_output = []
        """
        _rl_output = [out1, out2, ...]
        """

        _log.debug(f"BaseRL init {self._rl_id} {self._rl_en} {self._input_man} {self._rl_en_update}")

    def _set_is_updated(self):
        self._is_updated = True

    def _reset_is_updated(self):
        self._is_updated = False
    
    @property
    def is_updated(self):
        return self._is_updated

    @property
    def rl_output(self):
        return self._rl_output

    def enable_rl(self):
        self._rl_en = True
        # self.emit_rl_state()

    def disable_rl(self):
        self._rl_en = False
        # self.emit_rl_state()

    def enable_rl_update(self):
        self._rl_en_update = True
        # self.emit_rl_state()

    def disable_rl_update(self):
        self._rl_en_update = False
        # self.emit_rl_state()

    def _is_input_man_updated_and_not_none(self):
        is_man_updated = True
        is_data_none = False
        if not self._input_man:
            return False
        for i in self._input_man:
            if not i.check_update():
                is_man_updated = False
                break
            if not i.data:
                is_data_none = True
                break
            if i.data["out1"] is None:
                is_data_none = True
                break
        if is_man_updated and not is_data_none:
            return True
        return False

    def emit_rl_state(self, data_in: dict = {}):
        output_topic = f'''rein/{self._controller.core.identity}/{self._rl_id}/event'''
        data = {
            "device_id": self._rl_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_state",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "rl_enable": self._rl_en,
            "rl_update_enable": self._rl_en_update,
        }
        data.update(data_in)
        _log.debug(f"BaseRL emit_rl_state {self._rl_id} {data}")
        self._controller.publish(output_topic, data, "event")

    def decide_and_act(self, data):
        """
        Method that MUST be overridden to do input/output decission
        """

        raise AltoNotImpl("decide_and_act method must be implemented")


class HVACRL(BaseRL):

    def __init__(self, controller, rl_id, rl_en, input_man, rl_en_update, model_path):
        warnings.warn("In HVACRL, this class shall be removed soon.", DeprecationWarning)
        super().__init__(controller, rl_id, rl_en, input_man, rl_en_update)
        self._model_path = model_path
        self._model = None
        self._load_model()

    def decide_and_act(self):
        warnings.warn("In HVACRL, this class shall be removed soon.", DeprecationWarning)
        try:
            _log.debug(f"HVACRL decide_and_act {self._rl_id} current_rl_output {self._rl_output}")

            rl_input = {}
            rl_output = {}
            self._reset_is_updated()
            if self._is_input_man_updated_and_not_none():
                if self._rl_en:
                    self._get_action()
                    for idx, i in enumerate(self._input_man):
                        rl_input[f'''rl_input_{idx}'''] = i.data["out1"]
                    for idx, i in enumerate(self._rl_output):
                        rl_output[f'''rl_output_{idx}'''] = i
                    self._set_is_updated()

            if self._rl_en_update:
                output_topic = f'''rein/{self._controller.core.identity}/{self._rl_id}/event'''
                tmp_model_path = self._model_path.split("/")
                model_version = "unknown"
                if len(tmp_model_path) > 0:
                    if ".zip" in tmp_model_path[-1]:
                        model_version = tmp_model_path[-1].replace(".zip", "")
                data = {
                    "device_id": self._rl_id,
                    "subdevice_idx": 0,
                    "subdevice_name": "subdev_0",
                    "type": "rl",
                    "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
                    "unix_timestamp": time.time(),
                    "model_version": model_version,
                    "is_data_updated": self._is_updated,
                }
                data.update(rl_input)
                data.update(rl_output)
                _log.debug(f"HVACRL decide_and_act {self._rl_id} {self._is_updated} {self._rl_output}")
                self._controller.publish(output_topic, data, "event")
            self.emit_rl_state()
                    
        except Exception as e:
            _log.error(f"HVACRL decide_and_act {self._rl_id} {e}")

    def _load_model(self):
        """Load the model from a zip-file

        Returns:
            object: ppo model
                action_space = Box([21.], [30.], (1,), float32)
                obs_space = Box([10. 10. 10. 10. 10.  0.], [5.e+01 5.e+01 5.e+01 5.e+01 5.e+01 1.e+08], (6,), float32)
        """

        # self._model = PPO.load(path=self._model_path)

    def _get_action(self) -> None:
        """
        Observations
        1. OutdoorDrybulbTemp
        2. OutdoorWetbulbTemp
        3. ThermalZoneWorkingSpace1BTemp
        4. ThermalZoneWorkingSpace1BDewpointTemp
        5. Zone Mean Radiant Temperature [C]
        6. ElectricityFacility
        """

        input_list = []
        for i in self._input_man:
            input_list.append(i.data["out1"])
        obs = np.array(input_list)
        action = self._model.predict(obs, deterministic=True)
        # model = PPO.load(path=self._model_path)
        # action = model.predict(obs, deterministic=True)
        # action is np.ndarray|tuple [[]]
        _log.debug(f'''HVACRL get_action {type(action)} {action[0]}''')
        self._rl_output = []
        for i in action[0]:
            self._rl_output.append(int(i))


class AHURL(BaseRL):

    def __init__(self, controller, rl_id, rl_en, input_man, rl_en_update, co2_min, co2_max):
        super().__init__(controller, rl_id, rl_en, input_man, rl_en_update)
        self._co2_min = co2_min
        self._co2_max = co2_max

    def decide_and_act(self):
        try:
            _log.debug(f"AHURL decide_and_act {self._rl_id} current_rl_output {self._rl_output} co2 min,max {self._co2_min} {self._co2_max}")

            rl_input = {}
            rl_output = {}
            self._reset_is_updated()
            if self._is_input_man_updated_and_not_none():
                if self._rl_en:
                    self._get_action()
                    for idx, i in enumerate(self._input_man):
                        rl_input[f'''rl_input_{idx}'''] = i.data["out1"]
                    for idx, i in enumerate(self._rl_output):
                        rl_output[f'''rl_output_{idx}'''] = i
                    self._set_is_updated()

            if self._rl_en_update:
                output_topic = f'''rein/{self._controller.core.identity}/{self._rl_id}/event'''
                model_version = "unknown"
                data = {
                    "device_id": self._rl_id,
                    "subdevice_idx": 0,
                    "subdevice_name": "subdev_0",
                    "type": "rl",
                    "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
                    "unix_timestamp": time.time(),
                    "model_version": model_version,
                    "is_data_updated": self._is_updated,
                }
                data.update(rl_input)
                data.update(rl_output)
                _log.debug(f"AHURL decide_and_act {self._rl_id} {self._is_updated} {self._rl_output}")
                self._controller.publish(output_topic, data, "event")
            self.emit_rl_state()
        except Exception as e:
            _log.error(f"AHURL decide_and_act {self._rl_id} {e}")

    def _get_action(self) -> None:
        if self._input_man[0].data["out1"] > self._co2_max:
            self._rl_output = ["on",]
        elif self._input_man[0].data["out1"] < self._co2_min:
            self._rl_output = ["off",]
        else:
            self._rl_output = ["nop",]


class PMVRL(BaseRL):

    # def __init__(self, controller, rl_id, rl_en, input_man, rl_en_update, max_iteration, min_pmv, max_pmv):
    def __init__(self, controller, rl_id, rl_en, input_man, rl_en_update, **kwargs):
        super().__init__(controller, rl_id, rl_en, input_man, rl_en_update)
        self._max_iteration = kwargs.get("max_iteration", 11)
        self._min_pmv = kwargs.get("min_pmv", 0.0)
        self._max_pmv = kwargs.get("max_pmv", 1.0)

        self.met = kwargs.get("met", 1.4)
        self.clo = kwargs.get("clo", 0.685)
        self.v = kwargs.get("v", 0.1)

    def decide_and_act(self):
        try:
            _log.debug(f"PMVRL decide_and_act {self._rl_id} current_rl_output {self._rl_output} max_iteration {self._max_iteration}")

            rl_input = {}
            rl_output = {}
            self._reset_is_updated()
            if self._is_input_man_updated_and_not_none():
                if self._rl_en:
                    self._get_action()
                    for idx, i in enumerate(self._input_man):
                        rl_input[f'''rl_input_{idx}'''] = i.data["out1"]
                    for idx, i in enumerate(self._rl_output):
                        rl_output[f'''rl_output_{idx}'''] = i
                    self._set_is_updated()
                else:
                    self._set_none_rl_output()
            else:
                self._set_none_rl_output()

            if self._rl_en_update:
                output_topic = f'''rein/{self._controller.core.identity}/{self._rl_id}/event'''
                model_version = "unknown"
                data = {
                    "device_id": self._rl_id,
                    "subdevice_idx": 0,
                    "subdevice_name": "subdev_0",
                    "type": "rl",
                    "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
                    "unix_timestamp": time.time(),
                    "model_version": model_version,
                    "is_data_updated": self._is_updated,
                }
                data.update(rl_input)
                data.update(rl_output)
                _log.debug(f"PMVRL decide_and_act {self._rl_id} {self._is_updated} {self._rl_output}")
                self._controller.publish(output_topic, data, "event")
            self.emit_rl_state()
        except Exception as e:
            _log.error(f"PMVRL decide_and_act {self._rl_id} {e}")

    def emit_rl_state(self):
        pmv_rl_state = {
            "rl_min_pmv": self._min_pmv,
            "rl_max_pmv": self._max_pmv
        }
        super().emit_rl_state(pmv_rl_state)

    def _set_none_rl_output(self):
        if len(self._rl_output) > 0:
            self._rl_output = [None,]

    def _get_action(self) -> None:
        self._set_none_rl_output()
        pmv_val = self._input_man[0].data["out1"] # current pmv value
        set_temp = self._input_man[1].data["out1"] # current set_temperature
        indoor_air_temp = self._input_man[2].data["out1"] # current air temp
        indoor_air_humid = self._input_man[3].data["out1"] # current air humid

        if pmv_val >= self._min_pmv and pmv_val <= self._max_pmv:
            return
        
        _log.debug(f"PMVRL _get_action {self._rl_id} {pmv_val}")
        it = 0
        while it < self._max_iteration:
            if pmv_val < self._min_pmv:
                set_temp += 1
                indoor_air_temp += 1
            elif pmv_val > self._max_pmv:
                set_temp -= 1
                indoor_air_temp -= 1
            
            # pmv_val = PMVCalculation.calc_pmv(indoor_air_temp, indoor_air_humid)
            pmv_val = PMVCalculation.calc_pmv_with_constant(indoor_air_temp, 
                        indoor_air_humid, 
                        self.met, 
                        self.clo, 
                        self.v)
            _log.debug(f"PMVRL _get_action {self._rl_id} {it} {pmv_val}")

            it += 1
            if pmv_val >= self._min_pmv and pmv_val <= self._max_pmv:
                break

        if set_temp < 23:
            set_temp = 23
        elif set_temp > 29:
            set_temp = 29
        self._rl_output = [set_temp,]

    def update_min_pmv(self, value):
        self._min_pmv = value
        self._controller.update_rls_min_pmv(self._rl_id, value)
    
    def update_max_pmv(self, value):
        self._max_pmv = value
        self._controller.update_rls_max_pmv(self._rl_id, value)

