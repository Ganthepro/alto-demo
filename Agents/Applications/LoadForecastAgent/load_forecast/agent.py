"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron

from alto_ds.database import AltoTimescaleDB
import pendulum
import pandas as pd
from datetime import timedelta
import datetime
import pytz
import json
import os
import numpy as np
import yaml
from pycaret.time_series import load_model

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"
AGENT_PATH = os.path.dirname(os.path.abspath(__file__)) + "/"


def load_forecast(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: LoadForecast
    :rtype: LoadForecast
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    # Get the data from config, otherwise use defaults (2nd argument)
    agent_config = config.get("volttron_agents", dict()).get('load_forecast_agent', dict())

    model_path = agent_config.get("model_path", "")
    timescaledb = agent_config.get("timescaledb", {})
    look_back_time_step = agent_config.get("look_back_time_step", {"time_step": 10080, "multiplier_to_sec": 60})
    forecast_resolution = agent_config.get("forecat_resolution", '1H')
    prediction_horizon = agent_config.get("prediction_horizon", 1440)
    cron_string = agent_config.get("cron", "0 15 * * *")
    datapoint_list = agent_config.get("feature_column", [])
    upload_inference_table = agent_config.get("upload_inference_table", "ml_inference")
    
    return LoadForecast(model_path, 
                        timescaledb, 
                        look_back_time_step, 
                        forecast_resolution, 
                        prediction_horizon,
                        cron_string,
                        datapoint_list,
                        upload_inference_table,
                        **kwargs)

class LoadForecast(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, 
                 model_path, 
                 timescaledb, 
                 look_back_time_step, 
                 forecast_resolution, 
                 prediction_horizon, 
                 cron_string,
                 datapoint_list,
                 upload_inference_table,
                 **kwargs):

        super(LoadForecast, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.model_path = model_path
        self.timescaledb = timescaledb
        self.look_back_time_step = look_back_time_step
        self.forecast_resolution = forecast_resolution
        self.prediction_horizon = prediction_horizon
        self.cron_string = cron_string
        self.datapoint_list = datapoint_list
        self.upload_inference_table = upload_inference_table

        self.default_config = {
            "model_path": model_path,
            "timescaledb": timescaledb,
            "look_back_time_step": look_back_time_step,
            "forecast_resolution": forecast_resolution,
            "prediction_horizon": prediction_horizon,
            "cron": cron_string,
            "feature_column": datapoint_list,
            "upload_inference_table": upload_inference_table
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

        if isinstance(contents, dict):
            config = contents
        else:
            try:
                config = yaml.safe_load(contents)
            except yaml.YAMLError as e:
                _log.error("Error parsing YAML:", e)
                return None
            
        try:
            config = config['volttron_agents']['load_forecast_agent']
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        try:
            model_path = config.get("model_path", "")
            timescaledb = config.get("timescaledb", {})
            look_back_time_step = config.get("look_back_time_step", {})
            forecast_resolution = config.get("forecast_resolution", "")
            prediction_horizon = config.get("prediction_horizon", {})
            cron_string = config.get("cron", "0 15 * * *")
            datapoint_list = config.get("feature_column", [])
            upload_inference_table = config.get("upload_inference_table", "ml_inference")

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.model_path = model_path
        self.timescaledb = timescaledb
        self.look_back_time_step = look_back_time_step
        self.forecast_resolution = forecast_resolution
        self.prediction_horizon = prediction_horizon
        self.cron_string = cron_string
        self.datapoint_list = datapoint_list
        self.upload_inference_table = upload_inference_table
        
        self.altodb = AltoTimescaleDB(db_name=self.timescaledb['db_name'],
                                      username=self.timescaledb['username'],
                                      password=self.timescaledb['password'],
                                      host=self.timescaledb['host'],
                                      port=self.timescaledb['port'])

        # Schedule the agent to run every hour load forecast inference
        self.core.schedule(cron(self.cron_string),  # Every 00:15 (15 0 * * *)
                           self._load_forecast_inference,
                           model_path=self.model_path,
                           timescaledb=self.timescaledb,
                           look_back_time_step=self.look_back_time_step,
                           forecast_resolution=self.forecast_resolution,
                           prediction_horizon=self.prediction_horizon,
                           datapoint_list=self.datapoint_list,
                           upload_inference_table=self.upload_inference_table)
        
        # For Debugging
        # self._load_forecast_inference(self.model_path, 
        #                               self.timescaledb, 
        #                               self.look_back_time_step, 
        #                               self.forecast_resolution, 
        #                               self.prediction_horizon,
        #                               self.datapoint_list,
        #                               self.upload_inference_table)

    def _load_forecast_inference(self, 
                                 model_path, 
                                 timescaledb, 
                                 look_back_time_step, 
                                 forecast_resolution, 
                                 prediction_horizon,
                                 datapoint_list,
                                 upload_inference_table
                                 ):
        """
        Load the model and inference the load forecast
        """
        # Initiate class attributes
        self.datapoint_list = datapoint_list
        self.upload_inference_table = upload_inference_table

        # TODO: Change to query from TimescaleDB instead
        load_data_raw = self._get_data_from_timescaledb(timescaledb, look_back_time_step)
        # Processing data + Add features
        load_data_processed = self._process_data(load_data_raw, resample_time_step=look_back_time_step['data_resolution'])

        # TODO: Change to download from Wandb's Model Registry instead
        # Load Model
        model = self._load_model(model_path)

        # Make prediction
        forecast = model.predict(load_data_processed[model.feature_names_in_[:-1]])

        # Prepare forecst result in dataframe
        forecast_result = load_data_processed[['datetime']]
        forecast_result['yhat'] = forecast

        # Format the forecast result
        forecast_result_payload = self._format_forecast_result(forecast_result=forecast_result, resample_time_step=forecast_resolution)
        
        # Update model name
        self.model_path = model_path

        # Upload the forecast result to TimescaleDB
        self._upload_forecast_result_to_timescaledb(forecast_result_payload)


    def _get_data_from_timescaledb(self, timescaledb, look_back_time_step):
        """
        Get the data from the timescaledb
        """

        table_name = timescaledb.get("table", "aggregated_data_chiller")
        location = timescaledb.get("location", "qsncc")
        
        # Get the current timestamp for making inference
        timestamp_now = pendulum.now().int_timestamp

        # Convert UNIX timestamp to datetime
        current_date = pendulum.from_timestamp(timestamp_now, tz='Asia/Bangkok')
        
        # Intialize start_time and end_time for query (7 Days back)
        self.end_time = current_date.start_of('day').int_timestamp
        self.start_time = self.end_time - int(look_back_time_step["time_step"] * look_back_time_step["multiplier_to_sec"])
        logging.debug(f"Load Forecast Inference Time: start_time: {self.start_time}, end_time: {self.end_time}")
        data = []
        for datapoint in self.datapoint_list:
            IS_PLANT_DEVICE = False if datapoint in ["humidity", "drybulb_temperature"] else True
            table_name = "weather_forecast_data" if datapoint in ["humidity", "drybulb_temperature"] else "aggregated_data_chiller"
            
            if IS_PLANT_DEVICE:
                device_id = 'plant'
                res = self.altodb.query_data(table_name=table_name,
                                                    filters={
                                                        "timestamp": {
                                                            ">": self.start_time,
                                                            "<": self.end_time,
                                                        },
                                                        "device_id": {
                                                            "=": device_id
                                                        },
                                                        "location": {
                                                            "=": location
                                                        },
                                                        "datapoint": {
                                                            "=": datapoint
                                                        }
                                                    }
                                                )
                
            else:
                res = self.altodb.query_data(table_name=table_name,
                                    filters={
                                        "forecast_at_timestamp": {
                                            ">": self.end_time - 5300, # - 90 minutes
                                            "<": self.end_time + 5300, # + 90 minutes
                                        },
                                        "datapoint": {
                                            "=": datapoint
                                        }
                                    }
                                )
            
            data.append(res)

        # Flatten the data list.
        combined_list = [item for sublist in data for item in sublist]
        
        return combined_list

    def _process_data(self, load_data_raw, resample_time_step):
        """
        Process the raw data
        """
        df = pd.DataFrame(load_data_raw)
        # If there are repeated timestamps, drop them
        df = df.drop_duplicates(subset=['timestamp', 'datapoint'])
    
        # Now pivot the DataFrame to have one row per timestamp.
        df = df.pivot(index='timestamp', columns='datapoint', values='value')

        # Rename the columns
        df = df.reset_index()
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Bangkok')
        df['datetime'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')

        df.index = pd.to_datetime(df['datetime'])
        df = df[self.datapoint_list].astype(float)

        cooling_load_df = df['cooling_rate']
        cooling_load_df = cooling_load_df.resample(resample_time_step).mean()
        cooling_load_df = cooling_load_df.reset_index()

        # Ensure data resolution and handle with interpolate
        cooling_load_df['cooling_rate'] = cooling_load_df['cooling_rate'].interpolate(method='linear')

        cooling_load_df['time'] = cooling_load_df['datetime'].dt.time
        # Create a function to calculate 7-day average for each row
        def calculate_7day_avg(row, data):
            # Define the look-back period
            end_date = row['datetime']
            start_date = end_date - pd.Timedelta(days=6)

            # Filter the data for the 7-day period
            filtered_data = data[(data['datetime'] >= start_date) & (data['datetime'] < end_date)]
            
            # Calculate the average cooling rate for this period and time
            avg_cooling = filtered_data[filtered_data['time'] == row['time']]['cooling_rate'].mean()
            
            return avg_cooling

        # Apply the function to each row
        cooling_load_df['timebased_avg_7day'] = cooling_load_df.apply(lambda row: calculate_7day_avg(row, cooling_load_df), axis=1)
        
        cooling_load_df = cooling_load_df.dropna()
        cooling_load_df.index = cooling_load_df['datetime']

        # TODO: Handling unmatch length between weather forecast data and cooling rate data
        weather_forecast_df = df[['humidity', 'drybulb_temperature']]
        weather_forecast_df = weather_forecast_df.dropna()
        weather_forecast_df = weather_forecast_df.resample(resample_time_step).interpolate(bfill=True)

        # Ensure that weather_forecast_df have data in rage from 00:00:00-23:00:00
        today = datetime.datetime.now().date()
        weather_forecast_df = weather_forecast_df[weather_forecast_df.index.date == today]
        weather_forecast_df = weather_forecast_df.between_time('00:00:00', '23:00:00')

        processed_df = pd.DataFrame()
        processed_df['drybulb_temperature'] = weather_forecast_df['drybulb_temperature']
        processed_df['humidity'] = weather_forecast_df['humidity']
        processed_df['lagged1day_cooling_rate'] = np.array(cooling_load_df[cooling_load_df['datetime'].dt.day == pd.to_datetime(self.end_time, unit='s').day].between_time('00:00:00', '23:00:00')['cooling_rate'])
        processed_df['timebased_avg_7day'] = np.array(cooling_load_df[cooling_load_df['datetime'].dt.day == pd.to_datetime(self.end_time, unit='s').day].between_time('00:00:00', '23:00:00')['timebased_avg_7day'])
        
        processed_df = processed_df.reset_index()
        processed_df['month'] = processed_df['datetime'].dt.month
        processed_df['day_of_week'] = processed_df['datetime'].dt.dayofweek
        processed_df['hour'] = processed_df['datetime'].dt.hour
        processed_df['minute'] = processed_df['datetime'].dt.minute

        processed_df = processed_df.rename(columns={'drybulb_temperature':'WU_actual_drybulb_temperature', 
                                            'humidity':'WU_actual_humidity'})
        
        return processed_df

    def _load_model(self, model_path):
        """
        Load the model
        """
        # Load PyCaret model
        if '.pkl' in model_path:
            model_path = model_path.replace('.pkl', '')
        loaded_model = load_model(AGENT_PATH + model_path)

        return loaded_model
        

    def _format_forecast_result(self, forecast_result, resample_time_step="1H"):
        """
        Format the forecast result 
        """
        # Resample data
        forecast_result.index = pd.to_datetime(forecast_result['datetime'])
        forecast_result = forecast_result.resample(resample_time_step).mean()

        # Convert the dataframe to the desired format
        items = [{"timestamp": index, "value": float(row['yhat'])} for index, row in forecast_result.iterrows()]

        buildingLoadForecast = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "timestamp": {
                        "type": "int",
                    },
                    "value": {
                        "type": "number"
                    }
                },
                "required": [
                    "timestamp",
                    "value"
                ]
            }
        }

        buildingLoadForecast['items'] = items

        return buildingLoadForecast
    
    def _upload_forecast_result_to_timescaledb(self, forecast_result_payload):
        """
        Upload the forecast result to TimescaleDB
        """

        # Set the time zone to "Asia/Bangkok" for the naive datetime object
        bangkok_timezone = pytz.timezone('Asia/Bangkok')

        # Convert timestamps to UNIX timestamps with local Asia/Bangkok timezone
        for item in forecast_result_payload['items']:
            # item['timestamp'] = item['timestamp'].timestamp()
            naive_dt = datetime.datetime.strptime(str(item['timestamp']), '%Y-%m-%d %H:%M:%S')
            localized_dt = bangkok_timezone.localize(naive_dt)
            item['timestamp'] = int(localized_dt.timestamp())
        
        data = [{
            "timestamp": int(datetime.datetime.now(pytz.timezone('Asia/Bangkok')).timestamp()),
            "datetime": datetime.datetime.now(pytz.timezone('Asia/Bangkok')).isoformat(),
            "location": self.timescaledb['location'],
            "device_id": "plant",
            "model_name": self.model_path,
            "input_value": json.dumps({"start_time":str(forecast_result_payload['items'][0]['timestamp']-86400), 
                                       "end_time": str(forecast_result_payload['items'][-1]['timestamp']-86400)}),
            "output_value": json.dumps(forecast_result_payload['items']), 
            "success_status": True
        }]
        
        try:
            # TODO: Find a way to not hardcode the table name
            self.altodb.insert_data(table_name=self.upload_inference_table, data=data)
            logging.info("Successfully insert load forecast inference result data to TimescaleDB")
        except Exception as e:
            logging.error(f"Cannot insert data to TimescaleDB due to the follow error {e}")
            raise Exception(f"Cannot insert data to TimescaleDB due to the follow error {e}")

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        pass

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

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(load_forecast, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
