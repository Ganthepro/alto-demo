"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from threading import Thread
from queue import Queue
import datetime as dt
import pytz

import psycopg2
from psycopg2 import Error

import requests
import json

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.scheduling import cron

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class PostgresManage:

    def __init__(self, user, password, host, port, database):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self.connection = self.initiate_connection()

    def initiate_connection(self):
        try:
            _log.info("Connecting to PostgresSQL ...")
            connection = psycopg2.connect(user=self.user,
                                      password=self.password,
                                      host=self.host,
                                      port=self.port,
                                      database=self.database)
            _log.info("Successfully connected to PostgresSQL")
            return connection

        except (Exception, Error) as error:
            _log.info("Error while connecting to PostgreSQL", error)
            return None

    def execute_query(self, query):
        if self.connection is not None:
            cursor = self.connection.cursor()
            cursor.execute(query)
            records = cursor.fetchall()
            records_dict = self.make_dict_record(cursor, records)
            return records_dict
        else:
            return None

    def make_dict_record(self, cursor, records):
        try:
            column_names = [description.name for description in list(cursor.description)]

            records_dict = []
            for record in records:
                row_dict = {}
                for i, col in enumerate(column_names):
                    row_dict[col] = record[i]
                records_dict.append(row_dict)

            return records_dict

        except (Exception, Error) as error:
            _log.error("Error while connecting to PostgreSQL", error)
            return None


def custom_action_factory(catype):
    if catype == "reserve_batt_expire": # battery_reserve
        return ReserveBatteryExpire
    if catype == "reserve_batt_notify":
        return ReserveBatteryNotify

    raise Exception(f"Unknown custom-action type {catype}")


