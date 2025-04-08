import subprocess


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
        str_output = output.decode('UTF-8')
        str_output_list = str_output.split('\n')
        if len(str_output_list) > 1:
            for i in str_output_list:
                row = i.split()
                if "Memory:" in i:
                    if len(row) >= 2:
                        systemd_memory["systemd_volttron_service"] = float(row[1].replace("M", ""))
                elif "system/run-volttron" in i:
                    if len(row) == 3:
                        pid["run-volttron"] = int(''.join(c for c in row[0] if c.isdigit()))
                elif "env/bin/volttron" in i:
                    if len(row) >= 3:
                        pid["volttron"] = int(''.join(c for c in row[0] if c.isdigit()))
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


total_memory_usage = 0
agent_pid_list = AgentPID.get_list()
for k, v in agent_pid_list.items():
    pid_memory = PIDMemory.memory_usage(v)/1000
    print(f"{k} ({v}): {pid_memory} MB")
    total_memory_usage += pid_memory
print(total_memory_usage)
# agent_pid_list, mem_u = VolttronSystemd.get_pid_and_memory_usage()
# print(agent_pid_list, mem_u)
# for k, v in agent_pid_list.items():
#     pid_memory = PIDMemory.memory_usage(v)/1024
#     print(f"{k} ({v}): {pid_memory} MB")
# print(ProcMeminfo.get_available_memory())
# print(help(VolttronSystemd))
