"""
Chillerplantoptimization Agent Documentation

This agent optimizes the operation of a chiller plant system by providing optimal control actions for chiller sequencing, chilled water flow, condenser water flow, and cooling towers. It supports two modes of operation:

1. Copilot mode: The agent provides optimization suggestions without directly controlling the system. This is the default and currently only supported mode.

2. Autopilot mode: The agent directly controls the system based on its optimization decisions. This mode is not yet implemented.

Agent Configuration:
The agent requires a configuration file in YAML format that specifies:
- Device specifications for chillers, cooling towers, and other system components
- Location of the chiller plant
- Various operational settings and tolerances

Subscriptions:
The agent subscribes to the following topics on the message bus to receive data:
- datalogger/bacnet/settings/event: Receives current operational settings
- datalogger/bacnet/fdd/event: Receives fault detection and diagnosis information
- datalogger/bacnet/suggestion/event: Receives suggestion point values
- datalogger/bacnet/<device_id>/event: Receives state variable data for each device

Optimization Process:
Every 5 seconds, the agent performs the following optimization steps if the system is operating properly:

1. Checks for any critical system faults that should prevent optimization. Skips optimization if faults are detected.

2. Verifies state variables and settings were updated recently, otherwise skips optimization.

3. Placeholder for future ML-based optimization (not yet implemented).

4. Determines optimal control actions using engineering-based rules and logic for:
   - Chiller sequencing - optimal combination of chillers to run
   - Chilled water flow - optimal CHW flow rate
   - Condenser water flow - optimal CW flow rate
   - Cooling tower settings - optimal number of towers and fan speeds

5. Publishes the optimization results and suggestions to the message bus:
   - In copilot mode, results are published as suggestions
   - In autopilot mode, results would be published as control commands (not yet implemented)

The optimization logic takes into account the current system state, operational settings, equipment constraints, and incorporates temporal logic to make decisions only after key conditions are met for a certain duration.

Logging:
The agent logs informational messages to provide visibility into the optimization process and results at each time step. Debug level logs provide further details on the logic and decisions. Error messages are logged if issues occur that prevent successful optimization.
"""

__docformat__ = 'reStructuredText'

import logging
import re
import sys
import time

import pendulum
import yaml

from volttron.platform.agent import utils
from volttron.platform.scheduling import periodic
from volttron.platform.vip.agent import Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"
COMMON_KEYS = ['device_id', 'model', 'location', 'timestamp', 'datetime']


