"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import json
import time

import pyrebase
import pendulum
import pandas as pd
from azure.cosmos import CosmosClient
from datetime import datetime, timedelta, timezone
import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub
from volttron.platform.scheduling import periodic, cron
from pprint import pformat
from typing import Dict, List, Tuple, Union
import requests
from volttron.platform.messaging.health import STATUS_GOOD, STATUS_BAD, STATUS_STARTING, STATUS_UNKNOWN
import json
_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


# configuration and setting cosmosDB
cosmos_url = "https://altocosmos.documents.azure.com:443/"
cosmos_key = "W6BRohNWpaaOFAyFMxW5NPGuHCDUHTNwQwXDVOyvMeDxLEtKBE8oF62GoWH2j4xUa3td5jIh6ljt8EVf5lmNdw=="
client = CosmosClient(cosmos_url, credential=cosmos_key)
database_name = 'altonucminteldb'
database = client.get_database_client(database_name)
container_name = 'iotcontainer'
container = database.get_container_client(container_name)

# configuration and setting firebase
firebase_config = {
    "apiKey": "AIzaSyD9tk_eukD0pyRUAWO9lFqMTy4hGbTFJJA",
    "authDomain": "altogetstarted.firebaseapp.com",
    "databaseURL": "https://altogetstarted-default-rtdb.firebaseio.com",
    "storageBucket": "altogetstarted.appspot.com",
}
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()


