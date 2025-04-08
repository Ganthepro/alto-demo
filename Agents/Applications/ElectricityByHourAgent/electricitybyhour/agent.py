# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:
#
# Copyright 2019, Battelle Memorial Institute.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This material was prepared as an account of work sponsored by an agency of
# the United States Government. Neither the United States Government nor the
# United States Department of Energy, nor Battelle, nor any of their
# employees, nor any jurisdiction or organization that has cooperated in the
# development of these materials, makes any warranty, express or
# implied, or assumes any legal liability or responsibility for the accuracy,
# completeness, or usefulness or any information, apparatus, product,
# software, or process disclosed, or represents that its use would not infringe
# privately owned rights. Reference herein to any specific commercial product,
# process, or service by trade name, trademark, manufacturer, or otherwise
# does not necessarily constitute or imply its endorsement, recommendation, or
# favoring by the United States Government or any agency thereof, or
# Battelle Memorial Institute. The views and opinions of authors expressed
# herein do not necessarily state or reflect those of the
# United States Government or any agency thereof.
#
# PACIFIC NORTHWEST NATIONAL LABORATORY operated by
# BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
# under Contract DE-AC05-76RL01830
# }}}

import logging
import sys
import json
import time

import pandas as pd
import requests
import pendulum
import pyrebase
from azure.cosmos import CosmosClient

from volttron.platform.agent import utils
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.vip.agent.subsystems.query import Query
from volttron.platform.scheduling import periodic

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '3.3'
DEFAULT_MESSAGE = 'Listener Message'
DEFAULT_AGENTID = "listener"
DEFAULT_HEARTBEAT_PERIOD = 5


# CosmosDB
cosmos_url = "https://altocosmos.documents.azure.com:443/"
cosmos_key = "W6BRohNWpaaOFAyFMxW5NPGuHCDUHTNwQwXDVOyvMeDxLEtKBE8oF62GoWH2j4xUa3td5jIh6ljt8EVf5lmNdw=="
client = CosmosClient(cosmos_url, credential=cosmos_key)
database_name = 'altonucminteldb'
database = client.get_database_client(database_name)
container_name = 'iotcontainer'
container = database.get_container_client(container_name)


firebase_config = {
    "apiKey": "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM",
    "authDomain": "altohotel-b6ae5.firebaseapp.com",
    "databaseURL": "https://altohotel-b6ae5.firebaseio.com",
    "storageBucket": "altohotel-b6ae5.appspot.com",
}
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()


