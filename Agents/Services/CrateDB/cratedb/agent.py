"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import json
import logging
import sys
from json import dumps
from queue import Empty, Queue
from threading import Thread

import pendulum
import yaml
# from altolib import AltoHealth
from crate import client

from volttron.platform.agent import utils
from volttron.platform.scheduling import periodic
from volttron.platform.vip.agent import RPC, Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class CrateDBTableHandler(object):
    def __init__(self, controller, table_name, columns, partition_col):
        self.table_name = table_name
        self.controller = controller
        self.columns_info: dict = columns
        self.column_names = [col['name'] for col in columns]
        self.column_types = [col['type'] for col in columns]
        self.partition_col = partition_col

        self.build_table()  # Create new table if table_name does not exist in CrateDB

        # Queue of data entries which will be logged into Database
        self.data_queue = Queue()

        # Thread for handling data query
        # self.query = Queue()
        # self.query_thread = Thread(target=self._query_thread, name=f"cratedb_query_{self.table_name}", daemon=True)
        # self.query_thread.start()

        # Thread for handling data logging
        self.log_thread = Thread(target=self._flush_thread, name=f"cratedb_flush_{self.table_name}", daemon=True)
        self.log_thread.start()

        self.do_flush = False

    @property
    def url_string(self):
        return f"{self.controller.db_host}:{self.controller.db_port}"

    @property
    def user(self):
        return self.controller.db_user

    @property
    def password(self):
        return self.controller.db_password

    def build_table(self):
        """
        Create new table if table_name does not exist in CrateDB
        """
        query = "CREATE TABLE IF NOT EXISTS " + self.table_name + " ( "
        query += ", ".join(
            [
                f"{col['name']} {col['type']}"
                for col in self.columns_info
            ]
        )
        query += ")"

        if self.partition_col is not None and self.partition_col in self.column_names:
            query += f"PARTITIONED BY ({self.partition_col});"
        else:
            query += ";"
        cursor = None
        try:
            connection = client.connect(self.url_string, username=self.user, password=self.password)
            cursor = connection.cursor()
            cursor.execute(query)
        except Exception as e:
            _log.critical(f"Table could not be created: {e}")
        finally:
            if cursor:
                cursor.close()

    def log_data(self, data: dict):
        """
        Log data into self.data_queue

        For table with `datapoint` and `value` columns, log every data point exists in the incoming data.
        For example, the incoming data with payload as below will be converted into 3 data samples and get logged
        separately.

        data = {
            # These are common keys
            "timestamp": 1000000000,
            "location": "building1",
            "device_id": "device1",
            "model": "power_meter",

            # These are data specific keys
            "power": 671.2,
            "energy": 888918,
            "voltage": 120.2,
        }

        """
        # Keys that shouldn't be included into the data sample (e.g. timestamp, device_id, etc.)
        COMMON_KEYS = [
            "timestamp",
            "unix_timestamp",
            "week",
            "month",
            "year",
            "device_id",
            "subdevice_idx",
            "location",
            "type",
            "model",
            "device_name",
            "subdevice_name",
        ]
        # If timestamp exists in data. Make sure that the data type is float (timestamp in milliseconds) so CrateDB will
        # correctly parse it
        if "timestamp" in data.keys():
            data["timestamp"] = float(data["timestamp"])

        # Parse week and month and year column if in columns list if not in data
        timezone = 'Asia/Bangkok'
        if "week" in self.column_names and "week" not in data.keys():
            data["week"] = pendulum.from_timestamp(data['timestamp'], tz=timezone).start_of("week").timestamp()
        if "month" in self.column_names and "month" not in data.keys():
            data["month"] = pendulum.from_timestamp(data['timestamp'], tz=timezone).start_of("month").timestamp()
        if "year" in self.column_names and "year" not in data.keys():
            data["year"] = pendulum.from_timestamp(data['timestamp'], tz=timezone).year


        # Case 1: Old convention from DeviceAgent
        if ("datapoint" in self.column_names) and ("value" in self.column_names) and ("datapoint" not in data) and ("value" not in data):

            sample_template = {col: data[col] for col in list(set(self.column_names) - set(["datapoint", "value"]))}

            additional_points = list(set(data.keys()) - set(self.column_names) - set(COMMON_KEYS))
            for k in additional_points:
                sample = sample_template.copy()
                sample["datapoint"] = k
                sample["value"] = data[k]
                self.data_queue.put_nowait(sample)

        # Case 2: Data can be directly inserted into the table
        else:
            self.data_queue.put_nowait(data)

    def flush_data(self):
        """ Change the flag to flush data into CrateDB in the next loop in self._flush_thread """
        self.do_flush = True

    def query_data(self, query_string: str):
        """
        Query data from CrateDB with specified query string.
        """
        cursor = None
        try:
            connection = client.connect(self.url_string, username=self.user, password=self.password)
            cursor = connection.cursor()
            cursor.execute(query_string)
            datas = cursor.fetchall()

            # Preprocess list-of-lists into list-of-dicts with correct keys and values
            res = list()
            for row in datas:
                res.append({k: v for k, v in zip(self.column_names, row)})

            return res

        except Exception as e:
            _log.debug(f"Data could not be queried: {e}")
        finally:
            if cursor:
                cursor.close()

    def execute(self, sql_string: str):
        """
        Execute given SQL string. Return nothing
        """
        cursor = None
        try:
            connection = client.connect(self.url_string, username=self.user, password=self.password)
            cursor = connection.cursor()
            cursor.execute(sql_string)

        except Exception as e:
            _log.debug(f"Error `{e}` when executing command {sql_string}")
        finally:
            if cursor:
                cursor.close()

    def executemany(self, sql_string: str, data: list):
        """
        Execute given SQL string with multiple data. Return nothing
        """
        cursor = None
        try:
            connection = client.connect(self.url_string, username=self.user, password=self.password)
            cursor = connection.cursor()
            cursor.executemany(sql_string, data)

        except Exception as e:
            _log.debug(f"Error `{e}` when executing command {sql_string}")
        finally:
            if cursor:
                cursor.close()

    def _flush_thread(self):
        """
        A thread for handling data logging into CrateDB. The INSERT command will be executed every time self.do_flush
        is changed to True by the periodically-called function self.flush_data
        """
        time_to_die = False
        # Gather the queued data
        lod = []
        while True:
            while True:
                adata = []
                try:
                    data = self.data_queue.get(timeout=1)
                    self.data_queue.task_done()
                    if data == "Die":
                        time_to_die = True
                        break
                    for k in self.column_names:
                        if k == 'value':
                            adata.append(dumps(data[k]))
                        else:
                            adata.append(data[k])
                    lod.append(tuple(adata))

                    # _log.debug(f"Data LOD length: {len(lod)}")
                    # _log.debug(f"Queue Size: {self.data_queue.qsize()}")
                    if len(lod) >= 1000:
                        break

                except Empty:
                    break
                except Exception as e:
                    _log.debug(f"Queue exception: {e}")
                    break

            if self.do_flush and lod:
                query = "INSERT INTO " + self.table_name + " ( "
                query += ", ".join(self.column_names)
                query += ") VALUES (" + ",".join(["?" for x in self.column_names]) + ");"
                cursor = None
                try:
                    connection = client.connect(self.url_string, username=self.user, password=self.password)
                    cursor = connection.cursor()
                    cursor.executemany(query, lod)
                except Exception as e:
                    _log.critical(f"Data could not be saved: {e}")
                finally:
                    self.do_flush = False
                    lod = []
                    if cursor:
                        cursor.close()
            if time_to_die:
                break


