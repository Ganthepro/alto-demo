"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import time
import copy
import json
from datetime import timedelta
import datetime as dt
from typing import Any, List, Mapping

import gevent

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.scheduling import cron, periodic

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def data_store_factory(dtype):
    if dtype == "tuya_env_data":
        return TuyaEnvData
    if dtype == "tuya_aq_data":
        return TuyaAQData

    raise Exception(f"Unknown data_store {dtype}")


class AltoNotImpl(Exception):
    """
    Exception raised when a method must be overridden but has not been.
    """

    pass


class DataStore:

    def __init__(self, data_id, expiration=1200):
        """
        :param data_id: id of data from device (it can be same as device_id).
        :type data_id: str
        """

        self._data_id = data_id
        self._data = {}
        self._unix_timestamp = None
        self._expiration = expiration
    
    def _update_time(self):
        self._unix_timestamp = time.time()

    @property
    def unix_timestamp(self):
        return self._unix_timestamp

    @property
    def data(self):
        return self._data

    def check_update(self):
        if self._unix_timestamp is None:
            return False
        if (self._unix_timestamp + self._expiration) < time.time():
            return False
        return True

    def update_data(self, data):
        """
        Method that MUST be overridden to update the actual data

        :param data: data from device-agent event.
        :type data: dict
        """

        raise AltoNotImpl("update_data method must be implemented")


