"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
import json
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from datetime import datetime as dt
import pytz
import uuid
import psycopg2

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

def data_logger(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: DataLogger
    :rtype: DataLogger
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")
    
    _log.info(f"YAML Config: {config}")

    # username = config.get('username', "")
    # host = config.get('host', "")
    # database = config.get('database', "")
    # password = config.get('password', "")
    # topic = config.get('topic', [])

    conn = psycopg2.connect(
        host=host,
        database=database,
        user=username,
        password=password
    )
    cur = conn.cursor()

    return DataLogger(conn, cur, username, host, database, password, topic, **kwargs)

class DataLogger(Agent):
    def __init__(self, conn: psycopg2.extensions.connection, cur: psycopg2.extensions.cursor, username, host, database, password, topic, **kwargs):
        super(DataLogger, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.conn = conn
        self.cur = cur
        self.username = username
        self.host = host
        self.database = database
        self.password = password
        self.topic = topic    

        self.default_config = {"username": username,
                               "host": host,
                               "database": database,
                               "password": password,
                               "topic": topic}

        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        _log.info(f"Config: {contents}")
        config = self.default_config.copy()
        config.update(contents)

        _log.debug(f"Config: {config}")
        _log.debug("Configuring Agent")

        try:
            username = str(config["username"])
            host = str(config["host"])
            database = str(config["database"])
            password = str(config["password"])
            topic = list(config["topic"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.username = username
        self.host = host
        self.database = database
        self.password = password
        self.topic = topic

        self._create_subscriptions(self.topic)

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for t in topic:
            self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=t,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        _log.info(f"Topic: {topic}, Message: {message}")
        if topic == "lifebeing/data":
            self.insert_life_beings(message)
        elif topic == "iaq/data":
            self.insert_iaq(message)

    def insert_life_beings(self, body):
        insert_life_beings_query = """
            INSERT INTO lifebeing (id, device_id, online_status, sensitivity, datetime, presence_state)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        self.cur.execute(insert_life_beings_query, (str(uuid.uuid4()), body["id"], body["online_status"], body["sensitivity"], body["datetime"], body["presence_state"]))
        self.conn.commit()

    def insert_iaq(self, body):
        datetime_str = body['datetime']
        date_time = dt.strptime(datetime_str, "%Y-%m-%d %H:%M:%S.%f")
        timestamp = int(date_time.replace(tzinfo=pytz.UTC).timestamp())
        datetime_timestamptz = date_time.replace(tzinfo=pytz.UTC)
        
        insert_iaq_query = """
            INSERT INTO public.iaq
            (id, device_id, "timestamp", datetime, datapoint, value)
            VALUES(%s, %s, %s, %s, %s, %s);
        """
        queries = [
            (str(uuid.uuid4()), body["id"], timestamp, datetime_timestamptz, "temperature", body["temperature"]),
            (str(uuid.uuid4()), body["id"], timestamp, datetime_timestamptz, "humidity", body["humidity"]),
            (str(uuid.uuid4()), body["id"], timestamp, datetime_timestamptz, "co2", body["co2"])
        ]
        self.cur.executemany(insert_iaq_query, queries)
        self.conn.commit()

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        create_tables_query = """
            CREATE TABLE IF NOT EXISTS iaq (
                id UUID PRIMARY KEY,
                device_id VARCHAR DEFAULT NULL,
                timestamp INTEGER NOT NULL,
                datetime TIMESTAMP NOT NULL,
                datapoint VARCHAR NOT NULL DEFAULT '',
                value VARCHAR NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS lifebeing (
                id UUID PRIMARY KEY,
                online_status VARCHAR DEFAULT NULL,
                sensitivity VARCHAR NOT NULL DEFAULT '',
                datetime VARCHAR NOT NULL DEFAULT '',
                presence_state VARCHAR DEFAULT NULL,
                device_id VARCHAR DEFAULT NULL
            );"""
        self.cur.execute(create_tables_query)
        self.conn.commit()


    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        self.cur.close()
        self.conn.close()

    @RPC.export
    def query_iaq(self):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        self.cur.execute("SELECT * FROM iaq ORDER BY datetime DESC LIMIT 1")
        query = self.cur.fetchone()
        query = dict(zip([i[0] for i in self.cur.description], query))
        query["datetime"] = query["datetime"].strftime("%Y-%m-%d %H:%M:%S.%f")
        _log.info(f"IAQ query: {query}")
        return json.dumps(query)
    
    @RPC.export
    def query_lifebeing(self):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        self.cur.execute("SELECT * FROM lifebeing ORDER BY datetime DESC LIMIT 1")
        query = self.cur.fetchone()
        _log.info(f"Life beings query: {query}")
        return json.dumps(query)

def main():
    """Main method called to start the agent."""
    utils.vip_main(data_logger, 
                   version=__version__)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