def cratedb(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Cratedb
    :rtype: Cratedb
    """
    config = utils.load_config(config_path)
    agent_config = config['volttron_agents']['cratedb']

    if not agent_config:
        _log.info("Using Agent defaults for starting configuration.")

    db_host = agent_config.get("db_host", "localhost")
    db_port = agent_config.get("db_port", 4200)
    db_user = agent_config.get("db_user", "")
    db_password = agent_config.get("db_password", "")
    tables_settings = agent_config.get("tables_settings", dict())
    subscription_topics = agent_config.get("subscription_topics", dict())

    return Cratedb(db_host, db_port, db_user, db_password, tables_settings, subscription_topics, config, **kwargs)


class Cratedb(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, db_host, db_port, db_user, db_password, tables_settings, subscription_topics, default_config, **kwargs):
        super(Cratedb, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.db_host = db_host
        self.db_port = db_port
        self.db_user = db_user
        self.db_password = db_password
        self.tables_settings = tables_settings
        self.subscription_topics = subscription_topics

        self.tables = dict()

        self.default_config = default_config

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
        if isinstance(contents, dict):
            config = contents
        else:
            try:
                config = yaml.safe_load(contents)
            except yaml.YAMLError as e:
                _log.error("Error parsing YAML:", e)
                return None

        _log.debug("Configuring Agent")

        try:
            agent_config = config['volttron_agents']['cratedb']
            self.db_host = agent_config.get("db_host", "localhost")
            self.db_port = agent_config.get("db_port", 4200)
            self.db_user = agent_config.get("db_user", "")
            self.db_password = agent_config.get("db_password", "")
            self.tables_settings = agent_config.get("tables_settings", dict())
            self.subscription_topics = agent_config.get("subscription_topics", dict())
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.tables = dict()
        self._register_tables()

        self.subscribed_topics = []
        self._create_subscriptions(list(self.subscription_topics.values()))

        # Step 6: Define custom heartbeat and health payload
        # self.custom_health = AltoHealth(self.core, self.vip.pubsub, heartbeat_period=60, verbose=False)

        # Set intial status for functions and devices
        self.function_names = [
            "_handle_message_data",
            "_flush_data"
        ]
        self.device_names = []
        # self.custom_health.set_pending_status(names=self.function_names, type_label='function')
        # self.custom_health.set_pending_status(names=self.device_names, type_label='device')
        #
        # # Track function status (need to use this approach to pass `self` into decorator function)
        # self._handle_message_data = AltoHealth.track_status(self.custom_health)(self._handle_message_data)
        # self._flush_data = AltoHealth.track_status(self.custom_health)(self._flush_data)

        # Step 7: Set-up period for flushing and writing data into database
        self.core.schedule(periodic(5), self._flush_data)

    def _flush_data(self):
        """
        Periodically flush all data already logged into data queue and write into CrateDB
        """
        for table in self.tables.values():
            table.flush_data()

    def _register_tables(self):
        """
        Register tables from config files
        """
        for table_name, table_setting in self.tables_settings.items():
            table_columns = table_setting.get("columns", list())
            partition_col = table_setting.get("partition_col", None)

            if not table_columns:
                _log.warning("No columns defined for table {}".format(table_name))

            self.tables[table_name] = CrateDBTableHandler(self, table_name, table_columns, partition_col)

    def _create_subscriptions(self, topics: list):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback

        Args:
            topics (list[list[str]]): List of lists topics to subscribe to

        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for topic_list in topics:
            for t in topic_list:
                self.subscribed_topics.append(t)
                self.vip.pubsub.subscribe(peer='pubsub',
                                          prefix=t,
                                          callback=self._handle_message_data)

    def _handle_message_data(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        schema = topic.split("/")[0]

        if isinstance(message, str):
            message = json.loads(message)

        if schema in self.subscribed_topics:

            for table_name, table_topics in self.subscription_topics.items():
                if schema in table_topics:
                    t = self.tables.get(table_name, None)
                    if t is None:
                        _log.debug(f"Table {table_name} hasn't been initialized for data logging")
                        continue
                    else:
                        t.log_data(message)

    @RPC.export
    def get_data_from_cratedb(self, table_name: str, filters: dict):
        """
        RPC Method for querying data from CrateDB

        Args:
            table_name (str): Name of the table to query data from
            filters (dict): Dictionary of filters to apply to the query with the follwing format:

            filters = {                             |   ex.     filters = {
                <column_name_1>: {                  |               unix_timestamp: {
                    <operator_1>: <value_1>,        |                   ">": 100000,
                    <operator_2>: <value_2>,        |                   "<": 200000
                    ...                             |               },
                },                                  |               device_id: {
                <column_name_2>: ...                |                   "=": "device_1"
            }                                       |               }
                                                    |           }

        Supported operators: "=", "!=", ">", "<", ">=", "<=", "IN", "NOT IN", "LIKE", "NOT LIKE"

        Returns:
            data (list): List of dictionaries containing the data queried from CrateDB

            data = [{'timestamp': 1675245600000,
                    'location': 'chiller_plant/iot_devices',
                    'device_id': 'CSQ_plant',
                    'subdevice_idx': 0,
                    'type': 'calculated_power',
                    'aggregation_type': 'avg_1h',
                    'datapoint': 'power',
                    'value': '1289.8812590049934'}, ....]

        """

        if table_name not in self.tables.keys():
            _log.debug(f"Table [{table_name}] not found")
            return None

        query_string = "SELECT * FROM {} WHERE ".format(table_name)
        prefix = ""

        for col_name, f in filters.items():

            if col_name not in self.tables[table_name].column_names:
                _log.debug(f"Column [{col_name}] does not exist in table [{table_name}]")
                continue

            for oper, value in f.items():

                if value is None:
                    _log.debug(f"Invalid value for column [{col_name}] -- value = {value}")
                    continue

                # Preprocess value to be compatible with CrateDB query string
                if isinstance(value, str):
                    value_string = f"'{value}'"
                elif isinstance(value, list):
                    value_string = str(tuple(value)) if len(value) > 1 else str(tuple(value)).replace(",", "")
                else:
                    value_string = str(value)

                # Add filter to query string
                if oper in [">", "<", ">=", "<=", "=", "!=", "LIKE", "NOT LIKE"]:
                    query_string += f"{prefix}{col_name} {oper} {value_string}"
                    prefix = "\nAND "
                elif oper.upper() in ["IN", "NOT IN"] and isinstance(value, list):
                    query_string += f"{prefix}{col_name} {oper.upper()} {value_string}"
                    prefix = "\nAND "
                else:
                    print(f"Invalid filter specified for querying data from CrateDB -- {col_name}: {f}")

        # query_string += " LIMIT 100"

        _log.debug(f"Querying data from CrateDB: {query_string}")
        data = self.tables[table_name].query_data(query_string)
        _log.debug(f"Finished querying data from CrateDB")

        if data is None:
            _log.debug(f"No data found for query: {query_string}")

        return data

    @RPC.export
    def drop_data_from_cratedb(self, table_name: str, filters: dict):
        """
        RPC Method for deleting data from CrateDB in the specified table

        Args:
            table_name (str): Name of the table to query data from
            filters (dict): Dictionary of filters to apply to the query with the follwing format:

            filters = {                             |   ex.     filters = {
                <column_name_1>: {                  |               unix_timestamp: {
                    <operator_1>: <value_1>,        |                   ">": 100000,
                    <operator_2>: <value_2>,        |                   "<": 200000
                    ...                             |               },
                },                                  |               device_id: {
                <column_name_2>: ...                |                   "=": "device_1"
            }                                       |               }
                                                    |           }

        Supported operators: "=", "!=", ">", "<", ">=", "<=", "IN", "NOT IN", "LIKE", "NOT LIKE"

        """
        if table_name not in self.tables.keys():
            _log.debug(f"Table [{table_name}] not found")
            return None

        query_string = "DELETE FROM {} WHERE ".format(table_name)
        prefix = ""

        for col_name, f in filters.items():

            if col_name not in self.tables[table_name].column_names:
                raise IndexError(f"Column [{col_name}] does not exist in table [{table_name}]")

            for oper, value in f.items():

                if value is None:
                    _log.debug(f"Invalid value for column [{col_name}] -- value = {value}")
                    continue

                # Preprocess value to be compatible with CrateDB query string
                if isinstance(value, str):
                    value_string = f"'{value}'"
                elif isinstance(value, list):
                    value_string = str(tuple(value)) if len(value) > 1 else str(tuple(value)).replace(",", "")
                else:
                    value_string = str(value)

                # Add filter to query string
                if oper in [">", "<", ">=", "<=", "=", "!=", "LIKE", "NOT LIKE"]:
                    query_string += f"{prefix}{col_name} {oper} {value_string}"
                    prefix = "\nAND "
                elif oper.upper() in ["IN", "NOT IN"] and isinstance(value, list):
                    query_string += f"{prefix}{col_name} {oper.upper()} {value_string}"
                    prefix = "\nAND "
                else:
                    print(f"Invalid filter specified for querying data from CrateDB -- {col_name}: {f}")

        _log.debug(f"Deleting data from CrateDB: {query_string}")
        self.tables[table_name].execute(query_string)
        _log.debug(f"Successfully deleted data from CrateDB: {query_string}")

    @RPC.export
    def insert_data_to_cratedb(self, table_name: str, data: list):
        """
        RPC Method for deleting data from CrateDB in the specified table

        Args:
            table_name (str): Name of the table to query data from
            data (list): List of dictionaries containing the data to insert into the table

            ex. data = [{'timestamp': 1675245600000,
                         'location': 'chiller_plant/iot_devices',
                         'device_id': 'CSQ_plant',
                         'subdevice_idx': 0,
                         'type': 'calculated_power',
                         'aggregation_type': 'avg_1h',
                         'datapoint': 'power',
                         'value': '1289.8812590049934'}, ....]

        """
        _log.debug(f"Inserting data to CrateDB: {data}")

        table_column_names = self.tables[table_name].column_names
    
        entry = []
        for row in data:

            entry += [tuple([row[col] for col in table_column_names])]

        insert_string = f"INSERT INTO {table_name} ({','.join(table_column_names)}) VALUES ({','.join(['?'] * len(table_column_names))})"
        
        _log.debug(f"Inserting data to CrateDB: {insert_string}")
        self.tables[table_name].executemany(insert_string, entry)
        _log.debug(f"Successfully inserted data to CrateDB: {insert_string}")

        return "Success"


def main():
    """Main method called to start the agent."""
    utils.vip_main(cratedb,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