class TuyaEnvData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._update_time()
                    _log.debug(f"TuyaEnvData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"TuyaEnvData update_data {self._data_id} {e}")


class TuyaAQData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
            "co2": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._data["co2"] = data["co2"]
                    self._update_time()
                    _log.debug(f"TuyaAQData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"TuyaAQData update_data {self._data_id} {e}")


class DryModeHandle:

    def __init__(self, controller, device_id, sensor):
        self._controller = controller
        self._device_id = device_id
        self._sensor = sensor

        self._data = {
            "mode": None,
        }
        self._count_time = -2
    
    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "ac":
                    self._data["mode"] = data["mode"]
                    # self._update_time()
                    _log.debug(f"DryModeHandle update_data {self._device_id} {self._data} {self._sensor} {self._sensor.data}")

                    if (self._count_time == -2):
                        if (self._data["mode"] == "dry"):
                            gevent.sleep(3.0)
                            self._controller.emit_ac_mode(self._device_id, "cool")
                            self._count_time = -1
                            gevent.sleep(2.0)
                            _log.debug(f"DryModeHandle update_data first time from start dry --> cool {self._device_id}")
                        else:
                            self._count_time = -1
                            _log.debug(f"DryModeHandle update_data first time from start do nothing {self._device_id}")
                        return

                    if self._sensor.check_update():
                        if (self._count_time == -1 and 
                            self._sensor.data["humidity"] >= 65 and 
                            self._sensor.data["temperature"] <= 25 and 
                            self._data["mode"] == "cool"):
                            gevent.sleep(3.0) # for volttron, gevent.sleep is better than sleep
                            self._controller.emit_ac_mode(self._device_id, "dry")
                            self._count_time = 30
                            gevent.sleep(2.0)
                            _log.debug(f"DryModeHandle update_data cool --> dry {self._device_id}")

                        elif self._count_time == 0:
                            if self._data["mode"] == "dry":
                                gevent.sleep(3.0)
                                self._controller.emit_ac_mode(self._device_id, "cool")
                                gevent.sleep(2.0)
                                _log.debug(f"DryModeHandle update_data dry --> cool {self._device_id}")
                            self._count_time = -1
                            _log.debug(f"DryModeHandle update_data dry --> cool _count_time = 0 {self._device_id}")
                        elif (self._count_time == -1 and 
                            self._sensor.data["humidity"] < 65 and 
                            # self._sensor.data["temperature"] > 25 and 
                            self._data["mode"] == "dry"):
                            gevent.sleep(3.0)
                            self._controller.emit_ac_mode(self._device_id, "cool")
                            gevent.sleep(2.0)
                            _log.debug(f"DryModeHandle update_data humidity< dry --> cool {self._device_id}")
                        else:
                            _log.debug(f"DryModeHandle update_data do nothing {self._device_id}")
                    else:
                        if self._count_time == 0:
                            if self._data["mode"] == "dry":
                                gevent.sleep(3.0)
                                self._controller.emit_ac_mode(self._device_id, "cool")
                                gevent.sleep(2.0)
                                _log.debug(f"DryModeHandle update_data (sensor data is not update) dry --> cool {self._device_id}")
                            self._count_time = -1
                            _log.debug(f"DryModeHandle update_data (sensor data is not update) _count_time = 0 {self._device_id}")
                        elif (self._count_time == -1 and 
                            self._data["mode"] == "dry"):
                            gevent.sleep(3.0)
                            self._controller.emit_ac_mode(self._device_id, "cool")
                            gevent.sleep(2.0)
                            _log.debug(f"DryModeHandle update_data (sensor data is not update) _count_time == -1 dry --> cool {self._device_id}")
                        else:
                            _log.debug(f"DryModeHandle update_data (sensor data is not update) do nothing {self._device_id}")

        except Exception as e:
            _log.error(f"DryModeHandle update_data {self._device_id} {e}")
    
    def count_time(self):
        if self._count_time > 0:
            self._count_time -= 1


def drymodeagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Drymodeagent
    :rtype: Drymodeagent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    kwargs["agent_name"] = config.get("agent_name", "dry_mode")
    kwargs["output_agent"] = config.get("output_agent", "itm_fcu")
    kwargs["devices"] = config.get("devices", {})

    return Drymodeagent(**kwargs)


class Drymodeagent(Agent):
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
        super(Drymodeagent, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)
        self._loattr = set(["agent_name"])  # This will keep the list of attributes in the config
        for k, v in kwargs.items():
            if k not in pskiplist:
                setattr(self, k, v)
                self._loattr.add(k)
        if self.agent_name == "":
            self.agent_name = self.core.identity

        self.data_stores_ins = {}
        self.dry_mode_handle_ins = {}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.current_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

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
        
        self._build_object()
    
    def _build_object(self):
        try:
            self.data_stores_ins = {}
            self.dry_mode_handle_ins = {}
            
            for k, v in self.devices.items():
                dev = None
                if v[0] not in self.data_stores_ins:
                    Tmp = data_store_factory(v[1])
                    dev = Tmp(v[0])
                    self.data_stores_ins[v[0]] = dev
                if k not in self.dry_mode_handle_ins:
                    if dev is not None:
                        self.dry_mode_handle_ins[k] = DryModeHandle(self, k, dev)
                    elif dev in self.data_stores_ins:
                        self.dry_mode_handle_ins[k] = DryModeHandle(self, k, self.data_stores_ins[v[0]])
            
            for k, v in self.data_stores_ins.items():
                _log.info(f"Drymodeagent data_stores_ins {k} {v}")
            for k, v in self.dry_mode_handle_ins.items():
                _log.info(f"Drymodeagent dry_mode_handle_ins {k} {v}")

            _log.info("Drymodeagent create dry_mode_handle periodic schedule")
            self.core.schedule(periodic(60), self._periodic_dry_mode_handle)

        except Exception as e:
            _log.error(f"Drymodeagent _build_object {e}")

    def _handle_sub_sensor(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "event":
                if device_id in self.data_stores_ins:
                    self.data_stores_ins[device_id].update_data(message)
        except Exception as e:
            _log.error(f"Drymodeagent _handle_sub_sensor {e}")

    def _handle_sub_hvac(self, peer, sender, bus, topic, headers, message):
        try:
            topic_sec = topic.split("/")
            if len(topic_sec) != 4:
                return
            event_schema, agent_id, device_id, event_type = topic_sec
            if event_type == "event":
                if device_id in self.dry_mode_handle_ins:
                    self.dry_mode_handle_ins[device_id].update_data(message)
        except Exception as e:
            _log.error(f"Drymodeagent _handle_sub_hvac {e}")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    def _periodic_dry_mode_handle(self):
        for k, v in self.dry_mode_handle_ins.items():
            v.count_time()
    
    def emit_ac_mode(self, device_id, mode):
        # if not self.global_output_ins.global_output_enable:
        #     return
        topic = f'''hvac/{self.output_agent}/{device_id}/command'''
        message = {"subdevice_idx": 0, "mode": mode, "source": "trivial"}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"Drymodeagent emit_ac_mode: {topic}, message : {message}")


def main():
    """Main method called to start the agent."""
    utils.vip_main(drymodeagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
