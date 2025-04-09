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

from altolib import AltoHealth

import psycopg2

import pendulum
import datetime

from volttron.platform.agent import utils
from volttron.platform.scheduling import periodic
from volttron.platform.vip.agent import RPC, Agent, Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def postgresql(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Postgresql
    :rtype: Postgresql
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")
        
    db_name = config.get("db_name", "postgres")
    db_host = config.get("db_host", "localhost")
    db_port = config.get("db_port", 5432)
    db_user = config.get("db_user", "postgres")
    db_password = config.get("db_password", None)

    return Postgresql(db_name, db_host, db_port, db_user, db_password, **kwargs)


class Postgresql(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, db_name, db_host, db_port, db_user, db_password, **kwargs):
        super(Postgresql, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.db_name = db_name
        self.db_host = db_host
        self.db_port = db_port
        self.db_user = db_user
        self.db_password = db_password
        
        self.default_config = {
            "db_name": db_name,
            "db_host": db_host,
            "db_port": db_port,
            "db_user": db_user,
            "db_password": db_password
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
            db_name = config.get("db_name", "postgres")
            db_host = config.get("db_host", "localhost")
            db_port = config.get("db_port", 5432)
            db_user = config.get("db_user", "postgres")
            db_password = config.get("db_password", None)
            
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.db_name = db_name
        self.db_host = db_host
        self.db_port = db_port
        self.db_user = db_user
        self.db_password = db_password
    
    def get_table_column_names(self, table_name: str):
        """
        Get the column names of a table from Postgres DB

        Args:
            table_name (str): Name of the table to get column names from

        Returns:
            column_names (list): List of column names of the table

        """
        query_string = f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'"
        connection = psycopg2.connect(database=self.db_name,
                                      user=self.db_user,
                                      password=self.db_password,
                                      host=self.db_host,
                                      port=self.db_port)
        cursor = connection.cursor()

        cursor.execute(query_string)
        rows = cursor.fetchall()
        column_names = [row[0] for row in rows]

        return column_names

    def add_where_clause_to_sql_string(self, sql_string: str, table_name: str, filters: dict):
        """
        Add WHERE clause to a SQL query string from the filters dictionary
        
        Args:
            sql_string (str): SQL query string to add WHERE clause to
            table_name (str): Name of the table
            filters (dict): Dictionary of filters to apply to the query with the follwing format:
            
        Returns:
            sql_string (str): SQL query string with WHERE clause added
        
        """
        sql_string += " WHERE "
        prefix = ""
        for col_name, f in filters.items():

            if col_name not in self.get_table_column_names(table_name):
                _log.debug(f"Column [{col_name}] does not exist in table [{table_name}]")
                continue

            for oper, value in f.items():

                if value is None:
                    _log.debug(f"Invalid value for column [{col_name}] -- value = {value}")
                    continue

                # Preprocess value to be compatible with Postgres DB query string
                if isinstance(value, str):
                    value_string = f"'{value}'"
                elif isinstance(value, list):
                    value_string = str(tuple(value)) if len(value) > 1 else str(tuple(value)).replace(",", "")
                elif isinstance(value, (int, float, complex)):
                    value_string = str(value)
                else:
                    _log.debug(f"Invalid value type [{type(value)}] for filtering params for querying data from Postgres DB")
                    continue

                # Add filter to query string
                if oper in [">", "<", ">=", "<=", "=", "!=", "LIKE", "NOT LIKE"]:
                    sql_string += f"{prefix}{col_name} {oper} {value_string}"
                    prefix = "\nAND "
                elif oper.upper() in ["IN", "NOT IN"] and isinstance(value, list):
                    sql_string += f"{prefix}{col_name} {oper.upper()} {value_string}"
                    prefix = "\nAND "
                else:
                    _log.debug(f"Invalid filter specified for querying data from Postgres DB -- {col_name}: {f}")
                    
        return sql_string

    @RPC.export
    def get_data_from_postgres(self, table_name: str, filters: dict):
        """
        RPC Method for querying data from Postgres DB

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
            data (list): List of dictionaries containing the data queried from Postgres DB

            data = [{'timestamp': 1675245600000,
                    'location': 'chiller_plant/iot_devices',
                    'device_id': 'CSQ_plant',
                    'subdevice_idx': 0,
                    'type': 'calculated_power',
                    'aggregation_type': 'avg_1h',
                    'datapoint': 'power',
                    'value': '1289.8812590049934'}, ....]

        """
        # Step 1: Initialize query string
        query_string = "SELECT * FROM {}".format(table_name)

        # Step 2: Construct query string
        if filters:
            query_string = self.add_where_clause_to_sql_string(query_string, table_name, filters)
        
        # Step 3: Try to query data from Postgres DB
        cursor = None
        connection = None
        data = None
        try:
            connection = psycopg2.connect(
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=self.db_port
            )
            cursor = connection.cursor()
            cursor.execute(query_string)
            data = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        except Exception as e:
            _log.debug(f"Data could not be queried: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
        
        # Step 4: Construct return payload
        if data is None:
            _log.debug(f"No data found for query: {query_string}")
            return []
        else:
            response = []
            for row in data:
                
                # Turn unserializable data types such as datetime objects into serializable ones
                row = list(row)
                for i, v in enumerate(row):
                    if isinstance(v, datetime.datetime):
                        v = pendulum.instance(v).in_tz('Asia/Bangkok').isoformat()
                        row[i] = v
                
                response.append(dict(zip(columns, row)))
            return response
    
    @RPC.export
    def delete_data_from_postgres(self, table_name: str, filters: dict):
        """
        RPC Method for deleting data from Postgres DB in the specified table

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
        # Step 1: Initialize SQL deleting string
        delete_string = "DELETE FROM {}".format(table_name)

        # Step 2: Construct SQL deleting string
        if filters:
            delete_string = self.add_where_clause_to_sql_string(delete_string, table_name, filters)

        # Step 3: Try to delete data from Postgres DB
        cursor = None
        connection = None
        try:
            connection = psycopg2.connect(
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=self.db_port
            )
            cursor = connection.cursor()
            cursor.execute(delete_string)
            connection.commit()
        except Exception as e:
            _log.debug(f"Error `{e}` when executing deleting command {delete_string}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    @RPC.export
    def insert_data_to_postgres(self, table_name: str, data: list):
        """
        RPC Method for deleting data from Postgres DB in the specified table

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
        # Step 1: Get column names of the table
        table_column_names = self.get_table_column_names(table_name)

        # Step 2: Construct insert string
        insert_string = f"INSERT INTO {table_name} ({','.join(table_column_names)}) VALUES ({','.join(['%s'] * len(table_column_names))})"
        
        # Step 3: Add each row of data to insert SQL string
        entry = []
        for row in data:
            entry += [tuple([row.get(col, None) for col in table_column_names])]

        # Step 4: Try to insert data into Postgres DB
        cursor = None
        connection = None
        try:
            connection = psycopg2.connect(
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=self.db_port
            )
            cursor = connection.cursor()
            cursor.executemany(insert_string, entry)  # Remove last comma
            connection.commit()
            insert_success = True
        except Exception as e:
            _log.debug(f"Data could not be inserted: {e}")
            insert_success = False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

        return insert_success


def main():
    """Main method called to start the agent."""
    utils.vip_main(postgresql,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
