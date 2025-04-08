#!/usr/bin/env python3
#
# Proxy for Firebase logging
#
# A few settings
MAXQUEUE = 500  # Maximum number of pending data to be stored
NBPROC = 5  # Number of logging process to run
POLICY = "first"  # Define what to do when the queue is full:
#     "first": drop the first element in the queue
#     "last":  drop the last element in the queue
#     "wait":  wait until there is space
# any other value is considered to be "last"

# FBSECRET = "AIzaSyDjphOeX-zUJHvSAaoo3j1M5moba5ABSxE"
# FBURL = "https://altobuildings-default-rtdb.asia-southeast1.firebasedatabase.app"
# FBTARGET="buildings"

PORT = 8088
from firebase import firebase as pfb
from aiohttp import web
import asyncio as aio
import logging as _log
import sys
import threading
from queue import Queue
from copy import deepcopy

import argparse
import json

import pymongo


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
FBSECRET = config["FBSECRET"]
FBURL = config["FBURL"]
FBTARGET = config["FBTARGET"]

EN_MONGODB = config["EN_MONGODB"]


class MongoDBThread(threading.Thread):
    def __init__(self, mongo_data_queue):
        super().__init__()
        self.mongo_data_queue = mongo_data_queue

        self.is_run = True

        self.mongo_client = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

        self.mongo_db = self.mongo_client["altofiredb"]
        self.mongo_col_data_tree = self.mongo_db["lastest_data_tree"]
        self.mongo_col_data = self.mongo_db["lastest_data"]

    def run(self):
        while self.is_run:
            data = self.mongo_data_queue.get()
            self.mongo_data_queue.task_done()
            _log.debug(f"data: {data}")
            if data != 'Die' or True:
                try:
                    self.store_data(data)
                except Exception as e :
                    _log.warning(f"MongoDBThread {e}")
            else:
                break
        _log.debug('end 2')
    
    def store_data(self, data):
        with self.mongo_client.start_session() as session:
            with session.start_transaction():
                # orders.insert_one({"sku": "abc123", "qty": 100}, session=session)
                # inventory.update_one({"sku": "abc123", "qty": {"$gte": 100}},
                #                         {"$inc": {"qty": -100}}, session=session)
                topic = data["topic"]
                raw_topic = topic[1:]
                topic = raw_topic.replace("/", ".")
                payload = data["data"]
                path_and_data = [{ "$set": { topic: payload } }]
                self.mongo_col_data_tree.update_many({}, path_and_data, upsert=True, session=session)
                data_only = [{ "$set": { "data": payload } }]
                self.mongo_col_data.update_many({"_id": {"$in": [raw_topic]}}, data_only, upsert=True, session=session)


class Logger:
    def __init__(self, myid, mongo_data_queue=None):
        self.fbapp = pfb.FirebaseApplication(FBURL, authentication=None)
        # self.authenticate()
        self.data = None
        self.myid = myid

        self.mongo_data_queue = mongo_data_queue

    def authenticate(self):
        self.fbapp.authentication = pfb.FirebaseAuthentication(
            FBSECRET, "arm@gmail.com", extra={"id": 123}
        )

    async def logging(self):
        _log.debug(
            f"Logging to {FBTARGET}/{self.data['location']}/{self.data['device_id']}/{self.data['schema']} -> {self.data['subdevice']} value {self.data['data']}"
        )
        try:
            mytopic = (
                "/"
                + FBTARGET
                + "/"
                + self.data["location"]
                + "/"
                + self.data["device_id"]
                + "/"
                + self.data["schema"]
                + "/"
                + self.data["subdevice"]
            )
            # self.fbapp.put_async(mytopic,self.data["subdevice"],self.data["data"],callback=self.async_cb)
            try:
                if self.mongo_data_queue is not None:
                    self.mongo_data_queue.put_nowait(
                        {
                            "topic": mytopic,
                            "data": deepcopy(self.data["data"])
                        }
                    )
            except Exception as e:
                _log.warning(f"mongo_data_queue {e}")
            self.fbapp.patch_async(mytopic, self.data["data"], callback=self.async_cb)
        except Exception as e:
            # self.fbapp.put_async("/{}".format(FBTARGET+"/devices"),self.data["device_id"],self.data["data"],callback=self.async_cb)
            _log.warning(f"Problem with data. Data was dropped: {e}")
            self.data = None
            return
        await aio.sleep(1)
        tout = 6
        while self.data:
            await aio.sleep(0.5)
            tout -= 1
            if tout:
                continue
            _log.warning("Time out trying to send data to Firebase. data dropped.")
            self.data = None

    def async_cb(self, resp, *kargs, **kwargs):
        """Log data to Firebase by retrieving it from the queue"""
        _log.debug("Response is {}".format(resp))
        # if 'error' in resp and resp['error'] == 'error':
        # self.authenticate()
        # else:
        self.data = None

    async def runme(self):
        global dataqueue
        goon = True
        while goon:
            try:
                if self.data is None:
                    _log.debug(
                        "Logger {} waiting for data. Len is {}, data is {}".format(
                            self.myid, dataqueue.qsize(), self.data
                        )
                    )
                    self.data = await dataqueue.get()
                    _log.debug("Logger {} got {}".format(self.myid, self.data))
                else:
                    _log.debug("Logger {} trying again {}".format(self.myid, self.data))
                await self.logging()
            except aio.CancelledError as e:
                goon = False
            except Exception as ex:
                _log.debug("Something went bad. {}".format(ex))


async def submit(request):
    global dataqueue

    data = await request.json()
    _log.debug("Request is {}".format(data))
    if dataqueue.full():
        if POLICY == "first":
            tbddata = await dataqueue.get()
        elif POLICY == "wait":
            pass
        else:
            return web.Response(text="OK")
    await dataqueue.put(data)
    return web.Response(text="OK")


async def shutdown(app):
    _log.debug("Shutdown signal received")
    for tsk in app["loggers"]:
        tsk.cancel()


async def startup(app):
    global mongo_data_queue
    _log.debug("Start signal received")
    for x in range(NBPROC):
        _log.debug("Starting logger {}".format(x))
        newlog = Logger(x, mongo_data_queue)
        newtsk = aio.ensure_future(newlog.runme())
        app["loggers"].append(newtsk)
    await aio.sleep(0)


async def startmeup(app):
    global runner
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", PORT)
    await site.start()


_log.basicConfig(
    level=_log.DEBUG, format="%(levelname)7s: %(message)s", stream=sys.stderr
)
loop = aio.get_event_loop()
dataqueue = aio.Queue(MAXQUEUE)


# init mongo
mongo_data_queue = None
if EN_MONGODB:
    mongo_data_queue = Queue()
    mongo_thr = MongoDBThread(mongo_data_queue)
    mongo_thr.setDaemon(True)
    mongo_thr.start()


runner = None
app = web.Application()
app["loggers"] = []
app.add_routes([web.post("/submit", submit)])
app.on_shutdown.append(shutdown)
app.on_startup.append(startup)
# whandler = app.make_handler()
# wapp=loop.create_server(whandler,host=guiwscfg["host"],port=guiwscfg["port"],ssl=ssl_context)
loop.run_until_complete(startmeup(app))
try:
    loop.run_forever()
except KeyboardInterrupt:
    _log.debug("\nExiting at user's request")
finally:
    loop.run_until_complete(runner.cleanup())
    loop.run_until_complete(app.shutdown())
    # loop.run_until_complete(whandler.finish_connections(60.0))
    loop.run_until_complete(app.cleanup())
    loop.close()
