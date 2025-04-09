"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import json
import sys

from volttron.platform.agent import utils
from volttron.platform.scheduling import periodic
from volttron.platform.vip.agent import Agent

from altolib import AltoHealth

from .calculators import *

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def calculator_factory(devtype):
    if devtype == "general":
        return GeneralCalculator
    elif devtype == "engineering":
        return EngineeringCalculator
    else:
        raise NotImplementedError(f"Unknown device type {devtype}")


def calculator(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Calculator
    :rtype: Calculator
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    calculator_type = config.get("calculator_type", "general")
    calculate_interval = config.get('calculate_interval', '5sec')
    allowed_delay = config.get('allowed_delay', '5sec')
    constants = config.get('constants', dict())
    raw_inputs = config.get('raw_inputs', dict())
    agg_inputs = config.get('agg_inputs', dict())
    calculated_points = config.get('calculated_points', None)

    return Calculator(calculator_type, constants, raw_inputs, agg_inputs, calculated_points, calculate_interval, allowed_delay, **kwargs)


class Calculator(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, calculator_type, constants, raw_inputs, agg_inputs, calculated_points, calculate_interval, allowed_delay, **kwargs):
        super(Calculator, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.calculator_type = calculator_type
        self.calculate_interval = calculate_interval
        self.allowed_delay = allowed_delay
        self.constants = constants
        self.raw_inputs = raw_inputs
        self.agg_inputs = agg_inputs
        self.calculated_points = calculated_points
        self.calculator: BaseCalculator = None

        self.variables = dict()
        self.results = dict()
        self.location = None

        self.default_config = {
            "calculator_type": calculator_type,
            "calculate_interval": calculate_interval,
            "allowed_delay": allowed_delay,
            "constants": constants,
            "raw_inputs": raw_inputs,
            "agg_inputs": agg_inputs,
            "calculated_points": calculated_points,
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=[
                                  "NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        # Step 1: Parse the configuration file
        try:
            calculator_type = config.get('calculator_type', 'general')
            calculate_interval = config.get('calculate_interval', '5sec')
            allowed_delay = config.get('allowed_delay', 10)
            constants = config.get('constants', dict())
            raw_inputs = config.get('raw_inputs', dict())
            agg_inputs = config.get('agg_inputs', dict())
            calculated_points = config.get('calculated_points', None)

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        # Step 2: Validate that all the required parameters are present
        assert len(
            raw_inputs) > 0, "raw_inputs must be specified in the config file"
        assert calculated_points is not None, "calculated_points must be specified in the config file"

        # Step 3: Initialize the agent class variables
        self.calculate_interval = calculate_interval
        self.allowed_delay = allowed_delay
        self.constants = constants
        self.raw_inputs = raw_inputs
        self.agg_inputs = agg_inputs
        self.calculated_points = calculated_points
        self.calculator = calculator_factory(
            calculator_type)(self.allowed_delay)

        # Step 4: Subscribe to all the topics in the raw_inputs dictionary
        for topic in self.raw_inputs.keys():
            self._create_subscriptions(topic)

        # Step 5: Add defined constants to self.variables dictionary
        for c_name, value in self.constants.items():
            self.variables[c_name] = {
                "value": value,
                "unix_timestamp": float('inf')
            }

        # Step 6: Define custom heartbeat and health payload
        self.custom_health = AltoHealth(self.core, self.vip.pubsub, heartbeat_period=60, verbose=False)

        # Set intial status for functions and devices
        self.function_names = [
            "calculate_data",
            "update_agg_variables",
            "_evaluate_formula",
            "_emit_output"
        ]
        self.device_names = list(self.calculated_points.keys())
        self.custom_health.set_pending_status(names=self.function_names, type_label='function')
        self.custom_health.set_pending_status(names=self.device_names, type_label='device')

        # Track function status (need to use this approach to pass `self` into decorator function)
        self.calculate_data = AltoHealth.track_status(self.custom_health)(self.calculate_data)
        self.update_agg_variables = AltoHealth.track_status(self.custom_health)(self.update_agg_variables)
        self._evaluate_formula = AltoHealth.track_status(self.custom_health)(self._evaluate_formula)
        self._emit_output = AltoHealth.track_status(self.custom_health)(self._emit_output)

        # Step 7: Schedule the calculate_data function to run at the specified interval
        self.core.schedule(periodic(self.calculate_interval), self.calculate_data)

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        _log.debug("Subscribing to topic: {}".format(topic))
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """

        if isinstance(message, str):
            message = json.loads(message)

        # Step 1: Attempt to update location
        location = message.get('location', None)
        if location is not None:
            self.update_location(location)

        # Step 2: Parse all relevant parameters from received message
        subdevice_idx = str(message.get('subdevice_idx', 0))
        datapoint_mapping = self.raw_inputs[topic].get(subdevice_idx, dict())

        if not datapoint_mapping:
            return

        # Step 3: Iterate through every tracked variables and update them if datapoint exists in the received message
        for datapoint, var_name in datapoint_mapping.items():
            value = message.get(datapoint, None)
            if value is None:
                # _log.debug(f"No value for datapoint {datapoint} in message from topic {topic}")
                continue
            self.variables[var_name] = {
                "value": value,
                "unix_timestamp": message.get('unix_timestamp', int(time.time())),
            }

    def calculate_data(self):
        """
        Periodically calculate the specified calculated datapoint and publish to the output topic
        """
        # Step 1: Update the aggregated variables into self.variables dictionary (currently only supports LIST aggregation)
        self.update_agg_variables()

        # Step 2: Reset result dictionary
        self.results = dict()

        # Step 3: Iterate through every device_id
        for device_id, calculated_point in self.calculated_points.items():

            # Step 4: Iterate through every point to be calculated
            for point_name, point_config in calculated_point.items():

                # Step 5: Check if all variables are available
                formula = point_config.get('formula', None)

                if formula is None:
                    _log.debug(f"No formula specified for {device_id}/{point_name}")
                    continue

                # Step 6: Evaluate the formula and calculate the result for each specified calculated datapoint
                result = self._evaluate_formula(formula)
                if result:
                    if self.results.get(device_id) is None:
                        self.results[device_id] = {point_name: result}
                    else:
                        self.results[device_id][point_name] = result
                    self.custom_health.update_status_payload(name=device_id, type_label="device", status="GOOD", context="")
                else:  # Failed to evaluate formula
                    self.custom_health.update_status_payload(name=device_id, type_label="device", status="MISSING_DATA", context="")
                    continue

        # Step 7: Emit the calculated data to the desired output
        self._emit_output()

    def update_location(self, location):
        """
        Update the location of the agent
        """
        if self.location is None:
            self.location = location
            _log.debug(f"location updated at location: {location}")
        elif location != self.location:
            self.location = location
            _log.debug(f"location updated at location: {location}")

    def update_agg_variables(self):
        """
        Update aggregated variables from latest raw_inputs values

        Current supported data format of agg_inputs:
        - List

        """

        for var_name, value in self.agg_inputs.items():
            if isinstance(value, list):
                l = list()
                for item in value:
                    var_data = self.variables.get(item, None)
                    if var_data is None:
                        l = list()
                        break
                    l.append(self.variables[item].get("value", None))

                self.variables[var_name] = {
                    "value": l,
                    "unix_timestamp": int(time.time())
                }
            else:
                _log.debug(
                    f"Unsupported data format for aggregated variable {var_name}")

    def _evaluate_formula(self, formula):
        """
        Evaluate a formula and return the result
        """
        try:
            result = self.calculator.evaluate_formula(formula, self.variables)
            return result
        except Exception as e:
            _log.error(f"Error evaluating formula {formula}: {e}")
            return None

    def _emit_output(self):

        if self.results is None:
            _log.debug("No result to emit")
            return

        # Step 1: Iterate through every device_id and each calculated point of that device
        now_timestamp = int(time.time())
        for device_id, device_calculated_data in self.results.items():

            for calculated_point, value in device_calculated_data.items():

                # Step 2: Construct payload for the output
                payload = {
                    "device_id": device_id,
                    "subdevice_idx": 0,
                    "type": f"calculated_{calculated_point}",
                    "unix_timestamp": now_timestamp,
                    calculated_point: value,
                }
                if self.location is not None:  # Only add location if it is not None
                    payload["location"] = self.location

                # Step 3: Publish data to message bus
                self.vip.pubsub.publish(
                    peer='pubsub',
                    topic=f'calculated/{self.core.identity}/{device_id}/event',
                    message=payload
                )
                _log.debug(f"Published data to message bus for {device_id}:{calculated_point} = {value}")

def main():
    """Main method called to start the agent."""
    utils.vip_main(calculator,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
