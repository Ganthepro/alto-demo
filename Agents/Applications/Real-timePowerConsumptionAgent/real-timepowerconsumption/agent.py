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
            query_string = f"SELECT TOP 1 c.timestamp, c.power \
                             FROM c \
                             WHERE c.gatewayid='{kw['gatewayid']}' \
                             AND c.device_id='{kw['device_id']}' \
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

    def calculate_total_kw(self) -> float:
        results = []
        device_id_list = [f'9c:a5:25:ab:3a:a4:{i}' for i in range(8, 13)]

        for device_id in device_id_list:
            result = self.get_dataset_from_cosmosdb(gatewayid='altopicuterracemonitor', device_id=device_id)
            results.append(result[0].get('power', 0))

        total_kw = sum(results)
        return round(total_kw, 3)

    def update_firebase(self, total_kw):
        data = {
            'kw': total_kw,
            'updated_at': pendulum.now('Asia/Bangkok').int_timestamp
        }
        print(data)
        db.child("building").child("pmcu").child("pages").child("dashboard").child("kw_now").update(data)


    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self.config.get('message', DEFAULT_MESSAGE))
        self._agent_id = self.config.get('agentid')

        # Outline
        # Step 1: Get dataset from cosmosdb & calculate_total_kw
        # Step 2: Update Firebase

        try:
            # Step 1
            total_kw =  self.calculate_total_kw()

            # Step 2: Update Firebase
            self.update_firebase(total_kw)

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


    @Core.schedule(periodic(30)) # update every 30 seconds
    def electricity_bill(self):
        self.now_timestamp = pendulum.now('Asia/Bangkok').int_timestamp
        if self.counter == 0:
            self.counter += 1
            return None

        try:
            # Step 1
            total_kw =  self.calculate_total_kw()

            # Step 2: Update Firebase
            self.update_firebase(total_kw)

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