def tester(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Tester
    :rtype: Tester
    """
    try:
        config = utils.load_config(config_path)
    except Exception as er:
        print(er)
        config = {}
    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")
    heartbeat_period = int(config.get("heartbeat_period", 10))
    message = config.get('message', "DEFAULT_MESSAGE")
    return Tester(setting1, setting2, heartbeat_period, message, **kwargs)


class Tester(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic", heartbeat_period=10, message="message", **kwargs):
        super(Tester, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self._logfn = _log.info
        self.setting1 = setting1
        self.setting2 = setting2
        self.publish_value = 1
        self._heartbeat_period = heartbeat_period
        self._message = message
        self.default_config = {"setting1": setting1,
                               "setting2": setting2}

        self._heartbeat_period = heartbeat_period

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

        try:
            setting1 = int(config["setting1"])
            setting2 = str(config["setting2"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.setting1 = setting1
        self.setting2 = setting2

        self._create_subscriptions(self.setting2)

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
        self._logfn(
            "Peer: {0}, Sender: {1}:, Bus: {2}, Topic: {3}, Headers: {4}, "
            "Message: \n{5}".format(peer, sender, bus, topic, headers, pformat(message)))

    def get_dataset_from_cosmosdb(self, **kw):
        try:
            # SELECT c.timestamp, c.device_id, c.subdevice_idx, c.location, c.power, c.energy \
            query_string = f"SELECT * \
                             FROM c \
                             WHERE c.gatewayid='{kw['gatewayid']}' \
                             AND c._ts>={pendulum.now('Asia/Bangkok').subtract(minutes=15).int_timestamp} \
                             AND c.location LIKE 'cu_ihouse/%/iot_devices' \
                             ORDER BY c._ts ASC"

            results = []
            try:
                for item in container.query_items(
                        query=query_string,
                        enable_cross_partition_query=True):
                    # print(json.dumps(item, indent=True))
                    results.append(item)
            except Exception as e:
                print("no data")
                print(e)

            return results
        except Exception as e:
            print(f"[Error] get dataset from cosmosdb function: {e}")

    def prepare_dataframe(self, data: list):
        df = pd.DataFrame(data)
        columns_to_drop = ['id', '_rid', '_self', '_etag', '_attachments', '_ts']
        df = df.drop(columns=columns_to_drop)

        # datetime
        df = df.rename(columns={"timestamp": "datetime"})
        df['datetime'] = pd.to_datetime(df['datetime'], yearfirst=True)
        df['datetime'] = df['datetime'].map(lambda x: x.tz_convert('Asia/Bangkok'))

        # set index
        df.set_index('datetime', inplace=True)
        df = df.sort_index()
        return df

    def process_data(self, df) -> dict:
        """

        Args:
          df (DataFrame): incoming datafra,e
          df_all (DataFrame): all data dataframe
          df_id (DataFrame): each device_id dataframe

        Returns:
            dict: data to publish to IoTHub
        """
        df_all = df.copy()
        data = {}
        for device_id in df_all['device_id'].unique():
            try:
                df_id = df_all[df_all['device_id'] == device_id]
                df_last_record = df_id.iloc[-1]

                columns_to_calculate_mean = ['power', 'power_factor', 'frequency', 'power_apparent', 'power_reactive',
                                             'voltage', 'current']
                df = df_id[columns_to_calculate_mean]
                df = df.mean()

                for column in columns_to_calculate_mean:
                    df_last_record[column] = df[column]

                df_last_record = df_last_record.to_dict()
                df_last_record.update({
                    'timestamp': str(pendulum.now('UTC').to_atom_string()),
                    'sample_min': 15
                })
                data.update({
                    device_id: df_last_record
                })
            except Exception as e:
                print(e)

        return data

    def sum_all_df(self, data):
        try:
            df1 = pd.DataFrame(data.get('9c:a5:25:ab:3a:a4:8'), index=[0])
            df2 = pd.DataFrame(data.get('9c:a5:25:ab:3a:a4:9'), index=[0])
            df3 = pd.DataFrame(data.get('9c:a5:25:ab:3a:a4:10'), index=[0])
            df4 = pd.DataFrame(data.get('9c:a5:25:ab:3a:a4:11'), index=[0])
            df5 = pd.DataFrame(data.get('9c:a5:25:ab:3a:a4:12'), index=[0])
            df_all = df1 + df2 + df3 + df4 + df5
            columns = ['power', 'power_factor', 'energy', 'energy_reactive_to_grid', 'energy_reactive_net',
                       'power_apparent',
                       'power_reactive', 'energy_to_grid', 'energy_total', 'voltage', 'current', 'energy_apparent',
                       'energy_reactive',
                       'energy_reactive_total', 'energy_net']
            df_all = df_all[columns]
            df_all['power_factor'] = df_all['power_factor'] / 5
            df_all['voltage'] = df_all['voltage'] / 5
            df_all['type'] = 'electric'
            df_all['floor'] = 'floor_6'
            df_all['record_type'] = 'total_electric'
            df_all['location'] = 'cu_ihouse/floor_6/main_energy/iot_devices'
            df_all['gatewayid'] = 'altopicuterracemonitor'
            df_all['timestamp'] = str(pendulum.now('UTC').to_atom_string())
            df_all['sample_min'] = 15
            return df_all.to_dict('records')[0]
        except Exception as e:
            print(f"sum_all_df error: {e}")

    def publish_to_vip(self, data):
        for device_id, value in data.items():
            try:
                value['subdevice_idx'] = 0
                self.vip.pubsub.publish(peer='pubsub',
                                        topic=f"datalogger/room/{device_id}/function",
                                        headers={'requesterID': self.core.identity, "message_type": "event"},
                                        message=value
                                        )
                time.sleep(3)
            except Exception as e:
                print(f"publish_to_vip error: {e}")

        print("[publish_to_vip] datalogger Success!")

    def publish_sum_data_to_vip(self, data):
        self.vip.pubsub.publish(peer='pubsub',
                                topic=f"datalogger/floor/6/function",
                                headers={'requesterID': self.core.identity, "message_type": "event"},
                                message=data
                                )
        print("[publish_sum_data_to_vip] datalogger Success!")


    def run_all_fn(self):
        try:
            result = self.get_dataset_from_cosmosdb(gatewayid='altopicuterracemonitor')
            df_elec = self.prepare_dataframe(result)
            data = self.process_data(df_elec)
            self.publish_to_vip(data)

            sum_dict = self.sum_all_df(data)
            self.publish_sum_data_to_vip(sum_dict)

            print(f"datetime {datetime.now()}")
            print("Done Cron job")
            return data
        except Exception as e:
            print(f"run all fn error: {e}")

    def sayhi(self):
        print(f"datetime {datetime.now()}")
        print("Hello-World!")

    def sayperiodic_callback(self):
        print(f"datetime {datetime.now()}")
        print("sayperiodic_callback!")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        _log.debug("VERSION IS: {}".format(self.core.version()))
        # self.run_all_fn()
        # self.core.schedule(datetime.now() + timedelta(seconds=8), self.sayhi)
        self.core.schedule(cron('*/15 * * * *'), self.run_all_fn)

        # self.core.periodic(10, self.publish_oscillating_update)

        # if self._heartbeat_period != 0:
        #     _log.debug(f"Heartbeat starting for {self.core.identity}, published every {self._heartbeat_period}s")
        #     self.vip.heartbeat.start_with_period(self._heartbeat_period)
        #     self.vip.health.set_status(STATUS_GOOD, self._message)

        # Example RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        # pass

    # @Core.schedule(cron('0-59 * * * *'))
    # def cron_function(self):
    #     print(f"datetime {datetime.now()}")
    #     print("this is a cron-scheduled function")

    # @Core.periodic(60)
    # def poll_api(self):
    #     print(requests.get("https://altotech.free.beeceptor.com").json())

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        # Example publish to pubsub
        # self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # using the agent's core to schedule a task
        # self.core.schedule(periodic(5), self.sayhi)
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
        print(f"{self.core.identity} received RPC call {self.setting1 + arg1 - arg2}")
        print(kwarg1)
        return self.setting1 + arg1 - arg2

    @RPC.export
    def rpc_call(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        print(f"{self.core.identity} received RPC call {self.setting1 + arg1 + arg2}")
        print(kwarg1)
        return self.setting1 + arg1 + arg2

    # When calling this RPC method, the user should supply a string as input
    @RPC.export
    def type_hint_rpc(input_string: str):
        print(f"input_string: {input_string}")
        return input_string

    # API validation
    @RPC.export
    def type_checking_rpc(self, input_str: str) -> Dict:
        print(f"type_checking_rpc: {input_str}")
        if not isinstance(input_str, str):
            # Include a descriptive error message to help the user determine why input validation failed
            # You can make use of 'f-strings' to help the user with debugging
            raise ValueError(
                f'The expected input type for function "type_checking_rpc" is str, received {type(input_str)}')
        else:
            return {"result": "ok"}

    @RPC.export
    def value_checking_rpc(self, input_json: Union[str, dict]) -> dict:
        print(type(input_json))
        print(isinstance(input_json, dict))
        if not isinstance(input_json, str) and not isinstance(input_json, dict):
            # You can make use of 'f-strings' to help the user determine why input validation failed
            raise ValueError(
                f'The expected input type for function "value_checking_rpc" is str or dict, received {type(input_json)}')
        else:
            # since we expected the input to be valid JSON, be sure that it can be correctly parsed
            if isinstance(input_json, str):
                input_json = json.loads(input_json)
            # for this example, we expect our JSON to include two fields: test1 and test2
            # Use 'dict.get(<key>)' rather than 'dict[<key>]' to return None and avoid causing a KeyError if the key
            #  is not present.  Optionally, a second argument can be added to specify a default value to use in
            # place of None: 'dict.get(<key>, <default value>)'
            test_1 = input_json.get("test1")
            test_2 = input_json.get("test2")
            # test 1 must be any string value
            if not isinstance(test_1, str):
                raise ValueError('Input JSON should contain key "test1" with value of type str')
            # test 2 must be an integer value with value between 0 and 100 inclusive
            if isinstance(test_2, int) and (0 < test_2 or test_2 > 100):
                _log.warning(f'Field "test2" in input JSON was out of range (0 - 100): {test_2}, defaulting to 50')
                test_2 = 50
            else:
                test_2 = 50
            return {"result": test_2}


    def publish_oscillating_update(self):
        """
        Publish an "oscillating_value" which cycles between values 1 and 0 to the message bus using the topic
        "some/topic/oscillating_value"
        """
        self.publish_value = 1 if (self.publish_value == 0) else 0
        self.vip.pubsub.publish('pubsub', 'some/topic/', message={"oscillating_value": f"{self.publish_value}"})


def main():
    """Main method called to start the agent."""
    utils.vip_main(tester,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
