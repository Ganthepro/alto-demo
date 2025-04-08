"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread
import threading
from queue import Queue
import copy
import json
import datetime as dt
from typing import Any, List, Mapping

from gevent.lock import BoundedSemaphore

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.scheduling import cron, periodic

import pyrebase


from rlaction import (_log,
                      AltoNotImpl,
                      GlobalRLOutput,
                      data_store_factory,
                      UndergroundData,
                      OutdoorWeatherData,
                      OccupantData,
                      derived_data_factory,
                      manipulation_factory,
                      rl_factory,
                      HVACRL,
                      AHURL,
                      PMVRL,
                      output_device_factory,
                      HVACOutput,
                      AHUOutput,
                      ITMOAUOutput)


# _log = logging.getLogger(__name__)
# utils.setup_logging()
__version__ = "0.1"

bounded_sem = BoundedSemaphore(1)


class DefaultBuilder:

    @staticmethod
    def build(controller):
        data_stores = controller.data_stores
        data_stores_ins = controller.data_stores_ins
        for k, v in data_stores.items():
            if k not in data_stores_ins:
                Tmp = data_store_factory(v[0])
                # if v[0] not in data_stores_ins:
                #     data_stores_ins[v[0]] = {}
                if v[0] == "underground_data":
                    data_stores_ins[k] = Tmp(k, v[1])
                elif v[0] == "outdoor_weather_data":
                    data_stores_ins[k] = Tmp(k, v[1])
                elif v[0] == "occupant_data":
                    data_stores_ins[k] = Tmp(k, v[1])
                else:
                    data_stores_ins[k] = Tmp(k)

        derived_datas = controller.derived_datas
        derived_datas_ins = controller.derived_datas_ins
        for k, v in derived_datas.items():
            if k not in derived_datas_ins:
                Tmp = derived_data_factory(v[0])
                # if v[0] not in derived_datas_ins:
                #     derived_datas_ins[v[0]] = {}
                tmp_ins = []
                for i in v[1]:
                    if i in data_stores_ins:
                        tmp_ins.append(data_stores_ins[i])
                if v[0] == "pmv":
                    derived_datas_ins[k] = Tmp(k, tmp_ins, v[2]["met"], v[2]["clo"], v[2]["v"])
                else:
                    derived_datas_ins[k] = Tmp(k, tmp_ins)
        
        manipulations = controller.manipulations
        manipulations_ins = controller.manipulations_ins
        for k, v in manipulations.items():
            if k not in manipulations_ins:
                Tmp = manipulation_factory(v[0])
                # if v[0] not in manipulations_ins:
                #     self.manipulations_ins[v[0]] = {}
                tmp_ins = []
                for i in v[2]:
                    if isinstance(i, list):
                        if i[0] in data_stores_ins:
                            tmp_ins.append([data_stores_ins[i[0]], i[1]])
                        if i[0] in derived_datas_ins:
                            tmp_ins.append([derived_datas_ins[i[0]], i[1]])
                        if i[0] in manipulations_ins:
                            tmp_ins.append([manipulations_ins[i[0]], i[1]])
                    elif isinstance(i, (float, int)):
                        tmp_ins.append(i)
                manipulations_ins[k] = Tmp(k, tmp_ins, v[1])
        
        rls = controller.rls
        rls_ins = controller.rls_ins
        for k, v in rls.items():
            if k not in rls_ins:
                Tmp = rl_factory(v[0])
                # if v[0] not in rls_ins:
                #     rls_ins[v[0]] = {}
                tmp_ins = []
                for i in v[2]:
                    if i in manipulations_ins:
                        tmp_ins.append(manipulations_ins[i])
                if v[0] == "hvac_rl":
                    rls_ins[k] = Tmp(controller, k, v[1]["en"], tmp_ins, v[1]["en_up"], v[3])
                elif v[0] == "ahu_rl":
                    rls_ins[v[0]][k] = Tmp(controller, k, v[1]["en"], tmp_ins, v[1]["en_up"], v[3], v[4])
                elif v[0] == "pmv_rl":
                    pmv_rl_prop = {
                        "max_iteration": v[3]["max_iteration"],
                        "min_pmv": v[3]["min_pmv"],
                        "max_pmv": v[3]["max_pmv"],
                        "met": v[3]["met"],
                        "clo": v[3]["clo"],
                        "v": v[3]["v"]
                    }
                    rls_ins[k] = Tmp(controller, k, v[1]["en"], tmp_ins, v[1]["en_up"], **pmv_rl_prop)
        
        output_devices = controller.output_devices
        output_devices_ins = controller.output_devices_ins
        for k, v in output_devices.items():
            if k not in output_devices_ins:
                Tmp = output_device_factory(v[0])
                # if v[0] not in output_devices_ins:
                #     output_devices_ins[v[0]] = {}
                tmp_ins = []
                if v[2][0] in rls_ins:
                    tmp_ins = [rls_ins[v[2][0]], v[2][1]]
                output_devices_ins[k] = Tmp(controller, tmp_ins, k, v[1])


