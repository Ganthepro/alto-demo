"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.engine import URL
from datetime import datetime as dt
import pytz
from sqlalchemy import Column, Integer, String, TIMESTAMP, UUID, CheckConstraint
import uuid

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

Base = declarative_base()

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

    username = config.get('username', "")
    host = config.get('host', "")
    database = config.get('database', "")
    password = config.get('password', "")
    topic = config.get('topic', [])

    url = URL.create(
        drivername="postgresql",
        username=username,
        host=host,
        database=database,
        password=password
    )
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    return DataLogger(session, username, host, database, password, topic, **kwargs)


class DataLogger(Agent):
    def __init__(self, session, username, host, database, password, topic, **kwargs):
        super(DataLogger, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.session = session
        self.username = username
        self.host = host
        self.database = database
        self.password = password
        self.topic = topic    

        self.default_config = {"session": session,
                               "username": username,
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
        # self.insert(message)


    def insert_life_beings(self, body):
        payload = LifeBeingsRawData(
            online_status=body["online_status"],
            sensitivity=body["sensitivity"],
            datetime=body["datetime"],
            presence_state=body["presence_state"]
        )
        self.session.add(payload)
        self.session.commit()
        data = self.session.query(LifeBeingsRawData).all()[-1]
        data_dict = data.to_dict()
        _log.info("Query: {}".format(data_dict))

    def insert_iaq(self, body):
        datetime_str = body['datetime']
        date_time = dt.strptime(datetime_str, "%Y-%m-%d %H:%M:%S.%f")
        timestamp = int(date_time.replace(tzinfo=pytz.UTC).timestamp())
        datetime_timestamptz = date_time.replace(tzinfo=pytz.UTC)
        temperature = IaqRawData(
            device_id=body["id"],
            timestamp=timestamp,
            datetime=datetime_timestamptz,
            datapoint="temperature",
            value=body["temperature"]
        )
        humidity = IaqRawData(
            device_id=body["id"],
            timestamp=timestamp,
            datetime=datetime_timestamptz,
            datapoint="humidity",
            value=body["humidity"]
        )
        co2 = IaqRawData(
            device_id=body["id"],
            timestamp=timestamp,
            datetime=datetime_timestamptz,
            datapoint="co2",
            value=body["co2"]
        )
        self.session.add(temperature)
        self.session.add(humidity)
        self.session.add(co2)
        self.session.commit()
        # data = self.session.query(IaqRawData).all()[-1]
        # data_dict = data.to_dict()
        # _log.info("Query: {}".format(data_dict))

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        # Example publish to pubsub
        self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # Example RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        pass

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2

class IaqRawData(Base):
    __tablename__ = 'iaq_raw_data'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(String())
    timestamp = Column(Integer(), nullable=False)
    datetime = Column(TIMESTAMP, nullable=False)
    datapoint = Column(String(), nullable=False)
    value = Column(String(), nullable=False)

    def to_dict(self):
        """Convert the model instance to a dictionary with custom formatting."""
        return {
            'id': self.id,
            'timestamp': str(self.timestamp),  
            'datetime': str(self.datetime),
            'datapoint': self.datapoint,
            'value': self.value,
            'device_id': self.device_id
        }
    
class LifeBeingsRawData(Base):
    __tablename__ = 'life_beings_raw_data'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    online_status = Column(String())
    sensitivity = Column(Integer(), nullable=False)
    datetime = Column(String(), nullable=False)
    presence_state = Column(String())

    __table_args__ = (
        CheckConstraint('sensitivity >= 0 AND sensitivity <= 100', name='sensitivity_range'),
    )

    def to_dict(self):
        """Convert the model instance to a dictionary with custom formatting."""
        return {
            'id': self.id,
            'online_status': self.online_status,
            'sensitivity': self.sensitivity,
            'datetime': self.datetime,
            'presence_state': self.presence_state
        }

def main():
    """Main method called to start the agent."""
    utils.vip_main(data_logger, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