class ListenerAgent(Agent):
    """Listens to everything and publishes a heartbeat according to the
    heartbeat period specified in the settings module.
    """

    def __init__(self, config_path, **kwargs):
        super().__init__(**kwargs)
        self.config = utils.load_config(config_path)
        self._agent_id = self.config.get('agentid', DEFAULT_AGENTID)
        self._message = self.config.get('message', DEFAULT_MESSAGE)
        self._heartbeat_period = self.config.get('heartbeat_period', DEFAULT_HEARTBEAT_PERIOD)
        self.counter = 0

        try:
            self._heartbeat_period = int(self._heartbeat_period)
        except:
            _log.warning('Invalid heartbeat period specified setting to default')
            self._heartbeat_period = DEFAULT_HEARTBEAT_PERIOD
        log_level = self.config.get('log-level', 'INFO')
        if log_level == 'ERROR':
            self._logfn = _log.error
        elif log_level == 'WARN':
            self._logfn = _log.warning
        elif log_level == 'DEBUG':
            self._logfn = _log.debug
        else:
            self._logfn = _log.info


    def get_dataset_from_cosmosdb(self):
        # Get dataset from cosmosdb
        try:
            yesterday_date = pendulum.yesterday('Asia/Bangkok').to_date_string()
            tomorrow_date = pendulum.now('Asia/Bangkok').add(months=1).start_of('month').to_datetime_string()
            query_string = f"SELECT c.timestamp, c.device_id, c.subdevice_idx, c.location, c.subdevice_name, \
            c.energy, c.gatewayid FROM c WHERE c.gatewayid='altonucmintelmonitor' \
            AND c.location='main_energy/iot_devices' AND c.subdevice_idx=3 AND c.timestamp >= '{yesterday_date}' \
            AND c.timestamp < '{tomorrow_date}' \
            ORDER BY c.timestamp ASC"
            time1 = time.time()
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

            print(f"Query time [second]: {time.time() - time1:.3f}")
            df = pd.DataFrame(results)
            # print("finish get dataset from cosmosdb function")
            # print(df.head())
            # print(df.tail())
            return df
        except Exception as e:
            print(f"[Error] get dataset from cosmosdb function: {e}")


    def prepare_dataset(self, df):
        try:
            columns = ['timestamp', 'energy']
            df = df[columns]
            df['timestamp'] = df['timestamp'].apply(lambda x: pendulum.parse(x).add(hours=7).to_datetime_string())
            df['timestamp'] = pd.to_datetime(df['timestamp'], yearfirst=True)
            df.set_index('timestamp', inplace=True)
            start = pendulum.today('Asia/Bangkok').to_datetime_string()
            end = pendulum.tomorrow('Asia/Bangkok').start_of('day').to_date_string()
            df = df.loc[start:end]
            df = df.loc[start:f"{end} 00"]
            df.dropna(inplace=True)
            # print("finish prepare dataset function")
            # print(df.head())
            # print(df.tail())
            return df
        except Exception as e:
            print(f"[Error] prepare dataset function: {e}")


    def prepare_hourly_dataset(self, df, column=None):
        try:
            df = df.resample('1H').min().interpolate()
            if column is not None:
                # print("finish prepare hourly dataset function")
                # print(df.head())
                # print(df.tail())
                return df[column]
            return df
        except Exception as e:
            print(f"[Error] prepare hourly dataset function: {e}")


    def create_kwh_column(self, df):
        try:
            df2 = pd.DataFrame()
            date, kwh = [], []
            for i in range(df.shape[0] - 1):
                date.append(df.index[i])
                kwh.append(df.iloc[i + 1]['energy'] - df.iloc[i]['energy'])

            df2['date'] = date
            df2['kwh'] = kwh
            df2['date'] = pd.to_datetime(df2['date'], yearfirst=True)
            df2.set_index('date', inplace=True)
            # print("finish create kwh column function")
            # print(df2.head())
            # print(df2.tail())
            return df2
        except Exception as e:
            print(f"[Error] create kwh column function: {e}")


    def update_electricity_by_hour_to_firebase(self, df):
        try:
            d = {}
            for i in range(0, 24):
                if i < 10:
                    d.update({f'0{i}:00': 0})
                else:
                    d.update({f'{i}:00': 0})

            for i in range(0, 24):
                if i > df.index[-1].hour:
                    break
                if i < 10:
                    data = {f'0{i}:00': round(df.iloc[i].kwh, 2)}
                    d.update(data)
                else:
                    data = {f'{i}:00': round(df.iloc[i].kwh, 2)}
                d.update(data)

            # firebase
            print(d)
            db.child("hotel").child("mintel").child("energy").child("electricity_by_hour").update(d)
            # print("finish update electricity by hour to firebase function")
        except Exception as e:
            print(d)
            db.child("hotel").child("mintel").child("energy").child("electricity_by_hour").update(d)
            print(f"[Error] update electricity by hour to firebase function: {e}")


    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        # Outline
        # Step 1: Get dataset from cosmosdb
        # Step 2: Prepare dataset
        # Step 3: Prepare hourly dataset
        # Step 4: Create kwh column
        # Step 5: Update to firebase

        # Step 1: Get dataset from cosmosdb
        df = self.get_dataset_from_cosmosdb()

        # Step 2: Prepare dataset
        df = self.prepare_dataset(df=df)

        # Step 3: Prepare hourly dataset
        df = self.prepare_hourly_dataset(df=df, column=['energy'])

        # Step 4: Create kwh column
        df2 = self.create_kwh_column(df=df)

        # Step 5: Update to firebase
        self.update_electricity_by_hour_to_firebase(df=df2)

        print("onsetup Done!")


    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        _log.debug("VERSION IS: {}".format(self.core.version()))
        if self._heartbeat_period != 0:
            _log.debug(f"Heartbeat starting for {self.core.identity}, published every {self._heartbeat_period}s")
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)
        query = Query(self.core)
        _log.info('query: %r', query.query('serverkey').get())


    @Core.schedule(periodic(900))
    def electricity_by_hour(self):
        self.now_timestamp = pendulum.now('Asia/Bangkok').int_timestamp
        if self.counter == 0:
            self.counter += 1
            return None

        # Outline
        # Step 1: Get dataset from cosmosdb
        # Step 2: Prepare dataset
        # Step 3: Prepare hourly dataset
        # Step 4: Create kwh column
        # Step 5: Update to firebase

        # Step 1: Get dataset from cosmosdb
        df = self.get_dataset_from_cosmosdb()

        # Step 2: Prepare dataset
        df = self.prepare_dataset(df=df)

        # Step 3: Prepare hourly dataset
        df = self.prepare_hourly_dataset(df=df, column=['energy'])

        # Step 4: Create kwh column
        df2 = self.create_kwh_column(df=df)

        # Step 5: Update to firebase
        self.update_electricity_by_hour_to_firebase(df=df2)

        print("Periodic Done!")


def main(argv=sys.argv):
    # Main method called by the eggsecutable.
    try:
        utils.vip_main(ListenerAgent, version=__version__)
    except Exception as e:
        _log.exception('unhandled exception')


if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
