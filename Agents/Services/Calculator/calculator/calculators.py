import logging
import math
import re
import time
from abc import ABC, abstractmethod
from pythermalcomfort import pmv
from pythermalcomfort.utilities import v_relative

_log = logging.getLogger(__name__)


class BaseCalculator(ABC):

    def __init__(self, allowed_delay: float):
        self.allowed_delay = allowed_delay

    @abstractmethod
    def evaluate_formula(self, formula: str, variables: dict):
        """
        Evaluates a formula with variables

        ! Every Calculator class must implement this method

        Args:
            formula (str): Formula to evaluate
            variables (dict): Variables to use in the formula with following format:
            variables = {
                "variable_name_1": {
                    "value": 576.1,
                    "unix_timestamp": 1234567890
                }, ....
            }

        Returns:
            float: Result of the formula

        """
        return None


class GeneralCalculator(BaseCalculator):

    def evaluate_formula(self, formula: str, variables: dict):

        # Step 1: Extract all variables used in the formula using Regex
        var_list = re.findall("[a-zA-Z_][a-zA-Z0-9_]*", formula)

        # Step 2: Check validity of variables
        for var_name in var_list:
            # Step 2.1: Check if variable exists in the list of tracked variables
            var_data = variables.get(var_name, None)
            if var_data is None:
                _log.debug(f"Variable {var_name} is not defined")
                return False

            # Step 2.2: Check whether every variable has valid value abd is up-to-date
            value = var_data.get("value", None)
            unix_timestep = var_data.get("unix_timestamp", None)
            if value is None or unix_timestep is None:
                _log.debug(f"Variable {var_name} is not defined")
                return False
            elif (int(time.time()) - unix_timestep) > self.allowed_delay:
                _log.debug(f"Variable {var_name} is outdated")
                return False

        # Step 3: Try evaluating the formula and store result in `result` variable
        try:
            formula = re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*)', r'variables["\1"]["value"]', formula)
            result = eval(formula)
            return result
        except Exception as e:
            _log.debug(f"Getting error `{e}` while evaluating formula: {formula}")
            return None


class EngineeringCalculator(BaseCalculator):

    def evaluate_formula(self, formula: str, variables: dict):
        """
        Evaluates a formula with given variables

        The formula should be a string in the format of:

        <formula_name>(arg1, arg2, arg3, ...)    ex. "calculate_efficiency(plant_power, plant_btu)"

        where arg1, arg2, arg3, ... are the names of variables used in the formula specified in the config files

        """
        # Step 1: Extract all variables used in the formula using Regex
        var_list = re.findall("\(([^.]+)\)", formula)[0]
        var_list = [var.strip() for var in var_list.split(",")]

        # Step 2: Get function and function parameters' name
        func_name = re.findall("([^\(]+)\(", formula)[0]
        func = getattr(self, func_name)
        params_list = list(func.__code__.co_varnames)

        # Step 2: Get and check validity of variables to be used as arguments
        args_dict = {}
        for var_name, param_name in zip(var_list, params_list):

            var_data = variables.get(var_name, None)

            if var_data is None:
                _log.debug(f"Variable {var_name} is not defined")
                return None
            elif (int(time.time()) - var_data["unix_timestamp"]) > self.allowed_delay:
                _log.debug(f"Variable {var_name} is outdated")
                return None
            else:
                args_dict[param_name] = var_data["value"]

        # Step 3: Try evaluating the formula
        return func(**args_dict)

    @staticmethod
    def calculate_efficiency(power, capacity):
        """
        Calculates the efficiency in the unit of kW/TR from the following parameters,
        - power (float): power in kW
        - capacity (float): capacity in TR
        """
        return power / capacity

    @staticmethod
    def calculate_part_load_percentage(ch_cap_list, ch_status_list, load):
        """
        Calculates the part load percentage in % from the following parameters,
        - ch_cap_list (list): List of chiller capacities from in-paper specification in TR
        - ch_status_list (list): List of chiller status (0: OFF, 1: ON)
        - load (float): Cooling load in TR
        """

        if len(ch_cap_list) != len(ch_status_list):
            return None
        
        running_cap = 0
        for ch_cap, ch_status in zip(ch_cap_list, ch_status_list):

            # Try to parse ch_status to float
            try:
                ch_status = float(ch_status)
            except:
                pass

            if isinstance(ch_status, float):
                if ch_status == 3:
                    on_or_off = 1
                else:
                    on_or_off = 0
            elif isinstance(ch_status, str):
                ch_status = ch_status.replace('"', '').replace("'", '')
                if ch_status.lower() == "on":
                    on_or_off = 1
                else:
                    on_or_off = 0
            else:
                _log.error(f"Invalid chiller status: {ch_status}")
                return None

            running_cap += ch_cap * on_or_off

        return round(load / running_cap * 100, 2)
    
    @staticmethod
    def calculate_wb_from_db_and_rh(tdb, rh):
        """
        Calculates the chiller plant capacity in TR from the following parameters,
        - tdb (float): Dry-bulb temperature in Celcius
        - rh (float): Relative humidity in %

        Return wetbulb temperature in Farenheight
        """
        val_C = round(
            tdb * math.atan(0.151977 * (rh + 8.313659) ** (1 / 2))
            + math.atan(tdb + rh)
            - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** (3 / 2) * math.atan(0.023101 * rh)
            - 4.686035,
            1,
        )

        val_F = round(val_C * 9 / 5 + 32, 2)

        return val_F

    @staticmethod
    def calculate_load_from_flowrate_and_delta_t(flow_rate, delta_t):
        """
        Calculates load in TR from flowrate and delta T from the following parameters,
        - flow_rate (float): Flow rate in unit of gallons per minute
        - delta_t (float): Temperature difference in Fahrenheit
        """
        rho = 62.414  # Water density in lb/ft^3
        cp = 1.0007642  # Water specific heat capacity in BTU/lb/F

        load = 8.021 * rho * cp * flow_rate * delta_t / 12000

        return load

    @staticmethod
    def calculate_pmv(tdb, tr, v, rh, met, clo):
        """
        Calculates PMV

        Args:
            tdb (float): Dry-bulb temperature in Celcius
            tr (float): Mean radiant temperature in Celcius
            v (float): Air velocity in m/s
            rh (float): Relative humidity in %
            met (float): Metabolic rate in met
            clo (float): Clothing insulation coefficient

        Returns:
            float: PMV value

        """

        return pmv(tdb=tdb, tr=tr, vr=v_relative(v, met), rh=rh, met=met, clo=clo)
