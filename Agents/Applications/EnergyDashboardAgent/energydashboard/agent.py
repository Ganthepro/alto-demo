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
            self._logfn = _log.warn
        elif log_level == 'DEBUG':
            self._logfn = _log.debug
        else:
            self._logfn = _log.info

        self.thai_holidays = [
                '2021-01-01',
                '2021-02-26',

                '2021-04-06', '2021-04-13', '2021-04-14', '2021-04-15',
                '2021-05-01', '2021-05-04', '2021-05-26',
                '2021-06-03',
                '2021-07-24', '2021-07-25', '2021-07-28',
                '2021-08-12',

                '2021-10-13', '2021-10-23',

                '2021-12-05', '2021-12-10', '2021-12-31'
        ]

        # Electricity bill related variable
        self.onpeak_energy_charge = 4.1839
        self.offpeak_energy_charge = 2.6037

        self.d = {}


    def get_dataset_from_cosmosdb(self):
        # Get dataset from cosmosdb
        try:
            last_day_of_last_month_date = pendulum.now('Asia/Bangkok').subtract(months=1).end_of('month').to_date_string()
            first_day_of_next_month_date = pendulum.now('Asia/Bangkok').add(months=1).start_of('month').to_date_string()
            query_string = f"SELECT c.timestamp, c.device_id, c.subdevice_idx, c.location, c.subdevice_name, \
            c.energy, c.gatewayid FROM c WHERE c.gatewayid='altonucmintelmonitor' \
            AND c.subdevice_name='total' AND c.timestamp >= '{last_day_of_last_month_date}' \
            AND c.timestamp < '{first_day_of_next_month_date}' \
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
            print("finish get dataset from cosmosdb function")
            return df
        except Exception as e:
            print(f"[Error] get dataset from cosmosdb function: {e}")


    def prepare_dataset(self, df):
        try:
            columns = ['timestamp', 'energy', 'location']
            df = df[columns]
            df['timestamp'] = df['timestamp'].apply(lambda x: pendulum.parse(x).add(hours=7).to_datetime_string())
            df['timestamp'] = pd.to_datetime(df['timestamp'], yearfirst=True)
            df.set_index('timestamp', inplace=True)
            start = pendulum.now('Asia/Bangkok').start_of('month').to_datetime_string()
            end = pendulum.now('Asia/Bangkok').end_of('month').to_datetime_string()
            df = df.loc[start:end]
            df.dropna(inplace=True)
            # print("finish prepare dataset function")
            print(df.head())
            print(df.tail())
            return df
        except Exception as e:
            print(f"[Error] prepare dataset: {e}")


    def check_if_weekend(self, df):
        # check if each particular row is weekend or not.
        try:
            def create_column(column_name, day):
                if day == 'saturday':
                    df[column_name] = df.index.map(lambda x: pendulum.instance(x).day_of_week == pendulum.SATURDAY).values
                elif day == 'sunday':
                    df[column_name] = df.index.map(lambda x: pendulum.instance(x).day_of_week == pendulum.SUNDAY).values

            create_column(column_name='is_saturday', day='saturday')
            create_column(column_name='is_sunday', day='sunday')
            # print("finish check if weekend function")
        except Exception as e:
            print(f"[Error] check if weekend function: {e}")


    def check_if_holiday(self, df):
        # check if each particular row is holiday or not.
        try:
            df['date'] = df.index.map(lambda x: pendulum.instance(x).to_date_string())
            df['is_holiday'] = df.isin({'date': self.thai_holidays})['date'].values
            del df['date']
            # print("finish check if holiday function")
        except Exception as e:
            print(f"[Error] check if holiday function: {e}")


    def calculation(self, df):
        # update this month baht
        try:
            df_rtr = df[df['location'] == 'restaurant/iot_devices']
            restaurant_kwh = round(df_rtr['energy'].iloc[-1] - df_rtr['energy'].iloc[0], 2)

            df_ldry = df[df['location'] == 'laundry/iot_devices']
            laundry_kwh = round(df_ldry['energy'].iloc[-1] - df_ldry['energy'].iloc[0], 2)

            # main = lobby + room
            df_main = df[df['location'] == 'main_energy/iot_devices']
            main_kwh = df_main['energy'].iloc[-1] - df_main['energy'].iloc[0]
            room_kwh = round(main_kwh, 2)

            data = {
                "room": {
                    "kwh": room_kwh,
                },
                "restaurant": {
                    "kwh": restaurant_kwh,
                },
                "laundry": {
                    "kwh": laundry_kwh,
                },
            }
            self.d.update(data)
            # print("finish calculation function")
            # print(self.d)
            return df_rtr, df_ldry, df_main
        except Exception as e:
            print(f"[Error] calculation function: {e}")


    def calculate_onpeak_kWh_baht(self, df):
        try:
            on_peak_day_condition = (df['is_saturday'] == False) & (df['is_sunday'] == False) & (df['is_holiday'] == False)
            df_btw_10_22 = df[on_peak_day_condition].between_time('9:00', '22:00')
            unique_date = pd.Series(df_btw_10_22.index.date).unique()
            total_onpeak_kwh = 0
            for i in unique_date:
                each_day_kwh_sum = df_btw_10_22.loc[str(i)]['energy'][-1] - df_btw_10_22.loc[str(i)]['energy'][0]
                total_onpeak_kwh = total_onpeak_kwh + each_day_kwh_sum
            total_onpeak_kwh = round(total_onpeak_kwh, 2)
            total_onpeak_baht = round(total_onpeak_kwh * self.onpeak_energy_charge, 2)

            # print("finish calculate onpeak kWh baht function")
            return total_onpeak_kwh, total_onpeak_baht
        except Exception as e:
            print(f"[Error] calculate onpeak kWh baht function: {e}")


    def calculate_offpeak_kWh_baht(self, df, total_onpeak_kwh):
        try:
            total_kwh = round(df.iloc[-1]['energy'] - df.iloc[0]['energy'], 2)
            # calculate off peak kwh
            total_offpeak_kwh = round(total_kwh - total_onpeak_kwh, 2)
            total_offpeak_baht = round(total_offpeak_kwh * self.offpeak_energy_charge, 2)

            # print("finish calculate offpeak kWh baht function")
            return total_offpeak_baht
        except Exception as e:
            print(f"[Error] calculate offpeak kWh baht: {e}")


    def firebase(self, ldry_onpeak_baht, ldry_offpeak_baht, rtr_onpeak_baht, rtr_offpeak_baht, main_onpeak_baht, main_offpeak_baht):
        # push data to firebase
        laundry_baht = round(ldry_onpeak_baht + ldry_offpeak_baht, 2)
        restaurant_baht = round(rtr_onpeak_baht + rtr_offpeak_baht, 2)
        room_baht = round(main_onpeak_baht + main_offpeak_baht, 2)

        # For DASHBOARD & ENERGY/REALTIME
        data = {}
        data.update(
            {
                'laundry': {
                    'baht': laundry_baht,
                    'kwh': self.d['laundry']['kwh']
                },
                'restaurant': {
                    'baht': restaurant_baht,
                    'kwh': self.d['restaurant']['kwh']
                },
                'room': {
                    'baht': room_baht,
                    'kwh': self.d['room']['kwh']
                },
            }
        )

        d = {
            "items": data,
            "updated_at": pendulum.now('Asia/Bangkok').to_datetime_string()
        }
        print(d)
        db.child("hotel").child("mintel").child("dashboard").child("energy_summary").update(d)

        # For ENERGY/COST BREAKDOWN
        d2 = {
            'building': {
                'common_space': laundry_baht + restaurant_baht,
                'guest_room': room_baht,
            },
            'by_type': {
                'hotel': room_baht,
                'laundry': laundry_baht,
                'restaurant': restaurant_baht,
                'store': 0,
            }
        }
        db.child("hotel").child("mintel").child("energy").child("cost_breakdown").update(d2)


    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        # Outline
        # Step 1: Get dataset from cosmosdb
        # Step 2: Prepare dataset
        # Step 3: kWh calculation
        # Step 4: On peak baht calculation
        # Step 5: Off peak baht calculation
        # Step 6: Update Firebase

        try:
            # Step 1
            df = self.get_dataset_from_cosmosdb()

            # Step 2
            df = self.prepare_dataset(df)
            self.check_if_weekend(df)
            self.check_if_holiday(df)

            # Step 3
            df_rtr, df_ldry, df_main = self.calculation(df)

            # Step 4
            rtr_onpeak_kwh, rtr_onpeak_baht = self.calculate_onpeak_kWh_baht(df_rtr)
            ldry_onpeak_kwh, ldry_onpeak_baht = self.calculate_onpeak_kWh_baht(df_ldry)
            main_onpeak_kwh, main_onpeak_baht = self.calculate_onpeak_kWh_baht(df_main)

            # Step 5
            rtr_offpeak_baht = self.calculate_offpeak_kWh_baht(df_rtr, rtr_onpeak_kwh)
            ldry_offpeak_baht = self.calculate_offpeak_kWh_baht(df_ldry, ldry_onpeak_kwh)
            main_offpeak_baht = self.calculate_offpeak_kWh_baht(df_main, main_onpeak_kwh)

            # Step 6: Update Firebase
            self.firebase(ldry_onpeak_baht, ldry_offpeak_baht, rtr_onpeak_baht, rtr_offpeak_baht, main_onpeak_baht, main_offpeak_baht)

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


    @Core.schedule(periodic(300))
    def energy_dashboard(self):
        if self.counter == 0:
            self.counter += 1
            return None

        try:
            # Step 1
            df = self.get_dataset_from_cosmosdb()

            # Step 2
            df = self.prepare_dataset(df)
            self.check_if_weekend(df)
            self.check_if_holiday(df)

            # Step 3
            df_rtr, df_ldry, df_main = self.calculation(df)

            # Step 4
            rtr_onpeak_kwh, rtr_onpeak_baht = self.calculate_onpeak_kWh_baht(df_rtr)
            ldry_onpeak_kwh, ldry_onpeak_baht = self.calculate_onpeak_kWh_baht(df_ldry)
            main_onpeak_kwh, main_onpeak_baht = self.calculate_onpeak_kWh_baht(df_main)

            # Step 5
            rtr_offpeak_baht = self.calculate_offpeak_kWh_baht(df_rtr, rtr_onpeak_kwh)
            ldry_offpeak_baht = self.calculate_offpeak_kWh_baht(df_ldry, ldry_onpeak_kwh)
            main_offpeak_baht = self.calculate_offpeak_kWh_baht(df_main, main_onpeak_kwh)

            # Step 6: Update Firebase
            self.firebase(ldry_onpeak_baht, ldry_offpeak_baht, rtr_onpeak_baht, rtr_offpeak_baht, main_onpeak_baht, main_offpeak_baht)

            print("periodic Done!")

        except Exception as e:
            print(f'[Error] periodic: {e}')


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
