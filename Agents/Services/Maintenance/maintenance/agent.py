"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
import json
import statistics
import os

import pendulum
import pandas as pd
import numpy as np
import requests
from crate import client

from .models.dbscan_model import dbscan_model
from .utils.azure_storage_blob_util import BlobClient
from .utils.notification_util import check_anomaly_status
from .utils.plotly_util import render_plot

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"


class CrateDB:
    
    def __init__(self, host: str, port: int, table :str, username: str = "", password: str = ""):
        self._host = host
        self._port = port
        self._table = table
        self._username = username
        self._password = password
        self._client = None
        self._cursor = None
    
    def _connect(self):
        if self._username and self._password:
            self._client = client.connect(f"{self._host}:{self._port}", username=self._username,
                                          password=self._password)
        else:
            self._client = client.connect(f"{self._host}:{self._port}")

    def _disconnect(self):
        if self._client is not None:
            self._client.close()
        else:
            pass

    @staticmethod
    def _generate_sql_string_for_list(_list: list) -> str:
        """ Return string in a correct format for SQL query

        If list is empty, return empty string
        If list has one element, return "('DEVICE_1')"
        If list has more than one element, return "('DEVICE_1', 'DEVICE_2', ...)"

        Args:
            _list: List of items to be converted to SQL string

        Returns:
            String of list in a correct format for SQL query

        """
        if _list is None:
            return ""
        elif len(_list) == 0:
            return ""
        elif len(_list) == 1:
            return str(tuple(_list)).replace(',', '')  # Remove comma to avoid SQL syntax error ex. (3,) -> (3)
        else:
            return str(tuple(_list))

    @staticmethod
    def _convert_timestamp_to_datetime(df: pd.DataFrame,
                                       column_name: str = 'timestamp',
                                       unit: str = 's',
                                       tz: str = 'Asia/Bangkok',
                                       rename_col: bool = True) -> pd.DataFrame:
        """
            Convert timestamp to datetime with tz
            If data is queried from CrateDB then the specified unit should be 'ms'
        """

        df[column_name] = pd.to_datetime(df[column_name], unit=unit, utc=True)  # 2022-08-28 17:37:03+00:00
        df[column_name] = df[column_name].dt.tz_convert(tz)  # 2022-08-28 00:37:03+07:00
        df[column_name] = df[column_name].dt.tz_localize(None)  # 2022-08-28 17:37:03

        if rename_col:
            df = df.rename(columns={column_name: 'datetime'})

        return df

    def get_timeseries_data(
            self,
            location: str,
            device_id_list: list = None,
            datapoint_list: list = None,
            subdevice_idx_list: list = None,
            start_unix: float = None,
            end_unix: float = None) -> pd.DataFrame:
        """ Get data from Cratedb

            Args:
                location (str): Location of the site
                device_id_list (list): List of device_id
                datapoint_list (list): List of datapoint
                subdevice_idx_list (list): List of subdevice_idx
                start_unix (int): Start unix timestamp
                end_unix (int): End unix timestamp

            Returns:
                df (pd.DataFrame): Dataframe of data with datetime index and [`device_id`, `subdevice_idx`, `datapoint`,
                `value`] as columns
                - return empty dataframe if no data is found

        """
        assert len(device_id_list) > 0, "get_data_from_cratedb: device_id_list is empty"
        self._connect()

        # Step 1: Query data from CrateDB
        query_string = f"""
                SELECT
                    timestamp, device_id, subdevice_idx, datapoint, value
                FROM
                    {self._table}
                WHERE
                    location = '{location}'
                    {f'AND device_id IN {self._generate_sql_string_for_list(device_id_list)}' if device_id_list else ''}
                    {f'AND datapoint IN {self._generate_sql_string_for_list(datapoint_list)}' if datapoint_list else ''}
                    {f'AND subdevice_idx IN {self._generate_sql_string_for_list(subdevice_idx_list)}' if subdevice_idx_list else ''}
                    {f'AND timestamp >= {start_unix*1000}' if start_unix else ''}
                    {f'AND timestamp < {end_unix*1000}' if end_unix else ''}
        """

        try:
            df = pd.read_sql(query_string, self._client)
        except Exception:
            _log.error(f"database_utils.py - get_data_from_cratedb: Connection error when getting data from CrateDB")
            return pd.DataFrame()  # Return empty dataframe if query failed

        if df.empty:
            _log.warning(f"database_utils.py - get_data_from_cratedb: Data not found in CrateDB")
            return pd.DataFrame()  # Return empty dataframe if no data is found

        # Step 2: Convert timestamp to datetime
        df = self._convert_timestamp_to_datetime(df, unit='ms')

        # Step 3: Pivot dataframe
        df = df.pivot_table(index=['datetime', 'device_id', 'subdevice_idx'], columns='datapoint', values='value',
                            aggfunc='max')

        # Step 4: Convert numerical columns to float
        for _col in df.columns:
            try:
                df[_col] = df[_col].astype(float)
            except:
                pass

        df = df.reset_index(['device_id', 'subdevice_idx'])

        self._disconnect()

        return df


