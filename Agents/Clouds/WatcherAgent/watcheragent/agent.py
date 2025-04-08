"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import datetime as dt
from abc import ABCMeta, abstractmethod
from threading import Thread
from queue import Queue

from azure.eventhub import EventHubConsumerClient
from azure.iot.hub import IoTHubRegistryManager
import json

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


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

        self.client = EventHubConsumerClient.from_connection_string(self._connection_str, self._consumer_group)
        self.partition_ids = self.client.get_partition_ids()
        self.starting_positions = {}
        for i in self.partition_ids:
            partition_prop = self.client.get_partition_properties(i)
            self.starting_positions[i] = partition_prop["last_enqueued_sequence_number"]
        _log.debug(f'''AZIoTHubD2C starting_position {self.starting_positions}''')

        self.azrec_thread = Thread(target=self._azrec_thread)
        self.azrec_thread.setDaemon(True)

    def on_event(self, partition_context, event):
        # _log.debug(f'''{event.body_as_json()["gatewayid"]}''')
        try:
            # _log.debug(f'''{event.body_as_json()["gatewayid"]}''')
            data = {
                "data": event.body_as_json()
            }
            self.notify(**data)
            partition_context.update_checkpoint(event)
        except:
            pass

    def start_listening(self):
        self.azrec_thread.start()

    def new_connect(self, connection_str, consumer_group):
        self._connection_str = connection_str
        self._consumer_group = consumer_group

        self.client = EventHubConsumerClient.from_connection_string(self._connection_str, self._consumer_group)
        self.partition_ids = self.client.get_partition_ids()
        self.starting_positions = {}
        for i in self.partition_ids:
            partition_prop = self.client.get_partition_properties(i)
            self.starting_positions[i] = partition_prop["last_enqueued_sequence_number"]
        _log.debug(f'''AZIoTHubD2C starting_position {self.starting_positions}''')

    def _azrec_thread(self):
        try:
            with self.client:
                self.client.receive(
                    on_event=self.on_event,
                    starting_position=self.starting_positions,  # "-1" is from the beginning of the partition.
                )
        except EventHubCloseException as e:
            _log.debug(f'''AZIoTHub {e}''')
            return
        except KeyboardInterrupt as e:
            _log.debug(f'''AZIoTHub {e}''')
            return

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


class IObserver(metaclass=ABCMeta):
    "A method for the Observer to implement"

    @staticmethod
    @abstractmethod
    def notify(observable, **kwargs):
        "Receive notifications"


class Expiration(IObserver):

    def __init__(self, observable, azure_device_id, timeout, app_id, controller, target_id_map, sensor_type_map):
        self.azure_device_id = azure_device_id
        self.timeout = timeout
        self.app_id = app_id
        self.current_time = self.timeout
        self.enable_count = False
        self.match = -1
        self.controller = controller
        self.target_id_map = target_id_map
        self.sensor_type_map = sensor_type_map

        self.need_tel_normal = False
        self.need_tel_anomaly = True

        observable.subscribe(self, "gatewayid", azure_device_id)

    def notify(self, observable, **kwargs):
        _log.debug(f"Expiration received {observable} {kwargs}")
        if "data" in kwargs:
            if "send_index" in kwargs["data"]:
                if kwargs["data"]["send_index"] == self.match:
                    _log.debug(f"Expiration match")
                    self.stop_count()
                    self.reset_count()
                    if self.need_tel_normal:
                        self.need_tel_normal = False
                        noti_data = {
                            # "azure_device_id": azure_device_id,
                            "status": "normal",
                            "notification_message": f'''{self.target_id_map} is back to online''',
                            "current_value": False,
                            "notification_image": "https://media.giphy.com/media/aWPGuTlDqq2yc/giphy.gif",
                            "notify_to": "admin",
                            "detect_value": False,
                            "threshold_max": True,
                            "threshold_min": False,
                            "sensor_type": self.sensor_type_map,
                            "sensor_id": self.target_id_map,
                            "subdevice_idx": 0
                        }
                        self.controller.push_notification(noti_data)
                        self.need_tel_anomaly = True

    def countdown(self):
        if self.enable_count:
            self.current_time -= 1
            if self.current_time < 0:
                self.stop_count()
                self.reset_count()
                if self.need_tel_anomaly:
                    self.need_tel_anomaly = False
                    noti_data = {
                        # "azure_device_id": azure_device_id,
                        "status": "anomaly",
                        "notification_message": f'''{self.target_id_map} is offline''',
                        "current_value": True,
                        "notification_image": "https://media.giphy.com/media/aWPGuTlDqq2yc/giphy.gif",
                        "notify_to": "admin",
                        "detect_value": True,
                        "threshold_max": True,
                        "threshold_min": False,
                        "sensor_type": self.sensor_type_map,
                        "sensor_id": self.target_id_map,
                        "subdevice_idx": 0
                    }
                    self.controller.push_notification(noti_data)
                    self.need_tel_normal = True

    def update_match(self, match):
        self.match = match

    def reset_count(self):
        self.current_time = self.timeout

    def start_count(self):
        self.enable_count = True

    def stop_count(self):
        self.enable_count = False


class AZIoTHubC2D:

    def __init__(self, connection_str):
        self.connection_str = connection_str

    def send_c2d_message(self, azure_device_id, data):
        try:
            self.registry_manager = IoTHubRegistryManager(self.connection_str)
            data_json = json.dumps(data)
            result = self.registry_manager.send_c2d_message(azure_device_id, data_json)
            _log.debug(f'AZIoTHubC2D done sending c2d msg to {azure_device_id}: {data_json}: {result}')
        except Exception as ex:
            _log.debug("AZIoTHubC2D Unexpected error {0}".format(ex))
        except KeyboardInterrupt:
            _log.debug("AZIoTHubC2D IoT Hub C2D Messaging service sample stopped")

    def new_connect(self, connection_str):
        self.connection_str = connection_str


