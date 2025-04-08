#!/usr/bin/env python3

"""
deps:
    - pip install python-socketio==5.5.0
    - pip install python-socketio[client]
    - pip install uvicorn==0.17.6
    - pip install uvicorn[standard]
"""

import socketio
import uvicorn

import pymongo
from bson.json_util import dumps


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


async def startup():
    print("Starting Application")


# # @sio.on("FOO")
# # async def foo_event(sid, *args, **kwargs):
# #     data = FooEvent(**args[0])
# #     await sio.emit("BAR", {"foo": data.name})


class SocketIOServer:
    sio = socketio.AsyncServer(async_mode="asgi")

    def __init__(self):
        self._clients = {}
        self._topics = set()

    def init_events(self):
        @self.sio.event
        def connect(sid, environ, auth):
            self._clients[sid] = set()
            print(f"connect {sid} {self._clients}")
        
        @self.sio.event
        async def subscribe_many(sid, data):
            self._clients[sid].update(data['topic'])
            self._topics.update(data['topic'])
            print(f"subscribe_many {self._topics}")
        
        @self.sio.event
        async def subscribe_one(sid, data):
            self._clients[sid].add(data['topic'])
            self._topics.add(data['topic'])
            print(f"subscribe_one {self._topics}")
            
        @self.sio.event
        def disconnect(sid):
            dclient_topics = self._clients.pop(sid, set())
            topic_union = set()
            if dclient_topics:
                for _, topics in self._clients.items():
                    topic_union = topic_union.union(topics)
                dif = dclient_topics.difference(topic_union)
                self._topics = self._topics.difference(dif)
            print(f"disconnect {sid} {self._clients} {self._topics}")


if __name__ == "__main__":
    app = socketio.ASGIApp(SocketIOServer.sio, on_startup=startup)
    sockio = SocketIOServer()
    sockio.init_events()
    uvicorn.run(app, host="0.0.0.0", port=8050)

# https://github.com/miguelgrinberg/python-socketio/issues/390
# https://haseebmajid.dev/blog/testing-python-socketio