class ConditionBased:
    """
    This Class handle the condition-based maintenacne of devices 
    """
    
    def __init__(self, asset_id: str, condition_config: list, crate_instance: CrateDB):
        self._asset_id = asset_id
        self._condition_config = condition_config
        self._crate = crate_instance
    
    def gen_notify_text(self, results: list):
        """ Generate human-readable text from results list
        Currently, the function only supports conditions with at most 2 sub-conditions, and each sub-condition can take at most
        2 datapoints for calculation. The template for the text is formulated as below,

        Template 1 (sub-condition with only 1 datapoint considered):
        --- The current <datapoint> (<current_value> <unit>) is <operation> set value of <threshold_value> <unit> for <period> minutes.
        ex. The current temperature (23 °C) is higher than set value of 20 °C for 30 minutes.

        Template 2 (sub-condition with 2 datapoints being used to calculate another calculated datapoint)
        --- <calculate_operation> between <datapoint_1> and <datapoint_2> (= <current_value> <unit>) is <operation> set value of <threshold_value> <unit> for <period> minutes.
        ex. The difference between set_temperature and room_temperature (= 8 °C) is higher than set value of 5 °C for 20 minutes

        Note: If there are more than 1 condition, connect the sentence generated from template above with English connectors (such as `Also`)

        Args:
            results (list): List of condition-based conditions, each condition contain another list of chained
                            sub-conditions. Each sub-condition is a dictionary with following keys-values
                            {
                                "condition_name" : "Condition Name"   ## Note: this is condition name, not sub-condition
                                "consider_value" : [6, 8, 9]
                                "threshold_value" : 5  ## Note: value to check with
                                "operation" : ">"  ## Note: operation to compare `consider_value` and `device_value`
                                "calculate_operation": "-",
                                "datapoint_list": ["set_temperature", "room_temperature"],
                                "time_condition_type": "period"
                                "time_period": 600 ## Note: in seconds
                            }
        Returns:
            paragraph (str): Text for Line notification

        """
        # TODO: Move these config to somewhere else more proper
        _operation_sign_to_text = {
            ">": "higher than",
            ">=": "higher than",
            "<": "lower than",
            "<=": "lower than",
            "==": "equal to",
            "!=": "not equal to"
        }
        _unit_mapping = {
            "temperature": "°C",
            "room_temperature": "°C",
            "set_temperature": "°C",
            "power": "kW",
            "humidity": "%",
            "co2": "ppm"
        }
        _calculate_operation_to_text = {
            "diff": "The difference",
            "sum": "The addition",
        }

        paragraph = f"Asset: {self._asset_id}"
        for idx, condition in enumerate(results):

            paragraph += "\n\n"
            for sub_idx, subcondition in enumerate(condition):

                current_value = statistics.mean(subcondition.get("consider_value"))
                datapoint_list = subcondition.get("datapoint_list")
                device_id_list = subcondition.get("device_id_list")
                operation = subcondition.get("operation")
                calculate_operation = subcondition.get("calculate_operation")
                threshold_value = subcondition.get("threshold_value")
                time_condition_type = subcondition.get("time_condition_type")

                if time_condition_type == 'period':
                    period = subcondition.get("time_period")
                    period_text = "average"
                    time_text = f" for the past {period/60:.0f} minutes"
                elif time_condition_type == 'instant':
                    period_text = "current"
                    time_text = ""

                # Template 1:
                if len(datapoint_list) == 1:
                    datapoint_1 = datapoint_list[0]
                    text = f"The {period_text} {datapoint_1} {time_text} ({current_value:.1f} {_unit_mapping.get(datapoint_1, '')}) " \
                           f"is {_operation_sign_to_text.get(operation, 'violated from')} set value of {threshold_value} " \
                           f"{_unit_mapping.get(datapoint_1)}."
                # Template 2
                elif len(datapoint_list) == 2:
                    datapoint_1 = datapoint_list[0]
                    datapoint_2 = datapoint_list[1]
                    text = f"{_calculate_operation_to_text.get(calculate_operation, '')} between {datapoint_1} " \
                           f"and {datapoint_2} (= {current_value:.1f} {_unit_mapping.get(datapoint_1)}) is " \
                           f"{_operation_sign_to_text.get(operation, 'violated from')} set value of {threshold_value} " \
                           f"{_unit_mapping.get(datapoint_1)}{time_text}."

                if sub_idx == 1:  # Add connectors word `Also` between first and second condition
                    text = "Also, " + text[0].lower() + text[1:]

                paragraph += text
                paragraph += "\n"
                paragraph += f"https://shelldata.altotech.net/apps/all-data?" \
                             f"start_date={pendulum.today(tz='Asia/Bangkok').to_date_string()}" \
                             f"&end_date={pendulum.today(tz='Asia/Bangkok').add(days=1).to_date_string()}" \
                             f"&device_id={device_id_list[0]}"

            paragraph += "\n\n"

        return paragraph.strip()


    def check_condition(self):
        """
        return {
            "status": bool,
            "payload": list
        }
        """
        _log.debug(f"Start Check Condition Based")
        # Step 1: initialize memory variable
        results = list()  # list of violated conditions

        # Step 2: get all conditions for the selected device
        # device_condition: dict = self._condition_config.get(device_id)
        # assert device_condition is not None, "ConditionBased: invalid `device_id` input"
        # device_conditions: list = device_condition.get('condition_based')

        # (optional) TODO: query everything from Crate once and use the data throughout the checking (reduce redundant data query) 
        # - can be done by iterate through all conditions and store all unique case that need to be query

        # Step 3: iterative condition checking
        for device_condition in self._condition_config:
            condition_name = device_condition['condition_name']
            _log.debug(f"Condition Name: {condition_name}")
            
            conditions = device_condition['conditions']
            condition_operation = device_condition['operation']  # options: "and", "or"
            
            condition_results = list()  # list of sub-condition results

            # Step 3.1: iterate through each sub-condition
            for condition in conditions:
                # information for query
                datapoint_keys: list = condition['datapoint']
                time_condition: dict = condition['time_condition']

                # information for condition checking
                calculate_operation = condition['calculate_operation']
                operation = condition['operation']  # options: "==", "!=", ">", ">=", "<", "<="
                value = condition['value']

                # Check whether the time in between a specified range
                now = pendulum.now(tz='Asia/Bangkok')
                lower, upper = time_condition['value']['between']
                if now.hour < lower or now.hour > upper:
                    continue

                # Specify correct time period for each `time_condition`
                time_condition_type = time_condition['type']  # options: "period", "instant"
                
                if time_condition_type == "instant":
                    period = 60
                elif time_condition_type == "period":
                    period = time_condition['value']['period']
                else:
                    raise ValueError("time_condition_type `{time_condition_type}` is not supported")

                # get all data from CrateDB
                datapoints_list = list()
                device_id_list = list()
                datapoints_name_list = list()
                for datapoint_key in datapoint_keys: # datapoint_key = {"subdevice_idx": 0, "data_type": "environment", "datapoint": "temperature", "location": "XXX"}
                    _data: pd.DataFrame = self._crate.get_timeseries_data(
                        location=datapoint_key['location'],
                        device_id_list=[datapoint_key['device_id']],
                        datapoint_list=[datapoint_key['datapoint']],
                        subdevice_idx_list=[datapoint_key['subdevice_idx']],
                        start_unix=int(now.timestamp() - period),
                        end_unix=int(now.timestamp()),
                    )
                    if _data.empty:
                        datapoints_list = list()  # Reset datapoints list to empty list if any of the datapoint is not found
                        break
                    # _log.debug(f"_data: {_data}")
                    datapoints_list.append(_data[datapoint_key['datapoint']])  # Append pd.Series to datapoints list
                    device_id_list.append(datapoint_key['device_id'])
                    datapoints_name_list.append(datapoint_key['datapoint'])
                
                # calculate new value from datapoint based on `calculate_operation`                
                #  TODO: Add handle for empty data (ex. Line notify?)
                # Skip this condition to next condition if a single datapoint in datapoints list is not found
                if len(datapoints_list) == 0:
                    continue

                if calculate_operation == "None":
                    consider_value: pd.Series = datapoints_list[0]
                elif calculate_operation == "diff":
                    consider_value: pd.Series = abs(datapoints_list[0] - datapoints_list[1])
                else:
                    raise ValueError('ConditionBased: selected `calculate_operation` setting is not implemented yet')

                # _log.debug(f"consider_value: {consider_value}")
                # check condition between `consider_value` and `value`
                _condition_result = dict()  # will get update if violated
                if operation == "==":
                    if (consider_value == value).all():
                        _condition_result.update({
                            "condition_name": condition_name,
                            "consider_value": consider_value.to_list(), 
                            "threshold_value": value,
                            "operation": operation,
                            "calculate_operation": calculate_operation,
                            "device_id_list": device_id_list,
                            "datapoint_list": datapoints_name_list,
                            "time_condition_type": time_condition_type,
                            "time_period": period
                        })
                elif operation == "!=":
                    if (consider_value != value).all():
                        _condition_result.update({
                            "condition_name": condition_name,
                            "consider_value": consider_value.to_list(), 
                            "threshold_value": value,
                            "operation": operation,
                            "calculate_operation": calculate_operation,
                            "device_id_list": device_id_list,
                            "datapoint_list": datapoints_name_list,
                            "time_condition_type": time_condition_type,
                            "time_period": period
                        })
                elif operation == ">":
                    if (consider_value > value).all():
                        _condition_result.update({
                            "condition_name": condition_name,
                            "consider_value": consider_value.to_list(), 
                            "threshold_value": value,
                            "operation": operation,
                            "calculate_operation": calculate_operation,
                            "device_id_list": device_id_list,
                            "datapoint_list": datapoints_name_list,
                            "time_condition_type": time_condition_type,
                            "time_period": period
                        })
                elif operation == ">=":
                    if (consider_value >= value).all():
                        _condition_result.update({
                            "condition_name": condition_name,
                            "consider_value": consider_value.to_list(), 
                            "threshold_value": value,
                            "operation": operation,
                            "calculate_operation": calculate_operation,
                            "device_id_list": device_id_list,
                            "datapoint_list": datapoints_name_list,
                            "time_condition_type": time_condition_type,
                            "time_period": period
                        })
                elif operation == "<":
                    if (consider_value < value).all():
                        _condition_result.update({
                            "condition_name": condition_name,
                            "consider_value": consider_value.to_list(), 
                            "threshold_value": value,
                            "operation": operation,
                            "calculate_operation": calculate_operation,
                            "device_id_list": device_id_list,
                            "datapoint_list": datapoints_name_list,
                            "time_condition_type": time_condition_type,
                            "time_period": period
                        })
                elif operation == "<=":
                    if (consider_value <= value).all():
                        _condition_result.update({
                            "condition_name": condition_name,
                            "consider_value": consider_value.to_list(), 
                            "threshold_value": value,
                            "operation": operation,
                            "calculate_operation": calculate_operation,
                            "device_id_list": device_id_list,
                            "datapoint_list": datapoints_name_list,
                            "time_condition_type": time_condition_type,
                            "time_period": period
                        })
                else:
                    raise ValueError(f'ConditionBased: selected operator `{operation}` setting is not implemented yet')
                
                # update condition result to `condition_results`
                if len(_condition_result) > 0:
                    condition_results.append({"status": True, "condition": _condition_result})
                else:
                    condition_results.append({"status": False, "condition": dict()})
            
            # consider multiple sub-conditions and update to `results`
            if len(condition_results) > 1:
                all_status = [condition_result.get('status') for condition_result in condition_results]
                if condition_operation == "and":
                    if all(all_status):  # if all status is True
                        _result_conditions = [condition_result.get('condition') for condition_result in condition_results]
                        results.append({_result_conditions})
                elif condition_operation == "or":
                    if any(all_status):  # if any status is True
                        _result_conditions = [condition_result.get('condition') for condition_result in condition_results
                                              if condition_result.get('status')]
                        results.append(_result_conditions)
                else:
                    raise Exception('ConditionBased: selected `condition_operation` setting is not implemented yet')

            elif len(condition_results) == 1:
                _status = condition_results[0].get('status')
                if _status:
                    _result_conditions = [condition_result.get('condition') for condition_result in condition_results]
                    results.append(_result_conditions)
            else:
                # This is met when there is missing data and the condition cannot be checked
                _log.warning(f"Every conditions cannot be checked due to missing data - device_id: {datapoint_key['device_id']}")
                # raise Exception('ConditionBased: invalid `condition_results` results')

        # _log.debug(f"results: {results}")
        # Step 4: construct return payload
        # found at least 1 condition that got violated
        if len(results) > 0:
            response_text_list = list()
            for each_result in results:
                for condition in each_result:
                    text = f"{condition.get('condition_name')} with values {condition.get('consider_value')}"
                    response_text_list.append(text)
            device_id = self._condition_config[0]['conditions'][0]['datapoint'][0]['device_id']
            update_payload = {
                "device_id": device_id,
                "device_name": self._asset_id,
                "device_value": "-",
                "device_parameter": "-",
                "device_unit": "-",
                "asset_name": self._asset_id,
                "alert_type": "condition_based",
                "alert_status": "new",
                "alert_description": self.gen_notify_text(results),
                "notify_message": self.gen_notify_text(results),
                "env": "prod"
            }
            # _log.debug(f"update_payload: {update_payload}")
            return {"status": True, "payload": update_payload}
        # not found any condition that got violated
        else:
            return {"status": False, "payload": []}
        

