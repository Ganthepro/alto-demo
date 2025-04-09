# Must import gevent.monkey before importing other libraries especially reqqquest
import gevent.monkey
gevent.monkey.patch_all()

import logging
import sys
import re
import requests
from requests.exceptions import RequestException
import yaml
import pendulum

from datetime import datetime, timezone, timedelta
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron
from alto_ds.database import AltoCrateDB, AltoTimescaleDB
from pymongo import MongoClient
from contextlib import contextmanager


@contextmanager
def mongodb_connection(config):
    client = MongoClient(host=config.get('host', 'localhost'), 
                         port=config.get('port', 27017))
    try:
        yield client
    finally:
        client.close()


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.7"

def afdd(config_path, **kwargs):
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_config = config.get("volttron_agents", dict()).get('afdd', dict())
    location = config.get('location', 'staging')

    cron_string = agent_config.get('cron_string', "* * * * *")
    enable_multiproperty_alert = agent_config.get('enable_multiproperty_alert', True)
    enable_line_notify = agent_config.get('enable_line_notify', True)
    line_notify_group_id = agent_config.get('line_notify_group_id', '')
    cratedb_config = agent_config.get('cratedb_config', {})
    timescaledb_config = agent_config.get('timescaledb_config', {})
    mongodb_config = agent_config.get('mongodb_config', {})

    return Afdd(location, 
                cron_string, 
                enable_multiproperty_alert,
                enable_line_notify, 
                line_notify_group_id, 
                cratedb_config, 
                timescaledb_config, 
                mongodb_config, **kwargs)

class Afdd(Agent):
    def __init__(self, 
                location, 
                cron_string, 
                enable_multiproperty_alert,
                enable_line_notify, 
                line_notify_group_id, 
                cratedb_config, 
                timescaledb_config, 
                mongodb_config,
                **kwargs):
        super(Afdd, self).__init__(**kwargs)

        self.location = location
        self.cron_string = cron_string
        self.enable_multiproperty_alert = enable_multiproperty_alert
        self.enable_line_notify = enable_line_notify
        self.line_notify_group_id = line_notify_group_id
        self.cratedb_config = cratedb_config
        self.timescaledb_config = timescaledb_config
        self.mongodb_config = mongodb_config
        

        self.default_config = {
            "location": location,
            "cron_string": cron_string,
            "enable_multiproperty_alert": enable_multiproperty_alert,
            "enable_line_notify": enable_line_notify,
            "line_notify_group_id": line_notify_group_id,
            "cratedb_config": cratedb_config,
            "timescaledb_config": timescaledb_config,
            "mongodb_config": mongodb_config
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
        
    def get_mongodb_connection(self):
        """Get a MongoDB connection using the context manager"""
        return mongodb_connection(self.mongodb_config)

    def mongodb_operation(self, operation):
        """Wrapper for MongoDB operations using the context manager"""
        with self.get_mongodb_connection() as client:
            db = client[self.mongodb_db_name]
            collection = db[self.mongodb_collection]
            return operation(collection)

    def configure(self, config_name, action, contents):
        if isinstance(contents, dict):
            config = contents
        else:
            try:
                config = yaml.safe_load(contents)
            except yaml.YAMLError as e:
                _log.error("Error parsing YAML:", e)
                return None
            
        try:
            config = config['volttron_agents']['afdd']
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        try:
            location = config.get("location", "staging")
            cron_string = config.get("cron_string", "* * * * *")
            enable_multiproperty_alert = config.get("enable_multiproperty_alert", False)
            enable_line_notify = config.get("enable_line_notify", False)
            line_notify_group_id = config.get("line_notify_group_id", "")
            cratedb_config = config.get("cratedb_config", {})
            timescaledb_config = config.get("timescaledb_config", {})
            mongodb_config = config.get("mongodb_config", {})

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return
        
        self.location = location
        self.cron_string = cron_string
        self.enable_multiproperty_alert = enable_multiproperty_alert
        self.enable_line_notify = enable_line_notify
        self.line_notify_group_id = line_notify_group_id
        self.cratedb_config = cratedb_config
        self.timescaledb_config = timescaledb_config
        self.mongodb_config = mongodb_config
        self.mongodb_db_name = mongodb_config['db_name']
        self.mongodb_collection = mongodb_config['collection']

        self.timescaledb = AltoTimescaleDB(db_name=self.timescaledb_config['db_name'],
                                      username=self.timescaledb_config['username'],
                                      password=self.timescaledb_config['password'],
                                      host=self.timescaledb_config['host'],
                                      port=self.timescaledb_config['port'])

        self.cratedb = AltoCrateDB(host=self.cratedb_config['host'],
                                   port=self.cratedb_config['port'])

        # Schedule the agent to run every hour load forecast inference
        self.core.schedule(cron(self.cron_string),  
                           self.check_faults)

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        _log.info("AFDD Agent started.")
        # Example publish to pubsub
        self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # Example RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    def check_faults(self):
        _log.info("Running scheduled fault check")
        data = self.get_fault_rules()
        if not data:
            _log.error("No fault rules found in MongoDB")
            return
        self.check_condition_based_faults(data.get('condition-based', {}))

    def get_fault_rules(self):
        return self.mongodb_operation(lambda collection: collection.find_one())

    def check_condition_based_faults(self, condition_based):
        for fault_id, fault_data in condition_based.items():
            if not fault_data.get('enable', False):
                continue

            rule_violated, current_values, condition_values, operations = self.is_rule_violated(fault_data['rule'])
            if rule_violated:
                self.handle_fault_detection(fault_id, fault_data, current_values, condition_values, operations)
            else:
                self.update_fault_status(fault_id, last_trigger="")
                self.set_fault_status(fault_id, "normal")
                self.update_fault_status(fault_id, pending_time_count=0)

    def is_rule_violated(self, rules):
        all_violated = True
        current_values = []
        condition_values = []
        operations = []
        for rule in rules:
            violated, current_value, condition_value = self.evaluate_rule(rule)
            all_violated = all_violated and violated
            current_values.append((rule['datapoint'], current_value))
            condition_values.append((rule['datapoint'], condition_value))
            operations.append(rule['operation'])
        return all_violated, current_values, condition_values, operations

    def evaluate_rule(self, rule):
        device_id = rule['device_id']
        datapoint = rule['datapoint']
        operation = rule['operation']
        rule_type = rule['type']
        value = rule['value']

        current_value = self.get_current_value(device_id, datapoint)
        
        if rule_type == 'datapoint' and operation != '+/-':
            compare_value = self.get_current_value(value[0], value[1])
        elif rule_type == 'datapoint' and operation == '+/-':
            compare_value = value
        else:  # 'value' type
            compare_value = value[0]

        return self.compare_values(current_value, operation, compare_value), current_value, compare_value

    def get_current_value(self, device_id, datapoint):
        """
        Query the most recent value for the given device_id and datapoint from CrateDB
        """
        try:
            
            self.now = pendulum.now('Asia/Bangkok')
            five_minutes_ago = self.now - timedelta(minutes=5)

            #TODO: Change to query via datetime instead
            filters = {
                'device_id': {'=': device_id},
                'datapoint': {'=': datapoint},
                'timestamp': {
                    '>=': int(five_minutes_ago.timestamp() * 1000),  # Convert to milliseconds
                    '<=': int(self.now.timestamp() * 1000)  # Convert to milliseconds
                }
            }
            result = self.cratedb.query_data(self.cratedb_config['table_name'], filters)
            if not result:
                _log.warning(f"No data found for device_id: {device_id}, datapoint: {datapoint}")
                return None
            return result[0]['value']
        except Exception as e:
            _log.error(f"Error querying CrateDB: {str(e)}")
            return None

    def compare_values(self, current_value, operation, compare_value):
        """
        Compare the current value with the compare value based on the operation
        """
        _log.info(f"ALTO AFDD - current_value: {current_value}, operation: {operation}, compare_value: {compare_value}")
        if current_value is None:
            return False

        try:
            current_value = float(current_value)
        except ValueError:
            _log.error(f"Unable to convert current_value to float: {current_value}")
            return False
        if operation == '>':
            return current_value > float(compare_value)
        elif operation == '<':
            return current_value < float(compare_value)
        elif operation == '>=':
            return current_value >= float(compare_value)
        elif operation == '<=':
            return current_value <= float(compare_value)
        elif operation == '=':
            return current_value == float(compare_value)
        elif operation == 'between':
            if isinstance(compare_value, list) and len(compare_value) == 2:
                return float(compare_value[0]) <= current_value <= float(compare_value[1])
            else:
                _log.error(f"Invalid compare_value for 'between' operation: {compare_value}")
                return False
        elif operation == 'not between':
            if isinstance(compare_value, list) and len(compare_value) == 2:
                return not (float(compare_value[0]) <= current_value <= float(compare_value[1]))
            else:
                _log.error(f"Invalid compare_value for 'not between' operation: {compare_value}")
                return False
        elif operation == '+/-':

            if isinstance(compare_value, list) and len(compare_value) == 4:
                base_value = self.get_current_value(compare_value[0], compare_value[1])
                if base_value is None:
                    _log.error(f"Unable to get base value for +/- operation: {compare_value}")
                    return False
                try:
                    base_value = float(base_value)
                    lower_bound = base_value - float(compare_value[2])
                    upper_bound = base_value + float(compare_value[3])
                    return not (lower_bound <= current_value <= upper_bound)
                except ValueError:
                    _log.error(f"Unable to convert values to float for +/- operation: {compare_value}")
                    return False
            else:
                _log.error(f"Invalid compare_value for '+/-' operation: {compare_value}")
                return False
        else:
            _log.warning(f"Unknown operation: {operation}")
            return False

    def handle_fault_detection(self, fault_id, fault_data, current_values, condition_values, operations):
        """
        Handle the fault detection
        """
        
        if fault_data['last_trigger'] == "":
            self.update_fault_status(fault_id, last_trigger=self.now.isoformat())
        else:
            last_trigger = datetime.fromisoformat(fault_data['last_trigger'])
            time_diff = (self.now - last_trigger).total_seconds()
            pending_time_count = fault_data['pending_time_count'] + time_diff
            
            if pending_time_count >= fault_data['pending_time']:
                issue_ongoing_time = int(fault_data['pending_time_count']/60)
                self.update_fault_status(fault_id, pending_time_count=pending_time_count)
                self.set_fault_status(fault_id, "alert")

                # Get the device_id from the first rule
                device_id = fault_data['rule'][0]['device_id']
                description = self.generate_description(
                    device_id,
                    current_values,
                    condition_values,
                    operations
                )
                #TODO: Add logic for dynamically change the notify_idle_time
                # Case either user enable only line notify or both
                if self.enable_line_notify:
                    response = self.send_alarm_to_line_notify(fault_id, fault_data['fault_name'], issue_ongoing_time, 60, description)
                    if response.text == 'OK' and self.enable_multiproperty_alert:
                        self.send_alarm_to_timescaledb(fault_data['fault_name'])
                # Case where user enable only multi-property alert but not line notify
                if not self.enable_line_notify and self.enable_multiproperty_alert:
                    self.send_alarm_to_timescaledb(fault_data['fault_name'])
                
            else:
                self.update_fault_status(fault_id, pending_time_count=pending_time_count)


    def update_fault_status(self, fault_id, **kwargs):
        """
        Update fault status in MongoDB
        """
        def update_op(collection):
            collection.update_one(
                {"condition-based." + fault_id: {"$exists": True}},
                {"$set": {f"condition-based.{fault_id}.{k}": v for k, v in kwargs.items()}}
            )
        self.mongodb_operation(update_op)

    def set_fault_status(self, fault_id, status):
        """
        Set fault status in MongoDB
        """
        _log.info(f"Setting fault status for fault_id: {fault_id} to status: {status}")
        def set_status_op(collection):
            collection.update_one(
                {"$or": [
                    {"condition-based." + fault_id: {"$exists": True}},
                ]},
                {"$set": {
                    f"condition-based.{fault_id}.status": status,
                }}
            )
        self.mongodb_operation(set_status_op)

    def device_id_name_map(self, device_id):
        """
        Map a device ID to a more readable format based on patterns.
        
        Args:
            device_id (str): The original device ID
        
        Returns:
            str: The mapped, more readable device ID
        """

        # Define patterns and their mappings
        patterns = [
            (r'chiller_(\d+)', lambda m: f"CH-{int(m.group(1)):02d}"),
            (r'pchp_(\d+)', lambda m: f"PCHP-{int(m.group(1)):02d}"),
            (r'schp_(\d+)', lambda m: f"SCHP-{int(m.group(1)):02d}"),
            (r'chp_(\d+)', lambda m: f"CHP-{int(m.group(1)):02d}"),
            (r'cdp_(\d+)', lambda m: f"CDP-{int(m.group(1)):02d}"),
            (r'ct_(\d+)_(\d+)', lambda m: f"CT-{int(m.group(1)):02d}-{int(m.group(2)):02d}"),
            (r'ct_(\d+)', lambda m: f"CT-{int(m.group(1)):02d}"),
            (r'power_meter_ch(\d+)', lambda m: f"Power Meter CH-{int(m.group(1)):02d}"),
            (r'mvch_(\d+)', lambda m: f"MVCH-{int(m.group(1)):02d}"),
            (r'mvcd_(\d+)', lambda m: f"MVCD-{int(m.group(1)):02d}"),
            (r'btu_meter_chiller_(\d+)_chilled', lambda m: f"BTU Meter CH-{int(m.group(1)):02d} (Chilled)"),
            (r'btu_meter_chiller_(\d+)_condenser', lambda m: f"BTU Meter CH-{int(m.group(1)):02d} (Cond.)"),
        ]
        
        # Check if the device_id matches any pattern
        for pattern, mapping in patterns:
            match = re.match(pattern, device_id)
            if match:
                return mapping(match)
        
        # If no pattern matches, capitalize words and replace underscores with spaces
        return ' '.join(word.capitalize() for word in device_id.split('_'))
    
    def datapoint_name_map(self, datapoint):
        """
        Remove underscores and capitalize each word in the datapoint name
        """
        if datapoint == 'evap_leaving_water_temperature':
            return 'CHS'
        elif datapoint == 'evap_entering_water_temperature':
            return 'CHR'
        elif 'status' in datapoint:
            return 'Status'
        elif 'setpoint' in datapoint:
            return 'Setpoint'
        else:
            return ' '.join(word.capitalize() for word in datapoint.split('_'))

    def current_value_format(self, datapoint, current_value):
        """
        Format the condition value to a string
        """

        if 'temp' in datapoint:
            return f"{float(current_value):.1f}°F"
        elif 'status' in datapoint:
            if float(current_value) == float(0):
                return 'Off'
            elif float(current_value) == float(1):
                return 'Running'
            else:
                return f"{float(current_value):.1f}"
        else:
            return f"{float(current_value):.1f}"
    
    def condition_value_format(self, datapoint, condition_value, operation):
        """
        Format the condition value to a string
        """
        
        if operation == 'between' or operation == 'not between':
            return f"{float(condition_value[0]):.1f} - {float(condition_value[1]):.1f}"
        elif operation == '+/-':
            base_value = self.get_current_value(condition_value[0], condition_value[1])
            lower_bound = float(base_value) - float(condition_value[2])
            upper_bound = float(base_value) + float(condition_value[3])
            return f"{lower_bound:.1f} - {upper_bound:.1f}"
        else:
            return f"{float(condition_value):.1f}"


    def operation_format(self, operation):
        """
        Format the operation to a string
        """

        if operation == '>':
            return 'is greater than'
        elif operation == '<':
            return 'is less than'
        elif operation == '=':
            return 'is equal to'
        elif operation == '+/-':
            return 'is outside the range of'
        elif operation == 'between':
            return 'is between'
        elif operation == 'not between':
            return 'is not between'
        else:
            return operation

    def generate_description(self, device_id, current_values, condition_values, operations):
        """
        Generate the description for the fault
        """
        description = f"Fault Details:\n\n{self.device_id_name_map(device_id)}\n"
        
        for (datapoint, current_value), (_, condition_value), operation in zip(current_values, condition_values, operations):
            datapoint_name = self.datapoint_name_map(datapoint)
            formatted_current_value = self.current_value_format(datapoint, current_value)
            description += f"{datapoint_name} : {formatted_current_value}"
        
        # Add the condition explanation as the last line
        last_datapoint, _ = current_values[-1]
        last_operation = operations[-1]
        last_condition_value = condition_values[-1][1]
        
        condition_explanation = f"{self.operation_format(last_operation)} {self.condition_value_format(last_datapoint, last_condition_value, last_operation)}"
        if 'temp' in last_datapoint.lower():
            condition_explanation += " °F"
        
        description += f"{condition_explanation}\n"
        
        return description.strip()

    #TODO: Add logic when the fault is resolved
    #TODO: Add logic for dynamically change the notify_idle_time
    #TODO: Add dynamically change the description
    def send_alarm_to_line_notify(self, fault_id, fault_name, issue_ongoing_time, notify_idle_time, description):
        """
        Send alarm to Line Notify
        """
        _log.info(f"Sending alarm to Line Notify: {fault_name}")
        url = 'https://oyp0qhsie8.execute-api.us-east-1.amazonaws.com/dev/chiller_lineoa_summary/lineoa_alarm_trigger'
        #TODO: Add description for the fault dynamically as well as notify_idle_time
        payload = {
            "location": self.location,
            "issue_id": fault_id,
            "issue_name": fault_name,
            "unix_timestamp": int(self.now.timestamp()),
            "description": description,
            "issue_ongoing_time": issue_ongoing_time,  # This should be dynamically set based on the fault
            "group_ids": [self.line_notify_group_id],  # This should be dynamically set based on the fault
            "notify_idle_time": notify_idle_time  # This should be dynamically set based on the fault
        }
        
        headers = {
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            _log.info("Successfully sent alarm to Line Notify")
            return response
        except RequestException as e:
            _log.error(f"Failed to send alarm to Line Notify: {str(e)}")
            return None
        except Exception as e:
            _log.error(f"Unexpected error when sending alarm to Line Notify: {str(e)}")
            return None

    def send_alarm_to_timescaledb(self, fault_name):
        """
        Send alarm to TimescaleDB
        """
        _log.info(f"Sending alarm to TimescaleDB: {fault_name}")
        #TODO: Make the topic, message and priority scalable for multiple specific faults
        # Prepare data to insert
        bangkok_tz = timezone(timedelta(hours=7))  # Asia/Bangkok timezone
        data = [{
            "timestamp": int(self.now.timestamp()),
            "datetime": self.now.isoformat(),
            "location": self.location,
            "topic": "alto_afdd",
            "message": f"Fault Detected: \n {fault_name}",
            "type": "alarm",
            "priority": 1  # Set priority as needed
        }]
        
        # Insert data into TimescaleDB
        try:
            self.timescaledb.insert_data("multiproperty_events", data)
            _log.info(f"Successfully sent alarm to TimescaleDB: {fault_name}")
        except Exception as e:
            _log.error(f"Failed to send alarm to TimescaleDB: {e}")

    def get_fault_status(self, fault_id):
        """
        Get fault status from MongoDB
        """
        def get_status_op(collection):
            data = collection.find_one(
                {"$or": [
                    {"condition-based." + fault_id: {"$exists": True}},
                ]}
            )
            if data:
                fault_data = data.get('condition-based', {}).get(fault_id)
                return fault_data.get('status') if fault_data else None
            return None
        return self.mongodb_operation(get_status_op)

def main():
    utils.vip_main(afdd, version=__version__)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass