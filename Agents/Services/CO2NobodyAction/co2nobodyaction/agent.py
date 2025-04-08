"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread
from queue import Queue

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core

import pyrebase
import json

import requests
import pendulum

import pandas as pd
import numpy as np

from azure.cosmos import CosmosClient


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


# firebase config
FBDATABASEURL = "https://altohotel-b6ae5.firebaseio.com/"
FBAPIKEY = "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM"
FBAUTHDOMAIN = "altohotel-b6ae5.firebaseapp.com"
FBSTORAGEBUCKGET = "altohotel-b6ae5.appspot.com"
config = {
  "apiKey": FBAPIKEY,
  "authDomain": FBAUTHDOMAIN,
  "databaseURL": FBDATABASEURL,
  "storageBucket": FBSTORAGEBUCKGET
  }
firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
db = firebase.database()


# CosmosDB setup
def create_cosmos_client(cosmos_uri, cosmos_key, database_name, container_name):
    client = CosmosClient(cosmos_uri, credential=cosmos_key)
    database = client.get_database_client(database_name)
    container_client = database.get_container_client(container_name)
    return container_client

cosmos_uri = 'https://altocvcosmosdb.documents.azure.com:443/'
cosmos_key = 'atgM8P6DSilnZd6pbDagxzTb3oUjeuA5cODSC81iide1e5mG2MJhVNddxbTnpD2hcUA7M68U75SVRfBH1mHwUA=='
database_name = 'altocv'
container_name = 'mintel'

cosmos_client = create_cosmos_client(cosmos_uri, cosmos_key, database_name, container_name)

def get_occupant(cosmos_client, device_id, start, end, ctype='occupancy_detection'):
    query_string = f"""SELECT * FROM c
                    WHERE c.device_id='{device_id}' AND c.type='{ctype}' AND c.timestamp >= '{start}' AND c.timestamp < '{end}'
                    ORDER BY c._ts
                    """

    try:
        cosmos_data = []
        for item in cosmos_client.query_items(
            query=query_string, 
            enable_cross_partition_query=True
            ):
            cosmos_data.append(item)

        return cosmos_data

    except Exception as e:
        print(f"[Error] get dataset from cosmosdb function: {e}")
        return []

def prepare_occupant(data_occupant):
    if len(data_occupant) <= 0:
        return pd.DataFrame([])

    df_occupant = pd.DataFrame.from_dict(data_occupant)
    df_occupant['datetime'] = df_occupant['timestamp'].map(lambda x: pendulum.parse(x))
    df_occupant.set_index('datetime', inplace=True)
    df_occupant.index = df_occupant.index.tz_convert('Asia/Bangkok')
    df_occupant = df_occupant.sort_values(by=['unix_timestamp'], ascending=True)

    drop_columns = ['timestamp', '_ts', 'location', 'subdevice_idx', 'subdevice_name', 'id', '_rid', '_self', '_etag', '_attachments']
    df_occupant = df_occupant.drop(columns=drop_columns)

    df_occupant['reason'] = df_occupant['reason'].fillna('default')

    return df_occupant

def get_latest_occupant(room_num, dt_start, dt_end):
    """get latest occupant status and return as DICT
    if found no datapoint, return None
    """
    # get occupant data
    room_ids = {
        '414': '02:42:36:ad:4f:91:128:414',
        '415': '02:42:36:ad:4f:91:128:415',
        '416': '02:42:36:ad:4f:91:128:416'
    }
    room_id = room_ids[str(room_num)]
    data_occupant = get_occupant(cosmos_client, room_id, dt_start, dt_end)
    df_occupant = prepare_occupant(data_occupant)
    
    # get latest occupant status
    if len(df_occupant) <= 0:
        return None

    last_row = df_occupant.iloc[-1]
    occupant_metadata = dict()
    occupant_metadata['timestamp'] = last_row.name
    occupant_metadata['device_id'] = last_row['device_id']
    occupant_metadata['occupant'] = last_row['occupant']
    occupant_metadata['unix_timestamp'] = last_row['unix_timestamp']
    occupant_metadata['reason'] = last_row['reason']
    return occupant_metadata


def co2nobodyaction(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Co2Nobodyaction
    :rtype: Co2Nobodyaction
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Co2Nobodyaction(setting1, setting2, **kwargs)


class Co2Nobodyaction(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic", **kwargs):
        super(Co2Nobodyaction, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.send_queue = Queue()

        self.rooms = {}

        self.setting1 = setting1
        self.setting2 = setting2

        self.default_config = {"setting1": setting1,
                               "setting2": setting2}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.getsend_thread = Thread(target=self._send_data)
        self.getsend_thread.setDaemon(True)
        self.getsend_thread.start()

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

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """

        self.is_first_time = True
        self.core.periodic(120, self._period_signal)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """

        self.add_send_data_job("Die")

    def _period_signal(self):
        _log.debug(f"co2 nob _per {self.rooms}")
        if not self.is_first_time:
            self._periodic_get_firebase()
            _log.debug(f"co2 nob _fire")
            if "414" in self.rooms:
                _log.debug(f"co2 nob 414 {self.rooms['414']}")
                room_num = '414'
                dt_start = pendulum.datetime(2022, 1, 23, tz='Asia/Bangkok')
                dt_end = pendulum.datetime(2022, 1, 30, tz='Asia/Bangkok')
                occupant_metadata = get_latest_occupant(room_num, dt_start, dt_end)

                _log.debug(f"co2 nob occ {occupant_metadata}")
                if "occupant" in occupant_metadata:
                    if occupant_metadata["occupant"] == 0 and self.rooms['414'].startswith("o"):
                        subdevice_idx = 0
                        device_id = "ac_414"
                        self._control_ac(device_id, subdevice_idx, temperature=28)

        self.is_first_time = False

    def _periodic_get_firebase(self):
        try:
            fb_room_status = db.child("hotel").child("mintel").child("user_info").child("room_status").get()
            room_status = fb_room_status.val()
            is_fb_sync = True
            for k, v in room_status.items():
                if "clean_status" in v:
                    # _log.debug(f"co2 nob _periodic_get_firebase {k} {v['clean_status']}")
                    self.rooms[k] = v['clean_status']
        except Exception as e:
            _log.error(f"error in co2 nob _periodic_get_firebase function: {e}")

    def add_send_data_job(self, job):
        try:
            self.send_queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _send_data(self):
        _log.debug("_send_data")

        while True:
            job = self.send_queue.get()
            self.send_queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            # job["instance"].send_data(job["data"])

    def _control_ac(self, device_id, subdevice_idx, **kwargs):
        message = {}
        for k, v in kwargs.items():
            message[k] = v
        message["subdevice_idx"] = subdevice_idx
        topic = f"hvac/carrierac/{device_id}/command"
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={"requesterID": self.core.identity,
                                         "message_type":"command"},
                                message=message)
        _log.debug(f"co2 nob topic {topic}, msg {message}")

    def turnoff_ac(self, device_id):
        '''

        :return:
        '''
        topic = f"hvac/carrierac/{device_id}/command"
        message = {"subdevice_idx":0, "mode": "off"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"topic: {topic}, message : {message}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(co2nobodyaction, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