class PredictiveMT:
    
    def __init__(self, predictive_config: dict, crate_instance: CrateDB):
        self._predictive_config = predictive_config
        self._crate = crate_instance


class PreventiveMT:
    
    def __init__(self, preventive_config: dict, crate_instance: CrateDB):
        self._preventive_config = preventive_config
        self._crate = crate_instance


class Anomaly:
    
    def __init__(self, anomaly_config: dict, crate_instance: CrateDB):
        self._anomaly_config = anomaly_config
        self._crate = crate_instance
    
    def anomaly_inference(self, asset_id: str):
        """
        self._anomaly_config = {
            "model": xxx,
            "devices": [
                {
                    "device_id": xxx,
                    "subdevice": 0,
                    "data_type": "environment",
                    "datapoint": [
                    "temperature"
                    ],
                    "location": "alto_demo_room/iot_devices"
                },
                {
                    "device_id": "Tuya 60A meter 1",
                    "subdevice_idx": 0,
                    "data_type": "electric",
                    "datapoint": [
                    "current",
                    "energy",
                    "power",
                    "voltage"
                    ],
                    "location": "alto_demo_room/iot_devices"
                }
            ]
        }
        """
        if self._anomaly_config:
            data: list = self._anomaly_config['devices']

            df = pd.DataFrame()

            start_unix = int(pendulum.now().subtract(days=7).timestamp())
            end_unix = int(pendulum.now().timestamp())
            # for asset_data in data.keys():

            #     devices = data[asset_data]['anomaly']['devices']
            for device in data:

                device_id_list = []
                subdevice_idx_list = []

                device_id_list.append(device['device_id'])
                subdevice_idx_list.append(device['subdevice_idx'])
                datapoint_list = device['datapoint']
                location = device['location']

                device_data = self._crate.get_timeseries_data(location,
                                                                    device_id_list,
                                                                    datapoint_list,
                                                                    None,
                                                                    start_unix,
                                                                    end_unix)
                try:
                    device_data = device_data['power'].resample('1min').last().interpolate()
                except Exception as e:
                    device_data = device_data.resample('1min').last().bfill()

                df = pd.concat([df, device_data], axis=1)

            df = df.sort_index().dropna()

            # Prepare features from the dataframe columns
            features = ["current", "voltage", "power", "set_temperature", "room_temperature", "diff_temp", "humidity"]
            use_features = ["power", "temperature"]

            # Inference using DBSCAN model
            x, y = dbscan_model(df, use_features, _eps=0.9, _min_samples=4)

            # Prepare inference results for plotting
            plot_df = df[use_features].loc[df[use_features].index]

            if len(y) > 0:
                y = pd.DataFrame(y)[1]
            else:
                y = list([np.NaN])

            # Get figure for plotting and html data for uploading to database
            fig = render_plot(plot_df, x, y, use_features, asset_id)

            # Notify abnormal status
            abnormal_status_staging = check_anomaly_status(plot_df, x, 1)
            abnormal_status_prod = check_anomaly_status(plot_df, x, 3)

            # Set up date for uploading to database and notify message construction
            datetime = pendulum.now()
            local_datetime = pendulum.now(tz='Asia/Bangkok')
            unix_timestamp = time.mktime(datetime.timetuple())
            datetime_str = local_datetime.to_datetime_string().replace(' ', '_')

            # If anomaly status is True save log of Plotly figure as an .html file
            if abnormal_status_staging and abnormal_status_prod:
                print("[PRODUCTION] Anomaly detected in " + asset_id)
                current_path = os.path.dirname(__file__)

                # Initialize the Azure Storage Blob
                blob_connection_str = "DefaultEndpointsProtocol=https;AccountName=altotechstorage;AccountKey=JuSqym+3D61a7Hx+jEst9ZCBM5TW7kuf0zq61WmnCc9G3goAAsJQYgiJZE+4IH7vPc3hPU+VsdQFohhO6fXYnQ==;EndpointSuffix=core.windows.net"
                blob_container_name = "$web"
                blob_location_path = "shell/shell_select_rama2/"
                blob_client = BlobClient(blob_connection_str, blob_container_name)

                file_name = f"{asset_id.replace(' ', '_')}_{str(datetime_str)}.html"
                fig.write_html(current_path + "/assets/" + file_name)
                blob_file_path = blob_location_path + file_name

                # Upload the html file to Azure Storage Blob
                content_type = 'text/html'
                blob_client.upload(current_path + '/assets/' + file_name, blob_file_path, content_type)
                print('Successfully upload figure to Azure Storage Blob')
                html_link = "https://altotechstorage.z23.web.core.windows.net/" + blob_file_path
                msg = "Anomaly detected on " + asset_id + " at " + datetime_str + ". Please check the figure at " + html_link

                # TODO 
                # for testing change "env" into "staging"
                # for production change "env" into "prod"
                payload = {
                        "device_id": "ebc130be2d36e91da6nj92",
                        "device_name": asset_id,
                        "device_parameter": "-",
                        "device_value": "-",
                        "device_unit": "-",
                        "asset_name": asset_id,
                        "alert_type": "anomaly",
                        "alert_status": "new",
                        "alert_description": f"Anomaly detected at {asset_id}!",
                        "notify_message": msg,
                        "env": "prod"
                        }

                return {"status": True, "payload": payload}

            # Staging anomaly status
            if abnormal_status_staging and not abnormal_status_prod:
                print("[STAGING] Anomaly detected in " + asset_id)
                current_path = os.path.dirname(__file__)

                # Initialize the Azure Storage Blob
                blob_connection_str = "DefaultEndpointsProtocol=https;AccountName=altotechstorage;AccountKey=JuSqym+3D61a7Hx+jEst9ZCBM5TW7kuf0zq61WmnCc9G3goAAsJQYgiJZE+4IH7vPc3hPU+VsdQFohhO6fXYnQ==;EndpointSuffix=core.windows.net"
                blob_container_name = "$web"
                blob_location_path = "shell/shell_select_rama2/"
                blob_client = BlobClient(blob_connection_str, blob_container_name)

                file_name = f"{asset_id.replace(' ', '_')}_{str(datetime_str)}.html"
                fig.write_html(current_path + "/assets/" + file_name)
                blob_file_path = blob_location_path + file_name

                # Upload the html file to Azure Storage Blob
                content_type = 'text/html'
                blob_client.upload(current_path + '/assets/' + file_name, blob_file_path, content_type)
                print('Successfully upload figure to Azure Storage Blob')
                html_link = "https://altotechstorage.z23.web.core.windows.net/" + blob_file_path
                msg = "Anomaly detected on " + asset_id + " at " + datetime_str + ". Please check the figure at " + html_link

                payload = {
                        "device_id": "ebc130be2d36e91da6nj92",
                        "device_name": asset_id,
                        "device_parameter": "-",
                        "device_value": "-",
                        "device_unit": "-",
                        "asset_name": asset_id,
                        "alert_type": "anomaly",
                        "alert_status": "new",
                        "alert_description": f"Anomaly detected at {asset_id}!",
                        "notify_message": msg
                        }

                return {"status": True, "payload": payload}
            
        return {"status": False, "payload": []}
        


