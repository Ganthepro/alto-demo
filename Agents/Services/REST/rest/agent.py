"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
import requests

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from altolib import AltoHealth

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def rest(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Rest
    :rtype: Rest
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")
        
    credentials = config.get('credentials', {})
    apis = config.get('apis', {})

    return Rest(credentials, apis, **kwargs)


class Rest(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, credentials: dict, apis: dict, **kwargs):
        super(Rest, self).__init__(**kwargs, enable_web=True)
        _log.debug("vip_identity: " + self.core.identity)

        self.credentials = credentials
        self.apis = apis

        self.default_config = {"credentials": credentials,
                               "apis": apis}

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        # endpoint for the REST API to publish message directly to Message Bus
        # TODO: add authentication for this endpoint
        self.endpoint_device_control = '/devicecontrol/command'
        self.endpoint_agent_config = '/agent_config'
        
        # base endpoint for REST Agent to send request to the backend
        self.site_id = 1

        # define custom heartbeat and health payload
        self.custom_health = AltoHealth(self.core, self.vip.pubsub, heartbeat_period=60, verbose=False)
        
        # set intial status for functions and devices
        self.function_names = []  # no initial `pending` function
        self.custom_health.set_pending_status(names=self.function_names, type_label='function')
        
        # track function status (need to use this approach to pass `self` into decorator function)
        # self._handle_request_device_control_track = AltoHealth.track_status(self.custom_health)(self._handle_request_device_control)
        # self._handle_request_agent_config_track = AltoHealth.track_status(self.custom_health)(self._handle_request_agent_config)
        # # TODO: handle the tracking of RPC functions
        # self.control_result_callback = AltoHealth.track_status(self.custom_health)(self.control_result_callback)
        # self.update_alert_information = AltoHealth.track_status(self.custom_health)(self.update_alert_information)

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
            credentials = config["credentials"]
            apis = config["apis"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.credentials = credentials
        self.apis = apis

        # Register REST endpoint
        self.vip.web.register_endpoint(endpoint=self.endpoint_device_control,
                                       callback=self._handle_request_device_control)
        self.vip.web.register_endpoint(endpoint=self.endpoint_agent_config,
                                       callback=self._handle_request_agent_config)
        
        self._create_subscriptions()

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

    def _get_authentification_token(self):
        """
        Get authentification token from backend through GET request
        """
        # Step 1: Check whether login API is defined
        if "login" not in self.apis:
            _log.warning("No login API defined in config file")
            return None
                
        # Step 2: Login to Alto Backend
        if "username" and "password" not in self.credentials:
            _log.warning("No username or password defined in config file")
            return None
        login_payload = {
            "username": self.credentials['username'],
            "password": self.credentials['password']
        }
        login_headers = {
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", self.apis['login'], headers=login_headers, json=login_payload)

        # Step 3: Check response status and return token if successful
        if response.status_code != 200:
            return None
        else:
            return response.json()['access']

    def _handle_request_device_control(self, env, data):
        """ Sending control command from website (backend) to device-agent
        """
        _log.debug(f"{self.core.identity}: found data({type(data)})={data}")

        # get data from payload
        request_id = data.get('request_id', None)
        if request_id is None:
            return json.dumps({"message": "ERROR: `request_id` is required", "status_code": 400})
        _actions = data.get('actions', [])

        found_error = False
        for _action in _actions:
            try:
                # validate payload keys
                if all(payload_key in _action.keys() for payload_key in ["schema", "agent_id", "device_id"]):
                    # construct topic name
                    _schema = _action.get("schema", "")
                    _agent_id = _action.get("agent_id", "")
                    _device_id = _action.get("device_id", "")
                    if (_schema is None) or (_agent_id is None) or (_device_id is None):
                        return json.dumps({"message": "ERROR: invalid action payload", "status_code": 400})
                    # Case 1: modbus and bacnet controller
                    if _agent_id.startswith('modbus_') or _agent_id.startswith('bacnet_'):
                        _control_name = _agent_id.split('_')[0]
                        topic_name = f"{_control_name}/{_agent_id}/{_device_id}/command"
                    # Case 2: default case
                    else:
                        topic_name = f"{_schema}/{_agent_id}/{_device_id}/command"

                    # construct payload
                    payload = {
                        "request_id": request_id,
                        "callback_function": {
                            "agent_id": str(self.core.identity),
                            "function_name": "control_result_callback"
                        },
                        "action": _action
                    }

                    # publish command to message bus (action-by-action)
                    self.vip.pubsub.publish('pubsub', str(topic_name), message=payload)

                    _log.debug(f"{self.core.identity}: published payload to topic={topic_name}, payload={payload}")
            except Exception as e:
                found_error = True
                _log.error(f"{self.core.identity}: ERROR: {e}")

        if found_error:
            return json.dumps({"message": "ERROR: Failed to send some action commands to device", "status_code": 400})
        return json.dumps({"message": "Successfully send all action commands to device", "status_code": 200})

    def _handle_request_agent_config(self, env, data):
        """ Sending config update to agent
        """
        try:
            if isinstance(data, str):
                data: dict = json.loads(data)
                
            agent_id = data.get('agent_id', None)
            update_type = data.get('update_type', None)
            config_data = data.get('config_data', None)
            if not agent_id or not update_type or not config_data:
                return json.dumps({"message": "missing `agent_id`, `update_type`, or `config_data` data", "status_code": 400})
            
            if update_type == "insert":
                for condition_id, _data in config_data.items():
                    payload = {condition_id: _data}
                    self.vip.pubsub.publish('pubsub', f"config/{agent_id}/{condition_id}/insert", message=payload)
                    return json.dumps({"message": f"success insert: condition_id-{condition_id}", "status_code": 200})

            elif update_type == "update":
                return json.dumps({"message": "NotImplemented Error for `update_type = update`", "status_code": 400})

            elif update_type == "delete":
                for condition_id in config_data.keys():
                    self.vip.pubsub.publish('pubsub', f"config/{agent_id}/{condition_id}/delete", message=dict())
                    return json.dumps({"message": f"success delete: condition_id-{condition_id}", "status_code": 200})

            else:
                return json.dumps({"message": "Invalid `update_type` data", "status_code": 400})

        except Exception as e:
            _log.exception(f"{self.core.identity}: {e}")

    @RPC.export
    def send_restapi_request(self, request_type: str, api_name: str, body: dict, params: dict = None):
        """
        Sending REST API request to backend
        
        Args:
            request_type (str): type of request
            payload (dict): payload data 
            
        Returns:
            response (dict): response data with following structure
            
            response = {}
        
        """
        _log.debug(f"Found request_type={request_type}, api_name={api_name}, payload={body}")
        
        # Step 1: Check if specified API is available
        if api_name not in self.apis.keys():
            _log.error(f"{self.core.identity}: ERROR: API `{api_name}` is not defined")
            return {"message": f"ERROR: API `{api_name}` is not defined", "status_code": 400}
        
        # Step 2: Recieve auth token from login api
        token = self._get_authentification_token()
        
        # Step 3: Parse payload
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        if not isinstance(body, str):
            body = json.dumps(body)
        
        # Step 3: Send request to backend with correct endpoint and request type
        if request_type == 'GET':
            response = requests.get(url=self.apis[api_name], params=params, headers=headers)
        elif request_type == 'POST':
            response = requests.post(url=self.apis[api_name], data=body, headers=headers)
        elif request_type == 'PUT':
            response = requests.put(url=self.apis[api_name], data=body, headers=headers)
        elif request_type == 'DELETE':
            response = requests.delete(url=self.apis[api_name], params=params, headers=headers)
        else:
            _log.error(f"{self.core.identity}: ERROR: Invalid request type")
            return {"message": "ERROR: Invalid request type", "status_code": 400}
        
        return {"message": response.text, "status_code": response.status_code}

    @RPC.export
    def control_result_callback(self, payload: dict):
        """
        1. Send control result to frontend through Websocket Agent (ws endpoint: "/control_response")
        2. Send control result to store in CrateDB through CrateDBAgent (topic: "control_response")
        
        payload (JSON) to Websocket Agent (RPC)
        payload = {
            "request_id": "12345", 
            "action": {
                "device_id": "7DR341478", 
                "agent_id": "bacnet_controller", 
                "subdevice_idx": 0, 
                "subdevice_name": "pump", 
                "schema": "pump", 
                "command": {
                    "mode": "off"
                }
            },
            "result": "string",  # option: ["success", "fail"]
            "unix_timestamp": 1234567890
        }
        
        payload (DICT) to CrateDB Agent
        payload = {
            "request_id": "12345", 
            "device_id": "7DR341478", 
            "agent_id": "bacnet_controller", 
            "subdevice_idx": 0, 
            "subdevice_name": "pump", 
            "schema": "pump", 
            "command": json.dumps({
                "mode": "off"
            }),
            "result": "string",  # option: ["success", "fail"]
            "unix_timestamp": 1234567890
        }
        """

        _log.debug(f"{self.core.identity}: recieved control results payload, payload={json.dumps(payload)}")

        # Step 0: validate payload
        if not isinstance(payload, dict):
            return
        
        if not all([_key in list(payload.keys()) for _key in ['requst_id', 'action', 'result', 'unix_timestamp']]):
            return

        # Step 1: Send control result to frontend through Websocket Agent (ws endpoint: "/control_response")
        self.vip.rpc.call("socket", "send_control_response", payload=payload)
        _log.debug(f"{self.core.identity}: send data to frontend")
        
        # Step 2: Send control result to store in CrateDB through CrateDBAgent (topic: "control_response")
        payload_crate = payload.copy()
        _payload_action_infos = payload_crate.get("action", dict())
        for _key in _payload_action_infos:
            _payload_action_info = _payload_action_infos.get(_key, None)
            payload_crate[str(_key)] = _payload_action_info
        payload_crate.pop("action")
        
        topic_name = "control_response"
        self.vip.pubsub.publish('pubsub', str(topic_name), message=payload_crate)
        _log.debug(f"{self.core.identity}: publish data to CrateDB Agent")

    @RPC.export
    def update_alert_information(self, payload: dict):
        # TODO: Replace this method withe general REST API request method
        
        if "alert" not in self.apis:
            return json.dumps({"message": "alert API is not defined in RESTAgent config", "status_code": 400})
        
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            payload.update({"site": self.site_id})
            
            token = self._get_authentification_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            # send alert request to backend
            if not isinstance(payload, str):
                payload = json.dumps(payload)
            response = requests.request("POST", self.apis.get("alert"), headers=headers, data=payload)
            return json.dumps({"message": response.text, "status_code": response.status_code})
        except Exception as e:
            _log.debug(f"{self.core.identity}: `updated_alert_information`: {e}")
            return json.dumps({"message": e, "status_code": 400})

def main():
    """Main method called to start the agent."""
    utils.vip_main(rest,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
