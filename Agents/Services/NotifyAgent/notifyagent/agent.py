"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import altolib
import requests
import json
import datetime as dt
from threading import Thread
from queue import Queue
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def notify_factory(devtype):
    if devtype == "LineNotify":
        return LineNotify
    if devtype == "LineAndFirebaseNotify":
        return LineAndFirebaseNotify
    if devtype == "AltoBackendNotify":
        return AltoBackendNotify

    raise Exception(f"Unknown device type {devtype}")


class LineNotify(altolib.AltoDevice):
    """
    This is the LineNotify device (object)
    It may not make sense to treated this as Device but we can use this until altolib have a Main App Object
    """

    def __init__(self, controller, mac_addr, nb_subdev, **kwargs):
        super().__init__(controller, mac_addr, nb_subdev)
        self.rest_url_login = kwargs.get("rest_url_login", "https://altohospitaliotbackend.azurewebsites.net")
        self.rest_url = kwargs.get("rest_url", "https://altohospitaliotbackend.azurewebsites.net")
        self.token = "Token"
        self.username = kwargs.get("username", "username_x")
        self.password = kwargs.get("password", "password_x")
        self.go_login_now = False
        self.go_recursive_now = False
        # _log.debug(f'''LineNotify __init__''')

    def _send_request(self, message):
        # POST: NOTIFICATIONS
        # POST https://altohospitaliotbackend.azurewebsites.net/api/v2.0/line_notification

        _log.debug(f"notifyapi send_requet: {message}")
        while not self.go_recursive_now:
            pass
        self.go_recursive_now = False

        try:
            response = requests.post(
                url=self.rest_url,
                params={
                    "message": message["message"],
                },
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8",
                    "Cookie": "ARRAffinity=1cb1584d379d535b4e204d8b026c51e3639a903faa0012321764a71240054f98; ARRAffinitySameSite=1cb1584d379d535b4e204d8b026c51e3639a903faa0012321764a71240054f98",
                },
                data=json.dumps({

                })
            )
            _log.info('notifyapi Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            _log.info('notifyapi Response HTTP Response Body: {content}'.format(
                content=response.content))
            if response.status_code != 200:
                if response.status_code == 401:
                    self.get_token()
                    self._send_request(message)
        except requests.exceptions.RequestException:
            _log.error('notifyapi HTTP Request failed')
            self.get_token()
            self._send_request(message)
    
    def get_token(self):
        while not self.go_login_now:
            pass
        self.go_login_now = False
        
        try:
            response = requests.post(
                url=self.rest_url_login,
                headers={
                    "content-type": "application/json",
                },
                data=json.dumps({
                    "username": self.username,
                    "password": self.password
                })
            )
            _log.info('Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            if response.status_code != 200:
                self.get_token()
            token = json.loads((response.content).decode())
            self.token = token['token']
        except requests.exceptions.RequestException:
            _log.error('HTTP Request failed')
            self.get_token()

    def period_signal(self):
        self.go_login_now = True
        self.go_recursive_now = True

    def send_sample_thread(self, data):
        _log.debug(f'''LineNotify''')
        try:
            self._send_request({
                "message": data["notify_message"]
            })
        except Exception as e:
            _log.error(f"Device LineNotify send_sample_thread problem: {e}")


class LineAndFirebaseNotify(altolib.AltoDevice):
    """
    This is the LineFireNotify device (object)
    It may not make sense to treated this as Device but we can use this until altolib have a Main App Object
    """

    def __init__(self, controller, mac_addr, nb_subdev, **kwargs):
        super().__init__(controller, mac_addr, nb_subdev)
        self.rest_url_login = kwargs.get("rest_url_login", "https://altohospitaliotbackend.azurewebsites.net")
        self.rest_url = kwargs.get("rest_url", "https://altohospitaliotbackend.azurewebsites.net")
        self.token = "Token"
        self.username = kwargs.get("username", "username_x")
        self.password = kwargs.get("password", "password_x")
        self.go_login_now = False
        self.go_recursive_now = False
        # _log.debug(f'''LineNotify __init__''')

    def _send_request(self, message):
        # POST: NOTIFICATIONS
        # POST https://altohospitaliotbackend.azurewebsites.net/api/v2.0/line_notification

        _log.debug(f"notifyapi send_requet: {message}")
        while not self.go_recursive_now:
            pass
        self.go_recursive_now = False

        try:
            response = requests.post(
                url=self.rest_url,
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps(message)
            )
            _log.info('notifyapi Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            _log.info('notifyapi Response HTTP Response Body: {content}'.format(
                content=response.content))
            if response.status_code != 200:
                if response.status_code == 401:
                    self.get_token()
                    self._send_request(message)
        except requests.exceptions.RequestException:
            _log.error('notifyapi HTTP Request failed')
            self.get_token()
            self._send_request(message)
    
    def get_token(self):
        while not self.go_login_now:
            pass
        self.go_login_now = False
        
        try:
            response = requests.post(
                url=self.rest_url_login,
                headers={
                    "content-type": "application/json",
                },
                data=json.dumps({
                    "username": self.username,
                    "password": self.password
                })
            )
            _log.info('Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            if response.status_code != 200:
                self.get_token()
            token = json.loads((response.content).decode())
            self.token = token['token']
        except requests.exceptions.RequestException:
            _log.error('HTTP Request failed')
            self.get_token()

    def period_signal(self):
        self.go_login_now = True
        self.go_recursive_now = True

    def send_sample_thread(self, data):
        # _log.debug(f'''LineAndFirebaseNotify {data}''')
        try:
            data_in = {}
            for k, v in data.items():
                if k not in ["sensor_id", "status", "sensor_type", "subdevice_idx"]:
                    data_in[k] = v
            format_data = {}
            format_data["trigger"] = []
            format_data["trigger"].append({})
            format_data["trigger"][0][data["sensor_id"]] = {}
            if data["status"] == "anomaly":
                format_data["trigger"][0][data["sensor_id"]][data["status"]] = {}
                format_data["trigger"][0][data["sensor_id"]]["normal"] = {}
            else:
                format_data["trigger"][0][data["sensor_id"]][data["status"]] = {}
                format_data["trigger"][0][data["sensor_id"]]["anomaly"] = {}
            format_data["trigger"][0][data["sensor_id"]][data["status"]][data["sensor_type"]] = data_in
            _log.debug(f'''LineAndFirebaseNotify {format_data}''')
            self._send_request(format_data)
        except Exception as e:
            _log.error(f"LineAndFirebaseNotify send_sample_thread problem: {e}")


class AltoBackendNotify(altolib.AltoDevice):
    """
    This is the AltoBackendNotify object, which have a responsibility for sending notify message to alto backend
    """

    def __init__(self, controller, mac_addr, nb_subdev, **kwargs):
        super().__init__(controller, mac_addr, nb_subdev)
        self.rest_url_login = kwargs.get("rest_url_login", "https://authenticationservicebackend.azurewebsites.net/api/v2.0/login")
        self.rest_url = kwargs.get("rest_url", "https://utilservicebackend.azurewebsites.net/api/v3.0/notification")
        self.token = "Token"
        self.username = kwargs.get("username", "username_x")
        self.password = kwargs.get("password", "password_x")
        self.go_login_now = False
        self.go_recursive_now = False
        # _log.debug(f'''LineNotify __init__''')

    def _send_request(self, message):
        # POST: NOTIFICATIONS
        # POST https://altohospitaliotbackend.azurewebsites.net/api/v2.0/line_notification

        _log.debug(f"notifyapi send_requet: {message}")
        while not self.go_recursive_now:
            pass
        self.go_recursive_now = False

        try:
            response = requests.post(
                url=self.rest_url,
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                data=json.dumps(message),
                timeout=45
            )
            _log.info('notifyapi Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            _log.info('notifyapi Response HTTP Response Body: {content}'.format(
                content=response.content))
            if response.status_code != 200:
                if response.status_code == 401:
                    self.get_token()
                    self._send_request(message)
        except requests.exceptions.RequestException:
            _log.error('notifyapi HTTP Request failed')
            self.get_token()
            self._send_request(message)
    
    def get_token(self):
        while not self.go_login_now:
            pass
        self.go_login_now = False
        
        try:
            response = requests.post(
                url=self.rest_url_login,
                headers={
                    "content-type": "application/json",
                },
                data=json.dumps({
                    "username": self.username,
                    "password": self.password
                }),
                timeout=45
            )
            _log.info('Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            if response.status_code != 200:
                self.get_token()
            token = json.loads((response.content).decode())
            self.token = token['token']
        except requests.exceptions.RequestException:
            _log.error('HTTP Request failed')
            self.get_token()

    def period_signal(self):
        self.go_login_now = True
        self.go_recursive_now = True

    def send_sample_thread(self, data):
        # _log.debug(f'''LineAndFirebaseNotify {data}''')
        try:
            data_in = {}
            for k, v in data.items():
                if k not in ["sensor_id", "status", "sensor_type", "subdevice_idx"]:
                    data_in[k] = v
            if "trigger_type" in data_in:
                if data_in["trigger_type"] == "schedule":
                    format_data = {
                        "trigger": {
                            "trigger_type": "schedule",
                            "trigger_time": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
                        },
                        "automation_id": data_in["automation_id"],
                        "condition": {
                            "condition_event": "",
                            "condition_value": ""
                        },
                        "action": {
                            "status": "unknown",
                            "reason": ""
                        }
                    }
                    _log.debug(f'''AltoBackendNotify {format_data}''')
                    self._send_request(format_data)
                elif data_in["trigger_type"] == "device":
                    notification = {}
                    # if "dp_list_str" in data_in and "section_length" in data_in:
                    if "section_length" in data_in:
                        noti_message = ""
                        # dp_list = data_in["dp_list_str"].split(",")
                        sec_len = data_in["section_length"]
                        for i in range(sec_len):
                            sec_msg = data_in["sec_" + str(i)]
                            noti_message += f"{sec_msg}"
                        notification["noti_message"] = noti_message
                    format_data = {
                        "trigger": {
                            "trigger_type": "device",
                            "trigger_device": {
                                f"{data_in['room_name']}": {
                                    f"{data_in['subdevice_name']}": {
                                        f"{data_in['trigger_parameter']}": {
                                            f"{data_in['trigger_symbol']}": data_in["trigger_value"]
                                        }
                                    }
                                }
                            }
                        },
                        "automation_id": data_in["automation_id"],
                        "condition": {
                            "condition_event": "",
                            "condition_value": ""
                        },
                        "action": {
                            "status": "unknown",
                            "reason": ""
                        }
                    }
                    if notification:
                        format_data["notification"] = notification
                    _log.debug(f'''AltoBackendNotify {format_data}''')
                    self._send_request(format_data)
        except Exception as e:
            _log.error(f"AltoBackendNotify send_sample_thread problem: {e}")


def notifyagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Notifyagent
    :rtype: Notifyagent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    for x, y in zip(
        [
            "devices",
            "agent_name",
            "timezones",
            "default_timezone",
            "sampling_rate"
        ],
        [[], "notifyapi", {}, "Asia/Bangkok", 60]
    ):
        kwargs[x] = config.get(x, y)

    return Notifyagent(topic, **kwargs)


class Notifyagent(altolib.AltoBridgeAgent):
    """
    Document agent constructor here.
    """

    def __init__(self, topic, **kwargs):
        super(Notifyagent, self).__init__(topic, **kwargs)
        self.schemas.add("notify")
        self._sampling_rate_cd = 15 # overlide default start polling time
        self.auto_send = False  # set to True if you need set_sensor_data can be auto update after meet condition
        # self.discovery_lock = Lock()
        self.sample_locks = {}
        self.queue = Queue()
        _log.debug("vip_identity: " + self.core.identity)    
        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()

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

    def _build_device(self, **kwargs):
        _log.debug(f'''_build_device {kwargs}''')
        dev_id = kwargs.get("notify_id", "line_001")
        if dev_id not in self.device_list:
            Notify = notify_factory(kwargs.get("type", "LineNotify"))
            newdev = Notify(self, dev_id, nb_subdev=1, **kwargs)
            # _log.debug(f'''_build_device {newdev}''')
            self.register_new_device(newdev)

    def build_devices(self):
        self.device_list = {}
        for idx, conf in enumerate(self.devices):
            self._build_device(**conf)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        super().configure(config_name, action, contents)

        # after config the build_devices will be called
        # you may be need to do something here after config

    def handle_command_notify(self, topic, message):
        """
            Handle the commands meant for the notify schema.
        """
        
        # _log.debug(f'''topic notify {message}''')
        if len(topic) != 2:
            raise AltoSchemaError("Notify command handler cannot parse topic")

        devid, func = topic
        if func == "command":
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev == "all":
                losubdev = range(0, self.device_list[devid].number_subdevices)
            else:
                losubdev = [self.device_list[devid].subdevice_name_to_idx(subdev)]
            try:
                self._add_job({
                    "instance": self.device_list[devid],
                    "data": message
                })
            except Exception as e:
                _log.debug(f"{e.message}, {e.args}")
        else:
            _log.warning(f"Command {func} is not know to the notify schema")
        
    def last_rites(self):
        self._add_job("Die")

    def _add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _period_signal(self):
        for obj in self.device_list.values():
            obj.period_signal()

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
    utils.vip_main(notifyagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass