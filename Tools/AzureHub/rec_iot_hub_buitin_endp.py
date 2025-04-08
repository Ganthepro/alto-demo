__docformat__ = 'reStructuredText'

import logging
import sys
from abc import ABCMeta, abstractmethod
from threading import Thread
from queue import Queue

from azure.eventhub import EventHubConsumerClient
from azure.iot.hub import IoTHubRegistryManager
import json

# from volttron.platform.agent import utils
# from volttron.platform.vip.agent import Agent, Core, RPC


# _log = logging.getLogger(__name__)
# utils.setup_logging()
# __version__ = "0.1"

class EventHubCloseException(Exception):
    """Exception raise when you need to close azure event hub"""
    pass


class IObservable(metaclass=ABCMeta):
    "The Observable Interface"

    @staticmethod
    @abstractmethod
    def subscribe(observer):
        "The subscribe method"

    @staticmethod
    @abstractmethod
    def unsubscribe(observer):
        "The unsubscribe method"

    @staticmethod
    @abstractmethod
    def notify(**kwargs):
        "The notify method"


class AZIoTHubD2C(IObservable):

    def __init__(self, connection_str, consumer_group="$default"):
        self._connection_str = connection_str
        self._consumer_group = consumer_group
        self._observers = set() # can be override

        # self.client = EventHubConsumerClient.from_connection_string(self._connection_str, self._consumer_group)
        # self.partition_ids = self.client.get_partition_ids()

        self.azrec_thread = Thread(target=self._azrec_thread)
        self.azrec_thread.setDaemon(True)

    def on_event(self, partition_context, event):
        print(f'''{event.body_as_json()["gatewayid"]}''')
        data = {
            "data": event.body_as_json()
        }
        self.notify(**data)
        partition_context.update_checkpoint(event)

    # def start_listening(self, on_event, starting_position):
    def start_listening(self):
        self.azrec_thread.start()

    def new_connect(self, connection_str, consumer_group):
        self.end_event_hub()

        self._connection_str = connection_str
        self._consumer_group = consumer_group

        self.client = EventHubConsumerClient.from_connection_string(self._connection_str, self._consumer_group)
        self.partition_ids = self.client.get_partition_ids()

        self.start_listening()

    def _azrec_thread(self):
        while True:
            # try:
            #     self.client = EventHubConsumerClient.from_connection_string(self._connection_str, self._consumer_group)
            #     self.partition_ids = self.client.get_partition_ids()
            #     with self.client:
            #         self.client.receive(
            #             on_event=self.on_event,
            #             starting_position="-1",  # "-1" is from the beginning of the partition.
            #         )
            # except Exception as e:
            #     print(e)
            # except EventHubCloseException:
            #     return
            # except KeyboardInterrupt:
            #     return
            self.client = EventHubConsumerClient.from_connection_string(self._connection_str, self._consumer_group)
            self.partition_ids = self.client.get_partition_ids()
            with self.client:
                self.client.receive(
                    on_event=self.on_event,
                    starting_position="-1",  # "-1" is from the beginning of the partition.
                )

    def end_event_hub(self):
        raise EventHubCloseException("end event hub")

    def subscribe(self, observer):
        self._observers.add(observer)

    def unsubscribe(self, observer):
        self._observers.remove(observer)

    def notify(self, **kwargs):
        for observer in self._observers:
            observer.notify(**kwargs)


class D2CWithFilter(AZIoTHubD2C):

    def __init__(self, connection_str, consumer_group, app_id):
        super().__init__(connection_str, consumer_group)
        self._app_id = app_id
        self._observers = {}

    def subscribe(self, observer, kfilter, target):
        self._observers[observer] = {
            "kfilter": kfilter,
            "target": target
        }

    def unsubscribe(self, observer):
        if observer in self._observers:
            del self._observers[observer]

    def notify(self, **kwargs):
        for observer, v in self._observers.items():
            if kwargs["data"][v["kfilter"]] == v["target"]:
                observer.notify(self, **kwargs)

d2c_with_filters = {}

connection_str = 'Endpoint=sb://iothub-ns-betaiothub-13344990-073ef16d21.servicebus.windows.net/;SharedAccessKeyName=iothubowner;SharedAccessKey=9tv4A3cJpTzvy77f1WaLPxSRd8mMuLYN2Nd8f7nprFI=;EntityPath=betaiothubprod'
consumer_group = "$default"
app_id = "app_d2c_1"
newins = D2CWithFilter(connection_str, consumer_group, app_id)
d2c_with_filters[app_id] = newins

# connection_str = 'Endpoint=sb://iothub-ns-betaiothub-13344990-073ef16d21.servicebus.windows.net/;SharedAccessKeyName=iothubowner;SharedAccessKey=9tv4A3cJpTzvy77f1WaLPxSRd8mMuLYN2Nd8f7nprFI=;EntityPath=betaiothubprod'
# consumer_group = "$default"
# observable = self.d2c_with_filters["app_d2c_1"]
# azure_device_id = "beta_ev_tower_001_monitor"
# timeout = 20
# app_id = "app_exp_1"
# newins = Expiration(observable, azure_device_id, timeout, app_id)
# self.expirations[app_id] = newins

d2c_with_filters["app_d2c_1"].start_listening()