def rlaction(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Rlaction
    :rtype: Rlaction
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    kwargs["agent_name"] = config.get("agent_name", "rl_action")
    kwargs["rl_cron"] = config.get("rl_cron", "")
    kwargs["underground_interval"] = config.get("underground_interval", None)
    kwargs["ahu_interval"] = config.get("ahu_interval", None)
    kwargs["firebase_config"] = config.get("firebase_config", [])
    kwargs["in_out_agent"] = config.get("in_out_agent", {})
    
    kwargs["data_stores"] = config.get("data_stores", {})
    kwargs["derived_datas"] = config.get("derived_datas", {})
    kwargs["manipulations"] = config.get("manipulations", {})
    kwargs["rls"] = config.get("rls", {})
    kwargs["output_devices"] = config.get("output_devices", {})

    return Rlaction(**kwargs)


class Rlaction(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super(Rlaction, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)
        self._loattr = set(["agent_name"])  # This will keep the list of attributes in the config
        for k, v in kwargs.items():
            if k not in pskiplist:
                setattr(self, k, v)
                self._loattr.add(k)
        if self.agent_name == "":
            self.agent_name = self.core.identity

        self.queue = Queue()
        self.rl_queue = Queue()

        self.data_stores_ins = {}
        self.derived_datas_ins = {}
        self.manipulations_ins = {}
        self.rls_ins = {}
        self.output_devices_ins = {}

        self.fb_ins_list = {}
        self.firebase = None
        self.fbdb = None

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.current_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.getdata_thread = Thread(target=self._update_datas_thread)
        self.getdata_thread.setDaemon(True)
        self.getdata_thread.start()
        self.getrl_thread = Thread(target=self._rls_thread)
        self.getrl_thread.setDaemon(True)
        self.getrl_thread.start()
        self.getfirebase_thread = None

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """

        _log.debug(f"Configuring Agent ({action}) {config_name} {contents}")
        if config_name == "config":
            for k, v in contents.items():
                self._loattr.add(k)
                setattr(self, k, v)
        else:
            f = getattr(self, "configure_" + config_name, None)
            if f:
                f(action, contents)
            else:
                _log.error(f"Do not know how to handle config {config_name}")

        self._create_subscriptions()

    @property
    def current_config(self) -> Mapping[str, Any]:
        """
        Returns the current configuration.
        """

        r = {}
        for x in self._loattr:
            try:
                r[x] = getattr(self, x)
            except Exception as e:
                _log.debug(f"This should not happen. No attribute for {x}")
        return r

    def save_config(self):
        """
        Save the current configuration
        """

        _log.debug(f"New config updated with {self.current_config}")
        try:
            self.vip.config.set("config", self.current_config)
        except Exception as e:
            _log.debug(f"Error: Something went wrong with setting config store Error was: {e}")

    def update_rls_min_pmv(self, rl_id, value):
        # self.rls[rl_id][4] = value
        self.rls[rl_id][3]["min_pmv"] = value
        self.save_config()

    def update_rls_max_pmv(self, rl_id, value):
        # self.rls[rl_id][5] = value
        self.rls[rl_id][3]["max_pmv"] = value
        self.save_config()

    def update_output_devices_enable(self, output_id, enable):
        self.output_devices[output_id][1] = enable
        self.save_config()

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="sensor",
                                  callback=self._handle_sub_sensor)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="hvac",
                                  callback=self._handle_sub_hvac)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=f"rein/{self.core.identity}",
                                  callback=self._handle_sub_rein)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=f"rein_output/{self.core.identity}",
                                  callback=self._handle_sub_rein_output)
        
        self.rein_global_output_ins = GlobalRLOutput(self, "global_rl_output")
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=f"rein_global_output/{self.core.identity}",
                                  callback=self._handle_sub_rein_global_output)

        self._build_in_out_object()

    def _build_in_out_object(self):
        try:
            self.data_stores_ins = {}
            self.derived_datas_ins = {}
            self.manipulations_ins = {}
            self.rls_ins = {}
            self.output_devices_ins = {}
            
            DefaultBuilder.build(self)
            
            _log.info(f"RLAction data_stores_ins {self.data_stores_ins}")
            _log.info(f"RLAction derived_datas_ins {self.derived_datas_ins}")
            _log.info(f"RLAction manipulations_ins {self.manipulations_ins}")
            _log.info(f"RLAction rls_ins {self.rls_ins}")
            _log.info(f"RLAction output_devices_ins {self.output_devices_ins}")
            
            if self.rl_cron != "":
                _log.info("RLAction create cron schedule")
                self.core.schedule(cron(self.rl_cron), self._rl_cron_schedule)

            if self.underground_interval is not None:
                _log.info("RLAction create underground periodic schedule")
                self.core.schedule(periodic(self.underground_interval), self._period_signal)

            if self.ahu_interval is not None:
                _log.info("RLAction create ahu periodic schedule")
                self.core.schedule(periodic(self.ahu_interval), self._ahu_period_signal)

            if self.firebase_config and self.firebase is None and self.fbdb is None and self.getfirebase_thread is None:
                config = {
                    "apiKey": self.firebase_config[0],
                    "authDomain": self.firebase_config[1],
                    "databaseURL": self.firebase_config[2],
                    "storageBucket": self.firebase_config[3]
                }
                self.firebase = pyrebase.initialize_app(config)
                # auth = firebase.auth()
                self.fbdb = self.firebase.database()

                self.getfirebase_thread = Thread(target=self._firebase_thread)
                self.getfirebase_thread.setDaemon(True)
                self.getfirebase_thread.start()

        except Exception as e:
            _log.error(f"RLAction _build_in_out_object {e}")

    def _handle_sub_sensor(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "event":
                if device_id in self.data_stores_ins:
                    self._add_job({
                        "instance": self.data_stores_ins[device_id],
                        "data": copy.deepcopy(message)
                    })
        except Exception as e:
            _log.error(f"RLAction _handle_sub_sensor {e}")

    def _handle_sub_hvac(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "event":
                if device_id in self.data_stores_ins:
                    self._add_job({
                        "instance": self.data_stores_ins[device_id],
                        "data": copy.deepcopy(message)
                    })
        except Exception as e:
            _log.error(f"RLAction _handle_sub_hvac {e}")

    def _handle_sub_rein(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "command":
                devid = device_id
                v = self.rls_ins
                if devid in v:
                    if "device_id" in message:
                        devid = message["device_id"]
                    if "rl_enable" in message:
                        if message["rl_enable"]:
                            v[devid].enable_rl()
                        else:
                            v[devid].disable_rl()
                    if "rl_update_enable" in message:
                        if message["rl_update_enable"]:
                            v[devid].enable_rl_update()
                        else:
                            v[devid].disable_rl_update()
                    if "rl_min_pmv" in message:
                        f = getattr(v[devid], "update_min_pmv", None)
                        if f is not None:
                            f(message["rl_min_pmv"])
                    if "rl_max_pmv" in message:
                        f = getattr(v[devid], "update_max_pmv", None)
                        if f is not None:
                            f(message["rl_max_pmv"])

                    f = getattr(v[devid], "emit_rl_state", None)
                    if f is not None:
                        f()
        except Exception as e:
            _log.error(f"Rlaction _handle_sub_rein {e}")

    def _handle_sub_rein_output(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "command":
                devid = device_id
                v = self.output_devices_ins
                if devid in v:
                    if "device_id" in message:
                        devid = message["device_id"]
                    if "output_enable" in message:
                        if message["output_enable"]:
                            v[devid].enable_output()
                        else:
                            v[devid].disable_output()
                    
                    f = getattr(v[devid], "emit_rl_output_state", None)
                    if f is not None:
                        f()
        except Exception as e:
            _log.error(f"Rlaction _handle_sub_rein_output {e}")
    
    def _handle_sub_rein_global_output(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "command":
                devid = device_id
                # for k, v in self.output_devices_ins.items():
                #     if devid in v:
                if "device_id" in message:
                    devid = message["device_id"]
                if "global_output_enable" in message:
                    if message["global_output_enable"]:
                        self.rein_global_output_ins.enable_global_output()
                    else:
                        self.rein_global_output_ins.disable_global_output()
                
                f = getattr(self.rein_global_output_ins, "emit_rl_global_output_state", None)
                if f is not None:
                    f()
        except Exception as e:
            _log.error(f"Rlaction _handle_sub_rein_global_output {e}")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        
        self._add_job("Die")
        self._add_rl_job("Die")
        for k, v in self.fb_ins_list.items():
            try:
                v.close()
            except Exception as e:
                _log.error(f"RLAction onstop {e}")

    def _period_signal(self):
        for k, v in self.data_stores_ins.items():
            if isinstance(v, UndergroundData):
                self._add_job({
                    "instance": v,
                    "data": None
                })

    def _ahu_period_signal(self):
        self._process_rl_data_and_action(rl_type=(AHURL,), output_type=(AHUOutput, ITMOAUOutput))

    def _firebase_thread(self):
        for k1, v1 in self.data_stores_ins.items():
            if isinstance(v1, (OutdoorWeatherData, OccupantData)):
                v = v1
                fb_child = None
                path = v.firebase_path.split("/")
                for idx, d in enumerate(path):
                    if idx == 0:
                        fb_child = self.fbdb.child(d)
                    else:
                        fb_child = fb_child.child(d)
                if fb_child is not None:
                    self.fb_ins_list[k] = fb_child.stream(v.data_from_firebase)
                
        for k, v in self.fb_ins_list.items():
            _log.debug(f"RLAction fb_ins_list {k} {v}")

    def _rl_cron_schedule(self):
        self._process_rl_data_and_action(rl_type=(HVACRL, PMVRL), output_type=(HVACOutput,))

    def _process_rl_data_and_action(self, rl_type: list, output_type: list):
        _log.debug(f"Rlaction _process_rl_data_and_action {rl_type} {output_type}")
        acquire_ret = False
        try:
            acquire_ret = bounded_sem.acquire(blocking=True, timeout=5)
        except Exception as e:
            _log.error(f"_process_derived_and_manipulations_data acquire {e}")
        if acquire_ret:
            _log.debug(f"Rlaction _process_rl_data_and_action acquire_ret {acquire_ret}")
            for k, v in self.derived_datas_ins.items():
                self._add_rl_job({
                    "instance": v,
                    "type": "derived_data"
                })
            for k, v in self.manipulations_ins.items(): # pls make sure about ordering. if more than one mani type.
                self._add_rl_job({
                    "instance": v,
                    "type": "manipulation"
                })
            for k, v in self.rls_ins.items():
                if isinstance(v, rl_type):
                    self._add_rl_job({
                        "instance": v,
                        "type": "rl"
                    })
            for k, v in self.output_devices_ins.items():
                if isinstance(v, output_type):
                    self._add_rl_job({
                        "instance": v,
                        "type": "output_device"
                    })

            try:
                bounded_sem.release()
            except ValueError:
                _log.error("_process_derived_and_manipulations_data, the semaphore is being over-released")
            except Exception as e:
                _log.error(f"_process_derived_and_manipulations_data release {e}")

    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"RLAction _add_job {e}")

    def _add_rl_job(self, job):
        try:
            self.rl_queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"RLAction _add_rl_job {e}")

    def _update_datas_thread(self):
        while True:
            job = self.queue.get()
            self.queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            # _log.debug("_update_datas_thread")
            job["instance"].update_data(job["data"])

    def _rls_thread(self):
        while True:
            job = self.rl_queue.get()
            self.rl_queue.task_done()
            if isinstance(job, str):
                if job == "Die":
                    return
            # _log.debug("_rls_thread")
            if job["type"] == "derived_data":
                job["instance"].update_data(None)
            elif job["type"] == "manipulation":
                job["instance"].manipulate()
            elif job["type"] == "rl":
                job["instance"].decide_and_act()
            elif job["type"] == "output_device":
                job["instance"].process_output()

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

    def emit_ac_temperature(self, device_id, temperature):
        if not self.rein_global_output_ins.global_output_enable:
            return
        topic = f'''hvac/{self.in_out_agent["out"]["ac_out_1"]}/{device_id}/command'''
        # message = {"subdevice_idx": 0, "set_temperature": temperature, "source": "rl_action"}
        message = {"subdevice_idx": 0, "set_temperature": temperature, "fan": "high", "source": "rl_action"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"RLAction emit_ac_temperature: {topic}, message : {message}")

    def emit_relay_state(self, device_id, subdevice_idx, state):
        if not self.rein_global_output_ins.global_output_enable:
            return
        topic = f'''switch/{self.in_out_agent["out"]["ahu_out_1"]}/{device_id}/command'''
        message = {"subdevice_idx": subdevice_idx, "state": state}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"RLAction set_relay_state: {topic}, message : {message}")
    
    def emit_itm_oau_state(self, device_id, subdevice_idx, state):
        if not self.rein_global_output_ins.global_output_enable:
            return
        topic = f'''hvac/{self.in_out_agent["out"]["itm_oau_out_1"]}/{device_id}/command'''
        message = {"subdevice_idx": subdevice_idx, "mode": state}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"RLAction set_itm_oau_state: {topic}, message : {message}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(rlaction, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
