"""
BACnet agent for getting IoT data from BACnet devices. This agent will be mainly used for getting data from Niagara 4
"""

__docformat__ = 'reStructuredText'

import json
import logging
import sys
from queue import PriorityQueue
from threading import Thread

import BAC0
import gevent
import pendulum
import yaml

from volttron.platform.agent import utils
from volttron.platform.scheduling import periodic
from volttron.platform.vip.agent import Agent

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "1.0"

WRITE_PRIORITY = 1
READ_PRIORITY = 2


def bacnet(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Bacnet
    :rtype: Bacnet
    """
    config = utils.load_config(config_path)
    if not config:
        raise "Configuration for BACnet Agent not found."

    # Get the data from config, otherwise use defaults (2nd argument)
    agent_config = config['volttron_agents']['bacnet']
    location = config["location"]

    devices_config = agent_config['devices']
    ip_address = agent_config.get("ip_address", "127.0.0.1")
    interval = agent_config.get("interval", 5)

    return Bacnet(ip_address, interval, devices_config, location, config, **kwargs)


class Bacnet(Agent):
    """
    BACnet Volttron Agent for getting data and controlling BACnet devices.

    Args:
        ip_address (str): IP address of the host machine
        interval (int): Number of seconds between each data polling
        devices_config (dict): Dictionary container devices and points configuration
        location (str): Location of the agent
        default_config (dict): Dictionary containing the default configuration in site YAML file

    """

    def __init__(self, ip_address, interval, devices_config, location, default_config, **kwargs):
        super(Bacnet, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.ip_address = ip_address
        self.interval = interval
        self.devices_config = devices_config
        self.location = location

        self._command_queue = PriorityQueue()
        self.start_bacnet_communication()

        self.default_config = default_config.copy()

        # Set a default configuration to ensure that self.configure is called immediately to set up
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

        try:
            agent_config = config['volttron_agents']['bacnet']
            location = config["location"]

            devices_config = agent_config['devices']
            ip_address = agent_config.get("ip_address", "127.0.0.1")
            interval = agent_config.get("interval", 5)
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.ip_address = ip_address
        self.interval = interval
        self.devices_config = devices_config
        self.location = location

        # Subscribe to topic /bacnet/<device_id>/command and receive the commands
        self._create_subscriptions()

        # Set schedule to read all data from config file and publish to topic /bacnet/bacnet/<device_id>/event
        _log.info(f"Bacnet agent will read every {self.interval} seconds")
        self.core.schedule(periodic(self.interval), self.emit_data_from_bacnet_devices)

    def emit_data_from_bacnet_devices(self):
        """
        This method is periodically called to poll data from BACnet devices and publish to the message bus
        """
        try:
            for dev_id, dev_info in self.devices_config.items():

                bacnet_ip = dev_info["bacnet_ip"]
                dev_points = dev_info["points"]

                cmd = f"{bacnet_ip}"

                p_list = []  # A list of datapoint names to be read
                for p, p_addr in dev_points.items():
                    p_list.append(p)
                    cmd += " "
                    cmd += f"{p_addr} presentValue"

                dev_payload = {
                    "device_id": dev_id,
                    "model": dev_info['model'],
                    "location": self.location,
                }
                args = {'device_payload': dev_payload, 'points': p_list}
                args = json.dumps(args)

                self._command_queue.put((READ_PRIORITY, cmd, args))

        except Exception as e:
            _log.exception(f"Error sending sample data: {e}")

    def start_bacnet_communication(self):
        """ Initiate a forever-running thread for BACnet communication """
        _log.info("Starting thread for BACnet communication")
        thread = Thread(target=self._bacnet_thread, name="bacnet", daemon=True)
        thread.start()
        return thread

    def _bacnet_thread(self):
        """
        A function for BACnet communication thread. This function will be called when the agent is started and run
        indefinitely until the agent is stopped.

        This thread will continuously read the command from the queue and execute the command. There are 2 types of
        commands that can be executed which are WRITE and READ.
        - WRITE command: to send the command to the BACnet device
            cmd format = "192.168.10.51 binaryOutput 58 presentValue inactive - 1"
        - READ command: to read the data from the BACnet device
            cmd format = "192.168.10.51"

        The self._command_queue will emit a tuple of (priority, cmd)
        - priority: the priority of the command. The priority is used to determine whether the command is a WRITE (1) or
        READ (2) command
        - cmd: the command to be executed.

        """
        gevent.sleep(0.05)
        BAC0.log_level('error')
        # Step 1: Start BACnet communication by initiating a client
        client = None
        while client is None:
            try:
                _log.info("IP ADDRESS: " + self.ip_address)
                if self.ip_address:
                    client = BAC0.lite(ip=self.ip_address, port=0xBAC0)
                else:
                    client = BAC0.lite(port=0xBAC0)
            except Exception as e:
                _log.exception(f"Error connecting to BACnet: {e}")
                gevent.sleep(10)
                # return

        # Step 2: Run the BACnet communication on thread indefinitely
        while True:
            gevent.sleep(0.05)
            try:
                priority, cmd, args = self._command_queue.get()
                if args:
                    args = json.loads(args)

                # Step 3.1: If the command is WRITE command, execute the command
                if priority == WRITE_PRIORITY:
                    # FORMAT: bacnet.write("192.168.10.51 binaryOutput 58 presentValue inactive - 1")
                    _log.info(f"WRITE_PRIORITY : {cmd}")
                    self._handle_write_priority_command(client, cmd, args)

                # Step 3.2: If the command is READ command, execute the command
                elif priority == READ_PRIORITY:
                    self._handle_read_priority_command(client, cmd, args)

                self._command_queue.task_done()

            except Exception as err:
                _log.warning(f"Error: Problem with BACnet Operation")
                _log.exception(f"Error: {err}")

    def _handle_read_priority_command(self, client: BAC0.lite, cmd: str, args: dict):
        """
        Handle the READ command. This function will be called when the READ command is executed

        Args:
            client (BAC0.lite): The BAC0 client
            cmd (str): The bacnet command to be executed using bacnet.readMultiple() function
            args (dict): The dictionary containing the device information and list of points

        """
        # Step 1: Get the device information from args dictionary
        device_payload: dict = args.get("device_payload", None)
        points: list = args.get("points", None)

        if device_payload is None:
            _log.error("READ_PRIORITY: 'device_information' is missing from args")
            return
        if points is None:
            _log.error("READ_PRIORITY: 'points' is missing from args")
            return

        _log.debug(f"READ_PRIORITY : {cmd}")

        # Step 2: Attempt to read the data from the BACnet device
        try:
            values = client.readMultiple(cmd, timeout=0.3)
        except Exception as e:
            address = cmd.split(" ")[0]
            _log.exception(f"READ_PRIORITY: {cmd} to {address} failed due to error {e}")
            return

        # Step 3: Construct the payload to be published to the message bus
        payload = device_payload.copy()
        original_len = len(payload)
        for p, v in zip(points, values):
            v = {'inactive': 0, 'active': 1}.get(v, v)
            if v != '' and v is not None:
                payload[p] = v

        # Step 4: Publish the payload to the message bus
        if len(payload) > original_len:
            self.publish(payload)
        else:
            _log.warning(f"Cannot read data from '{device_payload['device_id']}'")

    def publish(self, message: dict):
        """
        Update "timestamp" and "unix_timestamp" to the message and publish to the message bus

        Args:
            message (dict): The dictionary containing the message to be published to the message bus. This dictionary
            should contain the "device_id" key

        """
        timestamp = int(pendulum.now().timestamp())
        datetime = pendulum.from_timestamp(timestamp, tz='Asia/Bangkok').isoformat()

        device_id = message.get("device_id")
        topic = f"datalogger/{self.core.identity}/{device_id}/event"

        headers = {
            "requesterID": self.core.identity,
            "message_type": "event",
            "TimeStamp": datetime
        }
        message.update({
            "timestamp": timestamp,
            "datetime": datetime
        })
        _log.debug(f"Publish message : {message}")
        self.vip.pubsub.publish("pubsub", topic, headers=headers, message=message)

    def _handle_write_priority_command(self, client: BAC0.lite, cmd: str, args: dict):
        """
        Handle the WRITE command. This function will be called when the WRITE command is executed

        Args:
            client (BAC0.lite): The BAC0 client
            cmd (str): The bacnet command to be executed using bacnet.readMultiple() function
            args (dict): The dictionary containing the device information and list of points

        """
        # Step 1: Parse the command into variables
        try:
            address, obj_type, obj_instance, prop, value, _, priority = cmd.split(" ")
        except Exception as e:
            _log.error(f"Cannot parse the command '{cmd}'")
            return

        # Step 2: Attempt to write the data to the BACnet device
        # TODO: Add checks for command response whether it is successful or not
        try:
            gevent.sleep(0.05)
            _log.info(f"WRITE_PRIORITY : Executing ... {cmd}")
            client.write(cmd, timeout=1)
        except Exception as e:
            # TODO: Add notification to the user
            _log.error(f"WRITE_PRIORITY: {cmd} to {address} failed due to error {e}")

    def _create_subscriptions(self):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        # Subscribe to the command topic from message bus starting with /bacnet
        # If so, `_handle_command`` function will be activated
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="bacnet",
                                  callback=self._handle_command_message)

    def _handle_command_message(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the commanding message received from message bus with topic starting with /bacnet
        """
        _log.info(f"RECEIVE COMMAND FROM TOPIC : {topic}, MESSAGE: {message}")

        # Step 1: If topic is not in the format of /bacnet/{agent_name}/{device_id}/command
        if len(topic.split("/")) != 4:
            _log.error(f"Invalid topic format: {topic}")
            return

        # Step 2: Split the topic to get the "device_id" and "message_type"
        schema, agent_name, device_id, message_type = topic.split("/")
        if isinstance(message, str):
            message = json.loads(message)

        if message_type == "command":

            # Get the command from the message received from message bus
            command = message["action"]["command"]

            # Get the controlled device from the configuration file
            controlled_device = self.devices_config.get(device_id)
            if controlled_device is None:
                _log.warning(f"Device '{device_id}' is not in the configuration file and the command will be ignored")
                return
            else:
                bacnet_ip = controlled_device["bacnet_ip"]

            for command_point, value in command.items():

                if command_point not in controlled_device['points']:
                    _log.warning(
                        f"Command point '{command_point}' is not in the configuration for device '{device_id}' and the command will be ignored")
                    continue
                else:
                    point_addr = controlled_device['points'][command_point]

                    if 'binary' in point_addr:
                        value = str(value)
                        value = {
                            '0': 'inactive',
                            '1': 'active',
                            'True': 'active',
                            'False': 'inactive'
                        }.get(value, value)

                    cmd = f"{bacnet_ip} {point_addr} presentValue {value} - 10"  # Send command to BACnet priority 10

                    self._command_queue.put((WRITE_PRIORITY, cmd, None))


def main():
    """Main method called to start the agent."""
    utils.vip_main(bacnet,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
