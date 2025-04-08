"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub
import json
from azure.iot.device import IoTHubDeviceClient, Message

import requests
import json

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def publish_factory(pub_type: str):
    if pub_type == "iot_hub":
        return IoTHub
    elif pub_type == "az_func":
        return AzureFunction


class Publisher:

    def publish(self, message: str):
        raise NotImplementedError


class IoTHub(Publisher):

    def __init__(self, connection_string: str):
        self._client = IoTHubDeviceClient.create_from_connection_string(connection_string)

    def publish(self, message: str):
        if not isinstance(message, str):
            message = json.dumps(message)
        try:
            self._client.connect()
            self._client.send_message(message)
            _log.debug(f"Message successfully sent to IoT Hub: {message}")
        except Exception as e:
            _log.error(f"IoTHub publish: Error {e}")


class AzureFunction(Publisher):

    def __init__(self, function_url: str):
        self.function_url = function_url

    def publish(self, message: str):
        try:
            if not isinstance(message, str):
                message = json.dumps(message)
            header = {
                "Content-Type": "application/json",
                "Connection": "close"
            }

            req = requests.session()
            req.keep_alive = False

            response = req.post(self.function_url, data=message, headers=header, timeout=9)
            if response.status_code == 200:
                _log.debug(f"Publish successfully: {response}, message: {message}")
            else:
                _log.warning(f"Publish failed: {response}")
        except Exception as e:
            _log.error(f"Publish Exception: {e}")


def publishIoT(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Publishiot
    :rtype: Publishiot
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    publish_type = config.get("publish_type", {})
    gateway_id = config.get("gateway_id", "")
    type_number = config.get("type_number", "")
    all_data = config.get("all_data", False)
    aggregate_data = config.get("aggregate_data", False)
    devices = config.get("devices", {})

    return Publishiot(publish_type, gateway_id, type_number, devices, all_data, aggregate_data, **kwargs)


class Publishiot(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, publish_type: dict, gateway_id: str, type_number: str, devices: dict, all_data: bool = False, aggregate_data: bool = False, **kwargs):
        super(Publishiot, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.publish_type = publish_type
        self.gateway_id = gateway_id
        self.type_number = type_number
        self.devices = devices
        self.all_data = all_data
        self.aggregate_data = aggregate_data
        self._instance = {}

        self.default_config = {
            "publish_type": publish_type,
            "gateway_id": gateway_id,
            "type_number": type_number,
            "all_data": all_data,
            "aggregate_data": aggregate_data,
            "devices": devices
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

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
            publish_type = config.get("publish_type", None)
            gateway_id = config.get("gateway_id", None)
            type_number = config.get("type_number", "2")
            all_data = config.get("all_data", False)
            aggregate_data = config.get("aggregate_data", False)
            devices = config.get("devices", {})
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.publish_type = publish_type
        self.gateway_id = gateway_id
        self.type_number = type_number
        self.all_data = all_data
        self.aggregate_data = aggregate_data
        self.devices = devices
        self.build_instance()
        self._create_subscriptions()

    def build_instance(self):
        _log.debug(f"Building instance...")
        for pub_type, pub_type_prop in self.publish_type.items():
            if pub_type == "iot_hub":
                self._instance[pub_type] = {}
                for hub_name, conn_str in pub_type_prop.items():
                    self._instance[pub_type][hub_name] = IoTHub(conn_str)
            elif pub_type == "az_func":
                self._instance[pub_type] = {}
                for az_func_name, url in pub_type_prop.items():
                    self._instance[pub_type][az_func_name] = AzureFunction(url)
        _log.debug(f"Build instance Done: {self._instance}")

    def _create_subscriptions(self):
        # Unsubscribe from everything.
        _log.debug("Create Subscriptions...")
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="datalogger",
                                  callback=self._handle_publish)
        _log.debug("Create Subscriptions to topic datalogger Done")

        if self.aggregate_data:
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix="aggregation",
                                    callback=self._handle_aggregate)
            _log.debug("Create Subscriptions to topic aggregation Done")

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        _log.debug(f"handle_publish: {topic}, message: {message}")
        command_to_log = ["query", "response"]
        try:
            topic = topic.split('/')
        except Exception as er:
            _log.debug(f"error topic cannot split(/) {er}")
        if topic[-1] not in command_to_log:
            if not self.all_data:
                if message['device_id'] not in self.devices:
                    return
                if str(message['subdevice_idx']) not in self.devices[message['device_id']]:
                    return
                if message['type'] not in self.devices[message['device_id']][str(message['subdevice_idx'])]:
                    return
            if "type" not in message:
                message["type"] = "unknown" + self.type_number
            else:
                message["type"] = message["type"] + self.type_number
            message["gatewayid"] = self.gateway_id
            flat_message = {}
            for k, v in message.items():
                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        flat_message[k2] = v2
                else:
                    flat_message[k] = v
            flat_message['aggregation_type'] = 'raw'
            self._publish(json.dumps(flat_message))

    def _handle_aggregate(self, peer, sender, bus, topic, headers, message):
        _log.debug(f"handle_aggregate: {topic}, message: {message}")
        if "type" not in message:
            message["type"] = "unknown" + self.type_number
        else:
            message["type"] = message["type"] + self.type_number
        message["gatewayid"] = self.gateway_id
        flat_message = {}
        for k, v in message.items():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    flat_message[k2] = v2
            else:
                flat_message[k] = v
        self._publish(json.dumps(flat_message))

    def _publish(self, message: str):
        for pub_type, pub_type_prop in self._instance.items():
            for instance in pub_type_prop.values():
                instance.publish(message)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(publishIoT,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
