#@title Agent's code
"""
Agent documentation goes here.
"""
from io import StringIO

import gevent.monkey
import pandas as pd
import requests
import urllib

gevent.monkey.patch_all()

__docformat__ = 'reStructuredText'

import logging
import sys
import time

import pendulum

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class DeviceHandler:

    def __init__(self, controller: Agent, device_id: str, datapoints_config: dict):
        """
        Initialize the DeviceHandler class

        Args:
            controller (Agent): The ConditionBased agent
            device_id (str): The device id
            datapoints_config (dict): The configuration of the datapoints for the device in the following format:

                datapoints_config = {
                    "datapoint_1": [
                        {
                            "alert": {"name": "", "operation": ">", "value": 47.0, "period": 900, "between": [0, 24]},
                            "alarm": {"name": "", "operation": ">", "value": 48.0, "period": 300, "between": [0, 24]}
                        },
                        {
                            "alert": {"name": "", "operation": "<", "value": 43.0, "period": 900, "between": [0, 24]},
                            "alarm": {"name": "", "operation": "<", "value": 42.0,"period": 300,"between": [0, 24]}
                        }
                    ],
                    "datapoint_2": [
                        {
                            "alert": {"name": "", "operation": ">", "value": 47.0, "period": 900, "between": [0, 24]},
                            "alarm": {"name": "", "operation": ">", "value": 48.0, "period": 300, "between": [0, 24]}
                        },
                        {
                            "alert": {"name": "", "operation": "<", "value": 43.0, "period": 900, "between": [0, 24]},
                            "alarm": {"name": "", "operation": "<", "value": 42.0,"period": 300,"between": [0, 24]}
                        }
                }
        """
        self.controller = controller
        self.device_id = device_id
        self.datapoints_config = datapoints_config

        self.point_objects = dict()
        self.initialize_point_objects()

        self.is_active = False  # Whether the device is active or not. If not, do not check any condition

    def initialize_point_objects(self):
        """ Initialize the PointHandler objects for each datapoint """
        for point_name, conditions_list in self.datapoints_config.items():
            self.point_objects[point_name] = PointHandler(self, point_name, conditions_list)

    def update_data(self, message: dict):
        """ Update the value of PointHandler objects when new data is received

        Args:
            message (dict): The message received from the controller

        """
        timestamp = message['unix_timestamp']
        device_type = message['type']

        # Step 1: Ignore chiller data when it is not running
        if device_type == 'chiller' and message['mode'] in [1, '1']:
            self.is_active = False
        else:
            self.is_active = True

        # Step 2: Update the value of each datapoint
        for datapoint in self.datapoints_config.keys():
            if datapoint not in message:
                _log.error(f"[{self.device_id}] Datapoint {datapoint} is not in the message")
                continue

            # Step 3: Try to convert the value to float. If not, keep it as it is
            try:
                value = float(message[datapoint])
            except:
                value = message[datapoint]

            # Step 4: Update the value of the datapoint
            self.point_objects[datapoint].update_value(value, timestamp)

            # Step 3: Publish the status of each datapoint
            if self.is_active:
                self.point_objects[datapoint].publish_point_status()
            else:
                self.controller.send_point_status_to_socket({
                    'status': 'GOOD',
                    'priority': 4,
                    'type': 'condition_based',
                    'datapoint': datapoint,
                    'device_id': self.device_id,
                    'context': ''
                })

    def publish(self, payload):
        """ Publish the payload to Volttron message bus through the controller

        Args:
            payload (dict): The payload to be published

            payload = {
                'status': 'GOOD' OR 'BAD'
                'priority': 1 or 2 or 3 or 4
                'type': 'conditioned_based'
                'datapoint': <datapoint_name>
                'device_id': <device_id>
                'context': <message>
            }

        """
        payload.update({
            "source": self.device_id
        })
        self.controller.publish(payload)