class ReserveBatteryNotify:

    def __init__(self, controller, rider_id, ca):
        # _log.debug(f'''ReserveBatteryNotify {ca}''')
        self.controller = controller
        self.rider_id = rider_id
        self.cron_time = ca.get("cron", None) # "0 1 * * *"
        self.reserve_battery_at = ca.get("reserve_battery_at", None)
        self.reserve_notify_time = ca.get("reserve_notify_time", 5)
        self.reserve_battery_id = ca.get("reserve_battery_id", "NONE")
        self.transaction_id = ca.get("transaction_id", "NONE")
        self.gateway_name = ca.get("gateway_name", "NONE")
        self.altobackend = ca.get("altobackend", {})

        self.token = "Token"
        self.go_login_now = False
        self.go_recursive_now = False

        if self.cron_time is None:
            if self.reserve_battery_at is not None:
                tt = self.reserve_battery_at.replace('+07:00','+0700') # for python 3.6.9
                d1 = dt.datetime.strptime(tt, "%Y-%m-%d %H:%M:%S.%f%z")
                d2 = d1.astimezone(pytz.utc)
                d3 = d2 + dt.timedelta(minutes=self.reserve_notify_time)
                _log.debug(f'''ReserveBatteryNotify {d3}''')
                self.cron_time = f'''{d3.minute} {d3.hour} * * *'''
                self.schedule = self.controller.core.schedule(cron(self.cron_time), self.reserve_notify)
        else:
            self.schedule = self.controller.core.schedule(cron(self.cron_time), self.reserve_notify)

    def cancel_schedule(self):
        self.schedule.cancel()

    def reserve_notify(self):
        _log.debug(f'''ReserveBatteryNotify {self.rider_id}''')
        row = self.controller.get_one_row_psql(self.rider_id)
        reserve_swapping = row.get("reserve_swapping", False)
        if reserve_swapping:
            _log.debug(f'''ReserveBatteryNotify reserve_swapping {reserve_swapping}''')
            self.controller.add_job({
                "instance": self,
                "data": {
                    "rider_id": self.rider_id,
                    # "reserve_battery_id": self.reserve_battery_id,
                    # "transaction_id": self.transaction_id
                    "gateway_name": self.gateway_name,
                    "type": "warn_reserve_battery"
                }
            })
        else:
            self.controller.add_des({
                "instance_typ": "reserve_batt_notify",
                "ca_id": self.rider_id
            })

    def _send_request(self, message):
        # POST: NOTIFICATIONS
        # POST https://altohospitaliotbackend.azurewebsites.net/api/v2.0/line_notification

        _log.debug(f"notifyapi send_requet: {message}")
        while not self.go_recursive_now:
            pass
        self.go_recursive_now = False

        try:
            response = requests.post(
                url=self.altobackend["rest_url_notify"],
                # params={
                #     "message": message["message"],
                # },
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
                self.get_token()
                self._send_request(message)
            else:
                self.controller.add_des({
                    "instance_typ": "reserve_batt_notify",
                    "ca_id": self.rider_id
                })
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
                url=self.altobackend["rest_url_login"],
                headers={
                    "content-type": "application/json",
                },
                data=json.dumps({
                    "username": self.altobackend["username"],
                    "password": self.altobackend["password"]
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
        _log.debug(f'''ReserveBatteryNotify send_sample_thread {data}''')
        self._send_request(data)


class ReserveBatteryExpire:

    def __init__(self, controller, rider_id, ca):
        # _log.debug(f'''ReserveBatteryExpire {ca}''')
        self.controller = controller
        self.rider_id = rider_id
        self.cron_time = ca.get("cron", None) # "0 1 * * *"
        self.reserve_battery_at = ca.get("reserve_battery_at", None)
        self.reserve_expire_time = ca.get("reserve_expire_time", 5)
        self.reserve_battery_id = ca.get("reserve_battery_id", "NONE")
        self.transaction_id = ca.get("transaction_id", "NONE")
        self.gateway_name = ca.get("gateway_name", "NONE")
        self.altobackend = ca.get("altobackend", {})

        self.token = "Token"
        self.go_login_now = False
        self.go_recursive_now = False

        if self.cron_time is None:
            if self.reserve_battery_at is not None:
                tt = self.reserve_battery_at.replace('+07:00','+0700') # for python 3.6.9
                d1 = dt.datetime.strptime(tt, "%Y-%m-%d %H:%M:%S.%f%z")
                d2 = d1.astimezone(pytz.utc)
                d3 = d2 + dt.timedelta(minutes=self.reserve_expire_time)
                _log.debug(f'''ReserveBatteryExpire {d3}''')
                self.cron_time = f'''{d3.minute} {d3.hour} * * *'''
                self.schedule = self.controller.core.schedule(cron(self.cron_time), self.reserve_expire)
        else:
            self.schedule = self.controller.core.schedule(cron(self.cron_time), self.reserve_expire)

    def cancel_schedule(self):
        self.schedule.cancel()

    def reserve_expire(self):
        _log.debug(f'''ReserveBatteryExpire {self.rider_id}''')
        row = self.controller.get_one_row_psql(self.rider_id)
        reserve_swapping = row.get("reserve_swapping", False)
        if reserve_swapping:
            _log.debug(f'''ReserveBatteryExpire reserve_swapping {reserve_swapping}''')
            self.controller.add_job({
                "instance": self,
                "data": {
                    "rider_id": self.rider_id,
                    # "reserve_battery_id": self.reserve_battery_id,
                    # "transaction_id": self.transaction_id
                    "gateway_name": self.gateway_name,
                    "type": "cancel_reserve_battery"
                }
            })
        else:
            self.controller.add_des({
                "instance_typ": "reserve_batt_expire",
                "ca_id": self.rider_id
            })
    
    def _send_request(self, message):
        # POST: NOTIFICATIONS
        # POST https://altohospitaliotbackend.azurewebsites.net/api/v2.0/line_notification

        _log.debug(f"notifyapi send_requet: {message}")
        while not self.go_recursive_now:
            pass
        self.go_recursive_now = False
        # _log.debug(f"notifyapi send_requet go")

        try:
            response = requests.post(
                url=self.altobackend["rest_url_expire"],
                # params={
                #     "message": message["message"],
                # },
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                data=json.dumps(message)
            )
            _log.info('notifyapi Response HTTP Status Code: {status_code}'.format(
                status_code=response.status_code))
            # _log.info('notifyapi Response HTTP Response Body: {content}'.format(
            #     content=response.content))
            if response.status_code != 200:
                self.get_token()
                self._send_request(message)
            else:
                self.controller.add_des({
                    "instance_typ": "reserve_batt_expire",
                    "ca_id": self.rider_id
                })
        except requests.exceptions.RequestException:
            _log.error('notifyapi HTTP Request failed')
            self.get_token()
            self._send_request(message)
    
    def get_token(self):
        # _log.debug(f'''notifyapi get_token: {self.altobackend["rest_url_login"]} {self.altobackend["username"]} {self.altobackend["password"]}''')
        while not self.go_login_now:
            pass
        self.go_login_now = False
        
        try:
            response = requests.post(
                url=self.altobackend["rest_url_login"],
                headers={
                    "content-type": "application/json",
                },
                data=json.dumps({
                    "username": self.altobackend["username"],
                    "password": self.altobackend["password"]
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
        _log.debug(f'''ReserveBatteryExpire send_sample_thread {data}''')
        self._send_request(data)


def customaction(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Customaction
    :rtype: Customaction
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get("agent_name", "custom_action")
    custom_actions = config.get("custom_actions", [])
    kwargs["reserve_notify_time"] = config.get("reserve_notify_time", 2)
    kwargs["reserve_expire_time"] = config.get("reserve_expire_time", 4)
    kwargs["altobackend"] = config.get("altobackend", {})

    kwargs["postgres_user"] = config.get("postgres_user", "altotech@altopostgres")
    kwargs["postgres_password"] = config.get("postgres_password", "Magicalmint636")
    kwargs["postgres_host"] = config.get("postgres_host", "altopostgres.postgres.database.azure.com")
    kwargs["postgres_port"] = config.get("postgres_port", "5432")
    kwargs["postgres_database"] = config.get("postgres_database", "postgres")

    return Customaction(agent_name, custom_actions, **kwargs)


class Customaction(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, custom_actions, **kwargs):
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super(Customaction, self).__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        _log.debug("vip_identity: " + self.core.identity)

        self.queue = Queue()
        self.des_queue = Queue()

        self.ca_list = {}
        self.reserve_batt_expire_list = {}
        self.reserve_batt_notify_list = {}
        self.psql = None

        self.agent_name = agent_name
        self.custom_actions = custom_actions
        self.reserve_notify_time = kwargs["reserve_notify_time"]
        self.reserve_expire_time = kwargs["reserve_expire_time"]
        self.altobackend = kwargs["altobackend"]

        self.postgres_user = kwargs["postgres_user"]
        self.postgres_password = kwargs["postgres_password"]
        self.postgres_host = kwargs["postgres_host"]
        self.postgres_port = kwargs["postgres_port"]
        self.postgres_database = kwargs["postgres_database"]

        self.default_config = {
            "agent_name": self.agent_name,
            "custom_actions": self.custom_actions,
            "reserve_notify_time": self.reserve_notify_time,
            "reserve_expire_time": self.reserve_expire_time,
            "altobackend": self.altobackend,
            "postgres_user": self.postgres_user,
            "postgres_password": self.postgres_password,
            "postgres_host": self.postgres_host,
            "postgres_port": self.postgres_port,
            "postgres_database": self.postgres_database
        }

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.getsample_thread = Thread(target=self._send_samples_thread)
        self.getsample_thread.setDaemon(True)
        self.getsample_thread.start()
        self.getdes_thread = Thread(target=self._destroyer_thread)
        self.getdes_thread.setDaemon(True)
        self.getdes_thread.start()

    def get_one_row_psql(self, rider_id):
        _log.debug(f'''Customaction psql {self.psql}''')
        if self.psql is not None:
            # _log.debug(f'''Customaction psql query''')
            query = f'''SELECT * FROM ev_relations WHERE rider_id={rider_id};'''
            records = self.psql.execute_query(query)
            for record in records:
                # _log.debug(f'''Customaction {record}''')
                return record
        return {}

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
            custom_actions = config["custom_actions"]
            reserve_notify_time = config["reserve_notify_time"]
            reserve_expire_time = config["reserve_expire_time"]
            altobackend = config["altobackend"]
            postgres_user = config["postgres_user"]
            postgres_password = config["postgres_password"]
            postgres_host = config["postgres_host"]
            postgres_port = config["postgres_port"]
            postgres_database = config["postgres_database"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.custom_actions = custom_actions
        self.reserve_notify_time = reserve_notify_time
        self.reserve_expire_time = reserve_expire_time
        self.altobackend = altobackend

        if (
            postgres_user != self.postgres_user or 
            postgres_password != self.postgres_password or 
            postgres_host != self.postgres_host or 
            postgres_port != self.postgres_port or 
            postgres_database != self.postgres_database or 
            self.psql is None
        ):
            self.postgres_user = postgres_user
            self.postgres_password = postgres_password
            self.postgres_host = postgres_host
            self.postgres_port = postgres_port
            self.postgres_database = postgres_database

            self.psql = PostgresManage(
                self.postgres_user,
                self.postgres_password,
                self.postgres_host,
                self.postgres_port,
                self.postgres_database
            )

        self._create_subscriptions()

    def _build_ca(self, ca_type, ca_id, ca):
        _log.debug(f'''_build_ca {ca_type} {ca_id}''')
        ca["reserve_notify_time"] = self.reserve_notify_time
        ca["reserve_expire_time"] = self.reserve_expire_time
        ca["altobackend"] = self.altobackend
        if ca_type == "reserve_battery" and ca["reserve_swapping"]:
            if ca_id not in self.reserve_batt_expire_list:
                Ca = custom_action_factory("reserve_batt_expire")
                newca = Ca(self, ca_id, ca)
                _log.debug(f'''_build_ca {newca}''')
                self.reserve_batt_expire_list[ca_id] = newca
            else:
                self.reserve_batt_expire_list[ca_id].cancel_schedule()
                del self.reserve_batt_expire_list[ca_id]
                Ca = custom_action_factory("reserve_batt_expire")
                newca = Ca(self, ca_id, ca)
                _log.debug(f'''_build_ca {newca}''')
                self.reserve_batt_expire_list[ca_id] = newca
            if ca_id not in self.reserve_batt_notify_list:
                Ca = custom_action_factory("reserve_batt_notify")
                newca = Ca(self, ca_id, ca)
                _log.debug(f'''_build_ca {newca}''')
                self.reserve_batt_notify_list[ca_id] = newca
            else:
                self.reserve_batt_notify_list[ca_id].cancel_schedule()
                del self.reserve_batt_notify_list[ca_id]
                Ca = custom_action_factory("reserve_batt_notify")
                newca = Ca(self, ca_id, ca)
                _log.debug(f'''_build_ca {newca}''')
                self.reserve_batt_notify_list[ca_id] = newca

    def _create_subscriptions(self):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=f'''config/{self.core.identity}/custom_action''',
                                  callback=self.subscribe_callback)

    def subscribe_callback(self, 
                            peer, 
                            sender, 
                            bus, 
                            topic, 
                            headers,
                            message):
        _log.debug(f"Customaction {sender} {topic} {headers} {message}")
        mtype = headers["message_type"].lower().strip()
        if sender != self.core.identity and mtype == "request":
            try:
                # self.controller._add_job({
                #     "instance": self,
                #     "data": data
                # })
                self._build_ca(message["type"], message["ca_id"], message)
                # self._build_ca("battery_reserve", "test_id", data)

            except Exception as e:
                # When the queue is full (So when?)
                _log.debug(f"Customaction {e}")

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
        
        self.add_job("Die")
        self.add_des("Die")

    def _period_signal(self):
        for obj in self.reserve_batt_expire_list.values():
            obj.period_signal()
        for obj in self.reserve_batt_notify_list.values():
            obj.period_signal()

    def add_des(self, des):
        try:
            self.des_queue.put_nowait(des)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def add_job(self, job):
        try:
            self.queue.put_nowait(job)
        except Exception as e:
            # When the queue is full (So when?)
            _log.debug(f"{e.message}, {e.args}")

    def _destroyer_thread(self):
        while True:
            des = self.des_queue.get()
            self.des_queue.task_done()
            if isinstance(des, str):
                if des == "Die":
                    return
            _log.debug("_destroyer_thread")
            if des["instance_typ"] == "reserve_batt_notify":
                del self.reserve_batt_notify_list[des["ca_id"]]
            elif des["instance_typ"] == "reserve_batt_expire": 
                del self.reserve_batt_expire_list[des["ca_id"]]

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
    utils.vip_main(customaction, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