class C2DWithID(AZIoTHubC2D):

    def __init__(self, connection_str, azure_device_id, data, app_id, expiration):
        super().__init__(connection_str)
        self.app_id = app_id
        self.azure_device_id = azure_device_id
        self.data = data
        self.send_index = 0
        self.expiration = expiration

    def send_message(self):
        self.expiration.update_match(self.send_index)
        self.data["send_index"] = self.send_index
        self.send_c2d_message(self.azure_device_id, self.data)
        self.expiration.start_count()
        self.send_index += 1

    def update_expiration(self, expiration):
        self.expiration = expiration


def watcheragent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Watcheragent
    :rtype: Watcheragent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    d2c_with_filters = config.get('d2c_with_filters', [])
    expirations = config.get('expirations', [])
    c2d_with_ids = config.get('c2d_with_ids', [])
    kwargs["countdown_interval"] = config.get("countdown_interval", 1)
    kwargs["send_message_interval"] = config.get("send_message_interval", 60)

    return Watcheragent(d2c_with_filters, expirations, c2d_with_ids, **kwargs)


class Watcheragent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, d2c_with_filters, expirations, c2d_with_ids, **kwargs):
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super(Watcheragent, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)

        self.queue = Queue()

        self.d2c_with_filters_ins = {}
        self.expirations_ins = {}
        self.c2d_with_ids_ins = {}

        self.d2c_with_filters = d2c_with_filters
        self.expirations = expirations
        self.c2d_with_ids = c2d_with_ids
        self.countdown_interval = kwargs["countdown_interval"]
        self.send_message_interval = kwargs["send_message_interval"]

        self.default_config = {"d2c_with_filters": d2c_with_filters,
                               "expirations": expirations,
                               "c2d_with_ids": c2d_with_ids,
                               "countdown_interval": self.countdown_interval,
                               "send_message_interval": self.send_message_interval}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

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
            d2c_with_filters = config["d2c_with_filters"]
            expirations = config["expirations"]
            c2d_with_ids = config["c2d_with_ids"]
            countdown_interval = config["countdown_interval"]
            send_message_interval = config["send_message_interval"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.d2c_with_filters = d2c_with_filters
        self.expirations = expirations
        self.c2d_with_ids = c2d_with_ids
        self.countdown_interval = countdown_interval
        self.send_message_interval = send_message_interval

        self._create_subscriptions()

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """

        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self._build_watcher()

        self.core.periodic(self.countdown_interval, self._countdown_interval_period)
        self.core.periodic(self.send_message_interval, self._send_message_interval_period)

    def _build_watcher(self):
        for i in self.d2c_with_filters:
            connection_str = i["connection_str"]
            consumer_group = i["consumer_group"]
            d2c_wf_id = i["d2c_wf_id"]
            newins = D2CWithFilter(connection_str, consumer_group, d2c_wf_id)
            self.d2c_with_filters_ins[d2c_wf_id] = newins
        for i in self.expirations:
            observable = self.d2c_with_filters_ins[i["observable"]]
            azure_device_id = i["azure_device_id"]
            timeout = i["timeout"]
            exp_id = i["exp_id"]
            target_id_map = i["target_id_map"]
            sensor_type_map = i["sensor_type_map"]
            newins = Expiration(observable, azure_device_id, timeout, exp_id, self, target_id_map, sensor_type_map)
            self.expirations_ins[exp_id] = newins

        for k, v in self.d2c_with_filters_ins.items():
            v.start_listening()

        for i in self.c2d_with_ids:
            connection_str = i["connection_str"]
            azure_device_id = i["azure_device_id"]
            c2d_id = i["c2d_id"]
            data = i["data"]
            expiration = self.expirations_ins[i["expiration"]]
            newins = C2DWithID(connection_str, azure_device_id, data, c2d_id, expiration)
            self.c2d_with_ids_ins[c2d_id] = newins

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """

        self._add_job("Die")

    def _countdown_interval_period(self):
        for k, v in self.expirations_ins.items():
            v.countdown()

    def _send_message_interval_period(self):
        for k, v in self.c2d_with_ids_ins.items():
            v.send_message()

    def push_notification(self, data):
        _log.debug(f'''Watcheragent push_notification {data}''')
        self._add_job({
            "instance": self,
            "data": data
        })

    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _send_samples_thread(self):
        while True:
            try:
                job = self.queue.get()
                self.queue.task_done()
                if isinstance(job, str):
                    if job == "Die":
                        return
                _log.debug("Watcheragent _send_samples_thread")
                topic = "notify/notifyapi/linefire_001/command"
                mtype = "command"
                job["instance"].publish(topic, job["data"], mtype)
            except Exception as e:
                _log.error(f"Watcheragent _send_samples_thread {e}")

    def publish(self, topic, value, mtype):
        """
        Publish to the Volttron bus
        :param topic: The topic to publish to.
        :type topic: string
        :param value: The message payload
        :type value: as needed
        :param mtype: The type to set in the header, command, evemt, request or response.
        :returns: None
        :rtype: None
        """

        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            message=value,
            headers={
                "requesterID": self.core.identity,
                "message_type": mtype,
                "TimeStamp": dt.datetime.utcnow()
                .replace(tzinfo=dt.timezone.utc)
                .isoformat(),
            },
        )


def main():
    """Main method called to start the agent."""
    utils.vip_main(watcheragent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
