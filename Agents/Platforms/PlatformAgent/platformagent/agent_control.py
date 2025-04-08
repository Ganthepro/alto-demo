import logging
import gevent
import subprocess

_log = logging.getLogger(__name__)


class AgentControl:
    __method_name__ = ['start', 'stop', 'restart', 'disable', 'enable']
    __expected_messages__ = ['Starting', 'Stopping', ['Stopping', 'Starting'], 'Disabling', 'Enabling']
    
    def control_agent(self, agent_tag: str, method_name: str = "restart", retry_count: int = 1) -> bool:
        """
        control agent through Volttron's CLI ex. start/stop/restart any agent based on `agent_tag`
        """

        # validate input parameters
        if method_name not in AgentControl.__method_name__:
            raise Exception("AgentControl: invalid `method_name` input")

        # get expected output message keywords
        expected_messages = AgentControl.__expected_messages__[AgentControl.__method_name__.index(method_name)]
        if not isinstance(expected_messages, list):
            expected_messages = [expected_messages]

        # control agent through Volttron's CLI
        for _ in range(retry_count):
            output, error = subprocess.Popen(['vctl', str(method_name), '--tag', agent_tag], stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
            if all(expected_message in output.decode('utf-8') for expected_message in expected_messages):
                _log.debug(f"AgentControl: Successfully {method_name} agent [{agent_tag}]")
                return True
            gevent.sleep(1)
        
        _log.debug(f"AgentControl: Failed to {method_name} agent [{agent_tag}]")
        return False

    def check_good_status(self, agent_tag: str) -> bool:
        output, error = subprocess.Popen(['vctl', 'status', '--tag', agent_tag], stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
        head, message, none = output.decode('utf-8').split("\n")
        status = message.split(" ")
        return 'GOOD' in status


if __name__ == '__main__':
    agent_control = AgentControl()
    response_status = agent_control.control_agent(agent_tag="", method_name="restart", retry_count=3)
    print('response_status: ', response_status)
