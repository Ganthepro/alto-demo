#!/usr/bin/env python3

"""
deps:
    - python-socketio==5.5.0
    - pip install python-socketio[client]
    - pip install uvicorn
    - pip install uvicorn[standard]
"""

import asyncio
import socketio
from socketio.exceptions import ConnectionRefusedError
from os import path
from typing import Optional
from asgiref.sync import SyncToAsync
from datetime import datetime, timedelta
import time
import logging
from pytz import timezone
from cscbackend.service.counter import CameraCounterResultEntry, query_counter_today
from cscbackend import models, permission
from cscbackend.settings import KAFKA_SERVER, CORS_ALLOWED_ORIGINS, CORS_ALLOW_ALL_ORIGINS
from cscbackend.kafka import deserialize_message
from cscbackend.apiusage import APIRequestMeasurement, worker
from django.db.models import Model, BigAutoField, CharField
from django.contrib.auth.models import User
from aiokafka import AIOKafkaConsumer
from schema_registry.client.schema import AvroSchema
from rest_framework import serializers
from oauth2_provider.models import AccessToken

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=CORS_ALLOWED_ORIGINS if not CORS_ALLOW_ALL_ORIGINS else '*')

typemapping = {
                models.Building: "building",
                models.BuildingFloor: "floor",
                models.Camera: "camera",
            }

rev_typemapping = dict((v, u) for (u, v) in typemapping.items())

def get_entity_model_id_from_key(key):
    etype, eid = key
    model = rev_typemapping[etype]
    field = model._meta.get_field('id').__class__
    if field is CharField:
        pass
    elif field is BigAutoField:
        eid = int(eid)
    else:
        assert False, "Model is is neither int nor char. actual: {}".format(field)
    return model, eid


def get_entity_from_key(key):
    model, eid = get_entity_model_id_from_key(key)
    ent =  model.objects.filter(id=eid).first()
    return ent

def wrap_sync(func):
    return SyncToAsync(func, thread_sensitive=False)

class ObservableCameraEventEntity:
    """ Represent enitity that can be affected by camera event and can be listened to """

    key: tuple[str, str]
    subscription: dict[str, set[str]]
    count_people_in: int
    count_people_out: int
    last_fetch: datetime
    lock: asyncio.Lock

    def __init__(self, key):
        self.key = key
        self.subscription = dict()
        self.lock = asyncio.Lock()

    def fetch(self):
        res = query_counter_today(get_entity_from_key(self.key))
        self.count_people_in = res.count_people_in
        self.count_people_out = res.count_people_out
        self.last_fetch = datetime.now()

    async def process_message(self, topic, msg, recv_time):
        start_time = datetime.now()

        if not self.last_fetch or datetime.now() - self.last_fetch >= timedelta(minutes=1):
            async with self.lock:
                await wrap_sync(self.fetch)()

        async with self.lock:
            subscription = self.subscription.copy()

        async def emit_camera_stream(sid):
            await sio.emit('camera-stream', {
                        'id': msg['device_id'],
                        'binjpeg': msg['image'],
                        'timestamp': recv_time,
                    }, room=sid)
            await record_apistat_measurement("socket::camera-stream", sid, datetime.now()-start_time)

        async def emit_inout(sid):
            await self.emit_count(sid, recv_time)
            await record_apistat_measurement("socket::inout-counting", sid, datetime.now()-start_time)

        target = []

        if topic == 'camera-stream':
            for sid, selections in subscription.items():
                if "video" not in selections:
                    continue
                target.append(emit_camera_stream(sid))

        if topic == 'inout-counting':
            async with self.lock:
                self.count_people_out += msg['count_people_out']
                self.count_people_in += msg['count_people_in']
            for sid, selections in subscription.items():
                if "count" not in selections:
                    continue
                target.append(emit_inout(sid))
        res = await asyncio.gather(*target, return_exceptions=True)
        err = []
        for r in res:
            if isinstance(r, Exception):
                err.append(r)
        if len(err) > 0:
            raise Exception(err)
                
    async def emit_count(self, sid, recv_time):
        await sio.emit('inout-counting', {
                            "type": self.key[0],
                            "id": self.key[1],
                            "count_people_in": self.count_people_in,
                            "count_people_out": self.count_people_out,
                            'timestamp': recv_time,
                        }, room=sid)


    async def register(self, sid, selections):
        async with self.lock:
            self.subscription[sid] = selections
        if 'count' in selections:
            await self.emit_count(sid, time.time())
    
    async def unregister(self, sid):
        async with self.lock:
            del self.subscription[sid]


class EntityNotFound(Exception):
    pass

