import json
import os
import subprocess
import logging
import time
import argparse


logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.DEBUG,
        datefmt='%Y-%m-%d %H:%M:%S')
_log = logging.getLogger(__name__)
# _log.setLevel("DEBUG")
_log.addHandler(logging.StreamHandler())
_log.addHandler(logging.FileHandler(os.path.expanduser('~/restart_with_memory_conditions.log')))

ap = argparse.ArgumentParser()
ap.add_argument("-c", "--config", required=True,
	help="path to config file")
args = vars(ap.parse_args())


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
    def get_memory_usage():
        """
        :return: The dict is pair of name and memory usage in MB {name: memory_usage}
        :rtype: dict[str, str]
        """

        systemd_memory = {}
        try:
            output = subprocess.check_output('systemctl status volttron.service', shell=True)
            str_output = output.decode('UTF-8')
            str_output_list = str_output.split('\n')
            if len(str_output_list) > 1:
                for i in str_output_list:
                    row = i.split()
                    if "Memory:" in i:
                        if len(row) >= 2:
                            systemd_memory["systemd_volttron_service"] = row[1]
        except Exception as e:
            _log.error(e)
        return systemd_memory

    @staticmethod
    def execute_cmd(cmd, passw=''):
        """
        :param cmd: command-line as list
        :type cmd: str
        :param passw: password
        :type passw: str
        """

        output = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate(input=(f'{passw}\n').encode('UTF-8'))
        return output[0].decode('UTF-8'), output[1].decode('UTF-8')

    @staticmethod
    def restart(passw):
        """
        :param passw: sudo password
        :type passw: str
        """

        try:
            output = VolttronSystemd.execute_cmd(["sudo", "-S", "systemctl", "restart", "volttron.service"], passw)
            _log.debug(f"VolttronSystemd restart {output}")
        except subprocess.CalledProcessError as e:
            _log.error(f"VolttronSystemd restart {e}")

    @staticmethod
    def stop(passw):
        """
        :param passw: sudo password
        :type passw: str
        """

        try:
            output = VolttronSystemd.execute_cmd(["sudo", "-S", "systemctl", "stop", "volttron.service"], passw)
            _log.debug(f"VolttronSystemd stop {output}")
        except subprocess.CalledProcessError as e:
            _log.error(f"VolttronSystemd stop {e}")

    @staticmethod
    def start(passw):
        """
        :param passw: sudo password
        :type passw: str
        """

        try:
            output = VolttronSystemd.execute_cmd(["sudo", "-S", "systemctl", "start", "volttron.service"], passw)
            _log.debug(f"VolttronSystemd start {output}")
        except subprocess.CalledProcessError as e:
            _log.error(f"VolttronSystemd start {e}")


class VolttronControl:
    "The VolttronControl is Singleton Class"

    @staticmethod
    def stop(agent_tag):
        try:
            run = subprocess.run(["vctl", "stop", "--tag", agent_tag], stdout=subprocess.PIPE)
            result = run.stdout.decode("utf-8")
            _log.debug(result)
            time.sleep(15)
            status = VolttronControl.check_status(agent_tag)
            _log.debug(f"stop: {status}")
            if status is None:
                return None
            if not status:
                return "STOPPED"
            return "STOP FAILED"
        except Exception as e:
            _log.error(f"stop Exception: {e}")

    @staticmethod
    def start(agent_tag):
        try:
            run = subprocess.run(["vctl", "start", "--tag", agent_tag], stdout=subprocess.PIPE)
            result = run.stdout.decode("utf-8")
            _log.debug(result)
            time.sleep(30)
            status = VolttronControl.check_status(agent_tag)
            _log.debug(f"start: {status}")
            if status is None:
                return None
            if status:
                return "STARTED"
            return "START FAILED"
        except Exception as e:
            _log.error(f"start Exception: {e}")

    @staticmethod
    def check_status(agent_tag):
        run = subprocess.run(["vctl", "status"], stdout=subprocess.PIPE)
        result = run.stdout.decode("utf-8")
        _log.debug(result)
        sp_line = result.split("\n")
        _log.debug(sp_line)
        for k in sp_line:
            l = k.split()
            if len(l) > 3:
                if agent_tag == l[3]:
                    if l[4] == "running":
                        return True
                    else:
                        return False
        return None


if __name__ == "__main__":
    try:
        config = None
        # dir_path = os.path.dirname(os.path.realpath(__file__))
        _log.debug(f"config path {args['config']}")
        with open(args["config"], "r") as configf:
            config = json.load(configf)
            _log.debug(f"config {config}")
        memory_limit = config["memory_limit"]["value"]
        sudo_password = config["sudo_password"]
        available_memory = ProcMeminfo.get_available_memory()["available_memory"]/1024
        _log.debug(f"memory_limit {memory_limit}")
        _log.debug(f"available_memory {available_memory}")
        if available_memory < memory_limit:
            pre_mem = VolttronSystemd.get_memory_usage().get("systemd_volttron_service", "")
            _log.debug(f"pre-memory {pre_mem}")
            # VolttronSystemd.restart(sudo_password)
            VolttronSystemd.stop(sudo_password)
            time.sleep(120) # 2 min
            VolttronSystemd.start(sudo_password)
            max_retry = 2
            while max_retry > 0 and False: # put False for disable start action_room 
                time.sleep(120)
                ret = VolttronControl.start("action_room")
                max_retry -= 1
                if ret is not None:
                    if ret == "STARTED":
                        max_retry = 0
                        _log.debug(f"action_room is {ret}")
            time.sleep(10)
            post_mem = VolttronSystemd.get_memory_usage().get("systemd_volttron_service", "")
            _log.debug(f"post-memory {post_mem}")
    except Exception as e:
        _log.error(f"{e}")

