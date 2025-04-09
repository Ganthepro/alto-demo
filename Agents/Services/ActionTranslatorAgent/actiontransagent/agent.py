"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from copy import deepcopy
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

# BETA, FIELD_HOSPITAL, FIELD_HOSPITAL2, DAIKIN_CCC, V3
MARK = "V3" # BETA, for tower as room. GENERAL, for normal hotel structure

num_to_dayofweek = ["", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def actiontransagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Actiontransagent
    :rtype: Actiontransagent
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    for k, v in config.items():
        setattr(self, k, v)
        self._loattr[k] = v
        kwargs[k] = v
    return Actiontransagent(
        **kwargs)

class AltoNotImpl(Exception):
    """
        Exception raised when a method must be overloaded but has not been.

    """

    pass

class Actiontransagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self,
                 **kwargs):
        super(Actiontransagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self._loattr = {}
        for k, v in kwargs.items():
            setattr(self, k, v)
            self._loattr[k] = v

        self.default_config = self._loattr

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
            for k, v in config.items():
                setattr(self, k, v)
                self._loattr[k] = v
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self._create_subscriptions("")

    def _create_subscriptions(self, topic):
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=f"app/{self.agent_name}/{self.feature_name}/request",
                                  callback=self._handle_publish)

        ## reformatting the json from subscribe iot hub to volttron bus

    def _handle_publish(self, peer, sender, bus, topic, headers, message):

        if self.core.identity != sender:
            if message["trigger"]["trigger_type"] == "schedule":
                self.configautomation_schedule(message)
            elif message["trigger"]["trigger_type"] == "device":
                self.configautomation_device(message)
            elif message["trigger"]["trigger_type"] == "event":
                self.configautomation_event(message)

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
        # self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        # Exmaple RPC call
        # self.vip.rpc.call("some_agent", "some_method", arg1, arg2)

    def backend_to_volttron(self, actions_backendformat):
        ## actions
        _log.debug(f'Actiontrans {actions_backendformat}')
        action_tasks = actions_backendformat
        actions = []
        for action in action_tasks:
            if "command" in action:
                act = "command"
            elif "config" in action:
                act = "config"
            elif "learn" in action:
                act = "learn"
            else:
                raise Exception("Action that send from iothub is not supported.")
            inmsg_topic = [action["schema"], action["agent_id"], action["device_id"], act]
            payload = action[act]
            if "subdevice_idx" in action:
                payload["subdevice_idx"] = action["subdevice_idx"]
            else:
                raise Exception("You need to specify 'subdevice_idx' in the action")
            inmsg_action = [inmsg_topic, payload]
            actions.append(inmsg_action)

        return actions

    def _num_to_dayofweek(self, num: int):
        '''

        :param num: 1,2,3,4,5,6,7
        :return: day of week in string e.g. "monday", "tuesday"
        '''
        return num_to_dayofweek[num]

    def cron_decoder(self, time_cronformat):
        '''
        this function conver time in crontab format to actionagent format (francois)
        :param time_cronformat: time in string copy cron format --> ['*','*','*','*','*','*']
        :return: time_actionformat
        '''


        ##formatting time from cron format
        time_cronformat = [int(i) if i != "*" else i for i in time_cronformat ]
        _log.debug(time_cronformat)
        minute = time_cronformat[0]
        hour = time_cronformat[1]
        day = time_cronformat[2]
        month = time_cronformat[3]
        day_of_week = time_cronformat[4]
        year = time_cronformat[5]
        time = {"hour": hour,
                "minute": minute}

        #mapping day of week

        schedule_specific_config = {}
        if '*' in time_cronformat[:4] + time_cronformat[5:]:
            occurence = "every"
            if day_of_week != "*":
                repeat = "day of week"
                day_of_week = self._num_to_dayofweek(day_of_week)
                time_actionformat = self.schedule_periodic_date(time, occurence, repeat, day_of_week=day_of_week)

            elif day == '*':
                repeat = "day"
                time_actionformat = self.schedule_periodic_date(time, occurence, repeat)

            elif month == '*':
                repeat = "month"
                time_actionformat = self.schedule_periodic_date(time, occurence, repeat, day=day)

            elif year == '*':
                repeat = "year"
                time_actionformat = self.schedule_periodic_date(time, occurence, repeat, day=day, month=month)

            elif minute == "*" or hour == "*":
                raise Exception("Scheduling the time is not supported.")
            else:
                raise Exception("Scheduling is too complex, not supported yet")

        else:
            time_actionformat = self.schedule_specific_date(time, day, month, year)

        return time_actionformat

    def schedule_periodic_date(self, time: dict, occurence: str, repeat: str, **kwargs):
        '''

        :param time: {"hour": 12, "minute":30}
        :param occurence: "on", "every", "nth"
        :param kwargs: "day", "day of week", "month", "year"
        :return:
        '''

        time_trigger = {}
        time_trigger["occurrence"] = occurence
        time_trigger["value"] = {}
        time_trigger["value"]["time"] = time
        time_trigger["value"]["repeat"] = repeat
        for k, v in kwargs.items():
            if k == "day_of_week":
                k = "day of week"
            time_trigger["value"][k] = v

        return time_trigger

    def schedule_specific_date(self, time: dict, day: int, month: int, year: int):
        time_trigger = {}

        ## occurence = on, every, nth
        time_trigger["occurrence"] = "on"
        time_trigger["value"] = {}

        ## time to trigger event
        time_trigger["value"]["time"] = time
        time_trigger["value"]["day"] = day
        time_trigger["value"]["month"] = month
        time_trigger["value"]["year"] = year

        return time_trigger

    def to_automationagent_msg(self, automation_id, trigger, conditions, actions: list):
        '''

        :param topic: ['<schema>','<agent_name>','<device_id>','<event>']
        :param conditions: list of conditions
        :param actions: list of actions
        :return:
        '''
        to_automationagent_message = {"reply_to": f"datalogger/actiontranslator/schedule/response",
         "rid": "an id",
         "rules": {
             f"{automation_id}": {
                 "trigger": trigger,
                 "conditions": conditions,
                 "actions": actions
             }
         }
         }
        return to_automationagent_message

    def configautomation_schedule(self, message):
        '''
        time is in cron format
         cron time format
         for example
         ['00','12','*','*','*','*']
         [minutes, hours, day, month, day of week, year]
        '''
        ##trigger object
        _log.debug(f"in automation schedule {message}")
        trigger_object = message["trigger"]["trigger_time"]["cron"]
        automation_id = message["automation_id"]

        time_actionformat = self.cron_decoder(trigger_object)

        ## actions
        if message["allow_notification"] and MARK == "V3":
            noti_body = {
                "trigger_type": "schedule",
                "trigger_time": "",
                "automation_id": automation_id,

                "condition_event": "",
                "condition_value": "",

                "status": "unknown",
                "reason": ""
            }
            tmp = {
                'device_id': 'notify_001',
                'agent_id': 'notifyapi',
                'subdevice_idx': 0,
                'subdevice_name': 'na',
                'room_name': 'na',
                'command': noti_body,
                'schema': 'notify'
            }
            msg_actions = deepcopy(message["action"])
            _log.debug(f'Actiontrans {msg_actions} {type(msg_actions)}')
            _log.debug(f'Actiontrans {tmp} {type(tmp)}')
            msg_actions.append(tmp)
            _log.debug(f'Actiontrans {msg_actions}')
            actions = self.backend_to_volttron(msg_actions)
        else:
            actions = self.backend_to_volttron(message["action"])


        schedule_message = self.to_automationagent_msg(automation_id, time_actionformat, [], actions)

        self.vip.pubsub.publish(peer="pubsub",
                                topic="config/automation/add_rules",
                                headers={"message_type": "request",
                                         "identity": self.core.identity},
                                message=schedule_message)
        _log.debug(schedule_message)

    def convert_a_dictitem_tolist(self,dict):

        return list(list(dict.items())[0])
    
    def convert_dictitems_tolist(self,dict):
        
        return dict.items()

    def get_key_indict(self, dict):
        '''

        :param dict: {<key1>:<value1> }
        :return: <key1>
        '''
        return list(dict.keys())[0]

    def get_value_indict(self, dict):
        '''

        :param dict: {<key1>:<value1> }
        :return: <value1>
        '''
        return list(dict.values())[0]

    def triggerevent_to_volttron(self, dict):
        
        event = self.get_key_indict(dict) # pms
        event_payload = dict[event] # {"room_201":{"is":"}}
        device = self.get_key_indict(event_payload)
        return

    def configautomation_device(self, message):

        ## trigger conditions
        _log.debug(f"in automation device {message}")
        automation_id = message["automation_id"]
        trigger_object = message["trigger"]["trigger_device"]
        object_schema = trigger_object["schema"]
        object_agentname = trigger_object["agent_id"]
        if MARK == "BETA": # should make this configable
            object_deviceid = trigger_object["room_name"]
        else:
            object_deviceid = trigger_object["device_id"]

        ##event of the device
        if "event" in trigger_object:
            trigger_event = "event"
        elif "command" in trigger_object  :
            trigger_event = "command"
        elif "config" in trigger_object:
            trigger_event = "config"
        else:
            trigger_event = ""


        ##  conditions to take actions
        if trigger_event != "":
            condition_tasks = trigger_object[trigger_event]

        if message["condition"]["condition_event"] != "":
            if trigger_object["schema"] in ["device", "environment", "location", "electric", "charger"]:
                object_schema = "sensor"
                # trigger_event = "sample"
                trigger_event = message["condition"]["condition_event"]

        conditions = []

        if message["condition"]["condition_event"] == "":
            raise AltoNotImpl("condition is to be implemented")

        for key, condition in condition_tasks.items():
            condition_type = "event"
            if condition_type == "timing":
                operator = condition["condition_comparator"][0]
                value = condition["condition_comparator"][1]
                inmsg_cond = [condition_type, value, operator]
            elif condition_type == "event":
                
                key_in_payload = key
                comparator = self.convert_a_dictitem_tolist(condition)
                inmsg_cond = [condition_type, key_in_payload, comparator]

            try:
                conditions.append(inmsg_cond)
            except Exception as e:
                _log.debug(f"Error in creating conditions for messages: {e}")

        ## actions
        if message["allow_notification"] and MARK == "V3":
            con_val = message["condition"]["condition_value"]
            trigger_parameter = list(trigger_object["event"].keys())[0]
            custom_msg = {}
            if isinstance(con_val, dict) and con_val:
                if "force_schema" in con_val:
                    object_schema = con_val["force_schema"]
                # for con_key in con_value:
                #     dp_list["trigger_value_" + con_key] = f"__event__{con_key}",
                dp_list = con_val["dp_list"]
                sec_len = con_val["section_length"]
                # dp_list_str = ""
                # for idx, i in enumerate(dp_list):
                #     if idx == 0:
                #         dp_list_str += i
                #     else:
                #         dp_list_str += f",{i}"
                # custom_msg["dp_list_str"] = dp_list_str
                custom_msg["section_length"] = sec_len
                for i in range(sec_len):
                    sec_msg = con_val["sec_" + str(i)]
                    if sec_msg not in dp_list:
                        custom_msg["sec_" + str(i)] = sec_msg
                    else:
                        custom_msg["sec_" + str(i)] = f"__event__{sec_msg}"
            noti_body = {
                "trigger_type": "device",
                "trigger_device": "",
                "room_name": trigger_object["room_name"],
                "subdevice_name": trigger_object["subdevice_name"],
                "trigger_parameter": trigger_parameter,
                "trigger_symbol": "=",
                "trigger_value": f"__event__{trigger_parameter}",
                "automation_id": automation_id,

                "condition_event": "",
                "condition_value": "",

                "status": "unknown",
                "reason": ""
            }
            noti_body.update(custom_msg)
            tmp = {
                'device_id': 'notify_001',
                'agent_id': 'notifyapi',
                'subdevice_idx': 0,
                'subdevice_name': 'na',
                'room_name': 'na',
                'command': noti_body,
                'schema': 'notify'
            }
            msg_actions = deepcopy(message["action"])
            _log.debug(f'Actiontrans {msg_actions} {type(msg_actions)}')
            _log.debug(f'Actiontrans {tmp} {type(tmp)}')
            msg_actions.append(tmp)
            _log.debug(f'Actiontrans {msg_actions}')
            actions = self.backend_to_volttron(msg_actions)
        elif message["allow_notification"] and MARK == "FIELD_HOSPITAL":
            tmp = [
                {
                    'device_id': 'line_001',
                    'agent_id': 'notifyapi',
                    'subdevice_idx': 0,
                    'subdevice_name': 'na',
                    'room_name': 'room10',
                    'command': {'notify_message': message["notification_message"]},
                    'schema': 'notify'
                }
            ]
            actions = self.backend_to_volttron(tmp)
        elif message["allow_notification"] and MARK == "FIELD_HOSPITAL2":
            tmp = [
                {
                    'device_id': 'linefire_001',
                    'agent_id': 'notifyapi',
                    'subdevice_idx': 0,
                    'subdevice_name': 'na',
                    'room_name': 'room10',
                    'command': message["condition"]["condition_value"],
                    'schema': 'notify'
                }
            ]
            actions = self.backend_to_volttron(tmp)
        elif message["allow_notification"] and MARK == "BETA":
            conditions.append([
                "event",
                "subdevice_idx",
                [
                    "==",
                    trigger_object["subdevice_idx"]
                ]
            ])
            message["condition"]["condition_value"]["sensor_id"] = trigger_object["device_id"]
            tmp = [
                {
                    'device_id': 'linefire_001',
                    'agent_id': 'notifyapi',
                    'subdevice_idx': 0,
                    'subdevice_name': 'na',
                    'room_name': 'room10',
                    'command': message["condition"]["condition_value"],
                    'schema': 'notify'
                }
            ]
            actions = self.backend_to_volttron(tmp)
        else:
            actions = self.backend_to_volttron(message["action"])

        ## convert to message that automationagent understand
        trigger = {}
        trigger["topic"] = [object_schema, object_agentname, object_deviceid, trigger_event]
        device_message = self.to_automationagent_msg(automation_id, trigger, conditions, actions)

        self.vip.pubsub.publish(peer="pubsub",
                                topic="config/automation/add_rules",
                                headers={"message_type": "request",
                                         "identity": self.core.identity},
                                message=device_message)
        _log.debug(f"Actiontrans device_message {device_message}")

    def configautomation_event(self, message):

        ## trigger conditions
        _log.debug("in automation 3rd party")
        automation_id = message["automation_id"]
        trigger_object = message["trigger"]["trigger_event"]
        hotel_name = "mintel"
        for event, payload in trigger_object.items(): ## event = pms , payload = "room_201":{"is": "check_in"}
            """
            'first' {
                'second': {
                    'third': 'fourth'
                }
            }
            """

            object_schema = event ## pms
            if MARK == "V3":
                object_schema = "custom_event"
                object_agentname = event ## first
                object_deviceid = self.get_key_indict(payload) ## second
                tmp = self.get_key_indict(payload[object_deviceid])
                object_trigger = self.get_value_indict(payload[object_deviceid]) ## fourth
            else:
                object_agentname = hotel_name ## hotel_name = mintel
                object_deviceid = self.get_key_indict(payload) ## object_deviceid = room_201
                object_trigger = self.get_value_indict(payload[object_deviceid]) ## object_command = "check_in"

        ##  conditions to take actions
        ## to be implemented
        conditions = []

        if "condition_event" in "condition":

            raise AltoNotImpl("condition is to be implemented")

        ## actions
        if MARK == "V3":
            trigger_parameter = list(trigger_object["event"].keys())[0]
            noti_body = {
                "trigger_type": "device",
                "trigger_device": "",
                "room_name": trigger_object["room_name"],
                "subdevice_name": trigger_object["subdevice_name"],
                "trigger_parameter": trigger_parameter,
                "trigger_symbol": "=",
                "trigger_value": f"__event__{trigger_parameter}",
                "automation_id": automation_id,

                "condition_event": "",
                "condition_value": "",

                "status": "unknown",
                "reason": ""
            }
            tmp = {
                'device_id': 'notify_001',
                'agent_id': 'notifyapi',
                'subdevice_idx': 0,
                'subdevice_name': 'na',
                'room_name': 'na',
                'command': noti_body,
                'schema': 'notify'
            }
            msg_actions = deepcopy(message["action"])
            _log.debug(f'Actiontrans {msg_actions} {type(msg_actions)}')
            _log.debug(f'Actiontrans {tmp} {type(tmp)}')
            msg_actions.append(tmp)
            _log.debug(f'Actiontrans {msg_actions}')
            actions = self.backend_to_volttron(msg_actions)
        else:
            actions = self.backend_to_volttron(message["action"])
        
        ## convert to message that automationagent understand
        trigger = {}
        trigger["topic"] = [object_schema, object_agentname, object_deviceid, object_trigger]
        event_message = self.to_automationagent_msg(automation_id, trigger, conditions, actions)

        self.vip.pubsub.publish(peer="pubsub",
                                topic="config/automation/add_rules",
                                headers={"message_type": "request",
                                         "identity": self.core.identity},
                                message=event_message)
        _log.debug(f"event message: {event_message}")

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

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(actiontransagent,
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass