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


# Firebase
firebase_config = {
    "apiKey": "AIzaSyD9tk_eukD0pyRUAWO9lFqMTy4hGbTFJJA",
    "authDomain": "altogetstarted.firebaseapp.com",
    "databaseURL": "https://altogetstarted-default-rtdb.firebaseio.com",
    "storageBucket": "altogetstarted.appspot.com",
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
        try:
            self._heartbeat_period = int(self._heartbeat_period)
        except:
            _log.warning('Invalid heartbeat period specified setting to default')
            self._heartbeat_period = DEFAULT_HEARTBEAT_PERIOD
        log_level = self.config.get('log-level', 'INFO')
        if log_level == 'ERROR':
            self._logfn = _log.error
        elif log_level == 'WARN':
            self._logfn = _log.warn
        elif log_level == 'DEBUG':
            self._logfn = _log.debug
        else:
            self._logfn = _log.info
        self.counter = 0
        self.dashboard_data = {}

    def get_dataset_from_cosmosdb(self, **kw):
        """Get data from cosmos db

        Args:
            gatewayid (str): gatewayid for that place
            from_when (str): Start date of the query.
            to_when (str): End date of the query.
        Returns:
            list: list of data

        """
        try:
            # SELECT c.timestamp, c.device_id, c.subdevice_idx, c.location, c.energy_total, c.power, c.energy, c.energy_net \
            query_string = f"SELECT c.timestamp, c.device_id, c.energy \
                             FROM c \
                             WHERE c.gatewayid='{kw['gatewayid']}' \
                             AND c.timestamp>='{kw['from_when']}' \
                             AND c.timestamp<='{kw['to_when']}' \
                             AND c.location LIKE 'cu_ihouse/%/iot_devices' \
                             AND c.subdevice_name='phase_1' \
                             ORDER BY c._ts DESC"
            results = []
            try:
                for item in container.query_items(
                        query=query_string,
                        enable_cross_partition_query=True):
                    print(json.dumps(item, indent=True))
                    results.append(item)
            except Exception as e:
                print("no data")
                print(e)

            return results
        except Exception as e:
            print(f"[Error] get dataset from cosmosdb function: {e}")

    def prepare_dataframe(self, data: list):
        """Prepare data for calculation.

        Args:
            data (list): list of data

        Returns:
            pandas DataFrame: DataFrame of this month only.

        """
        df = pd.DataFrame(data)

        # datetime
        df = df.rename(columns={"timestamp": "datetime"})
        df['datetime'] = pd.to_datetime(df['datetime'], yearfirst=True)
        df['datetime'] = df['datetime'].map(lambda x: x.tz_convert('Asia/Bangkok'))

        # set index
        df.set_index('datetime', inplace=True)
        df = df.sort_index()

        # loc this month
        now = pendulum.now('Asia/Bangkok')
        this_month = str(now.month)
        this_year = str(now.year)
        df = df.loc[f'{this_year}-{this_month}']
        return df

    def total_energy_consumption(self, df) -> dict:
        kwh = []
        for device_id in df['device_id'].unique():
            print(f"device_id: {device_id}")
            start = df[df['device_id'] == device_id].iloc[0][['energy']]
            end = df[df['device_id'] == device_id].iloc[-1][['energy']]
            e = round(end.values[0] - start.values[0], 2)
            print(f"Energy Consumption: {e} kWh\n\n")
            kwh.append(e)

            data = {
                'value': sum(kwh),
                'updated_at': pendulum.now('Asia/Bangkok').int_timestamp
            }
            self.dashboard_data.update({'total_energy_consumption': data})

        return self.dashboard_data

    def convert_kwh_to_co2e(self, dashboard_data):
        kwh = dashboard_data['total_energy_consumption']['value']
        co2 = 0.548
        data = {
            "annual_car_use": {"value": kwh, "unit": "cars"},
            "co2_emissions": {"value": round(co2 * kwh, 2), "unit": "kg"},
            "trees_to_absorb_co2": {"value": kwh, "unit": "trees"},
            'updated_at': pendulum.now('Asia/Bangkok').int_timestamp
        }
        dashboard_data.update({'co2_emission_equivalent': data})
        return dashboard_data

    def energy_by_floor(self, dashboard_data) -> dict:
        floor6_kwh = dashboard_data['total_energy_consumption']['value']
        data = {
            "floor_6": floor6_kwh,
            "floor_10": floor6_kwh + 1,
            "floor_20": floor6_kwh + 2,
            'updated_at': pendulum.now('Asia/Bangkok').int_timestamp
        }
        dashboard_data.update({"energy_consumption_by_floor_cu_ihouse": data})

        floor_usage_data = {
            'energy_consumption_kwh': floor6_kwh,
            'peak_demand_kw': 40, # TODO: calculate real peak demand,
            'co2_emission_kg': round(floor6_kwh*0.548, 3),
            'predicted_cost_thb': 625, # TODO: calculate real predicted cost
            'updated_at': pendulum.now('Asia/Bangkok').int_timestamp,
        }
        return dashboard_data, floor_usage_data

    def update_firebase(self, dashboard_data, floor_usage_data):
        db.child("building").child("pmcu").child("pages").child("dashboard").update(dashboard_data)
        db.child("building").child("pmcu").child("pages").child("floor_usage").child('cu_ihouse').child('floors').child('floor_6').child('energy').update(floor_usage_data)


    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        # Outline
        # Step 0: Datetime
        # Step 1: Get dataset from cosmosdb
        # Step 2: Prepare dataset
        # Step 3: Calculate total energy consumption
        # Step 4: Update Firebase

        try:
            # Step 0
            today = pendulum.today('Asia/Bangkok')
            dt = today.subtract(months=1)
            end_of_former_month = dt.end_of('month').to_date_string()
            dt = today.add(months=1)
            start_of_latter_month = dt.start_of('month').to_date_string()

            # Step 1
            result = self.get_dataset_from_cosmosdb(gatewayid='altopicuterracemonitor', from_when=end_of_former_month, to_when=start_of_latter_month)

            # Step 2: Prepare dataset
            df_elec = self.prepare_dataframe(result)

            # Step 3:
            dashboard_data = self.total_energy_consumption(df_elec)

            # Step 4:
            dashboard_data = self.convert_kwh_to_co2e(dashboard_data)
            dashboard_data, floor_usage_data = self.energy_by_floor(dashboard_data)

            # Step 5: Update Firebase
            self.update_firebase(dashboard_data, floor_usage_data)

            print("onsetup Done!")

        except Exception as e:
            print(f'[Error] onsetup: {e}')


    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        _log.debug("VERSION IS: {}".format(self.core.version()))
        if self._heartbeat_period != 0:
            _log.debug(f"Heartbeat starting for {self.core.identity}, published every {self._heartbeat_period}s")
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)
        query = Query(self.core)
        _log.info('query: %r', query.query('serverkey').get())


    @Core.schedule(periodic(28800)) # update every 6 hours
    def electricity_bill(self):
        self.now_timestamp = pendulum.now('Asia/Bangkok').int_timestamp
        if self.counter == 0:
            self.counter += 1
            return None

        try:
            # Step 0
            today = pendulum.today('Asia/Bangkok')
            dt = today.subtract(months=1)
            end_of_former_month = dt.end_of('month').to_date_string()
            dt = today.add(months=1)
            start_of_latter_month = dt.start_of('month').to_date_string()

            # Step 1
            result = self.get_dataset_from_cosmosdb(gatewayid='altopicuterracemonitor', from_when=end_of_former_month, to_when=start_of_latter_month)

            # Step 2: Prepare dataset
            df_elec = self.prepare_dataframe(result)

            # Step 3:
            dashboard_data = self.total_energy_consumption(df_elec)

            # Step 4:
            dashboard_data = self.convert_kwh_to_co2e(dashboard_data)
            dashboard_data, floor_usage_data = self.energy_by_floor(dashboard_data)

            # Step 5: Update Firebase
            self.update_firebase(dashboard_data, floor_usage_data)

            print("Periodic Done!")

        except Exception as e:
            print(f"[Error] Periodic: {e}")


    # @PubSub.subscribe('pubsub', '')
    # def on_match(self, peer, sender, bus, topic, headers, message):
    #     """Use match_all to receive all messages and print them out."""
    #     self._logfn(
    #         "Peer: {0}, Sender: {1}:, Bus: {2}, Topic: {3}, Headers: {4}, "
    #         "Message: \n{5}".format(peer, sender, bus, topic, headers, pformat(message)))


def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(ListenerAgent, version=__version__)
    except Exception as e:
        _log.exception('unhandled exception')


if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