class CameraEventProcessor:
    lock: asyncio.Lock
    entitymap: dict[tuple[str, str],ObservableCameraEventEntity]
    task: asyncio.Task

    def __init__(self):
        self.lock = asyncio.Lock()
        self.entitymap = dict()
        self.task = None

    async def get(self, key):
        async with self.lock:
            if key in self.entitymap:
                return self.entitymap[key]
            newentity = ObservableCameraEventEntity(key)
            await wrap_sync(newentity.fetch)()
            self.entitymap[newentity.key] = newentity
            return self.entitymap[key]

    async def ensure_running(self):
        async with self.lock:
            if not self.task:
                self.task = asyncio.create_task(self.run())
            if self.task.done():
                e = self.task.exception()
                self.task = None
                if e:
                    self.task = None
                    raise e
                else:
                    self.task = None
                    raise Exception("Task is done so it is not running")

    async def run(self):
        topics = ["camera-stream", "inout-counting"]
        schemas = dict((topic, AvroSchema.load(path.join(path.dirname(__file__), 'avro', topic + ".avsc"))) for topic in topics)
        consumer = AIOKafkaConsumer(*topics, bootstrap_servers=KAFKA_SERVER)
        await consumer.start()
        try:
            async for msg in consumer:
                try:
                    data = deserialize_message(msg.value, schemas[msg.topic])
                    recv_time = time.time()
                    async with self.lock:
                        target = []
                        if msg.topic == 'camera-stream':
                            target.append(("camera", data['device_id']))
                        if msg.topic == 'inout-counting':
                            target.append(('camera', data['device_id']))
                            target.append(('floor', str(data['floor_id'])))
                            target.append(('building', str(data['building_id'])))
                        for k in target:
                            if  k not in self.entitymap:
                                continue
                            async def run_and_log_error(routine):
                                try:
                                    await routine
                                except Exception as e:
                                    logger.exception('Error while processing message')
                            asyncio.create_task(self.entitymap[k].process_message(msg.topic, data, recv_time))
                except Exception as e:
                    logger.exception('Error while processing message')
        finally:
            await consumer.stop()

camera_event_processor = CameraEventProcessor()

class AuthSerializer(serializers.Serializer):
    token = serializers.CharField()

class AclCredential:
    """Credential for SocketIO"""

    def __init__(self, user: User, application: models.CustomApplication):
        self.user = user
        self.application = application
        self.user_id = user.id
        self.app_id = application.id
        self.app_owner_id = application.user.id

    def check_observation_list_valid(self, observation_items: list) -> bool:
        target = { t: set() for t in typemapping.keys() }
        for e in observation_items:
            try:
                t, eid = get_entity_model_id_from_key((e['type'], e['id']))
            except ValueError:
                return False
            target[t].add(eid)
        for t, ids in target.items():
            if not permission.AclEvaluator(t).check_multiple_with_id(ids, self.user, read=True):
                return False
        return True


    @classmethod
    async def from_access_token(cls, token: str) -> Optional['AclCredential']:
        def f():
            obj = AccessToken.objects.filter(token=token, expires__gt=datetime.now().astimezone(timezone("UTC"))).first()
            if not obj:
                return None
            return cls(obj.user if obj.user else obj.application.user, obj.application)
        return await wrap_sync(f)()


async def record_apistat_measurement(endpoint: str, sid, response_time=timedelta()):
    async with sio.session(sid) as session:
        try:
            acl: AclCredential = session['acl']
        except KeyError:
            return
        m = APIRequestMeasurement(
            user_id=acl.user_id, 
            endpoint=endpoint,
            app_id=acl.app_id,
            app_owner_id=acl.app_owner_id,
            response_time=response_time,
            method='SOCKETIO',
        )
        await wrap_sync(worker.send_measurement)(m)

@sio.event
async def connect(sid, environ, auth):
    start_time = datetime.now()
    ser = AuthSerializer(data=auth)
    if not ser.is_valid():
        logger.warn("Connection Refused, Bad Request %s", ser.errors)
        raise ConnectionRefusedError(ser.errors)
    acl = await AclCredential.from_access_token(ser.validated_data['token'])
    if not acl:
        logger.warn("Invalid Access Token")
        raise ConnectionRefusedError("Access token invalid")
    async with sio.session(sid) as session:
        session['observing'] = []
        session['acl'] = acl
    await record_apistat_measurement("socket::connect", sid, datetime.now() - start_time)
    return "OK"


class ObservationItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(['camera', 'floor', 'building'])
    selections = serializers.MultipleChoiceField(['video', 'count'])
    id = serializers.CharField()

@sio.event
async def observe(sid, data):
    start_time = datetime.now()
    s = ObservationItemSerializer(data=data, many=True)
    if not s.is_valid():
        return "ERROR", s.errors
    req = s.validated_data
    async with sio.session(sid) as session:
        for o in session['observing']:
            await o.unregister(sid)
        session['observing'] = []
        observing = []
        try:
            await camera_event_processor.ensure_running()
            if not await wrap_sync(lambda : session['acl'].check_observation_list_valid(req))():
                return "ERROR", "User lacks permission"
            for r in req:
                key = (r['type'], r['id'])
                obs = await camera_event_processor.get(key)
                await obs.register(sid, r['selections'])
                observing.append(obs)
            session['observing'] = observing
        except EntityNotFound as e:
            return "ERROR", e.args
    await record_apistat_measurement("socket::observe", sid, datetime.now() - start_time)
    return "OK"

@sio.event
async def disconnect(sid):
    start_time = datetime.now()
    async with sio.session(sid) as session:
        try:
            obsvs = session['observing']
            for o in obsvs:
                await o.unregister(sid)
        except KeyError:
            pass
    await record_apistat_measurement("socket::disconnect", sid, datetime.now() - start_time)