class PointHandler:
    """
    Class for storing datapoint information and the condition associated with it """

    def __init__(self, device_handler: DeviceHandler, datapoint: str, conditions: list[dict]):
        """
        Initialize the PointHandler class

        Args:
            device_handler (DeviceHandler): The device handler object
            datapoint (str): The datapoint name
            conditions (list[dict]): The conditions for checking the validity of the datapoint. Each condition consists
            of 3 levels of severity: alert, alarm, and critical.

            each_condition = {
                "alert": {
                    "name": "Chiller 7 (running): Cond. Entering Water Temp. higher than 104 degreeF for 5 minutes",
                    "operation": ">=",
                    "value": 104.0,
                    "period": 300,
                    "between": [
                        0,
                        24
                    ]
                },
                "alarm": {
                    "name": "Chiller 7 (running): Cond. Entering Water Temp. higher than 105 degreeF for 3 minutes",
                    "operation": ">=",
                    "value": 105.0,
                    "period": 180,
                    "between": [
                        0,
                        24
                    ]
                },
                "critical": {
                    "name": "Chiller 7 (running): Cond. Entering Water Temp. higher than 107 degreeF",
                    "operation": ">",
                    "value": 107.0,
                    "period": 0,
                    "between": [
                        0,
                        24
                    ]
                }
            }

        """
        # Initialize important variables
        self.device_handler = device_handler
        self.device_id = device_handler.device_id
        self.datapoint = datapoint
        self.conditions_config = conditions
        self.conditions = list()  # List of ConditionBased objects
        self.initialize_conditions()

        self.value = None
        self.timestamp = 0

    def update_value(self, value, timestamp):
        """
        Update the value of the datapoint

        Args:
            value (float): The value of the datapoint to be updated
            timestamp (int): The timestamp of the datapoint to be updated

        """
        self.value = value
        self.timestamp = timestamp

        for condition in self.conditions:
            condition.update_condition_status()

    def publish_point_status(self):
        """
        Iterate through every conditions related to this datapoint of this device and check the validity of the
        datapoint. If any condition is found to be violated, record that condition and change the status of
        self.is_alert, self.is_alarm, and self.is_critical accordingly.

        """
        point_is_normal = True
        for condition in self.conditions:

            if condition.is_critical:
                point_is_normal = False
                priority = 1
            elif condition.is_alarm:
                point_is_normal = False
                priority = 2
            elif condition.is_alert:
                point_is_normal = False
                priority = 3
            else:
                condition.recently_published_prio = 4
                continue

            # If the condition is not normal, then publish the condition
            if priority != condition.recently_published_prio:
                self.device_handler.publish({
                    'status': 'BAD',
                    'priority': priority,
                    'type': 'condition_based',
                    'datapoint': self.datapoint,
                    'device_id': self.device_handler.device_id,
                    'context': f"{condition.message} (current value: {self.value:.1f})"
                })
                condition.recently_published_prio = priority
            self.device_handler.controller.send_point_status_to_socket({
                'status': 'BAD',
                'priority': priority,
                'type': 'condition_based',
                'datapoint': self.datapoint,
                'device_id': self.device_handler.device_id,
                'context': f"{condition.message} (current value: {self.value:.1f})"
            })

        # If every condition is normal, then the point of that device is normal
        if point_is_normal:
            self.device_handler.controller.send_point_status_to_socket({
                'status': 'GOOD',
                'priority': 4,
                'type': 'condition_based',
                'datapoint': self.datapoint,
                'device_id': self.device_handler.device_id,
                'context': ''
            })

    def initialize_conditions(self):
        """
        Initialize the conditions for checking the validity of the datapoint

        The severity degree of the conditions can be divided into 3 levels:
        - Normal (Priority = 4)
        - Alert (Priority = 3)
        - Alarm (Priority = 2)
        - Critical (Priority = 1)

        """
        self.conditions = [ConditionHandler(self, cond) for cond in self.conditions_config]


