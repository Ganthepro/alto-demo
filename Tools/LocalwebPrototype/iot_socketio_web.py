#!/usr/bin/env python3

"""
deps:
    - pip install python-socketio==5.5.0
    - pip install python-socketio[client]
    - pip install uvicorn==0.17.6
    - pip install uvicorn[standard]
    - pip install janus
    - pip install motor==3.0.0
"""

import threading
import janus
import asyncio as aio

from aiohttp import web
# import asyncio as aio

import socketio
# import uvicorn

from motor.motor_asyncio import AsyncIOMotorClient
import pymongo
from bson.json_util import dumps


# class MongoDBChangeStreamThread(threading.Thread):
#     def __init__(self, mqtt_pub_queue):
#         super().__init__()
#         self.mqtt_pub_queue = mqtt_pub_queue

#         self.is_run = True

#         self.mongo_client = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

#         self.mongo_db = self.mongo_client["altofiredb"]
#         self.mongo_col_data = self.mongo_db["lastest_data"]

#     def run(self):
#         # while self.is_run:
#         try:
#             with self.mongo_col_data.watch() as change_stream:
#                 for change in change_stream:
#                     full_document = change["fullDocument"]
#                     _log.debug(dumps(full_document))
#                     self.put_to_pub(full_document)
#         except Exception as e :
#             _log.warning(f"MongoDBChangeStreamThread {e}")
#         _log.debug('end 2')

#     def close_mongodb_client(self):
#         self.mongo_db.close()
    
#     def put_to_pub(self, full_document):
#         try:
#             self.mqtt_pub_queue.put_nowait(
#                 {
#                     "topic": full_document["_id"],
#                     "data": deepcopy(full_document["data"])
#                 }
#             )
#         except Exception as e:
#             _log.warning(f"mqtt_pub_queue {e}")




# class PubThread(threading.Thread):
#     def __init__(self, pub_queue, socketio_ins):
#         super().__init__()
#         self.pub_queue = pub_queue
#         self.socketio_ins = socketio_ins

#         self.is_run = True
#         # self.sent_count = 0

#         # self.client = mqtt.Client(client_id = "mqtt-pub-proxy", clean_session = True)
#         # self.client.connect(mqtt_broker_ip, mqtt_broker_port, mqtt_timelive)
#         # self.client.on_publish = self.on_publish
#         # self.client.on_connect = self.on_connect
#         # self.client.on_disconnect = self.on_disconnect

#     def run(self):
#         while self.is_run:
#             data = self.pub_queue.get()
#             self.pub_queue.task_done()
#             _log.debug(f"data: {data}")
#             if data != 'Die' or True:
#                 try:
#                     self.publish(data)
#                 except Exception as e :
#                     _log.error(e)
#             else:
#                 break
#         _log.debug('end 2')
    
#     def publish(self, data):
#         self.socketio_ins.publish(data["topic"], dumps(data["data"]))
#         _log.debug(f"publish sent_count: {data['topic']}")


async def startup():
    print("Starting Application")


# # @sio.on("FOO")
# # async def foo_event(sid, *args, **kwargs):
# #     data = FooEvent(**args[0])
# #     await sio.emit("BAR", {"foo": data.name})


class SocketIOServer:
    # sio = socketio.AsyncServer(async_mode="asgi")
    sio = socketio.AsyncServer(async_mode='aiohttp')

    def __init__(self):
        self._clients = {}
        self._topics = set()

        uri = "mongodb://root:Magicalmint636@127.0.0.1:27017/?replicaSet=rs0"
        self.mongo_client = AsyncIOMotorClient(uri)
        self.mongo_db = self.mongo_client.get_database("altofiredb")
        self.mongo_col_data_tree = self.mongo_db.get_collection("lastest_data_tree")
    
    async def publish(self, topic, data):
        print(topic, data)
        dbdata = await self.mongo_col_data_tree.find_one()
        print(dbdata["buildings"])
        for tl in self._topics:
            len_tl = len(tl)
            len_topic = len(topic)
            if len_tl <= len_topic:
                if tl == topic[:len_tl]:
                    print(tl)
                    stls = tl.split("/")
                    # print(stls)
                    kodata = None
                    is_first = True
                    for stl in stls:
                        if is_first:
                            is_first = False
                            kodata = dbdata.get(stl, None)
                        else:
                            kodata = kodata.get(stl, None)
                        # print(stl, kodata)
                        if kodata is None:
                            break
                    # print(kodata)
                    await self.sio.emit(tl, kodata)

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


