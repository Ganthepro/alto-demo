"""
This Agent investigate memory usage of each agents running in the os.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from gevent import subprocess
import datetime as dt
import time

from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


class ProcMeminfo:
    "The ProcMeminfo is Singleton Class"

    @staticmethod
    def get_available_memory():
        """
        :return: available memory in kB
        :rtype: dict[str, int]
        """

        available_memory = {}
        output = subprocess.check_output('cat /proc/meminfo', shell=True)
        str_output = output.decode('UTF-8')
        str_output_list = str_output.split('\n')
        if len(str_output_list) > 1:
            for i in str_output_list:
                row = i.split()
                if "MemAvailable:" in i:
                    if len(row) >= 2:
                        available_memory["available_memory"] = int(row[1])
        return available_memory


class VolttronSystemd:
    "The VolttronSystemd is Singleton Class"

    @staticmethod
    def get_pid_and_memory_usage():
        """
        :return: First dict is pair of name and pid number {name: pid_number}, Second dict is pair of name and memory usage in MB {name: memory_usage}
        :rtype: (dict[str, int], dict[str, float])
        """

        pid = {}
        systemd_memory = {}
        output = subprocess.check_output('systemctl status volttron.service', shell=True)
        str_output = output.decode(encoding='utf-8', errors='ignore')

        # str_output = str(output, "windows-1252")
        # str_output = output.decode('ascii')
        # _log.debug(f"VTSD2 {str_output.find('Memory')}")
        target = "Memory:"
        idx = str_output.find(target)
        if idx > -1:
            l = 0
            idx += len(target)
            val = ""
            while str_output[idx] != 'k' and str_output[idx] != 'M' and str_output[idx] != 'G' and l < 200:
                val += str_output[idx]
                l += 1
                idx += 1
            if str_output[idx] == 'G':
                systemd_memory["systemd_volttron_service"] = float(val.strip())*1024
            elif str_output[idx] == 'M':
                systemd_memory["systemd_volttron_service"] = float(val.strip())
            else:
                systemd_memory["systemd_volttron_service"] = float(val.strip())/1024
        target = "/system.slice/volttron.service"
        idx = str_output.find(target)
        if idx > -1:
            l = 0
            idx += len(target)
            val = ""
            while str_output[idx] != '/' and l < 200:
                val += str_output[idx]
                l += 1
                idx += 1
            pid["run-volttron"] = int(''.join(c for c in val if c.isdigit()))
        target = "system/run-volttron"
        idx = str_output.find(target)
        if idx > -1:
            l = 0
            idx += len(target)
            val = ""
            while str_output[idx] != '/' and l < 200:
                val += str_output[idx]
                l += 1
                idx += 1
            pid["volttron"] = int(''.join(c for c in val if c.isdigit()))
        return pid, systemd_memory


class AgentPID:
    "The AgentPID is Singleton Class"

    @staticmethod
    def get_list():
        """
        :return: pair of agent id and pid number {agent_id: pid_number}
        :rtype: dict[str, int]
        """

        pid = {}
        output = subprocess.check_output('vctl status', shell=True)
        str_output = output.decode('UTF-8')
        str_output_list = str_output.split('\n')
        if len(str_output_list) > 1:
            for i in str_output_list:
                row = i.split()
                if len(row) == 7:
                    if row[5].find('[') > -1 and row[5].find(']') > -1:
                        pid[row[2]] = int(row[5].replace('[', '').replace(']', ''))
        return pid


class PIDMemory:
    "The PIDMemory is Singleton Class"

    @staticmethod
    def memory_usage(pid):
        """
        :param pid: Process ID
        :type pid: int

        :return: memory usage in kB
        :rtype: int
        """

        output = subprocess.check_output(f'pmap {pid} | tail -n 1', shell=True)
        str_output = output.decode('UTF-8')
        if str_output.find("total") > -1:
            memus = str_output.split()
            if len(memus) > 1:
                return int(memus[1].replace("K", "")) # return memory usage in kB
        return None


class MemoryUsage:

    def __init__(self, controller, memory_usage_id):
        self._controller = controller
        self._memory_usage_id = memory_usage_id
        self._memories = {}

        self._is_first_time = True

    def check_memory(self):
        if not self._is_first_time:
            self._memories = {}
            total_memory_usage = 0
            agent_pid_list = AgentPID.get_list()
            agent_pid_list_from_systemd, systemd_memory_usage = VolttronSystemd.get_pid_and_memory_usage()
            agent_pid_list.update(agent_pid_list_from_systemd)
            available_memory = ProcMeminfo.get_available_memory()
            for k, v in agent_pid_list.items():
                pid_memory = PIDMemory.memory_usage(v)/1024 # memory in MB
                self._memories[k] = {
                    "pid": v,
                    "memory_usage": pid_memory
                }
                total_memory_usage += pid_memory
            self._memories["total_memory_usage"] = {
                "pid": "unknown",
                "memory_usage": total_memory_usage
            }
            self._memories["systemd_volttron_service"] = {
                "pid": "unknown",
                "memory_usage": systemd_memory_usage["systemd_volttron_service"]
            }
            self._memories["available_memory"] = {
                "pid": "unknown",
                "memory_usage": available_memory["available_memory"]/1024
            }
            self.emit_memory_usage()
        self._is_first_time = False

    def emit_memory_usage(self):
        output_topic = f'''os_memory/{self._controller.core.identity}/{self._memory_usage_id}/event'''
        data = {
            "memory_usage_id": self._memory_usage_id,
            "type": "memory_usage",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "data": self._memories
        }
        _log.debug(f"MemoryUsage emit_memory_usage {self._memory_usage_id} {self._memories}")
        self._controller.publish(output_topic, data, "event")


def memoryusagemonitor(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Memoryusagemonitor
    :rtype: Memoryusagemonitor
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    agent_name = config.get('agent_name', "memory_usage_monitor")
    memory_usage_id = config.get('memory_usage_id', "memory_usage_1")
    sampling_rate = int(config.get('sampling_rate', 60))

    return Memoryusagemonitor(agent_name, memory_usage_id, sampling_rate, **kwargs)


class Memoryusagemonitor(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, agent_name, memory_usage_id, sampling_rate, **kwargs):
        super(Memoryusagemonitor, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self._memory_usages = {}

        self.agent_name = agent_name
        self.memory_usage_id = memory_usage_id
        self.sampling_rate = sampling_rate

        self.default_config = {"agent_name": agent_name,
                               "memory_usage_id": memory_usage_id,
                               "sampling_rate": sampling_rate}

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
            agent_name = config["agent_name"]
            memory_usage_id = config["memory_usage_id"]
            sampling_rate = config["sampling_rate"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.agent_name = agent_name
        self.memory_usage_id = memory_usage_id
        self.sampling_rate = sampling_rate

        self._memory_usages[self.memory_usage_id] = MemoryUsage(self, self.memory_usage_id)

        self.core.periodic(self.sampling_rate, self._period_signal)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        
        _log.debug("Memoryusagemonitor stop")

    def _period_signal(self):
        for k, v in self._memory_usages.items():
            v.check_memory()

    def publish(self, topic, value, mtype):
        """
        Publish to the Volttron bus
        :param topic: The topic to publish to.
        :type topic: string
        :param value: The message payload
        :type value: as needed
        :param mtype: The type to set in the header, command, evemt, request or response.
        :returns: None
        :rtype: None
        """

        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            message=value,
            headers={
                "requesterID": self.core.identity,
                "message_type": mtype,
                "TimeStamp": dt.datetime.utcnow()
                .replace(tzinfo=dt.timezone.utc)
                .isoformat(),
            },
        )


def main():
    """Main method called to start the agent."""
    utils.vip_main(memoryusagemonitor, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
