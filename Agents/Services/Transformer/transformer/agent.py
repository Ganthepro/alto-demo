"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread
from queue import Queue
import datetime as dt

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def transformer_factory(atype):
    if atype == "EVBattery":
        return EVBattery
    if atype == "EVBattery2":
        return EVBattery2

    raise Exception(f"Unknown transformer type {atype}")


class EVTower():

    def __init__(self, parent, subdevice_idx, subdevice_name, battery_id):
        self.parent = parent
        self.subdevice_idx = subdevice_idx
        self.subdevice_name = subdevice_name
        self.battery_id = battery_id
        self.device = {}
        self.electric = {}

    def update_data(self, data):
        # _log.debug(f"EVTower update_data {data}")

        if data["subdevice_idx"] != self.subdevice_idx:
            return None

        if data["data"]["type"] == "device":
            if data["data"]["battery_id"] != self.battery_id:
                self.battery_id = data["data"]["battery_id"]
                self.device = {}
                self.electric = {}

        if data["data"]["type"] == "device":
            for k, v in data["data"].items():
                if k not in ["battery_id"]:
                    self.device[k] = v
                # else:
                #     self.device["device_id"] = v

        if data["data"]["type"] == "electric":
            for k, v in data["data"].items():
                if k not in []:
                    self.electric[k] = v

        if self.device and self.electric:
            edata = {
                "device_id": self.battery_id,
                "subdevice_idx": 0,
                "subdevice_name": "subdev_0",
                "data": self.device
            }
            self.parent.emit_event_sample(edata)
            edata = {
                "device_id": self.battery_id,
                "subdevice_idx": 0,
                "subdevice_name": "subdev_0",
                "data": self.electric
            }
            self.parent.emit_event_sample(edata)


class EVBattery():

    def __init__(self, controller, trans_id, tran):
        self.controller = controller
        self.trans_id = trans_id
        self.input_topic = tran.get("input_topic", "sensor/charger/ev_tower_001/sample")
        # self.output_topic = tran.get("output_topic", self.input_topic)
        self.from_agent_id = tran.get("from_agent_id", "charger")
        self.ev_tower_list = {}

        self.controller.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=self.input_topic,
                                  callback=self.subscribe_callback)
    
    def subscribe_callback(self, 
                            peer, 
                            sender, 
                            bus, 
                            topic, 
                            headers,
                            message):
        # _log.debug(f"EVBattery {sender} {topic} {headers} {message}")
        if sender != self.controller.core.identity and sender == self.from_agent_id:
            try:
                data = message

                # _log.debug(f"EVBattery {data}")

                self.controller._add_job({
                    "instance": self,
                    "data": data
                })

            except Exception as e:
                # When the queue is full (So when?)
                _log.debug(f"EVBattery {e.message}, {e.args}")

    def emit_event_sample(self, data):
        input_topic = self.input_topic.split("/")
        output_topic = f'''{input_topic[0]}/{self.controller.core.identity}/{data["device_id"]}/{input_topic[3]}'''
        _log.debug(f'''EVBattery emit_event_sample {output_topic} {data}''')
        self.controller.publish(output_topic, data, "event")

    def send_sample_thread(self, data):
        # _log.debug(f'''EVBattery {data}''')
        if data["data"]["type"] == "device":
            # _log.debug(f'''EVBattery 1 {data["subdevice_idx"]} {data["data"]["battery_id"]}''')
            if data["subdevice_idx"] not in self.ev_tower_list:
                # _log.debug(f'''EVBattery 2 {data["subdevice_idx"]} {data["data"]["battery_id"]}''')
                self.ev_tower_list[data["subdevice_idx"]] = EVTower( self, data["subdevice_idx"], data["subdevice_name"], data["data"]["battery_id"])
        for k, v in self.ev_tower_list.items():
            v.update_data(data)


class EVTower2():

    def __init__(self, parent, subdevice_idx, subdevice_name, battery_id):
        self.parent = parent
        self.subdevice_idx = subdevice_idx
        self.subdevice_name = subdevice_name
        self.battery_id = battery_id
        self.device = {}
        self.electric = {}

        self._key_skip = ["device_id", "subdevice_idx", "subdevice_name"]

    def update_data(self, data):
        # _log.debug(f"EVTower update_data {data}")

        if data["subdevice_idx"] != self.subdevice_idx:
            return None

        if data["type"] == "device":
            if data["battery_id"] != self.battery_id:
                self.battery_id = data["battery_id"]
                self.device = {}
                self.electric = {}

        if data["type"] == "device":
            for k, v in data.items():
                if k not in ["battery_id"] and k not in self._key_skip:
                    self.device[k] = v
                # else:
                #     self.device["device_id"] = v

        if data["type"] == "electric":
            for k, v in data.items():
                if k not in self._key_skip:
                    self.electric[k] = v

        if self.device and self.electric:
            edata = {
                "device_id": self.battery_id,
                "subdevice_idx": 0,
                "subdevice_name": "subdev_0"
            }
            edata.update(self.device)
            self.parent.emit_event_sample(edata)
            edata = {
                "device_id": self.battery_id,
                "subdevice_idx": 0,
                "subdevice_name": "subdev_0"
            }
            edata.update(self.electric)
            self.parent.emit_event_sample(edata)