# g_queue = ContextVar('g_queue')
class HTTPServer:
    webserver = web.Application()

    def __init__(self, dataqueue):
        self.socketio_ins = None
        self.dataqueue = dataqueue
        # g_queue.set(self.dataqueue)

        # self.mongo_client = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

        # self.mongo_db = self.mongo_client["altofiredb"]
        # self.mongo_col_data_tree = self.mongo_db["lastest_data_tree"]
        # self.mongo_col_data = self.mongo_db["lastest_data"]

        self.init_endpoint()

    async def submit(self, request):
        """Endpoint for submitting data"""
        # return web.Response(text="Ok", content_type='text/html')
        data = await request.json()
        try:
            self.dataqueue.put_nowait(data)
        except Exception as e:
            print(f"HTTPServer submit {e}")
        return web.Response(text="OK")

    def init_endpoint(self):
        self.webserver["pubs"] = []
        # self.webserver.router.add_get('/submit', self.submit)
        self.webserver.add_routes([web.post("/submit", self.submit)])
        self.webserver.on_shutdown.append(self.shutdown)
        self.webserver.on_startup.append(self.startup)
    
    def bind_socketio(self, socketio_ins):
        self.socketio_ins = socketio_ins
    
    async def run(self):
        is_run = True
        uri = "mongodb://root:Magicalmint636@127.0.0.1:27017/?replicaSet=rs0"
        mongo_client = AsyncIOMotorClient(uri)
        db = mongo_client.get_database("altofiredb")
        collection = db.get_collection("lastest_data_tree")
        # self.mongo_db = self.mongo_client["altofiredb"]
        # self.mongo_col_data_tree = self.mongo_db["lastest_data_tree"]
        # self.mongo_col_data = self.mongo_db["lastest_data"]
        while is_run:
            try:
                print("HTTPServer run")
                await aio.sleep(0.05)
                data = await self.dataqueue.get()
                # print(data)
                FBTARGET = "buildings"
                mytopic = (
                    "/"
                    + FBTARGET
                    + "/"
                    + data["location"]
                    + "/"
                    + data["device_id"]
                    + "/"
                    + data["schema"]
                    + "/"
                    + data["subdevice"]
                )
                topic = mytopic
                raw_topic = topic[1:]
                topic = raw_topic.replace("/", ".")
                payload = data["data"]
                # payload.update({"device_id": data["device_id"]})
                path_and_data = [{ "$set": { topic: payload } }]
                await collection.update_many({}, path_and_data, upsert=True)
                # data_only = [{ "$set": { "data": payload } }]
                # self.mongo_col_data.update_many({"_id": {"$in": [raw_topic]}}, data_only, upsert=True, session=session)
                await self.socketio_ins.publish(raw_topic, data["data"])
            except aio.CancelledError as e:
                is_run = False
            except Exception as e:
                print("HTTPServer {}".format(e))
    
    async def shutdown(self, app):
        for pub in app["pubs"]:
            pub.cancel()
    
    async def startup(self, app):
        newtsk = aio.ensure_future(self.run())
        app["pubs"].append(newtsk)
        await aio.sleep(0.1)


async def startmeup(app):
    global runner
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8050)
    await site.start()


if __name__ == "__main__":
    try:
        loop = aio.get_event_loop()
        dataqueue = aio.Queue()
        runner = None
        http_server = HTTPServer(dataqueue)
        SocketIOServer.sio.attach(http_server.webserver)
        app = socketio.ASGIApp(SocketIOServer.sio, on_startup=startup)
        sockio = SocketIOServer()
        sockio.init_events()
        http_server.bind_socketio(sockio)
        
        # uvicorn.run(app, host="0.0.0.0", port=8050)
        # uvicorn.run(webserver, host="0.0.0.0", port=8050)
        # web.run_app(http_server.webserver, host="0.0.0.0", port=8050)
        loop.run_until_complete(startmeup(http_server.webserver))
        loop.run_forever()
    except KeyboardInterrupt:
        print("\nExiting at user's request")
    finally:
        loop.run_until_complete(runner.cleanup())
        loop.run_until_complete(http_server.webserver.shutdown())
        loop.run_until_complete(http_server.webserver.cleanup())
        loop.close()

# https://github.com/miguelgrinberg/python-socketio/issues/390
# https://haseebmajid.dev/blog/testing-python-socketio
