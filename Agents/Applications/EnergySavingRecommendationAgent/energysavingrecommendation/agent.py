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

from azure.cosmos import CosmosClient
import pandas as pd
import requests
import pendulum
import pyrebase

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
            last_day_of_last_month_date = pendulum.now('Asia/Bangkok').subtract(months=1).end_of('month').to_date_string()
            tomorrow_date = pendulum.tomorrow('Asia/Bangkok').to_date_string()
            query_string = f"SELECT c.timestamp, c.device_id, c.subdevice_idx, c.location, c.subdevice_name, \
            c.power, \
            c.energy, c.gatewayid FROM c WHERE c.gatewayid='altonucmintelmonitor' \
            AND c.location='main_energy/iot_devices' AND c.subdevice_idx=3 AND c.timestamp >= '{last_day_of_last_month_date}' \
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
            # print(df)
            return df
        except Exception as e:
            print(f"[Error] get dataset from cosmosdb function: {e}")


    def prepare_dataset(self, df):
        try:
            df.dropna(inplace=True)
            columns = ['timestamp', 'power']
            df = df[columns]
            df['timestamp'] = df['timestamp'].apply(lambda x: pendulum.parse(x).add(hours=7).to_datetime_string())
            df['timestamp'] = pd.to_datetime(df['timestamp'], yearfirst=True)
            df.set_index('timestamp', inplace=True)
            start_of_this_month = pendulum.now('Asia/Bangkok').start_of('month').to_datetime_string()
            end_of_this_month = pendulum.now('Asia/Bangkok').end_of('month').to_datetime_string()
            df = df.loc[start_of_this_month:end_of_this_month]
            df = df.resample('1H').mean().interpolate()
            # print("finish prepare dataset function")
            # print(df)
            return df
        except Exception as e:
            print(f"[Error] prepare dataset: {e}")


    def calculate_each_hour_average_power(self, df):
        try:
            df['hour'] = df.index.hour
            kw = []
            for i in range(0, 24):
                power_list = df[df['hour']==i]['power'].values
                power = round(sum(power_list)/len(power_list), 2)
                kw.append(power)
            # print("finish calculate each hour average power function")
            return kw
        except Exception as e:
            print(f"[Error] calculate each hour average power function: {e}")


    def update_firebase(self, kw):
        try:
            d = {}
            for i in range(0, 24):
                if i < 10:
                    data = {f'0{i}:00': kw[i]}
                    d.update(data)
                else:
                    data = {f'{i}:00': kw[i]}
                    d.update(data)
            #firebase
            print(d)
            db.child("hotel").child("mintel").child("energy").child("energy_saving_recommendation").child("power_consumption").update(d)
            db.child("hotel").child("mintel").child("energy").child("solar_pv_recommendation").child("power_consumption").update(d)
        except Exception as e:
            print(f"[Error] calculate update firebase function: {e}")



    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        # Outline
        # Step 1: Get dataset from cosmosdb
        # Step 2: Prepare dataset
        # Step 3: Calculate each hour average power
        # Step 4: Update firebase

        # Step 1
        df = self.get_dataset_from_cosmosdb()

        # Step 2: Prepare dataset
        df = self.prepare_dataset(df)

        # Step 3: Calculate each hour average power
        kw = self.calculate_each_hour_average_power(df=df)

        # Step 4: Update firebase
        self.update_firebase(kw=kw)

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


    @Core.schedule(periodic(1800))
    def electricity_by_hour(self):
        self.now_timestamp = pendulum.now('Asia/Bangkok').int_timestamp
        if self.counter == 0:
            self.counter += 1
            return None

        # Step 1
        df = self.get_dataset_from_cosmosdb()

        # Step 2: Prepare dataset
        df = self.prepare_dataset(df)

        # Step 3: Calculate each hour average power
        kw = self.calculate_each_hour_average_power(df=df)

        # Step 4: Update firebase
        self.update_firebase(kw=kw)

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