class EVBattery2():

    def __init__(self, controller, trans_id, tran):
        self.controller = controller
        self.trans_id = trans_id
        self.input_topic = tran.get("input_topic", "sensor/charger/ev_tower_002/event")
        # self.output_topic = tran.get("output_topic", self.input_topic)
        self.from_agent_id = tran.get("from_agent_id", "charger")
        self.ev_tower_list = {}

        self.controller.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=self.input_topic,
                                  callback=self.subscribe_callback)
    
    def subscribe_callback(self, 
                            peer, 
                            sender, 
                            bus, 
                            topic, 
                            headers,
                            message):
        # _log.debug(f"EVBattery {sender} {topic} {headers} {message}")
        if sender != self.controller.core.identity and sender == self.from_agent_id:
            try:
                data = message

                # _log.debug(f"EVBattery {data}")

                self.controller._add_job({
                    "instance": self,
                    "data": data
                })

            except Exception as e:
                # When the queue is full (So when?)
                _log.debug(f"EVBattery2 {e.message}, {e.args}")

    def emit_event_sample(self, data):
        input_topic = self.input_topic.split("/")
        output_topic = f'''{input_topic[0]}/{self.controller.core.identity}/{data["device_id"]}/{input_topic[3]}'''
        _log.debug(f'''EVBattery2 emit_event_sample {output_topic} {data}''')
        self.controller.publish(output_topic, data, "event")

    def send_sample_thread(self, data):
        # _log.debug(f'''EVBattery {data}''')
        if data["type"] == "device":
            # _log.debug(f'''EVBattery 1 {data["subdevice_idx"]} {data["data"]["battery_id"]}''')
            if data["subdevice_idx"] not in self.ev_tower_list:
                # _log.debug(f'''EVBattery 2 {data["subdevice_idx"]} {data["data"]["battery_id"]}''')
                self.ev_tower_list[data["subdevice_idx"]] = EVTower2( self, data["subdevice_idx"], data["subdevice_name"], data["battery_id"])
        for k, v in self.ev_tower_list.items():
            v.update_data(data)


def transformer(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Transformer
    :rtype: Transformer
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get('agent_name', "transformer")
    transformers = config.get('transformers', [])


    return Transformer(agent_name,
                          transformers,
                          **kwargs)


class Transformer(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, transformers, **kwargs):
        super(Transformer, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.queue = Queue()
        self.trans_list = {}

        self.agent_name = agent_name
        self.transformers = transformers

        self.default_config = {"agent_name": agent_name,
                               "transformers": transformers}


        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
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
            agent_name = config["agent_name"]
            transformers = config["transformers"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.transformers = transformers

        self._create_subscriptions()

    def _build_trans(self, trans_type, trans_id, tran):
        _log.debug(f'''_build_trans {trans_type} {trans_id}''')
        if trans_id not in self.trans_list:
            Tran = transformer_factory(trans_type)
            newdev = Tran(self, trans_id, tran)
            _log.debug(f'''_build_trans {newdev}''')
            self.trans_list[trans_id] = newdev

    def _create_subscriptions(self):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)
        
        _log.debug(f'''Transformer {self.transformers}''')
        self.trans_list = {}
        try:
            for tran in self.transformers:
                # _log.debug(f'''Transformer {tran["type"]} {tran["trans_id"]} {tran}''')
                self._build_trans(tran["type"], tran["trans_id"], tran)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"Transformer {e.message}, {e.args}")

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        
        self.core.periodic(1, self._period_signal)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        
        self._add_job("Die")

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

    def _period_signal(self):
        pass

    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _send_samples_thread(self):
        while True:
            job = self.queue.get()
            self.queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            # _log.debug("_send_samples_thread")
            job["instance"].send_sample_thread(job["data"])

def main():
    """Main method called to start the agent."""
    utils.vip_main(transformer, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
