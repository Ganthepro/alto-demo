"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import gevent
from gevent import monkey
monkey.patch_all()

import logging
import sys
import json
import time
import socketio

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import periodic, cron

from altolib import AltoHealth

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def socketagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Socketagent
    :rtype: Socketagent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    rpc_config = config.get('rpc_config', dict())
    socketio_config = config.get('socketio_config', dict())
    associated_devices = config.get('associated_devices', dict())
    endpoint_config = config.get('endpoint_config', dict())

    return SocketAgent(rpc_config, socketio_config, associated_devices, endpoint_config, **kwargs)


class SocketAgent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, rpc_config, socketio_config, associated_devices, endpoint_config, **kwargs):
        super(SocketAgent, self).__init__(**kwargs, enable_web=True)
        _log.debug("vip_identity: " + self.core.identity)

        # Store config for RedisAgent for calling RPC methods
        self.rpc_config = rpc_config
        self.rpc_redis_agent_identity = self.rpc_config.get('rpc_redis_agent_identity', '')
        self.rpc_redis_method_measured = self.rpc_config.get('rpc_redis_method_measured', '')
        self.rpc_redis_method_calculated = self.rpc_config.get('rpc_redis_method_calculated', '')

        # Store config for SocketIO
        self.socketio_config = socketio_config
        self.sio_url = self.socketio_config.get('sio_url', "http://localhost")
        self.sio_port = self.socketio_config.get('sio_port', "4000")
        self.sio_enable = self.socketio_config.get('sio_enable', False)

        # Store config for associated devices and endpoints
        self.associated_devices = associated_devices
        self.endpoint_config = endpoint_config
        self.all_endpoints = list(self.endpoint_config.keys()) + ['/']

        # Construct a dict that maps each endpoint to its list of Volttron topics to listen to
        self.endpoint_and_topics = dict()
        self._init_endpoint_to_topic_mappings()

        self.default_config = {
            "rpc_config": self.rpc_config,
            "rpc_redis_agent_identity": self.rpc_redis_agent_identity,
            "rpc_redis_method_measured": self.rpc_redis_method_measured,
            "rpc_redis_method_calculated": self.rpc_redis_method_calculated,
            "socketio_config": self.socketio_config,
            "sio_url": self.sio_url,
            "sio_port": self.sio_port,
            "sio_enable": self.sio_enable,
            "associated_devices": self.associated_devices,
            "endpoint_config": self.endpoint_config
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        # define custom heartbeat and health payload
        self.custom_health = AltoHealth(self.core, self.vip.pubsub, heartbeat_period=60, verbose=False)

        # set intial status for functions and devices
        self.function_names = [
            "_ws_opened",
            "_send_realtime_data",
            # "send_control_response",
            # "send_alert"
        ]
        self.custom_health.set_pending_status(names=self.function_names, type_label='function')

        # track function status (need to use this approach to pass `self` into decorator function)
        self._ws_opened_track = AltoHealth.track_status(self.custom_health)(self._ws_opened)
        self._send_realtime_data_track = AltoHealth.track_status(self.custom_health)(self._send_realtime_data)
        # TODO: handle the tracking of RPC functions
        # self.send_control_response = AltoHealth.track_status(self.custom_health)(self.send_control_response)
        # self.send_alert = AltoHealth.track_status(self.custom_health)(self.send_alert)

        self.sio = socketio.Client(reconnection=True)

        @self.sio.on('connect', namespace='/')
        def on_connect():
            _log.info(f"{self.core.identity}: socketio connected to the / namespace")

    def connect_socketio(self):
        """ Connect to SocketIO server according to the config file """
        if not self.sio.connected:
            self.sio.connect(f'{self.sio_url}:{self.sio_port}', namespaces=self.all_endpoints)
        _log.info(f"{self.core.identity}: connect to socketio, status={self.sio.connected}")

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
            rpc_config = config.get('rpc_config', dict())
            socketio_config = config.get('socketio_config', dict())
            associated_devices = config.get('associated_devices', dict())
            endpoint_config = config.get('endpoint_config', dict())
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        # Store config for RedisAgent for calling RPC methods
        self.rpc_config = rpc_config
        self.rpc_redis_agent_identity = self.rpc_config.get('rpc_redis_agent_identity', '')
        self.rpc_redis_method_measured = self.rpc_config.get('rpc_redis_method_measured', '')
        self.rpc_redis_method_calculated = self.rpc_config.get('rpc_redis_method_calculated', '')

        # Store config for SocketIO
        self.socketio_config = socketio_config
        self.sio_url = self.socketio_config.get('sio_url', "http://localhost")
        self.sio_port = self.socketio_config.get('sio_port', "4000")
        self.sio_enable = self.socketio_config.get('sio_enable', False)

        # Store config for associated devices and endpoints
        self.associated_devices = associated_devices
        self.endpoint_config = endpoint_config
        self.all_endpoints = list(self.endpoint_config.keys()) + ['/']

        # Construct a dict that maps each endpoint to its list of Volttron topics to listen to
        self.endpoint_and_topics = dict()
        self._init_endpoint_to_topic_mappings()

        # Re-register Websocket endpoints
        # for endpoint in self.endpoint_and_topics.keys():
        #     self.vip.web.unregister_websocket(endpoint=endpoint)
        #     time.sleep(0.1)
        #     self.vip.web.register_websocket(
        #         endpoint=endpoint,
        #         opened=self._ws_opened_track,
        #         closed=self._ws_closed,
        #         received=None
        #     )

        # Set up periodic checking on heartbeat status
        # self.core.schedule(periodic(30), self.check_ws_status)

        # Set up periodic checking on health status
        self._create_subscriptions()

        # Connect to SocketIO
        self.connect_socketio()

    def _init_endpoint_to_topic_mappings(self):
        """ Initialize the mapping between endpoint and topic names.

        This method is a helper method that use the `endpoint_config` and `associated_devices` dict to construct the
        mapping between WS endpoint and Volttron topics to listen to.

        The `endpoint_config` is a 2-level dictionary that contains the mapping between WS endpoint and list of device
        directory to be mapped from the `associated_devices` dict. Should be in the format of:

        endpoint_config = {                                    #     ex. endpoint_config = {
            <WS_ENDPOINT>: {                                   #         /data/overview_plant/calculated: {
                "<schema>/<agent_id>/<subdir_1>/<subdir_2>",   #             "sensor/bacnet_controller/pump",
                "<schema>/<agent_id>/<subdir_1>"               #             "sensor/modbus_vsd_pump"
                "<schema>/<agent_id>"                          #         }
            }                                                  #     }
        }                                                      #

        The `associated_devices` is a multi-level dictionary that contains AT LEAST 2 levels.
        - 1st-Level Key: Schema name (e.g. "sensor" or "calculated")
        - 2nd-Level Key: Agent name (e.g. "bacnet_controller" or "general_calculator")
        - Other-Level Key: Used to divide the list of devices into subdirectories providing conveniece for the user to
        separately send the data of groups of devices to different WS endpoints.
        - Last-Level Value: List of device_id (e.g. ["chiller1", "chiller2", "chiller3"])

        associated_devices = {                                  #   ex. associated_devices = {
            "<schema>": {                                       #       "sensor": {
                "<agent_id>": {                                 #           "bacnet_controller": {
                    "<subdir_1>": [device_id_list_1],           #               "pump": ["pump1", "pump2", "pump3"],
                },                                              #           },
                "<agent_id>": [device_id_list_2]                #           "modbus_vsd_pump": ["vsd_pump1", ...]
            },                                                  #       },
        }                                                       #


        From the example above, the endpoint "/data/overview_plant/calculated" will be mapped to the following topics:
        - "sensor/bacnet_controller/pump1/event"
        - "sensor/bacnet_controller/pump2/event"
        - "sensor/bacnet_controller/pump3/event"
        - "sensor/modbus_vsd_pump/vsd_pump1/event"
        - ...

        """
        self.endpoint_and_topics = dict()
        for endpoint, device_dir_list in self.endpoint_config.items():

            self.endpoint_and_topics[endpoint] = list()

            for device_dir in device_dir_list:

                paths = device_dir.split('/')

                if len(paths) < 2:
                    _log.error("Invalid device directory: {}".format(device_dir))
                    continue
                else:
                    schema = paths[0]
                    agent_id = paths[1]

                    subdir = self.associated_devices.get(schema, dict()).get(agent_id, dict())

                    for path in paths[2:]:
                        subdir = subdir.get(path, dict())

                    for device_id in subdir:
                        topic = f"{schema}/{agent_id}/{device_id}/event"
                        self.endpoint_and_topics[endpoint].append(topic)

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _send_realtime_data_track callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for topic_list in self.endpoint_and_topics.values():
            for topic in topic_list:
                _log.info(f"{self.core.identity}: subscribe to {topic}")
                self.vip.pubsub.subscribe(peer='pubsub', prefix=topic, callback=self._send_realtime_data_track)

    def check_ws_status(self):
        """ Check the status of websocket endpoints, if there is any endpoint is not registered, register them"""
        _registered_ws = list(self.vip.web._ws_endpoint.keys())
        for endpoint in self.endpoint_config.keys():
            if endpoint not in _registered_ws:
                try:
                    self.vip.web.unregister_websocket(endpoint=endpoint)
                    time.sleep(0.5)
                    self.vip.web.register_websocket(
                        endpoint=endpoint,
                        opened=self._ws_opened,
                        closed=self._ws_closed,
                        received=None
                    )
                    _log.info(f"{self.core.identity}: re-register-{endpoint}")
                except Exception as e:
                    _log.exception(f"{self.core.identity}: re-register-{endpoint}, error-{e}")

    def _ws_opened(self, fromip, endpoint):
        """
        Callback function for websocket opened event which will send initial latest data to the Frontend through Websocket

        Steps
        1. get endpoint key from topic name
        2. get all `device_id` related to the `endpoint`
        3. query data from Redis database and construct payload
        4. check missing `device_id` and query data from CrateDB database
        5. send payload to WS endpoint as JSON format
        """

        _log.debug(f"{self.core.identity}: opened ip: {fromip}, endpoint: {endpoint}")

        if len(endpoint.split('/')) <=2:
            return

        # Step 1: get endpoint key from topic name
        endpoint_key = endpoint.split('/')[2]

        # Step 2: get all `device_id` related to the `endpoint`
        # get all path for `device_id` in `associated_devices` dict
        _all_paths = self.endpoint_details[endpoint_key]
        # get all `device_id`
        device_ids = list()
        for _all_path in _all_paths:
            # get all device_id in the specified `associated_devices` dict's path
            _paths = _all_path.split('/')
            _device_ids = list()
            if len(_paths) > 0:
                _device_ids = self.associated_devices.get(_paths[0])
                for _path in _paths[1:]:
                    _device_ids = _device_ids.get(_path)
                device_ids.extend(_device_ids)

        # Step 3: query data from Redis database and construct payload
        payload = ""
        if endpoint_key == 'overview_plant':
            payload: str = self.vip.rpc.call(self.rpc_redis_agent_identity, self.rpc_redis_method_measured, device_ids=device_ids).get(timeout=10)
        elif endpoint_key == 'overview_btu':
            payload: str = self.vip.rpc.call(self.rpc_redis_agent_identity, self.rpc_redis_method_measured, device_ids=device_ids).get(timeout=10)
        elif endpoint_key == 'plants':
            datapoints = ['calculated_energy_rate', 'calculated_part_load_percentage']
            payload: str = self.vip.rpc.call(self.rpc_redis_agent_identity, self.rpc_redis_method_calculated, device_ids=device_ids, datapoints=datapoints).get(timeout=10)
        elif endpoint_key == 'kpis':
            datapoints = ['calculated_efficiency', 'calculated_energy_rate', 'calculated_power', 'calculated_flow_rate', 'calculated_flow_efficiency']
            payload: str = self.vip.rpc.call(self.rpc_redis_agent_identity, self.rpc_redis_method_calculated, device_ids=device_ids, datapoints=datapoints).get(timeout=10)
        elif endpoint_key == 'outdoorweather':
            payload: str = self.vip.rpc.call(self.rpc_redis_agent_identity, self.rpc_redis_method_measured, device_ids=device_ids).get(timeout=10)
        elif endpoint_key == 'power_meter':
            payload: str = self.vip.rpc.call(self.rpc_redis_agent_identity, self.rpc_redis_method_measured, device_ids=device_ids).get(timeout=10)

        _log_redis_message = f"{self.core.identity}: (on-connect) success request redis data, endpoint-`{endpoint_key}`"
        if endpoint_key == 'kpis':
            _log_redis_message = f"{_log_redis_message}, payload-{payload}"
        _log.info(_log_redis_message)

        if payload == "":
            _log.info(f"{self.core.identity}: can't request redis data-{endpoint_key}")
            return

        # Step 4: check missing data and query data from CrateDB database
        _payload: dict = json.loads(payload)
        missing_device_ids = [device_id for device_id in device_ids if device_id not in _payload.keys()]
        # TODO: get data from CrateDB database and update to `payload`

        # Step 5: send payload to WS endpoint as JSON format
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        try:
            self.vip.web.send(endpoint, payload)
        except Exception as e:
            _log.exception(f"{self.core.identity}: {e}")
            self.vip.web.unregister_websocket(endpoint=endpoint)
            self.vip.web.register_websocket(
                endpoint=endpoint,
                opened=self._ws_opened,
                closed=self._ws_closed,
                received=None
            )

    def _ws_closed(self, endpoint):
        """ Callback function for websocket closed event """
        _log.debug(f"{self.core.identity}: closed endpoint: {endpoint}")

    def construct_ws_message(self, topic: str, message: dict, target_ws_endpoint: str):
        """ Preprocess message received from Volttron platform to message to be sent to Frontend

        Args:
            topic (str): topic of the message
            message (dict): message received from Volttron platform
            target_ws_endpoint (str): target websocket endpoint

        Returns:
            dict: message to be sent to Frontend through SocketIO or Websocket

        """
        _common_keys = ["device_id", "subdevice_idx", "subdevice_name", "type", "timestamp", "unix_timestamp", "location"]
        message = message.copy()

        # Case 1: The message is RAW DATA (Topic: sensor/*)
        if topic.startswith("sensor/"):
            # Step 1.1: List all non-common keys
            non_common_keys = [k for k in message.keys() if k not in _common_keys]
            # Step 1.2: Construct payload
            payload = dict()
            _subdevice_name = message.get('subdevice_name', None)
            for key in non_common_keys:
                # handle `nan` data in power meter
                if topic.startswith("sensor/modbus_power_meter") and _subdevice_name == "total" and key in ["power_factor"]:
                    message[key] = str(message[key])

                payload.update({key: message[key]})
                message.pop(key, None)
            message["payload"] = payload

        # Case 2: The message is CALCULATED DATA (Topic: calculated/*)
        elif topic.startswith("calculated/"):
            # Step 2.1: List all datatypes and datapoints for each endpoint
            # selected_datapoints = list()
            # if target_ws_endpoint in ['/data/plants/calculated', '/dataPlantsCalculated']:
            #     selected_datapoints = ['calculated_energy_rate', 'calculated_part_load_percentage']
            # elif target_ws_endpoint in ['/data/kpis/calculated', '/kpis', '/dataKpisCalculated']:
            #     selected_datapoints = ['calculated_efficiency', 'calculated_energy_rate', 'calculated_power',
            #                            'calculated_flow_rate', 'calculated_flow_efficiency']
            # elif target_ws_endpoint == '/dataOutdoorweatherMeasured':
            #     selected_datapoints = ['calculated_wetbulb_temperature']

            # _type = message.get("type")
            # if _type in selected_datapoints:

            # Step 2.2: List all non-common keys
            non_common_keys = [k for k in message.keys() if k not in _common_keys]
            # Step 2.3: Construct message
            payload = dict()
            for key in non_common_keys:
                payload.update({key: message[key]})
                message.pop(key, None)
            message["payload"] = payload

            # else:
            #     return dict()

        else:
            _log.warning(f'{self.core.identity}: Topic - "{topic}" is not currently supported in this version')
            return dict()

        return message

    def _send_realtime_data(self, peer, sender, bus, topic, headers, message):
        """
        Callback function to send latest updated data to Frontend through SocketIO or Websocket
        """
        _common_keys = ["device_id", "subdevice_idx", "subdevice_name", "type", "timestamp", "unix_timestamp", "location"]

        # Step 1: Iterate through all available websocket endpoints
        for endpoint, topic_list in self.endpoint_and_topics.items():
            if topic not in topic_list:
                continue

            # Step 2: Construct message to be sent to Frontend
            ws_message = self.construct_ws_message(topic, message, endpoint)
            if not ws_message:
                continue

            # Step 3: Send the message to the target endpoint with SocketIO
            try:
                if not self.sio.connected:
                    _log.info(f"{self.core.identity}: socketio not connected, try to connect")
                    self.connect_socketio()
                self.sio.emit('volttron_event', json.dumps(ws_message), namespace=endpoint)
                _log.debug(f"{self.core.identity}: successfully sent data to socketio (endpoint: {endpoint})")
                continue
            except Exception as e:
                _log.exception(f"{self.core.identity}: can't send data to socketio (endpoint: {endpoint}) due to error {e}")

            # Step 4: Send the message to the target endpoint with Websocket in case of SocketIO failure
            # try:
            #     _log.info(f"{self.core.identity}: try to send data to websocket (endpoint: {endpoint}) instead")
            #     self.vip.web.send(endpoint, json.dumps(ws_message))
            # except Exception as e:
            #     _log.exception(f"{self.core.identity}: failed to send data to websocket (endpoint: {endpoint}) due to error {e}")
            #     self.vip.web.unregister_websocket(endpoint=endpoint)
            #     time.sleep(0.5)
            #     self.vip.web.register_websocket(
            #         endpoint=endpoint,
            #         opened=self._ws_opened,
            #         closed=self._ws_closed,
            #         received=None
            #     )

    @RPC.export
    def send_control_response(self, payload: dict):
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        try:
            self.vip.web.send('/control_response', payload)
        except Exception as e:
            _log.exception(f"{self.core.identity}: {e}")
            self.vip.web.unregister_websocket(endpoint='/control_response')
            time.sleep(0.5)
            self.vip.web.register_websocket(
                endpoint='/control_response',
                opened=self._ws_opened,
                closed=self._ws_closed,
                received=None
            )

    @RPC.export
    def send_alert(self, payload: dict):
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        try:
            self.vip.web.send('/alert', payload)
        except Exception as e:
            _log.exception(f"{self.core.identity}: {e}")
            self.vip.web.unregister_websocket(endpoint='/alert')
            time.sleep(0.5)
            self.vip.web.register_websocket(
                endpoint='/alert',
                opened=self._ws_opened,
                closed=self._ws_closed,
                received=None
            )

    @RPC.export
    def send_custom_message(self, endpoint: str, payload: dict):
        """
        RPC method for sending custom message to the Frontend through SocketIO

        Args:
            endpoint (str): endpoint of the SocketIO to send the payload to
            payload (dict): payload to be sent to the Frontend

        """
        # Step 1: If the endpoint is not registered, register it and reconnect the SIO
        if endpoint not in self.all_endpoints:
            self.sio.disconnect()
            self.all_endpoints.append(endpoint)
            gevent.sleep(1)
            self.connect_socketio()

        # Step 2: Send the payload to the Frontend
        try:
            if not self.sio.connected:
                _log.info(f"{self.core.identity}: socketio not connected, try to connect")
                self.connect_socketio()
            self.sio.emit('volttron_event', json.dumps(payload), namespace=endpoint)
            _log.info(f"{self.core.identity}: successfully RPC sent custom data to socketio (endpoint: {endpoint})")
        except Exception as e:
            _log.exception(f"{self.core.identity}: can't RPC send data to socketio (endpoint: {endpoint}) due to error {e}")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        self.sio.disconnect()


def main():
    """Main method called to start the agent."""
    utils.vip_main(socketagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