class ConditionHandler:
    """
    Class for storing the condition information. Each condition consists of 3 levels of severity: alert, alarm,
    and critical.

    """

    def __init__(self, point_handler: PointHandler, condition_config: dict):
        """
        Initialize the Condition class

        Args:
            point_handler (PointHandler): The point handler object
            condition_config (dict): The condition configuration (containing 3 keys of severity: alert, alarm, critical)

        """

        # Initialize important variables
        self.point_handler = point_handler
        self.condition_config = condition_config

        # Initialize status of each condition
        self.message = ''  # The message to be sent to the user
        self.is_alert = False
        self.is_alarm = False
        self.is_critical = False
        self.non_alert_timestamp = pendulum.now().timestamp()  # Timestamp recorded the last time the alert condition is NOT violated
        self.non_alarm_timestamp = pendulum.now().timestamp()  # Timestamp recorded the last time the alarm condition is NOT violated
        self.non_critical_timestamp = pendulum.now().timestamp()  # Timestamp recorded the last time the critical condition is NOT violated
        self.recently_published_prio = 0  # The priority of the recently published condition

    def update_condition_status(self):
        """
        Check the validity of the condition and update the status of the condition accordingly

        """

        # Check alert condition
        for level in ['alert', 'alarm', 'critical']:

            if not self.condition_config.get(level):
                continue
            condition_info = self.condition_config[level]

            name = condition_info['name']
            operation = condition_info['operation']
            threshold_value = condition_info['value']
            period = condition_info['period']
            between = condition_info['between']

            # Check if the condition is violated from the given operation and threshold value
            if operation == '>':
                is_violated = self.point_handler.value > threshold_value
            elif operation == '>=':
                is_violated = self.point_handler.value >= threshold_value
            elif operation == '<':
                is_violated = self.point_handler.value < threshold_value
            elif operation == '<=':
                is_violated = self.point_handler.value <= threshold_value
            else:
                raise ValueError(f"Invalid operation: {operation}")

            # Check if the time is between the given time range
            if between is not None:
                current_hour = pendulum.from_timestamp(self.point_handler.timestamp, tz='Asia/Bangkok').hour
                if current_hour < int(between[0]) or current_hour > int(between[1]):
                    is_violated = False

            if is_violated:
                # Check if the condition is violated for a period of time
                if self.point_handler.timestamp - getattr(self, f'non_{level}_timestamp') > period:
                    setattr(self, f'is_{level}', True)
                    self.message = f"[{level.upper()}] {name}"
            else:
                setattr(self, f'is_{level}', False)
                setattr(self, f'non_{level}_timestamp', self.point_handler.timestamp)

        # If no condition is violated, reset the message
        if (not self.is_alert) and (not self.is_alarm) and (not self.is_critical):
            self.message = ""