def maintenance(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Maintenance
    :rtype: Maintenance
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    cron_interval = config.get('cron_interval', "*/10 * * * *")
    stage = config.get('stage', 'staging')
    databases = config.get('databases', {})
    devices = config.get('devices', {})
    backend_url = config.get('backend_url', "https://buildingfunctions.azurewebsites.net/api/alert")
    
    return Maintenance(cron_interval, stage, databases, devices, backend_url, **kwargs)


class Maintenance(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, cron_interval: str, stage: str, databases: dict, devices: dict, backend_url: str, **kwargs):
        super(Maintenance, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        
        self._cron_intetval = cron_interval
        self._stage = stage
        self._databases = databases
        self._devices = devices
        self._backend_url = backend_url
        
        self._crate_client = None
        self._condition_based = None
        self._anomaly = None
        self._preventive = None
        self._predictive = None
        self._databases_instance = {}
        self._devices_instance = {}

        self.default_config = {
            "cron_interval": cron_interval,
            "stage": stage,
            "databases": databases,
            "devices": devices,
            "backend_url": backend_url
            }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        # Step 1: config storing and variables
        try:
            cron_interval = config.get('cron_interval', "*/5 * * * *")
            stage = config.get('stage', 'staging')
            databases = config.get('databases', {})
            devices = config.get('devices', {})
            backend_url = config.get('backend_url', {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self._cron_intetval = cron_interval
        self._stage = stage
        self._databases = databases
        self._devices = devices
        self._backend_url = backend_url
        
        # Step 2: Build Maintenance Instances
        self._build_instance()
        # self._run()
        self.core.schedule(cron(self._cron_intetval), self._run)
        
    def _build_instance(self):
        _log.debug("Maintenance _build_instance")
        try:
            if self._databases:
                for db_name, cred in self._databases.items():
                    if cred['username'] and cred['password']:
                        self._databases_instance[db_name] = CrateDB(
                            host=cred['host'],
                            port=cred['port'],
                            username=cred['username'],
                            password=cred['password'],
                            table=cred['table']
                        )
                    else:
                        self._databases_instance[db_name] = CrateDB(
                            host=cred['host'],
                            port=cred['port'],
                            table=cred['table']
                        )
                _log.debug(f"Databases Instance: {self._databases_instance}")
            
            if self._devices:
                for asset_id, maintenance_type in self._devices.items():
                    database = self._databases_instance[maintenance_type['database'][0]]
                    self._devices_instance[asset_id] = {
                        "condition_based": ConditionBased(
                           asset_id, maintenance_type['condition_based'], database
                        ),
                        "predictive": PredictiveMT(
                            maintenance_type['predictive'], database
                        ),
                        "preventive": PreventiveMT(
                            maintenance_type['preventive'], database
                        ),
                        "anomaly": Anomaly(
                            maintenance_type['anomaly'], database
                        )
                    }
                _log.debug(f"devices_instance: {self._devices_instance}")
        except Exception as e:
            _log.exception(f"_build_instance Error: {e}")
        
    def _run(self):
        try:
            for asset_id, maintenance in self._devices_instance.items():
                # Step 3: Check Condition-Based
                cond_ret = maintenance['condition_based'].check_condition()
                _log.debug(f"cond_ret: {cond_ret}")
                if cond_ret['status']:
                    self._publish(cond_ret['payload'])
                    continue
                else:
                    # Step 4: Check Predictive Maintenance
                    # Step 5: Check Anomaly
                    anomaly_ret = maintenance['anomaly'].anomaly_inference(asset_id)
                    _log.debug(f"anomaly_ret: {anomaly_ret}")
                    if anomaly_ret['status']:
                        pass
                        # self._publish(anomaly_ret['payload'])
        except Exception as e:
            _log.exception(f"_run Error: {e}")

    def _publish(self, data_payload: dict):
        payload = {
            "site": "shell",
            "unix_timestamp": int(time.time()),
            "env": self._stage
        }
        payload.update(data_payload)
        headers = {
            "Content-Type": 'application/json'
        }
        _log.debug(f'Payload: {payload}')
        try:
            response = requests.post(self._backend_url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                _log.debug(f"Success, response")
            else:
                _log.warning(f"Fail response")
        except Exception as e:
            _log.exception(f"Maintenance _publish Error: {e}")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        # Example publish to pubsub
        self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # Example RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(maintenance, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
