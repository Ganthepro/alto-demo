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


    def get_dataset_from_cosmosdb(self):
        # Get dataset from cosmosdb
        try:
            last_day_of_last_month_date = pendulum.now('Asia/Bangkok').subtract(months=1).end_of('month').to_date_string()
            first_day_of_next_month_date = pendulum.now('Asia/Bangkok').add(months=1).start_of('month').to_date_string()
            query_string = f"SELECT * FROM c WHERE c.topic='guestcheckin' AND c.hotel='Mintel' AND c.serverTime>'{last_day_of_last_month_date}' AND c.serverTime<'{first_day_of_next_month_date}'"
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
            # print("finish get dataset from cosmosdb function")
            return results
        except Exception as e:
            print(f"[Error] get dataset from cosmosdb function: {e}")


    def load_and_prepare_data(self, data):
        try:
            df = pd.DataFrame(data)
            df['datetime'] = pd.to_datetime(df['serverTime'], yearfirst=True)
            # print(df.columns)
            columns = ['datetime', 'serverTime', 'Data', 'topic', 'hotel', 'type', 'RoomNo', 'firstname', 'lastname']
            df = df[columns]

            df['Adult'] = [df.iloc[i]['Data'][0]['Adult'] for i in range(df.shape[0])]
            df['CheckIn'] = [pd.to_datetime(df.iloc[i]['Data'][0]['CheckIn'], yearfirst=True) for i in
                             range(df.shape[0])]
            df['CheckOut'] = [pd.to_datetime(df.iloc[i]['Data'][0]['CheckOut'], yearfirst=True) for i in
                              range(df.shape[0])]
            df['Child'] = [df.iloc[i]['Data'][0]['Child'] for i in range(df.shape[0])]
            # df['GuestList'] = [df.iloc[i]['Data'][0]['GuestList'][0]  for i in range(df.shape[0])]
            df['GuestName'] = [df.iloc[i]['Data'][0]['GuestList'][0]['GuestName'] for i in range(df.shape[0])]
            df['GuestId'] = [df.iloc[i]['Data'][0]['GuestList'][0]['GuestId'] for i in range(df.shape[0])]
            df['People'] = [df.iloc[i]['Data'][0]['People'] for i in range(df.shape[0])]
            df['Night'] = [df.iloc[i]['Data'][0]['Night'] for i in range(df.shape[0])]

            del df['serverTime']
            del df['Data']
            return df
        except Exception as e:
            print(f"[Error] load_and_prepare_data dataset: {e}")


    def clean_data(self, df):
        try:
            # Filter out some guests by GuestName
            guest_name = ['testiot testiot', 'testiot tarn', 'testiot', 'aaa']
            df = df[~df.GuestName.isin(guest_name)]

            # Filter out some guests by firstname
            guest_firstname = ['Warodom', 'testiot', 'Weangchai', 'keng']
            df = df[~df.firstname.isin(guest_firstname)]

            # drop duplicate columns
            df = df.drop_duplicates(subset=['CheckIn', 'GuestId'], keep='last')
            df = df.drop_duplicates(subset=['CheckIn', 'GuestId'], keep='last')
            df = df.drop_duplicates(subset=['CheckIn', 'RoomNo'], keep='last')
            df = df.drop_duplicates(subset=['CheckOut', 'RoomNo'], keep='last')

            # drop particular index
            index_to_drop = df[(df.GuestName == 'Onkanya Merklein') & (df.CheckIn == '2021-01-29 14:00:00')].index
            df.drop(index_to_drop, inplace=True)

            # set index colum
            df.set_index('datetime', inplace=True)

            return df
        except Exception as e:
            print(f"[Error] clean data function: {e}")


    def preprocess_data(self, df):
        try:
            df['CheckInDayOfYear'] = df['CheckIn'].dt.dayofyear
            df['CheckOutDate'] = df['CheckOut'].dt.date
            return df
        except Exception as e:
            print(f"[Error] preprocess data function: {e}")


    def calculate_night(self, df):
        # already checkout nights
        try:
            df_out = df[df['CheckOutDate'] <= pendulum.today('Asia/Bangkok').date()]
            return df_out.Night.sum()
        except Exception as e:
            print(f"[Error] calculate night function: {e}")

    def calculate_nights_guest_not_out_yet(self, df):
        # calculate nights for guests not check out yet
        try:
            today = pendulum.today('Asia/Bangkok')
            df_not_out_yet = pd.DataFrame()
            df_not_out_yet = df[df['CheckOutDate'] > today.date()]
            df_not_out_yet['NightToDate'] = df_not_out_yet['CheckInDayOfYear'].map(lambda x: today.day_of_year - x)
            return df_not_out_yet.NightToDate.sum()
        except Exception as e:
            print(f"[Error] calculate nights guest not out yet function: {e}")

    def calculate_baht_per_room_night(self, already_checkout_nights, not_out_yet_night_to_date):
        try:
            this_month_baht = db.child('hotel').child('mintel').child('energy').child('electricity_bill').child('this_month_baht').get().val()
            room_night = already_checkout_nights + not_out_yet_night_to_date
            baht_per_room_night = round(this_month_baht / (room_night), 2)
            return baht_per_room_night, this_month_baht, room_night
        except Exception as e:
            print(f"[Error] calculate baht per room night: {e}")

    def update_firebase(self, baht_per_room_night, this_month_baht, room_night):
        try:
            data = {
                'data': {
                    'this_month_baht': this_month_baht,
                    'room-night': int(room_night),
                },
                'items': {
                    'before': round(baht_per_room_night/0.714, 2),
                    'after': baht_per_room_night,
                },
                'updated_at': pendulum.now('Asia/Bangkok').to_datetime_string()
            }
            db.child('hotel').child('mintel').child('dashboard').child('electricity_bills_per_room_night').update(data)
        except Exception as e:
            print(f"[Error] update firebase: {e}")


    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        # Outline
        # Step 1: Get dataset from cosmosdb
        # Step 2: Load & Prepare data
        # Step 3: clean data
        # Step 4: preprocess data
        # Step 5: calculate already checkout nights
        # Step 6: calculate nights for guests not check out yet
        # Step 7: calculate baht per room night
        # Step 8: Update Firebase

        try:
            # Step 1
            result = self.get_dataset_from_cosmosdb()

            # Step 2
            df = self.load_and_prepare_data(data=result)

            # Step 3
            df = self.clean_data(df=df)

            # Step 4
            df = self.preprocess_data(df=df)

            # Step 5
            already_checkout_nights = self.calculate_night(df=df)

            # Step 6:
            not_out_yet_night_to_date = self.calculate_nights_guest_not_out_yet(df=df)

            # Step 7:
            baht_per_room_night, this_month_baht, room_night = self.calculate_baht_per_room_night(already_checkout_nights, not_out_yet_night_to_date)

            # Step 8:
            self.update_firebase(baht_per_room_night, this_month_baht, room_night)


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


    @Core.schedule(periodic(36000))
    def energy_dashboard(self):
        if self.counter == 0:
            self.counter += 1
            return None

        try:
            # Step 1
            result = self.get_dataset_from_cosmosdb()

            # Step 2
            df = self.load_and_prepare_data(data=result)

            # Step 3
            df = self.clean_data(df=df)

            # Step 4
            df = self.preprocess_data(df=df)

            # Step 5
            already_checkout_nights = self.calculate_night(df=df)

            # Step 6:
            not_out_yet_night_to_date = self.calculate_nights_guest_not_out_yet(df=df)

            # Step 7:
            baht_per_room_night = self.calculate_baht_per_room_night(already_checkout_nights, not_out_yet_night_to_date)

            # Step 8:
            self.update_firebase(baht_per_room_night)


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
