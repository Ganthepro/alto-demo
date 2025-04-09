"""
Aget logging samples to crateDB. The table must be created with the following statement

   CREATE TABLE mintel (
            timestamp TIMESTAMP,
            location VARCHAR(128),
            device_id VARCHAR(32),
            subdevice_idx SMALLINT,
            data_type VARCHAR(32),
            datapoint VARCHAR(32),
            value TEXT
     );

"""

__docformat__ = "reStructuredText"

import logging
import sys
import altolib
from crate import client
from json import dumps
from threading import Thread, Lock
from queue import Queue, Empty
from volttron.platform.agent import utils

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class crateDBDev(altolib.AltoLoggerDevice):
    def __init__(self, controller, devid, logtype=None):
        super().__init__(controller, devid, logtype)
        self.data = Queue()
        self.query = Queue()
        self.query_thread = Thread(
            target=self._query_thread, name="cratedb", daemon=True
        )
        self.query_thread.start()
        self.log_thread = Thread(target=self._flush_thread, name="cratedb", daemon=True)
        self.log_thread.start()
        self.do_flush = False

    @property
    def dbstring(self):
        return f"{self.controller.db_host}:{self.controller.db_port}"

    @property
    def user(self):
        return self.controller.db_user

    @property
    def passwd(self):
        return self.controller.db_password

    @property
    def table(self):
        return self.controller.db_table

    def log_data(self, data: dict):
        """
        Must be implemented by the actual AltoLoggerDevice

        """
        self.data.put_nowait(data)

    def flush_data(self):
        self.do_flush = True

    def _flush_thread(self):
        time_to_die = False
        lok = [
            "location",
            "device_id",
            "subdevice_idx",
            "type",
            "timestamp",
            "datapoint",
            "value",
        ]
        lokcrate = [
            "location",
            "device_id",
            "subdevice_idx",
            "data_type",
            "timestamp",
            "datapoint",
            "value",
        ]
        # Gather the queued data
        lod = []
        while True:
            while True:
                adata = []
                try:
                    thisdata = self.data.get(timeout=5)
                    self.data.task_done()
                    if thisdata == "Die":
                        time_to_die = True
                        break
                    for k in lok:
                        adata.append(thisdata[k])
                    adata[-1] = dumps(adata[-1])
                    lod.append(tuple(adata))
                except Empty:
                    break
                except Exception as e:
                    _log.debug(f"Queue exception: {e}")
                    break

            if self.do_flush and lod:
                query = "INSERT INTO " + self.table + " ( "
                query += ", ".join(lokcrate)
                query += ") VALUES (" + ",".join(["?" for x in lok]) + ");"
                cursor = None
                try:
                    connection = client.connect(self.dbstring)
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

    def _query_thread(self):
        while True:
            lok = [
                "location",
                "device_id",
                "subdevice_idx",
                "type",
                "timestamp",
                "datapoint",
                "value",
            ]
            lokcrate = [
                "location",
                "device_id",
                "subdevice_idx",
                "data_type",
                "timestamp",
                "datapoint",
                "value",
            ]
            myquery = None
            try:
                thisdata = self.query.get()
                self.query.task_done()
                if thisdata == "Die":
                    break
                if "reply_to" not in thisdata:
                    continue
                if "rid" not in thisdata:
                    continue
                # Let's build the query
                myquery = "SELECT "
                myquery += ", ".join(lokcrate)
                myquery += " FROM " + self.table
                mydata = []
                prefix = " WHERE "
                for k, ck in zip(lok, lokcrate):
                    if k in thisdata:
                        if k == "value":
                            for cv, op in thisdata[k]:
                                myquery += f"{prefix} {ck} {op} ?"
                                mydata.append(cv)
                                prefix = " AND "
                        elif k == "timestamp":
                            for cv, op in thisdata[k]:
                                if isinstance(cv, int) or isinstance(cv, float):
                                    myquery += f"{prefix} {ck} {op} ?"
                                else:
                                    myquery += f"{prefix} {ck} {op} ?"
                                mydata.append(cv)
                                prefix = " AND "
                        else:
                            if isinstance(thisdata[k], list):
                                myquery += f"{prefix} {ck} IN ("
                                sqpre = ""
                                for av in thisdata[k]:
                                    myquery += f"{sqpre}?"
                                    sqpre = ", "
                                    mydata.append(av)
                                myquery += ")"
                            else:
                                myquery += f"{prefix} {ck} = ?"
                                mydata.append(thisdata[k])
                            prefix = " AND "
            except Exception as e:
                _log.debug(f"Queue exception: {e}")
                msg = {"rid": thisdata["rid"], "status": "error"}
                msg["errmsg"] = "Query could not be parsed"
                topic = thisdata["reply_to"]
                self.controller.publish(topic, msg, "response")
                continue

            if myquery:
                myquery += " ORDER BY timestamp LIMIT 200"
                _log.debug(f"Query is {myquery}, with {mydata}")
                try:
                    connection = client.connect(self.dbstring)
                    cursor = connection.cursor()
                    cursor.execute(myquery, mydata)
                    allres = cursor.fetchall()
                    cursor.close()
                    myres = []
                    for ares in allres:
                        myres.append({k: v for k, v in zip(lok, ares)})
                    msg = {"rid": thisdata["rid"], "status": "ok"}
                    msg["result"] = myres
                    topic = thisdata["reply_to"]
                    self.controller.publish(topic, msg, "response")

                except Exception as e:
                    _log.critical(f"Data could not be retrieved: {e}")
                    msg = {"rid": thisdata["rid"], "status": "error"}
                    msg["errmsg"] = f"Query could not be executed: {e}"
                    topic = thisdata["reply_to"]
                    self.controller.publish(topic, msg, "response")


def cratedb(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Blremote
    :rtype: Blremote
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "cratedb")
    kwargs["db_host"] = config.get("db_host", "localhost")
    kwargs["db_port"] = config.get("db_port", 4200)
    kwargs["db_user"] = config.get("db_user", "")
    kwargs["db_password"] = config.get("db_password", "")
    kwargs["db_table"] = config.get("db_table", "altotech")

    return CrateDB(topic, **kwargs)


class CrateDB(altolib.AltoDatalogger):
    """
    Document agent constructor here.
    """

    def register_self(self):
        ndev = crateDBDev(self, self.agent_name)
        self.register_new_device(ndev)

    def handle_query_request(self, devid, message):
        """
        Query the database and return the results in a response.
        """

        self.device_list[self.agent_name].query.put_nowait(message)

    def last_rites(self):
        """
        Something to do upon imminent death

        Should be overloaded by agents needing it.
        """
        self.handle_query_request(self.agent_name, "Die")
        self.device_list[self.agent_name].data.put_nowait("Die")


def main():
    """Main method called to start the agent."""
    utils.vip_main(cratedb, identity="cratedb", version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
