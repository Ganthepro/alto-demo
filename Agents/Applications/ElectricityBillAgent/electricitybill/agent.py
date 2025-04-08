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

        # Date & Time
        self.now = pendulum.now('Asia/Bangkok')
        self.now_timestamp = self.now.int_timestamp
        self.today_date = pendulum.today(tz='Asia/Bangkok').to_date_string()
        self.yesterday_date = pendulum.yesterday(tz='Asia/Bangkok').to_date_string()

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

        # Power & Energy
        self.on_peak_demand = 0
        self.total_onpeak_kwh = 0
        self.total_offpeak_kwh = 0
        self.total_kwh = 0
        self.d = {}

        # Electricity bill related variable
        self.peak_demand_charge = 132.93
        self.onpeak_energy_charge = 4.1839
        self.offpeak_energy_charge = 2.6037
        self.service_charge = 312.24
        self.ft_charge = -0.1532
        self.co2_emission_per_kwh = 0.489 # ref: http://www.eppo.go.th/index.php/en/en-energystatistics/co2-statistic

        # Baht
        self.total_onpeak_baht = 0
        self.total_offpeak_baht = 0

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
            query_string = f"SELECT c.timestamp, c.device_id, c.subdevice_idx, c.location, c.subdevice_name, \
                                    c.power_reactive, c.voltage, c.power, \
                                    c.energy, c.current, c.power_factor, c.gatewayid \
                                    FROM c WHERE c.gatewayid='altonucmintelmonitor' \
                                    AND c.location='main_energy/iot_devices' AND c.subdevice_idx=3 AND c.timestamp >= '{last_day_of_last_month_date}' \
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
            df.dropna(inplace=True)
            columns = ['timestamp', 'power', 'energy']
            df = df[columns]
            df['timestamp'] = df['timestamp'].apply(lambda x: pendulum.parse(x).add(hours=7).to_datetime_string())
            df['timestamp'] = pd.to_datetime(df['timestamp'], yearfirst=True)
            df.set_index('timestamp', inplace=True)
            start_of_this_month = pendulum.now('Asia/Bangkok').start_of('month').to_datetime_string()
            start_of_next_month = pendulum.now('Asia/Bangkok').add(months=1).start_of('month').to_datetime_string()
            df = df.loc[start_of_this_month:f"{start_of_next_month} 00:00"]
            print("finish prepare dataset function")
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
            print("finish check if weekend function")
        except Exception as e:
            print(f"[Error] check if weekend function: {e}")


    def check_if_holiday(self, df):
        # check if each particular row is holiday or not.
        try:
            df['date'] = df.index.map(lambda x: pendulum.instance(x).to_date_string())
            df['is_holiday'] = df.isin({'date': self.thai_holidays})['date'].values
            del df['date']
            print("finish check if holiday function")
        except Exception as e:
            print(f"[Error] check if holiday function: {e}")


    def calculate_onpeak_demand(self, df):
        try:
            # on peak day
            on_peak_day_condition = (df['is_saturday'] == False) & (df['is_sunday'] == False) & (df['is_holiday'] == False)
            self.on_peak_demand = round(max(df[on_peak_day_condition]['power'].between_time('9:00', '22:00')), 2)
            # firebase
            data = {
                "onpeak_demand_kw": self.on_peak_demand,
                "onpeak_demand_kw_updated_at": pendulum.now('Asia/Bangkok').int_timestamp
            }
            self.d.update(data)
            print("finish calculate onpeak demand function")
        except Exception as e:
            print(f"[Error] calculate on peak demand function: {e}")


    def calculate_onpeak_kWh_baht(self, df):
        try:
            on_peak_day_condition = (df['is_saturday'] == False) & (df['is_sunday'] == False) & (df['is_holiday'] == False)
            df_btw_10_22 = df[on_peak_day_condition].between_time('9:00', '22:00')
            unique_date = pd.Series(df_btw_10_22.index.date).unique()
            total_onpeak_kwh = 0
            for i in unique_date:
                each_day_kwh_sum = df_btw_10_22.loc[str(i)]['energy'][-1] - df_btw_10_22.loc[str(i)]['energy'][0]
                total_onpeak_kwh = total_onpeak_kwh + each_day_kwh_sum
            self.total_onpeak_kwh = round(total_onpeak_kwh, 2)
            self.total_onpeak_baht = round(self.total_onpeak_kwh * self.onpeak_energy_charge, 2)

            # firebase
            data = {
                "onpeak_kwh": self.total_onpeak_kwh,
                "onpeak_kwh_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
                "onpeak_baht": self.total_onpeak_baht,
                "onpeak_baht_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
            }
            self.d.update(data)
            print("finish calculate onpeak kWh baht function")
        except Exception as e:
            print(f"[Error] calculate onpeak kWh baht function: {e}")


    def calculate_offpeak_demand(self, df):
        try:
            # off peak day
            off_peak_day_condition = (df['is_saturday'] == True) | (df['is_sunday'] == True) | (df['is_holiday'] == True)
            df_offpeak_day = df[off_peak_day_condition]
            try:
                off_peak_demand = round(max(df_offpeak_day['power'].between_time('9:00', '22:00')), 2)
            except Exception as e:
                print(f"[Error] off peak demand: {e}")
            # off peak period on on peak day
            on_peak_day_condition = (df['is_saturday'] == False) & (df['is_sunday'] == False) & (df['is_holiday'] == False)
            df_offpeak_peroid_on_onpeak_day = df[on_peak_day_condition].between_time("22:00", "9:00", include_start=False, include_end=False)
            try:
                off_peak_demand2 = round(max(df_offpeak_peroid_on_onpeak_day['power']), 2)
            except Exception as e:
                print(f"[Error] off peak demand2: {e}")
            if off_peak_demand < off_peak_demand2:
                off_peak_demand = off_peak_demand2

            # firebase
            data = {
                "offpeak_demand_kw": off_peak_demand,
                "offpeak_demand_kw_updated_at": pendulum.now('Asia/Bangkok').int_timestamp
            }
            self.d.update(data)
            print("finish calculate offpeak demand function")
        except Exception as e:
            print(f"[Error] calculate offpeak demand: {e}")


    def calculate_offpeak_kWh_baht(self, df):
        try:
            # total kwh
            self.total_kwh = round(df.iloc[-1]['energy'] - df.iloc[0]['energy'], 2)
            # calculate off peak kwh
            self.total_offpeak_kwh = round(self.total_kwh - self.total_onpeak_kwh, 2)
            self.total_offpeak_baht = round(self.total_offpeak_kwh * self.offpeak_energy_charge, 2)

            # firebase
            data = {
                "offpeak_kwh": self.total_offpeak_kwh,
                "offpeak_kwh_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
                "offpeak_baht": self.total_offpeak_baht,
                "offpeak_baht_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
            }
            self.d.update(data)
            print("finish calculate offpeak kWh baht function")
        except Exception as e:
            print(f"[Error] calculate offpeak kWh baht: {e}")


    def both_onpeak_offpeak(self, df):
        # update this month total kwh
        try:
            data = {
                "this_month_kwh": self.total_kwh,
                "this_month_kwh_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
            }
            self.d.update(data)
            print("finish both onpeak off peak function")
        except Exception as e:
            print(f"[Error] both onpeak off peak: {e}")


    def electricity_bill_calculation(self, df):
        # update this month baht
        try:
            peak_demand_baht = round(self.on_peak_demand * self.peak_demand_charge, 2)
            onpeak_baht = round(self.total_onpeak_kwh * self.onpeak_energy_charge, 2)
            offpeak_baht = round(self.total_offpeak_kwh * self.offpeak_energy_charge, 2)
            total_baht = peak_demand_baht + onpeak_baht + offpeak_baht + self.service_charge
            # VAT 7%
            ft_baht = self.total_kwh * self.ft_charge
            vat7 = round((total_baht + ft_baht) * 0.07, 2)
            # final baht
            final_baht = round(total_baht + ft_baht + vat7, 2)

            # firebase
            data = {
                "this_month_baht": final_baht,
                "this_month_baht_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
            }
            self.d.update(data)
            print("finish electricity bill calculation function")
        except Exception as e:
            print(f"[Error] electricity bill calculation: {e}")


    def co2_kwh_per_m2(self):
        try:
            kwh = self.d.get('this_month_kwh')
            co2 = round(kwh * self.co2_emission_per_kwh, 2)
            m2 = 4016.08375 # ref for mintel m2: https:shorturl.at/dsBPR
            kwh_per_m2 = round(kwh / m2, 2)
            data = {
                "co2": co2,
                "co2_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
                "kwh_per_m2": kwh_per_m2,
                "kwh_per_m2_updated_at": pendulum.now('Asia/Bangkok').int_timestamp,
            }
            self.d.update(data)
            print("finish co2 kwh per m2 function")
        except Exception as e:
            print(f"[Error] co2 kwh per m2: {e}")


    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        try:
            # Step 1: Get dataset from cosmosdb
            df = self.get_dataset_from_cosmosdb()

            # Step 2: Prepare dataset
            df = self.prepare_dataset(df)

            # Step 3: On peak & Off peak identification
            # Step 3.1: check if weekend
            self.check_if_weekend(df=df)
            # Step 3.2: check if holidays
            self.check_if_holiday(df=df)

            # Step 4: On Peak Calculation
            # Step 4.1: On peak demand
            self.calculate_onpeak_demand(df=df)
            # Step 4.2: On peak kWh & baht
            self.calculate_onpeak_kWh_baht(df=df)

            # Step 5: Off Peak Calculation
            # Step 5.1: Off peak demand
            self.calculate_offpeak_demand(df=df)
            # Step 5.2: Off peak kWh & baht
            self.calculate_offpeak_kWh_baht(df=df)

            # Step 6: Both On Peak & Off Peak
            self.both_onpeak_offpeak(df=df)

            # Step 7: Electricity Bill
            self.electricity_bill_calculation(df=df)

            # Step 8: Co2 & kwh per m2
            self.co2_kwh_per_m2()

            # Step 9: Update Firebase
            db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(self.d)

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


    def peak_demand(self, df):
        yesterday = pendulum.yesterday(tz='Asia/Bangkok')
        is_saturday = (yesterday.day_of_week == pendulum.SATURDAY)
        is_sunday = (yesterday.day_of_week == pendulum.SUNDAY)

        def check_if_holiday(date_string):
            if date_string in self.thai_holidays:
                return True
            else:
                return False

        is_holiday = check_if_holiday(date_string=yesterday.to_date_string())

        if (is_saturday) | (is_sunday) | (is_holiday):
            # off peak day
            off_peak_day_condition = (df['is_saturday'] == True) | (df['is_sunday'] == True) | (df['is_holiday'] == True)
            off_peak_demand = round(max(df[off_peak_day_condition]['power'].between_time('9:00', '22:00')), 2)
            # firebase
            current_off_peak_demand = db.child("hotel").child("mintel").child("energy").child("electricity_bill").child("offpeak_demand_kw").get().val()
            if off_peak_demand > current_off_peak_demand:
                data = {"offpeak_demand_kw": off_peak_demand}
                db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(data)
        else:
            # on peak day
            on_peak_day_condition = (df['is_saturday'] == False) & (df['is_sunday'] == False) & (df['is_holiday'] == False)
            on_peak_demand = round(max(df[on_peak_day_condition]['power'].between_time('9:00', '22:00')), 2)
            # firebase
            current_on_peak_demand = db.child("hotel").child("mintel").child("energy").child("electricity_bill").child("onpeak_demand_kw").get().val()
            if on_peak_demand > current_on_peak_demand:
                data = {"onpeak_demand_kw": on_peak_demand}
                db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(data)
                return on_peak_demand
            return current_on_peak_demand


    def calculate_new_onpeak_kwh(self, df):
        # yesterday onpeak kwh
        on_peak_day_condition = (df['is_saturday'] == False) & (df['is_sunday'] == False) & (df['is_holiday'] == False)
        df_onpeak = df[on_peak_day_condition]
        yesterday_onpeak_kwh = df_onpeak.at_time('22:00')['energy'].values - df_onpeak.at_time('9:00')['energy'].values
        yesterday_onpeak_kwh = round((yesterday_onpeak_kwh).sum(), 2)

        # current onpeak kwh from firebase
        current_onpeak_kwh = db.child("hotel").child("mintel").child("energy").child("electricity_bill").child("onpeak_kwh").get().val()
        new_onpeak_kwh = round(yesterday_onpeak_kwh + current_onpeak_kwh, 2)

        # baht
        yesterday_onpeak_baht = round(yesterday_onpeak_kwh * self.onpeak_energy_charge, 2)
        current_onpeak_baht = round(current_onpeak_kwh * self.onpeak_energy_charge, 2)
        new_onpeak_baht = round(yesterday_onpeak_baht + current_onpeak_baht, 2)

        # firebase
        data = {"onpeak_kwh": new_onpeak_kwh,
                "onpeak_kwh_updated_at": self.now_timestamp,
                "onpeak_baht": new_onpeak_baht,
                "onpeak_baht_updated_at": self.now_timestamp,
        }
        db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(data)

        return yesterday_onpeak_kwh


    def calculate_new_offpeak_kWh(self, df, yesterday_onpeak_kwh):
        midnight_last_day_energy = df.at_time('0:00').iloc[-1]['energy']
        midnight_first_day_energy = df.at_time('0:00').iloc[0]['energy']
        # yesterday total kWh
        yesterday_total_kWh = round(midnight_last_day_energy - midnight_first_day_energy, 2)
        # yesterday offpeak kWh
        yesterday_offpeak_kWh = round(yesterday_total_kWh - yesterday_onpeak_kwh, 2)
        # Get the current off peak kwh from firebase
        current_offpeak_kwh = db.child("hotel").child("mintel").child("energy").child("electricity_bill").child("offpeak_kwh").get().val()
        # new offpeak kwh
        new_offpeak_kwh = round(current_offpeak_kwh + yesterday_offpeak_kWh, 2)

        # baht
        off_peak_energy_charge = 2.6037
        yesterday_offpeak_baht = round(yesterday_onpeak_kwh * off_peak_energy_charge, 2)
        current_offpeak_baht = round(current_offpeak_kwh * off_peak_energy_charge, 2)
        new_offpeak_baht = round(yesterday_offpeak_baht + current_offpeak_baht, 2)

        # firebase
        data = {"offpeak_kwh": new_offpeak_kwh,
                "offpeak_kwh_updated_at": self.now_timestamp,
                "offpeak_baht": new_offpeak_baht,
                "offpeak_baht_updated_at": self.now_timestamp,
        }
        db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(data)


    def this_month_kwh(self):
        # Set current off peak kwh, and current on peak kwh.
        current_onpeak_kwh = db.child("hotel").child("mintel").child("energy").child("electricity_bill").child("onpeak_kwh").get().val()
        current_offpeak_kwh = db.child("hotel").child("mintel").child("energy").child("electricity_bill").child("offpeak_kwh").get().val()
        # Calculate new this month kwh. Then push to firebase.
        new_this_month_kwh = round(current_onpeak_kwh + current_offpeak_kwh, 2)

        # firebase
        data = {
            "this_month_kwh": new_this_month_kwh,
            "this_month_kwh_updated_at": self.now_timestamp,
        }
        db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(data)

        return current_onpeak_kwh, current_offpeak_kwh


    def new_electricity_bill_calculation(self, current_on_peak_demand, current_onpeak_kwh, current_offpeak_kwh):
        # this month baht
        peak_demand_baht = round(current_on_peak_demand * self.peak_demand_charge, 2)
        onpeak_baht = round(current_onpeak_kwh * self.onpeak_energy_charge, 2)
        offpeak_baht = round(current_offpeak_kwh * self.offpeak_energy_charge, 2)
        total_baht = peak_demand_baht + onpeak_baht + offpeak_baht + self.service_charge
        # VAT 7%
        ft_baht = self.total_kwh * self.ft_charge
        vat7 = round((total_baht + ft_baht) * 0.07, 2)
        # final baht
        final_baht = round(total_baht + ft_baht + vat7, 2)

        # firebase
        data = {
            "this_month_baht": final_baht,
            "this_month_baht_updated_at": self.now_timestamp,
        }
        db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(data)


    @Core.schedule(periodic(21600)) # run every 6 hours
    def electricity_bill(self):
        self.now_timestamp = pendulum.now('Asia/Bangkok').int_timestamp
        if self.counter == 0:
            self.counter += 1
            return None

        # Step 5: Off Peak Calculation
        # Step 6: Both On Peak & Off Peak
        # Step 7: Electricity Bill
        # Step 8: Co2 & kwh per m2
        # Step 9: Update Firebase

        try:
            # Step 1: Get dataset from cosmosdb
            df = self.get_dataset_from_cosmosdb()

            # Step 2: Prepare dataset
            df = self.prepare_dataset(df)

            """
            Step 3: On peak & Off peak identification
                3.1: check if weekend
                3.2: check if holidays
            """
            self.check_if_weekend(df=df)
            self.check_if_holiday(df=df)

            """
            Step 4: On Peak Calculation
                4.1: On peak demand
                4.2: On peak kWh & baht
            """
            self.calculate_onpeak_demand(df=df)
            self.calculate_onpeak_kWh_baht(df=df)

            # Step 5: Off Peak Calculation
            # Step 5.1: Off peak demand
            self.calculate_offpeak_demand(df=df)
            # Step 5.2: Off peak kWh & baht
            self.calculate_offpeak_kWh_baht(df=df)

            # Step 6: Both On Peak & Off Peak
            self.both_onpeak_offpeak(df=df)

            # Step 7: Electricity Bill
            self.electricity_bill_calculation(df=df)

            # Step 8: Co2 & kwh per m2
            self.co2_kwh_per_m2()

            # Step 9: Update Firebase
            db.child("hotel").child("mintel").child("energy").child("electricity_bill").update(self.d)

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