def chillerplantoptimization(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Chillerplantoptimization
    :rtype: Chillerplantoptimization
    """
    config = utils.load_config(config_path)
    if not config:
        raise "Site configuration file not found."

    # Get the device specification and location from config file
    device_specs = config['site_metadata']['device_specs']
    location = config['location']

    return Chillerplantoptimization(device_specs, location, **kwargs)


class Chillerplantoptimization(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, device_specs, location, **kwargs):
        super(Chillerplantoptimization, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.mode = 'copilot'  # Currently only 'copilot' mode is supported. Future modes will include 'autopilot'
        self.self_driving_status = False
        self.faults = dict()
        self.state_variables = dict()
        self.settings = dict()
        self.settings_updated_timestamp = 0
        self.constraints = dict()
        self.device_specs = device_specs
        self.location = location
        self.delay_timers = {
            'last_chiller_sequencing_timestamp': None,
            'last_smart_chw_flow_timestamp': None,
            'last_smart_cdw_flow_timestamp': None,
            'last_smart_ct_timestamp': None,
            
            'last_high_load_timestamp': None,
            'last_low_load_timestamp': None,
            'last_low_chw_delta_temperature_timestamp': None,
            'last_high_chw_delta_temperature_timestamp': None,
            'last_low_cdw_delta_temperature_timestamp': None,
            'last_high_cdw_delta_temperature_timestamp': None,
            'last_too_high_dpt_timestamp': None,
            'last_too_low_dpt_timestamp': None,
            'last_high_cds_temperature_timestamp': None,
            'last_low_cds_temperature_timestamp': None
        }
        self.agent_start_timestamp = time.time()

        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        if isinstance(contents, dict):
            config = contents
        else:
            try:
                config = yaml.safe_load(contents)
            except yaml.YAMLError as e:
                _log.error("Error parsing YAML:", e)
                return None


        try:
            # Get the device specification and location from config file
            device_specs = config['site_metadata']['device_specs']
            location = config['location']            
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.device_specs = device_specs
        self.location = location

        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix='datalogger',
                                  callback=self._handle_incoming_message)

        self.core.schedule(periodic(5), self.get_and_publish_optimal_control_actions)
        
    def _handle_incoming_message(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        if len(topic.split('/')) != 4:
            _log.error(f"Received message with invalid topic: {topic}")
            return

        _, _, device_id, message_type = topic.split('/')

        if message_type == 'event':
            if topic == 'datalogger/bacnet/settings/event':
                self._handle_settings(message)
            elif topic == 'datalogger/bacnet/fdd/event':
                self._handle_fdd(message)
            elif topic == 'datalogger/bacnet/suggestion/event':
                self._handle_suggestion_points(message)
            else:
                self._handle_device_state_variables(device_id, message)
                self.update_constraints()

    def _handle_suggestion_points(self, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        SUGGESTION_KEYS = [
            'trigger_chiller_sequencing',
            'suggested_chiller_sequence',
            'trigger_smart_chw_flow',
            'suggested_chw_flow_rate',
            'trigger_increase_chw_flow_from_dpt',
            'trigger_decrease_chw_flow_from_dpt',
            'trigger_increase_ct_frequency',
            'trigger_decrease_ct_frequency',
            'trigger_add_ct',
            'trigger_subtract_ct',
            'trigger_smart_cdw_flow',
            'suggested_cdw_flow_rate',
        ]

        missing_suggestion_points = set(SUGGESTION_KEYS) - set(message.keys())
        if missing_suggestion_points:
            _log.error(f"Missing suggestion points: {missing_suggestion_points}. Please ensure that these points are available for BACnet write commands.")
        else:
            _log.info(f"Received a complete set of suggestion points")

    def _handle_settings(self, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        self.settings = {k:v for k, v in message.items() if k not in COMMON_KEYS}
        self.settings_updated_timestamp = message['timestamp']

        SETTINGS_KEYS = [
            'self_driving_status',
            'self_driving_mode',

            'enable_chiller_sequencing',
            'max_chilled_water_return_temperature',
            'min_chilled_water_return_temperature',
            'max_setpoint_temperature_deviation',
            'max_chiller_percentage_rla',
            'min_chiller_percentage_rla',
            'high_load_tolerance_duration',
            'low_load_tolerance_duration',
            'chiller_sequencing_delay_duration',
            'chiller_priority',
            'enable_smart_chw_flow',
            'enable_dpt_control',
            'dpt_setpoint',
            'unmet_dpt_tolerance_duration',
            'min_schp_frequency',
            'design_chw_delta_temperature',
            'high_chw_delta_temperature_tolerance',
            'low_chw_delta_temperature_tolerance',
            'high_chw_delta_temperature_tolerance_duration',
            'low_chw_delta_temperature_tolerance_duration',
            'smart_chw_delay_duration',
            'enable_smart_ct',
            'target_ct_approach_temperature',
            'min_condenser_supply_temperature',
            'max_ct_frequency_for_addition',
            'min_ct_frequency',
            'min_ct_water_flow',
            'smart_ct_delay_duration',
            'enable_direct_cds_setpoint',
            'enable_smart_cdw_flow',
            'min_cdp_frequency',
            'design_cdw_delta_temperature',
            'high_cdw_delta_temperature_tolerance',
            'low_cdw_delta_temperature_tolerance',
            'high_cdw_delta_temperature_tolerance_duration',
            'low_cdw_delta_temperature_tolerance_duration',
            'smart_cdw_delay_duration',
            'enable_direct_cds_setpoint',
            'unmet_cdw_setpoint_tolerance_duration',
            'cds_setpoint_deviation_deadband',
        ]

        missing_settings = set(SETTINGS_KEYS) - set(self.settings.keys())
        if missing_settings:
            _log.error(f"Missing settings: {missing_settings}")
        else:
            self_driving_mode = self.settings['self_driving_mode']
            assert self_driving_mode in ['autopilot', 'copilot'], f"Invalid self_driving_mode: {self_driving_mode}"
            self.mode = self_driving_mode
            self.self_driving_status = bool(self.settings['self_driving_status'])
            _log.info(f"Received a complete set of settings")

    def _handle_fdd(self, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        self.faults['faults'] = {k:v for k, v in message.items() if k not in COMMON_KEYS}
        self.faults['timestamp'] = message['timestamp']

        # TODO: Add notification through LINE

    def _handle_device_state_variables(self, device_id, message):
        """
        Handles incoming state variable data for a specific device.

        Extracts relevant device data from the message, excluding common keys.
        Updates the `state_variables` dictionary with the latest data and timestamp
        for the given device.

        Args:
            device_id (str): The unique identifier of the device.
            message (dict): The message containing device state variables.

        """
        # _log.debug(f"Received data from device {device_id}")

        device_data = {k:v for k, v in message.items() if k not in COMMON_KEYS}
        
        if device_id not in self.state_variables:
            self.state_variables[device_id] = dict()
            
        self.state_variables[device_id]['data'] = device_data
        self.state_variables[device_id]['timestamp'] = message['timestamp']

    def update_constraints(self):
        """ Update constraints status and valid timestamp 
        
        This function supports the following constraints:
        1. Min-Max total chilled water flow calculated from the sum of the min-max flow of each running chiller
        2. Minimum condenser water from the sum of minimum CDW flow for each CT
        
        """
        if not self.settings:
            self.constraints = dict()
            return None

        # 1. Update Min-Max total chilled water flow
        all_chillers_from_states = set()
        all_chillers_from_config = set()
        all_chillers_from_priority = set(self.settings['chiller_priority'].split(' '))
        for key in self.state_variables:
            if re.match(r'^chiller_\d+(?:_\d+)*$', key):
                all_chillers_from_states.add(key)
        for chiller in self.device_specs['chiller']:
            all_chillers_from_config.add(chiller['device_id'])
        
        if all_chillers_from_states != all_chillers_from_config:
            _log.error(f"Chillers from states and config do not match: {all_chillers_from_states} vs {all_chillers_from_config}")
            self.constraints = dict()
            return None
        elif all_chillers_from_states != all_chillers_from_priority:
            _log.error(f"Chillers from states and priority setting do not match: {all_chillers_from_states} vs {all_chillers_from_priority}")
            self.constraints = dict()
            return None
        elif all_chillers_from_config != all_chillers_from_priority:
            _log.error(f"Chillers from config and priority setting do not match: {all_chillers_from_config} vs {all_chillers_from_priority}")
            self.constraints = dict()
            return None
        
        else:
            min_chw_flow = 0
            max_chw_flow = 0
            min_cdw_flow = 0
            max_cdw_flow = 0

            chillers_dict = {ch_data['device_id']: ch_data for ch_data in self.device_specs['chiller']}
            min_chw_flow = sum(chillers_dict[chiller_id]['chw_min_flow'] for chiller_id in all_chillers_from_config if self.state_variables[chiller_id]['data']['status_read'])
            max_chw_flow = sum(chillers_dict[chiller_id]['chw_max_flow'] for chiller_id in all_chillers_from_config if self.state_variables[chiller_id]['data']['status_read'])
            min_cdw_flow = sum(chillers_dict[chiller_id]['cdw_min_flow'] for chiller_id in all_chillers_from_config if self.state_variables[chiller_id]['data']['status_read'])
            max_cdw_flow = sum(chillers_dict[chiller_id]['cdw_max_flow'] for chiller_id in all_chillers_from_config if self.state_variables[chiller_id]['data']['status_read'])

            current_timestamp = time.time()
            self.constraints['chw_min_flow'] = {'value':min_chw_flow, 'timestamp': current_timestamp}
            self.constraints['chw_max_flow'] = {'value':max_chw_flow, 'timestamp': current_timestamp}
            self.constraints['cdw_min_flow'] = {'value':min_cdw_flow, 'timestamp': current_timestamp}
            self.constraints['cdw_max_flow'] = {'value':max_cdw_flow, 'timestamp': current_timestamp}

        # 2: Update Minimum condenser water from the sum of minimum CDW flow for each CT
        # Override cdw_min_flow from chiller constraints if smaller
        all_cts_from_states = set()
        all_cts_from_priority = set(self.settings['ct_priority'].split(' '))
        for key in self.state_variables:
            if re.match(r'^ct_\d+(?:_\d+)*$', key):
                all_cts_from_states.add(key)
        
        cts_in_states_not_priority = all_cts_from_states - all_cts_from_priority
        cts_in_priority_not_states = all_cts_from_priority - all_cts_from_states

        if cts_in_states_not_priority:
            _log.error(f"These CTs in states but not in priority setting: {cts_in_states_not_priority}")
            self.constraints = dict()
            return None
        elif cts_in_priority_not_states:
            _log.error(f"These CTs in priority setting but not in states: {cts_in_priority_not_states}")
            self.constraints = dict()
            return None
        else:
            on_cts = [ct_id for ct_id in all_cts_from_priority if self.state_variables[ct_id]['data']['status_read']]
            min_cdw_flow_from_cts = len(on_cts) * self.settings['min_ct_water_flow']

            if min_cdw_flow_from_cts > self.constraints['cdw_min_flow']['value']:
                self.constraints['cdw_min_flow']['value'] = min_cdw_flow_from_cts
                self.constraints['cdw_min_flow']['timestamp'] = current_timestamp

    def check_system_faults(self):
        STOP_AI_FAULTS = [
            'cdw_flow_rate_sensor_invalid_value',
            'cdw_return_temperature_sensor_invalid_value',
            'cdw_supply_temperature_sensor_invalid_value',
            'chw_flow_rate_sensor_invalid_value',
            'chw_return_temperature_sensor_invalid_value',
            'chw_supply_temperature_sensor_invalid_value',
        ]

        system_is_ok = True
        for critical_case in STOP_AI_FAULTS:
            if critical_case not in self.faults['faults']:
                _log.error(f"Cannot find {critical_case} in exported faults list")
                system_is_ok = False
            elif self.faults['faults'][critical_case]:
                _log.error(f"Critical case detected: {critical_case}")
                system_is_ok = False

        return system_is_ok

    def get_and_publish_optimal_control_actions(self):
        """
        Get optimal control action and publish to message bus

        Currently, there are 4 suggestions to be made which are
        1. Chiller Sequencing (optimal_chiller_sequencing)
            - The value is a dictionary with chiller ids as keys and {'status_write': BOOLEAN} as a value
        2. Chilled Water Flow (optimal_chw_flow)
            - The value is a dictionary with 'plant' as a key and {'target_chw_flow_rate': VALUE} as a value
            - OR the value can also be follwing strings
                - "Increase CHW flow rate"
                - "Decrease CHW flow rate"
        3. Condenser Water Flow (optimal_cdw_flow)
            - The value is a dictionary with 'plant' as a key and {'target_cdw_flow_rate': VALUE} as a value
        4. Optimal CT (optimal_ct)
            - The value is a dictionary with CT ids as keys and {'status_write': VALUE} as a value
            - OR the value can also be following strings
                - "Increase CT frequency"
                - "Decrease CT frequency"
                - "Add another CT"
        
        """
        if time.time() - self.agent_start_timestamp < 120:
            _log.debug("Agent is still initializing. Skipping optimization process.")
            return
        elif not self.faults:
            _log.error("The agent cannot retrieve faults from the system. Skipping optimization process.")
            return
        elif not self.state_variables:
            _log.error("The agent cannot retrieve state variables from the system. Skipping optimization process.")
            return
        elif not self.settings:
            _log.error("The agent cannot retrieve settings from the system. Skipping optimization process.")
            return

        if not self.self_driving_status:
            _log.info(f"[Mode: {self.mode}] Self-driving mode is disabled.")
        else:
            _log.info(f"[Mode: {self.mode}] Self-driving mode is enabled.")

        # Step 1: Check system faults
        # system_is_ok = self.check_system_faults()
        system_is_ok = True
        if not system_is_ok:
            timestamp = int(pendulum.now().timestamp())
            datetime = pendulum.from_timestamp(timestamp, tz='Asia/Bangkok').isoformat()
            log_payload = {
                "timestamp": timestamp,
                "datetime": datetime,
                "location": self.location,
                "mode": "-",
                "result": "failed from faults",
                "state_variables": self.state_variables,
                "settings": self.settings,
                "remarks": self.faults
            }
            self.vip.pubsub.publish(
                peer="pubsub", 
                topic=f'{self.mode}/optimization/suggestion/event', 
                headers={"requesterID": self.core.identity, "message_type": "event", "TimeStamp": datetime},
                message=log_payload
            )
            return

        # Step 2: Check whether state variables and settings are updated within the last 1 minutes
        current_timestamp = time.time()
        up_to_date = True
        for device_id in self.state_variables:
            if current_timestamp - self.state_variables[device_id]['timestamp'] > 60:
                _log.error(f"State variables for {device_id} are not updated within the last 1 minute")
                up_to_date = False
        if not up_to_date:
            _log.error("State variables are not up to date. Skipping optimization process.")
            return
        
        if current_timestamp - self.settings_updated_timestamp > 60:
            _log.error("Settings are not updated within the last 1 minute")
            return

        # Step 3: Solve ML-based optimization problem
        # TODO: Add ML-based optimization problem

        # Step 4: Engineering-based Logic
        try:
            optimal_chiller_sequencing = self.get_optimal_chiller_sequencing()
        except Exception as e:
            _log.error(f"Failed to get optimal chiller sequencing: {e}")
            optimal_chiller_sequencing = None

        try:
            optimal_chw_flow = self.get_optimal_chw_flow()
        except Exception as e:
            _log.error(f"Failed to get optimal chilled water flow: {e}")
            optimal_chw_flow = None

        try:
            optimal_cdw_flow = self.get_optimal_cdw_flow()
        except Exception as e:
            _log.error(f"Failed to get optimal condenser water flow: {e}")
            optimal_cdw_flow = None

        try:
            optimal_ct = self.get_optimal_ct_settings()
        except Exception as e:
            _log.error(f"Failed to get optimal cooling tower settings: {e}")
            optimal_ct = None

        # Step 5: Publish optimal control actions
        # If self.mode == 'copilot', then publish the optimal control actions as suggestions
        # If self.mode == 'autopilot', then publish the optimal control actions as commands
        if self.mode == 'copilot':
            self.publish_copilot_suggestions(
                optimal_chiller_sequencing=optimal_chiller_sequencing,
                optimal_chw_flow=optimal_chw_flow,
                optimal_cdw_flow=optimal_cdw_flow,
                optimal_ct=optimal_ct,
            )
        elif self.mode == 'autopilot':
            raise NotImplementedError
        else:
            raise ValueError(f"Invalid mode: {self.mode}")
            
    def get_optimal_chiller_sequencing(self):

        # Step 1: Read relevant settings
        chiller_sequencing_delay_duration = self.settings['chiller_sequencing_delay_duration']
        max_chr = self.settings['max_chilled_water_return_temperature']
        min_chr = self.settings['min_chilled_water_return_temperature']
        max_setpoint_temperature_deviation = self.settings['max_setpoint_temperature_deviation']
        max_rla = self.settings['max_chiller_percentage_rla']
        min_rla = self.settings['min_chiller_percentage_rla']
        high_load_tolerance_duration = self.settings['high_load_tolerance_duration']
        low_load_tolerance_duration = self.settings['low_load_tolerance_duration']
        chiller_priority = self.settings['chiller_priority'].split(' ')

        # Step 2: Read relevant state variables
        current_chs = self.state_variables['chilled_water_loop']['data']['supply_water_temperature']
        current_chr = self.state_variables['chilled_water_loop']['data']['return_water_temperature']
        current_setpoint = self.state_variables['plant']['data']['target_chw_setpoint']
        chillers_data = {k: v['data'] for k, v in sorted(self.state_variables.items()) if re.match(r'^chiller_\d+(?:_\d+)*$', k)}
        on_chillers_data = {k: v['data'] for k, v in sorted(self.state_variables.items()) if re.match(r'^chiller_\d+(?:_\d+)*$', k) and v['data']['status_read']}

        # Step 3: Check for chiller sequencing delay
        if self.delay_timers['last_chiller_sequencing_timestamp'] is not None:
            if time.time() - self.delay_timers['last_chiller_sequencing_timestamp'] < chiller_sequencing_delay_duration:
                self.delay_timers['last_high_load_timestamp'] = None
                self.delay_timers['last_low_load_timestamp'] = None
                _log.debug(f"Chiller sequencing is still in delay: {time.time() - self.delay_timers['last_chiller_sequencing_timestamp']:.0f}/{chiller_sequencing_delay_duration:.0f} seconds")
                return None

        # Step 4.1: Check for TOO HIGH load
        HIGH_CHR = current_chr > max_chr
        DEVIATED_SETPOINT = abs(current_chs - current_setpoint) > max_setpoint_temperature_deviation
        HIGH_RLA = all(datapoints['status_read'] and datapoints['percentage_rla'] >= max_rla for datapoints in on_chillers_data.values())

        if (HIGH_CHR and HIGH_RLA) or (DEVIATED_SETPOINT and HIGH_RLA):

            last_high_load_timestamp = self.delay_timers['last_high_load_timestamp']

            if last_high_load_timestamp is None:
                self.delay_timers['last_high_load_timestamp'] = time.time()
                return None
            else:
                if time.time() - last_high_load_timestamp > high_load_tolerance_duration:
                    # If the system is in HIGH CHW RETURN, DEVIATED SETPOINT, or HIGH RLA state, then new chiller should be added to the system
                    for chiller_id in chiller_priority:  # Transverse from high-priority number to low-priority number
                        if chiller_id not in on_chillers_data:
                            # If the chiller is not running, then start the chiller
                            self.delay_timers['last_chiller_sequencing_timestamp'] = time.time()
                            _log.debug(f"Adding {chiller_id} into system operation...")
                            return {
                                **{ch_id: {'status_write': ch_dp['status_read']} for ch_id, ch_dp in chillers_data.items()},
                                **{chiller_id: {'status_write': True}}
                            }
                    _log.error("All chillers are running. Cannot add new chiller to the system.")
                    return None
                else:
                    _log.debug(
                        f"High load detected for duration: {time.time() - last_high_load_timestamp:.0f}/{high_load_tolerance_duration:.0f} seconds" \
                        f" (from {'high CHR' if HIGH_CHR else ''} {'deviated setpoint' if DEVIATED_SETPOINT else ''} {'high RLA' if HIGH_RLA else ''})"
                    )
                    return None
        else:
            self.delay_timers['last_high_load_timestamp'] = None
                
        # Step 4.2: Check for TOO LOW load
        LOW_CHR = current_chr < min_chr
        LOW_RLA = all([datapoints['status_read'] and datapoints['percentage_rla'] <= min_rla for datapoints in on_chillers_data.values()])

        if LOW_CHR or LOW_RLA:
            last_low_load_timestamp = self.delay_timers.get('last_low_load_timestamp', None)

            if last_low_load_timestamp is None:
                self.delay_timers['last_low_load_timestamp'] = time.time()
                return None
            else:
                if time.time() - last_low_load_timestamp > low_load_tolerance_duration:
                    # If the system is in LOW CHW RETURN or LOW RLA state, then the chiller should be stopped
                    for chiller_id in chiller_priority[::-1]:  # Transverse from low-priority number to high-priority number
                        if chiller_id in on_chillers_data:
                            # If the chiller is running, then stop the chiller
                            self.delay_timers['last_chiller_sequencing_timestamp'] = time.time()
                            _log.debug(f"Stopping {chiller_id} from system operation.")
                            return {
                                **{ch_id: {'status_write': ch_dp['status_read']} for ch_id, ch_dp in chillers_data.items()},
                                **{chiller_id: {'status_write': False}}
                            }
                else:
                    _log.debug(
                        f"Low load detected for duration: {time.time() - last_low_load_timestamp:.0f}/{low_load_tolerance_duration:.0f} seconds" \
                        f" (from {'low CHR' if LOW_CHR else ''} {'low RLA' if LOW_RLA else ''})"
                    )
                    return None
                
        else:
            self.delay_timers['last_low_load_timestamp'] = None

    def get_optimal_chw_flow(self):
        
        # Step 1: Read relevant settings
        chw_min_flow = self.constraints['chw_min_flow']['value']
        chw_max_flow = self.constraints['chw_max_flow']['value']
        enable_dpt_control = self.settings['enable_dpt_control']
        dpt_setpoint = self.settings['dpt_setpoint']
        unmet_dpt_tolerance_duration = self.settings['unmet_dpt_tolerance_duration']
        min_schp_frequency = self.settings['min_schp_frequency']
        design_delta_temperature = self.settings['design_chw_delta_temperature']
        high_delta_temperature_tolerance = self.settings['high_chw_delta_temperature_tolerance']
        low_delta_temperature_tolerance = self.settings['low_chw_delta_temperature_tolerance']
        high_delta_temperature_tolerance_duration = self.settings['high_chw_delta_temperature_tolerance_duration']
        low_delta_temperature_tolerance_duration = self.settings['low_chw_delta_temperature_tolerance_duration']
        smart_chw_delay_duration = self.settings['smart_chw_delay_duration']

        # Step 2: Read relevant state variables
        dpt_last_ahu = self.state_variables['plant']['data']['dpt_last_ahu']
        cooling_rate = self.state_variables['plant']['data']['cooling_rate']
        chs = self.state_variables['chilled_water_loop']['data']['supply_water_temperature']
        chr = self.state_variables['chilled_water_loop']['data']['return_water_temperature']

        # Step 3: Check for smart chw flow delay.
        if self.delay_timers['last_smart_chw_flow_timestamp'] is not None:
            if time.time() - self.delay_timers['last_smart_chw_flow_timestamp'] < smart_chw_delay_duration:
                _log.info(f"Smart CHW flow is still in delay: {time.time() - self.delay_timers['last_smart_chw_flow_timestamp']:.0f}/{smart_chw_delay_duration:.0f} seconds")
                self.delay_timers['last_too_low_dpt_timestamp'] = None
                self.delay_timers['last_too_high_dpt_timestamp'] = None
                self.delay_timers['last_high_chw_delta_temperature_timestamp'] = None
                self.delay_timers['last_low_chw_delta_temperature_timestamp'] = None
                return None

        # Step 4: Check DPT Condition
        if enable_dpt_control:
            # Check for unmet DPT tolerance delay
            last_too_low_dpt_timestamp = self.delay_timers['last_too_low_dpt_timestamp']
            last_too_high_dpt_timestamp = self.delay_timers['last_too_high_dpt_timestamp']
            
            if dpt_last_ahu < dpt_setpoint:
                if last_too_low_dpt_timestamp is None:
                    self.delay_timers['last_too_low_dpt_timestamp'] = time.time()
                    return None
                elif time.time() - last_too_low_dpt_timestamp > unmet_dpt_tolerance_duration:
                    self.delay_timers['last_smart_chw_flow_timestamp'] = time.time()
                    _log.info(f"Too low DPT detected for duration for more than {unmet_dpt_tolerance_duration} seconds. Increasing CHW flow.")
                    return 'Increase CHW flow rate'
                    # return {'plant': {'target_chw_flow_rate': 'increase'}}
                else:
                    _log.info(f"Too low DPT detected for duration: {time.time() - last_too_low_dpt_timestamp:.0f}/{unmet_dpt_tolerance_duration:.0f} seconds")
            elif dpt_last_ahu > dpt_setpoint:
                if last_too_high_dpt_timestamp is None:
                    self.delay_timers['last_too_high_dpt_timestamp'] = time.time()
                    return None
                elif time.time() - last_too_high_dpt_timestamp > unmet_dpt_tolerance_duration:
                    self.delay_timers['last_smart_chw_flow_timestamp'] = time.time()
                    _log.debug(f"Too high DPT detected for duration for more than {unmet_dpt_tolerance_duration} seconds. Decreasing CHW flow.")
                    return 'Decrease CHW flow rate'
                    # return {'plant': {'target_chw_flow_rate': 'decrease'}}
                else:
                    _log.debug(f"Too high DPT detected for duration: {time.time() - last_too_high_dpt_timestamp:.0f}/{unmet_dpt_tolerance_duration:.0f} seconds")
            else:
                self.delay_timers['last_too_low_dpt_timestamp'] = None
                self.delay_timers['last_too_high_dpt_timestamp'] = None
                return None
        else:
            self.delay_timers['last_too_low_dpt_timestamp'] = None
            self.delay_timers['last_too_high_dpt_timestamp'] = None
            
        # Step 5.1: Check for low CHW ΔT
        if chr - chs < low_delta_temperature_tolerance:
            last_low_delta_temp_timestamp = self.delay_timers['last_low_chw_delta_temperature_timestamp']
            if last_low_delta_temp_timestamp is None:
                self.delay_timers['last_low_chw_delta_temperature_timestamp'] = time.time()
                return None
            elif time.time() - last_low_delta_temp_timestamp > low_delta_temperature_tolerance_duration:
                self.delay_timers['last_smart_chw_flow_timestamp'] = time.time()
                new_flow = cooling_rate / design_delta_temperature * 24
                if new_flow < chw_min_flow:
                    new_flow = chw_min_flow
                _log.debug(f"Low CHW ΔT (high CHW flow) detected for duration for more than {low_delta_temperature_tolerance_duration:.0f} seconds. Decreasing CHW flow to {new_flow:.0f} GPM (Minimum: {chw_min_flow} GPM).")
                return {'plant': {'target_chw_flow_rate': new_flow}}
            else:
                _log.debug(f"Low CHW ΔT (high CHW flow) detected for duration: {time.time() - last_low_delta_temp_timestamp:.0f}/{low_delta_temperature_tolerance_duration:.0f} seconds")
        else:
            self.delay_timers['last_low_chw_delta_temperature_timestamp'] = None

        # Step 5.2: Check for high CHW ΔT
        if chr - chs > high_delta_temperature_tolerance:
            last_high_delta_temp_timestamp = self.delay_timers['last_high_chw_delta_temperature_timestamp']
            if last_high_delta_temp_timestamp is None:
                self.delay_timers['last_high_chw_delta_temperature_timestamp'] = time.time()
                return None
            elif time.time() - last_high_delta_temp_timestamp > high_delta_temperature_tolerance_duration:
                self.delay_timers['last_smart_chw_flow_timestamp'] = time.time()
                new_flow = cooling_rate / design_delta_temperature * 24
                if new_flow > chw_max_flow:
                    new_flow = chw_max_flow
                _log.debug(f"High CHW ΔT (low CHW flow) detected for duration for more than {high_delta_temperature_tolerance_duration:.0f} seconds. Increasing CHW flow to {new_flow:.0f} GPM (Maximum: {chw_max_flow} GPM).")
                return {'plant': {'target_chw_flow_rate': new_flow}}
            else:
                _log.debug(f"High CHW ΔT detected (low CHW flow) for duration: {time.time() - last_high_delta_temp_timestamp:.0f}/{high_delta_temperature_tolerance_duration:.0f} seconds")
        else:
            self.delay_timers['last_high_chw_delta_temperature_timestamp'] = None

    def get_optimal_cdw_flow(self):
        
        # Step 1: Read relevant settings
        cdw_min_flow = self.constraints['cdw_min_flow']['value']
        cdw_max_flow = self.constraints['cdw_max_flow']['value']
        enable_smart_cdw_flow = self.settings['enable_smart_cdw_flow']
        smart_cdw_delay_duration = self.settings['smart_cdw_delay_duration']
        min_cdp_frequency = self.settings['min_cdp_frequency']
        design_delta_temperature = self.settings['design_cdw_delta_temperature']
        high_delta_temperature_tolerance = self.settings['high_cdw_delta_temperature_tolerance']
        low_delta_temperature_tolerance = self.settings['low_cdw_delta_temperature_tolerance']
        high_delta_temperature_tolerance_duration = self.settings['high_cdw_delta_temperature_tolerance_duration']
        low_delta_temperature_tolerance_duration = self.settings['low_cdw_delta_temperature_tolerance_duration']

        # Step 2: Read relevant state variables
        cds = self.state_variables['condenser_water_loop']['data']['supply_water_temperature']
        cdr = self.state_variables['condenser_water_loop']['data']['return_water_temperature']
        cdw_flow_rate = self.state_variables['condenser_water_loop']['data']['flow_rate']
        if 'heat_reject' in self.state_variables['plant']['data']:
            heat_reject = self.state_variables['plant']['data']['heat_reject']
        else:
            heat_reject = (cdr - cds) * cdw_flow_rate /24

        # Step 3: Check for smart CDW flow delay
        if self.delay_timers['last_smart_cdw_flow_timestamp'] is not None:
            if time.time() - self.delay_timers['last_smart_cdw_flow_timestamp'] < smart_cdw_delay_duration:
                _log.debug(f"Smart CDW flow is still in delay: {time.time() - self.delay_timers['last_smart_cdw_flow_timestamp']:.0f}/{smart_cdw_delay_duration} seconds")
                self.delay_timers['last_high_cdw_delta_temperature_timestamp'] = None
                self.delay_timers['last_low_cdw_delta_temperature_timestamp'] = None
                return None

        # Step 4: Check for low CDW ΔT
        if cdr - cds < low_delta_temperature_tolerance:
            last_low_delta_temp_timestamp = self.delay_timers['last_low_cdw_delta_temperature_timestamp']
            if last_low_delta_temp_timestamp is None:
                self.delay_timers['last_low_cdw_delta_temperature_timestamp'] = time.time()
                return None
            elif time.time() - last_low_delta_temp_timestamp > low_delta_temperature_tolerance_duration:
                self.delay_timers['last_smart_cdw_flow_timestamp'] = time.time()
                new_flow = heat_reject / design_delta_temperature * 24
                if new_flow < cdw_min_flow:
                    new_flow = cdw_min_flow
                _log.debug(f"Low CDW ΔT (high CDW flow) detected for duration for more than {low_delta_temperature_tolerance_duration:.0f} seconds. Decreasing CDW flow from {cdw_flow_rate} to {new_flow:.0f} GPM (Minimum: {cdw_min_flow} GPM).")
                return {'plant': {'target_cdw_flow_rate': new_flow}}
            else:
                _log.debug(f"Low CDW ΔT (high CDW flow) detected for duration: {time.time() - last_low_delta_temp_timestamp:.0f}/{low_delta_temperature_tolerance_duration:.0f} seconds")
        else:
            self.delay_timers['last_low_cdw_delta_temperature_timestamp'] = None

        # Step 5: Check for high CDW ΔT
        if cdr - cds > high_delta_temperature_tolerance:
            last_high_delta_temp_timestamp = self.delay_timers['last_high_cdw_delta_temperature_timestamp']
            if last_high_delta_temp_timestamp is None:
                self.delay_timers['last_high_cdw_delta_temperature_timestamp'] = time.time()
                return None
            elif time.time() - last_high_delta_temp_timestamp > high_delta_temperature_tolerance_duration:
                self.delay_timers['last_smart_cdw_flow_timestamp'] = time.time()
                new_flow = heat_reject / design_delta_temperature * 24
                if new_flow > cdw_max_flow:
                    new_flow = cdw_max_flow
                _log.debug(f"High CDW ΔT (low CDW flow) detected for duration for more than {high_delta_temperature_tolerance_duration:.0f} seconds. Increasing CDW flow to {new_flow:.0f} GPM (Maximum: {cdw_max_flow} GPM).")
                return {'plant': {'target_cdw_flow_rate': new_flow}}
            else:
                _log.debug(f"High CDW ΔT (low CDW flow) detected for duration: {time.time() - last_high_delta_temp_timestamp:.0f}/{high_delta_temperature_tolerance_duration:.0f} seconds")

    def get_optimal_ct_settings(self):
        
        # Step 1: Read relevant settings
        enable_smart_ct = self.settings['enable_smart_ct']
        enable_direct_cds_setpoint = self.settings['enable_direct_cds_setpoint']
        smart_ct_delay_duration = self.settings['smart_ct_delay_duration']
        target_ct_approach_temperature = self.settings['target_ct_approach_temperature']
        min_condenser_supply_temperature = self.settings['min_condenser_supply_temperature']
        target_cdw_setpoint = self.state_variables['plant']['data']['target_cdw_setpoint']
        max_ct_frequency_for_addition = self.settings['max_ct_frequency_for_addition']
        min_ct_frequency = self.settings['min_ct_frequency']
        min_ct_water_flow = self.settings['min_ct_water_flow']
        ct_priority = self.settings['ct_priority'].split(' ')
        unmet_cdw_setpoint_tolerance_duration = self.settings['unmet_cdw_setpoint_tolerance_duration']
        cds_setpoint_deviation_deadband = self.settings['cds_setpoint_deviation_deadband']

        # Step 2: Read relevant state variables
        cds = self.state_variables['condenser_water_loop']['data']['supply_water_temperature']
        cdw_flow_rate = self.state_variables['condenser_water_loop']['data']['flow_rate']
        wbt = self.state_variables['outdoor_weather_station']['data']['wetbulb_temperature']
        on_cts_data = {dev_id: v['data'] for dev_id, v in sorted(self.state_variables.items()) if re.match(r'^ct_\d+(?:_\d+)*$', dev_id) and v['data']['status_read']}
        on_vsd_cts = {ct_id: dp for ct_id, dp in on_cts_data.items() if 'frequency_read' in dp}
        cts_data = {k: v['data'] for k, v in sorted(self.state_variables.items()) if re.match(r'^ct_\d+(?:_\d+)*$', k)}

        # Step 3: Check for smart CT delay
        if self.delay_timers['last_smart_ct_timestamp'] is not None:
            if time.time() - self.delay_timers['last_smart_ct_timestamp'] < smart_ct_delay_duration:
                _log.debug(f"Smart CT is still in delay: {time.time() - self.delay_timers['last_smart_ct_timestamp']:.0f}/{smart_ct_delay_duration:.0f} seconds")
                self.delay_timers['last_high_cds_temperature_timestamp'] = None
                return None

        # Step 4: Check if CDW flow rate is sufficient for CTs
        if cdw_flow_rate < self.constraints['cdw_min_flow']['value']:
            _log.debug(f"CDW flow rate is insufficient for CTs. Currently, CDW flow is at {cdw_flow_rate:.0f} GPM while {len(on_cts_data)} CTs need {min_ct_water_flow*len(on_cts_data)} GPM ({min_ct_water_flow:.0f} GPM each).")
            for ct_id in ct_priority[::-1]:
                if ct_id in on_cts_data:
                    _log.debug(f"Stopping {ct_id} from system operation to increase CDW flow per CT.")
                    return {
                        **{device_id: {'status_write': ct_dp['status_read']} for device_id, ct_dp in cts_data.items()},
                        **{ct_id: {'status_write': False}}
                    }

        # Step 5: Check if CDS is lower than CDS lower bound
        if cds < min_condenser_supply_temperature:
            _log.debug(f"CDS is lower than CDS lower bound of {min_condenser_supply_temperature:.0f}°F. DO NOTHING.")
            return None
        
        # Step 6: Select the desired CDS setpoint
        if not enable_direct_cds_setpoint:
            target_cdw_setpoint = wbt + target_ct_approach_temperature
            _log.debug(f"Using WBT + Approach as CDS setpoint of {target_cdw_setpoint:.0f}°F")
        else:
            _log.debug(f"Using user specified {target_cdw_setpoint:.0f}°F as CDS setpoint.")
        
        # Step 7: Check if CDS is higher or lower than target CDS setpoint
        if cds > (target_cdw_setpoint + cds_setpoint_deviation_deadband):
            if self.delay_timers['last_high_cds_temperature_timestamp'] is None:
                self.delay_timers['last_high_cds_temperature_timestamp'] = time.time()
                return None
            elif time.time() - self.delay_timers['last_high_cds_temperature_timestamp'] > unmet_cdw_setpoint_tolerance_duration:
                # Check whether all CTs are running at max speed (Non-vsd CT is always running at 100%)
                # If not yet, we can increase CT frequency further
                # If yes, we need to add another CT to pull down actual CDS to approach CDS setpoint
                all_vsd_cts_running_at_max_speed = all(ct_data.get('frequency_read', 100) >= max_ct_frequency_for_addition for ct_data in on_vsd_cts.values())
                if len(on_vsd_cts) > 0 and not all_vsd_cts_running_at_max_speed:
                    _log.debug(f"CTs are not running at max speed. Increasing CT frequency.")
                    self.delay_timers['last_smart_ct_timestamp'] = time.time()
                    return "Increase CT frequency"
                elif cdw_flow_rate >= (len(on_cts_data) + 1) * min_ct_water_flow:
                    # TODO: Add logic to check and determine which CT should be turned on based on priority
                    return "Add another CT"
            else:
                _log.debug(f"CDS temperature is higher than target CDS setpoint for duration: {time.time() - self.delay_timers['last_high_cds_temperature_timestamp']:.0f}/{unmet_cdw_setpoint_tolerance_duration:.0f} seconds")
        elif cds < (target_cdw_setpoint - cds_setpoint_deviation_deadband):
            if self.delay_timers['last_low_cds_temperature_timestamp'] is None:
                self.delay_timers['last_low_cds_temperature_timestamp'] = time.time()
                return None
            elif time.time() - self.delay_timers['last_low_cds_temperature_timestamp'] > unmet_cdw_setpoint_tolerance_duration:
                # Check whether any CTs are running above minimum speed
                # If yes, we can decrease CT frequency
                all_cts_above_min_speed = all(ct_data.get('frequency_read', 100) > min_ct_frequency for ct_data in on_cts_data.values())
                if all_cts_above_min_speed:
                    _log.debug(f"CTs are running above minimum speed. Decreasing CT frequency.")
                    self.delay_timers['last_smart_ct_timestamp'] = time.time()
                    return "Decrease CT frequency"
            else:
                _log.debug(f"CDS temperature is lower than target CDS setpoint for duration: {time.time() - self.delay_timers['last_low_cds_temperature_timestamp']:.0f}/{unmet_cdw_setpoint_tolerance_duration:.0f} seconds")
                return None

    def publish_copilot_suggestions(self, optimal_chiller_sequencing, optimal_chw_flow, optimal_cdw_flow, optimal_ct):
        
        full_command_payload = dict()

        # Step 1: Transform chiller sequencing into encoded string
        # Extract all numbers from the chiller sequencing
        if optimal_chiller_sequencing is not None:
            all_chillers = set(self.settings['chiller_priority'].split(' '))
            assert all_chillers == set(optimal_chiller_sequencing.keys()), f"Chiller IDs in sequencing command does not correspond to settings: {optimal_chiller_sequencing.keys()} vs {all_chillers}"

            encoded_string = '69'
            for chiller_id in sorted(optimal_chiller_sequencing.keys()):
                current_status_read = self.state_variables[chiller_id]['data']['status_read']
                new_status_write = optimal_chiller_sequencing[chiller_id]['status_write']

                if new_status_write == current_status_read:
                    encoded_string += '0'
                elif int(new_status_write) == 1:
                    encoded_string += '1'
                elif int(new_status_write) == 0:
                    encoded_string += '2'
            
            full_command_payload['trigger_chiller_sequencing'] = True
            full_command_payload['suggested_chiller_sequence'] = int(encoded_string)

        # Step 2: Handle optimal_chw_flow
        if optimal_chw_flow is not None:
            if isinstance(optimal_chw_flow, dict):
                full_command_payload['trigger_smart_chw_flow'] = True
                full_command_payload['suggested_chw_flow_rate'] = optimal_chw_flow['plant']['target_chw_flow_rate']
            elif optimal_chw_flow == 'Increase CHW flow rate':
                full_command_payload['trigger_increase_chw_flow_from_dpt'] = True
            elif optimal_chw_flow == 'Decrease CHW flow rate':
                full_command_payload['trigger_decrease_chw_flow_from_dpt'] = True

        # Step 3: Handle optimal_cdw_flow
        if optimal_cdw_flow is not None:
            full_command_payload['trigger_smart_cdw_flow'] = True
            full_command_payload['suggested_cdw_flow_rate'] = optimal_cdw_flow['plant']['target_cdw_flow_rate']

        # Step 4: Handle optimal_ct
        if optimal_ct is not None:
            if isinstance(optimal_ct, dict):
                # TODO: Change this to proper device sequencing in the future
                full_command_payload['trigger_subtract_ct'] = True
            elif optimal_ct == "Increase CT frequency":
                full_command_payload['trigger_increase_ct_frequency'] = True
            elif optimal_ct == "Decrease CT frequency":
                full_command_payload['trigger_decrease_ct_frequency'] = True
            elif optimal_ct == "Add another CT":
                full_command_payload['trigger_add_ct'] = True

        # Step 5: Remove commands if settings are disabled
        actual_commands = {k: v for k, v in full_command_payload.items()}

        if not self.settings.get('enable_chiller_sequencing'):
            actual_commands.pop('trigger_chiller_sequencing', None)
            actual_commands.pop('suggested_chiller_sequence', None)
        if not self.settings.get('enable_smart_chw_flow'):
            actual_commands.pop('trigger_smart_chw_flow', None)
            actual_commands.pop('suggested_chw_flow_rate', None)
            actual_commands.pop('trigger_increase_chw_flow_from_dpt', None)
            actual_commands.pop('trigger_decrease_chw_flow_from_dpt', None)
        if not self.settings.get('enable_smart_cdw_flow'):
            actual_commands.pop('trigger_smart_cdw_flow', None)
            actual_commands.pop('suggested_cdw_flow_rate', None)
        if not self.settings.get('enable_smart_ct'):
            actual_commands.pop('trigger_subtract_ct', None)
            actual_commands.pop('trigger_increase_ct_frequency', None)
            actual_commands.pop('trigger_decrease_ct_frequency', None)
            actual_commands.pop('trigger_add_ct', None)

        # Step 6: Construct message and publish to message bus
        timestamp = int(pendulum.now().timestamp())
        datetime = pendulum.from_timestamp(timestamp, tz='Asia/Bangkok').isoformat()
        
        command_payload = {
            "timestamp": timestamp,
            "datetime": datetime,
            "location": self.location,
            "mode": self.mode,
            "action": {"command": actual_commands},
        }
    
        if self.self_driving_status and actual_commands:
            self.vip.pubsub.publish(
                peer="pubsub", 
                topic='bacnet/optimization/suggestion/command',
                headers={"requesterID": self.core.identity, "message_type": "command", "TimeStamp": datetime},
                message=command_payload
            )
            _log.info(f"Publish control command to BACnet agent: {actual_commands}")

        log_payload = {
            "timestamp": timestamp,
            "datetime": datetime,
            "location": self.location,
            "mode": self.mode,
            "result": full_command_payload,
            "state_variables": self.state_variables,
            "settings": self.settings,
            "remarks": self.delay_timers
        }
        self.vip.pubsub.publish(
            peer="pubsub", 
            topic='copilot/optimization/suggestion/event', 
            headers={"requesterID": self.core.identity, "message_type": "event", "TimeStamp": datetime},
            message=log_payload
        )


def main():
    """Main method called to start the agent."""
    utils.vip_main(chillerplantoptimization, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
