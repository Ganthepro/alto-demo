#!/usr/bin/env python3

import argparse
import json
import logging
import os
import threading
from queue import Queue
from copy import deepcopy
import json

import paho.mqtt.client as mqtt

import pymongo
from bson.json_util import dumps


_log = logging.getLogger(__name__)
_log.setLevel("DEBUG")
_log.addHandler(logging.StreamHandler())
_log.addHandler(logging.FileHandler(os.path.expanduser('/home/alto/mqtt-proxy.log')))


ap = argparse.ArgumentParser()
ap.add_argument("-c", "--config", required=True,
    help="path to config file")
args = vars(ap.parse_args())
config = None
_log.debug(f"config path {args['config']}")
with open(args["config"], "r") as configf:
    config = json.load(configf)
    _log.debug(f"config {config}")
if config is None:
    raise Exception("Please provide config file.")
mqtt_broker_ip = config["mqtt_broker_ip"]
mqtt_broker_port = config["mqtt_broker_port"]
mqtt_timelive = config["mqtt_timelive"]


class MongoDBChangeStreamThread(threading.Thread):
    def __init__(self, mqtt_pub_queue):
        super().__init__()
        self.mqtt_pub_queue = mqtt_pub_queue

        self.is_run = True

        self.mongo_client = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

        self.mongo_db = self.mongo_client["altofiredb"]
        self.mongo_col_data = self.mongo_db["lastest_data"]

    def run(self):
        # while self.is_run:
        try:
            with self.mongo_col_data.watch() as change_stream:
                for change in change_stream:
                    full_document = change["fullDocument"]
                    _log.debug(dumps(full_document))
                    self.put_to_pub(full_document)
        except Exception as e :
            _log.warning(f"MongoDBChangeStreamThread {e}")
        _log.debug('end 2')

    def close_mongodb_client(self):
        self.mongo_db.close()
    
    def put_to_pub(self, full_document):
        try:
            self.mqtt_pub_queue.put_nowait(
                {
                    "topic": full_document["_id"],
                    "data": deepcopy(full_document["data"])
                }
            )
        except Exception as e:
            _log.warning(f"mqtt_pub_queue {e}")


class MQTTPubThread(threading.Thread):
    def __init__(self, mqtt_pub_queue):
        super().__init__()
        self.mqtt_pub_queue = mqtt_pub_queue

        self.is_run = True
        self.sent_count = 0

        self.client = mqtt.Client(client_id = "mqtt-pub-proxy", clean_session = True)
        self.client.connect(mqtt_broker_ip, mqtt_broker_port, mqtt_timelive)
        self.client.on_publish = self.on_publish
        # self.client.on_connect = self.on_connect
        # self.client.on_disconnect = self.on_disconnect

    def run(self):
        while self.is_run:
            data = self.mqtt_pub_queue.get()
            self.mqtt_pub_queue.task_done()
            _log.debug(f"data: {data}")
            if data != 'Die' or True:
                try:
                    self.publish(data)
                except Exception as e :
                    _log.error(e)
            else:
                break
        _log.debug('end 2')
    
    def publish(self, data):
        if self.sent_count < 10:
            ret = self.client.publish(data["topic"], dumps(data["data"]))
        else:
            self.re_connect()
            ret = self.client.publish(data["topic"], dumps(data["data"]))
        self.sent_count += 1
        _log.debug(f"publish sent_count: {self.sent_count}")
    
    def re_connect(self):
        self.client.reinitialise()
        self.client.connect(mqtt_broker_ip, mqtt_broker_port, mqtt_timelive)
        self.client.on_publish = self.on_publish
        self.sent_count = 0
        
    def on_publish(self, client, userdata, result):
        self.sent_count -= 1
        _log.debug(f"mqtt-pub-proxy: Data published. {self.sent_count}")

    def on_connect(self, client, userdata, flags, rc):
        self.is_mqtt_connected = True
    
    def on_disconnect(self, client, userdata, rc):
        self.is_mqtt_connected = False


class MQTTSub:

    def __init__(self, mqtt_pub_queue):
        self.mqtt_pub_queue = mqtt_pub_queue

        self.client = mqtt.Client(client_id = "mqtt-sub-proxy", clean_session = True)
        self.client.connect(mqtt_broker_ip, mqtt_broker_port, mqtt_timelive)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.mongo_client = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

        self.mongo_db = self.mongo_client["altofiredb"]
        self.mongo_col_data = self.mongo_db["lastest_data"]
    
    def loop(self):
        self.client.loop_forever()

    def on_connect(self, client, userdata, flags, rc):
        _log.debug("Connected with result code " + str(rc))
        self.client.subscribe("alto_reserve_topic/request_all_data")

    def on_message(self, client, userdata, msg):
        data = json.loads(msg.payload.decode())
        _log.debug(f"MQTTSub {data}")
        if data["path"] == "all":
            for mongo_data in self.mongo_col_data.find():
                self.put_to_pub(mongo_data)
    
    def put_to_pub(self, mongo_data):
        try:
            self.mqtt_pub_queue.put_nowait(
                {
                    "topic": mongo_data["_id"],
                    "data": deepcopy(mongo_data["data"])
                }
            )
        except Exception as e:
            _log.warning(f"MQTTSub mqtt_pub_queue {e}") 


if __name__ == "__main__":
    try:
        mqtt_pub_queue = Queue()

        mqtt_pub_thr = MQTTPubThread(mqtt_pub_queue)
        mqtt_pub_thr.setDaemon(True)
        mqtt_pub_thr.start()

        mongodb_change_stream_thr = MongoDBChangeStreamThread(mqtt_pub_queue)
        mongodb_change_stream_thr.setDaemon(True)
        mongodb_change_stream_thr.start()

        mqtt_sub = MQTTSub(mqtt_pub_queue)
        mqtt_sub.loop()
    except KeyboardInterrupt:
        _log.debug("\nExiting at user's request")
    except Exception as e:
        _log.warning(f"\nException {e}")
    finally:
        pass