def condition_based(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    Args:
        config_path (str): Path to the configuration file

    Returns:
        ConditionBasedMaintenance: An instance of the agent build according to the configuration file

    """
    try:
        config = utils.load_config(config_path)
    except Exception as e:
        _log.error("Error loading ConditionBasedMaintenance Agent configuration file: {}".format(e))
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    stage = config.get('stage', 'staging')
    condition_based_config = config.get('condition_based_config', dict())
    topic_config = config.get('topic_config', dict())
    google_sheet_id = config.get('google_sheet_id', None)

    return CondtionBasedMaintenance(stage, condition_based_config, topic_config, google_sheet_id, **kwargs)


class CondtionBasedMaintenance(Agent):

    def __init__(self, stage: str, condition_based_config: dict, topic_config: dict, google_sheet_id: str, **kwargs):
        """
        Initialize the ConditionBasedMaintenance Agent class

        Args:
            stage (str): The stage of the agent (staging or production)
            condition_based_config (dict): The condition based configuration in the format below:

                    - condition_based = {
                        "S3050-003465": { // Device ID
                            "temp_2": [ // Point name
                                {
                                    "alert": {"name": ..., "operation": ..., "value": ..., "period": ..., "between": ...},
                                    "alarm": {"name": ..., "operation": ..., "value": ..., "period": ..., "between": ...},
                                    "critical": {"name": ..., "operation": ..., "value": ..., "period": ..., "between": ...}
                                }, ...
                            ],...
                        },...
                    }

            topic_config (dict): The Volttron message topic configuration in the format below:

                    - topic_config = {
                        "<schema_1>": {
                            "<agent_id_1>": [device_id_1, device_id_2, ...],
                            ...
                        },
                        ...
                    }

                    ex. topic_config = {
                            "sensor": {
                                "modbus_btu_meter": [
                                    "S3050-003465",
                                    "S3050-003466",
                                    "S3050-002896",
                                    "S3050-003467",
                                    "S3050-002974"
                                ],
                                "bacnet_controller": [
                                    "G22J03542",
                                    "G22J03541",
                                    "G22J03540"
                                ]
                            }
                        }

            google_sheet_id (str): The Google Sheet ID to get the condition based maintenance data from (Optional)

        """
        super(CondtionBasedMaintenance, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.stage = stage
        self.condition_based_config = condition_based_config
        self.topic_config = topic_config
        self.google_sheet_id = google_sheet_id
        self.device_instances = dict()

        self.default_config = {
            'stage': stage,
            'condition_based_config': condition_based_config,
            'topic_config': topic_config,
            'google_sheet_id': google_sheet_id
        }

        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.info("Configuring Agent...")

        try:
            stage = config.get('stage', 'staging')
            condition_based_config = config.get('condition_based_config', dict())
            topic_config = config.get('topic_config', dict())
            google_sheet_id = config.get('google_sheet_id', None)
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.stage = stage
        self.condition_based_config = condition_based_config
        self.topic_config = topic_config
        self.google_sheet_id = google_sheet_id

        try:
            self.get_condition_based_config_from_google_sheet()
            _log.info(f"Successfully got the condition based configuration from the google sheet: {self.condition_based_config}")
        except Exception as e:
            _log.error(f"Error getting condition based configuration from google sheet: {e}")

        self.build_device_instances()
        self.create_subscriptions()

    def get_condition_based_config_from_google_sheet(self):
        """
        When the agent is restarted, try to get the condition based configuration from the google sheet
        If failed, use the default configuration

        """
        # Step 1: Get the dataframe from the google sheet
        url = f'https://docs.google.com/spreadsheets/d/{self.google_sheet_id}/export?format=csv'

        # Send HTTP GET request and fetch the data
        # response = requests.get(url)
        response = urllib.request.urlopen(url)

        # Check the response status code to see if the request was successful
        if response.status == 200:
            # Content of the response, in bytes
            data = response.read()

            # Convert bytes to string
            csv_data = data.decode('utf-8')

            # Convert string to DataFrame
            df = pd.read_csv(StringIO(csv_data),
                             names=['device_id', 'datapoint_name', 'condition', 'name', 'operation', 'value', 'period',
                                    'between_start', 'between_end'])[1:]
            df.fillna(inplace=True, method='ffill')
            # Remove NA rows
            df.dropna(inplace=True)

        else:
            _log.error(f"Failed to get the condition based configuration from the google sheet: {response.status_code}")
            return

        # Step 2: Convert the dataframe to the condition based configuration
        condition_based_config = dict()

        for index, record in df.iterrows():
            device_id = record["device_id"]
            datapoint_name = record["datapoint_name"]
            condition = record["condition"]
            name = record["name"]
            operation = record["operation"]
            value = float(record["value"])
            period = int(record["period"])
            between_start = int(record["between_start"])
            between_end = int(record["between_end"])

            device = condition_based_config.setdefault(device_id, {})
            datapoint = device.setdefault(datapoint_name, [])

            # Find existing condition dictionaries if any exists for the given datapoint and operation
            existing_conditions = [cond for cond in datapoint if
                                   all(k in cond for k in ['alert', 'alarm', 'critical']) and cond['alert'].get(
                                       'operation') == operation]

            if existing_conditions:
                # Add the new condition to the existing dictionaries
                for existing_condition in existing_conditions:
                    existing_condition[condition] = {
                        "name": name,
                        "operation": operation,
                        "value": value,
                        "period": period,
                        "between": [between_start, between_end]
                    }
            else:
                # Create a new condition dictionary and add it to the list
                new_condition = {"alert": {}, "alarm": {}, "critical": {}}
                new_condition[condition] = {
                    "name": name,
                    "operation": operation,
                    "value": value,
                    "period": period,
                    "between": [between_start, between_end]
                }
                datapoint.append(new_condition)

        self.condition_based_config = condition_based_config.copy()

    def build_device_instances(self):
        """
        Initialize the device instances for DeviceHandler class
        """
        _log.debug("ConditionBasedMaintenance: build_device_instances")
        try:

            for device_id, datapoints_config in self.condition_based_config.items():
                if device_id not in self.device_instances:
                    self.device_instances[device_id] = DeviceHandler(self, device_id, datapoints_config)

        except Exception as e:
            _log.exception(f"_build_instance Error: {e}")

    def create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_message callback
        """

        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for schema, agent_props in self.topic_config.items():
            for agent_id, device_id_list in agent_props.items():
                for device_id in device_id_list:
                    self.vip.pubsub.subscribe(
                        peer='pubsub',
                        prefix=f"{schema}/{agent_id}/{device_id}/event",
                        callback=self._handle_message
                    )
                    _log.info(f"Subscribed to topic: {schema}/{agent_id}/{device_id}/event")

    def _handle_message(self, peer, sender, bus, topic, headers, message):
        """
        When receiving a message from the pub/sub, update the value of each point in the device instance
        """

        _log.debug(f"Received message on topic: {topic} and message: {message}")

        if len(topic.split("/")) != 4:
            _log.warning(f"Invalid topic: {topic}")
            return

        schema, agent_id, device_id, message_type = topic.split("/")
        if device_id in self.device_instances:
            self.device_instances[device_id].update_data(message)

    def publish(self, payload: dict):
        """
        Publish the payload to Volttron message bus with topic: alert/<agent_id> and send the point_status
        payload to websocket endpoint /point_status

        *Note: This function needs RPC call from 'socket' agent to publish the payload to websocket endpoint

        payload = {
            'status': 'GOOD' OR 'BAD'
            'priority': 1 or 2 or 3 or 4
            'type': 'conditioned_based'
            'datapoint': <datapoint_name>
            'device_id': <device_id>
            'context': <message>
        }
        """
        try:
            unix_timestamp = int(time.time())
            timestamp = pendulum.from_timestamp(unix_timestamp).to_atom_string()
            payload.update({
                "agent_id": self.core.identity,
                "timestamp": timestamp,
                "unix_timestamp": unix_timestamp
            })
            self.vip.pubsub.publish("pubsub", f"alert/{self.core.identity}", message=payload)
            _log.info(f"Publish to topic: alert/{self.core.identity} with payload: {payload}")

        except Exception as e:
            _log.exception(f"ConditionBased publish Error: {e}")

    def send_point_status_to_socket(self, payload: dict):
        """
        Send the point_status payload to websocket endpoint /point_status

        Args:
            payload (dict): point_status payload

        """
        try:
            unix_timestamp = int(time.time())
            timestamp = pendulum.from_timestamp(unix_timestamp).to_atom_string()
            payload.update({
                "agent_id": self.core.identity,
                "timestamp": timestamp,
                "unix_timestamp": unix_timestamp
            })
            self.vip.rpc.call("socket", "send_custom_message", *('/point_status', payload))
            _log.info(f"ConditionBased: Send point status to SocketIO endpoint: /point_status with payload: {payload}")

        except Exception as e:
            _log.exception(f"ConditionBased publish Error: {e}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(condition_based,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
