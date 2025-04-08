"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'
import json
import logging
import sys
import random
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub, compat
from volttron.platform.scheduling import cron, periodic
import subprocess
import asyncio

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"
mapping_schema_to_command = {"ac":"set",
                              "switch":"relay",
                             "tv_remote":"send"}
add_command_template = {"reply_to": "me/myself",
                   "rid": "an id",
                   "action": "add",
                   "name": "BlastOff",
                   "order": 1,
                   "device": [

                   ],
                   "command": "relay",
                   "mapping": {
                       "turn": [
                           "state",
                           [
                               [
                                   "on",
                                   "on"
                               ],
                               [
                                   "off",
                                   "off"
                               ]
                           ]
                       ]
                   }
                   }

def tester(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Tester
    :rtype: Tester
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Tester(setting1,
                          setting2,
                          **kwargs)


class Tester(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic",
                 **kwargs):
        super(Tester, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.y = 1
        self.setting1 = setting1
        self.setting2 = setting2

        self.default_config = {"setting1": setting1,
                               "setting2": setting2}


        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
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
            setting1 = int(config["setting1"])
            setting2 = str(config["setting2"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.setting1 = setting1
        self.setting2 = setting2

        self._create_subscriptions(self.setting2)

    def del_rules(self, del_rules):
        topic = f"config/scheduleagent/del_rules"
        message = {"reply_to": "replyto/schedule", "rid": self.core.identity,
                   "rules": del_rules}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "request"},
                                message=message)
    def del_commands(self, building,room,cmd_name ,order):
        topic = f"config/{building}/{room}/map"
        payload = {"reply_to": "me/myself",
                            "rid": "an id",
                            "action": "delete",
                            "name": cmd_name,
                            "order": order
                            }
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "request"},
                                message=payload)
        ## we find all rooms available in the hotel by retrieveing from all roomagents that run in the volttron
    def grep_rooms_from_vctl(self):
        cmd = ['vctl', 'status']
        grep = ['grep', 'room_']

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        end_of_pipe = subprocess.Popen(grep, stdin=proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        o, e = end_of_pipe.communicate(timeout=5)
        o = o.decode('ascii')
        room_list = []
        index = 0
        while index < len(o):
            index = o.find('room_', index)
            if index == -1:
                break
            room_list.append(o[index:index + 8])
            index += 8
        room_list = list(set(room_list))
        _log.debug(f"roomlist:-> {room_list}")
        return room_list

    @PubSub.subscribe(peer='pubsub', prefix='app/configapp/someconfig/add_rules')
    def recieve_from_sub_some(self, peer, sender, bus, topic, headers, commsg):
        _log.debug(f"topic in recieve from sub some: {topic}")
        self.messsage_from_sub_some = commsg
        self.vip.pubsub.publish(peer="pubsub",
                                topic='action/scheduleagent/list_rules',
                                headers={'requesterID': self.core.identity,
                                         "message_type": "request"},
                                message={"reply_to": "app/configapp/someconfig/next", "rid": "123"})

    @PubSub.subscribe(peer='pubsub', prefix='app/configapp/someconfig/add_rules')
    def recieve_from_sub_some(self, peer, sender, bus, topic, headers, commsg):
        _log.debug(f"topic in recieve from sub some: {topic}")
        self.messsage_from_sub_some = commsg
        self.vip.pubsub.publish(peer="pubsub",
                                topic='action/scheduleagent/list_rules',
                                headers={'requesterID': self.core.identity,
                                         "message_type": "request"},
                                message={"reply_to": "app/configapp/someconfig/next", "rid": "123"})

    @PubSub.subscribe(peer='pubsub', prefix='app/configapp/someconfig/next')
    def recieve_from_schedule(self, peer, sender, bus, topic, headers, commsg):
        _log.debug("for some")

        ##delete old rules before add new rules
        list_rules = list(commsg["rules"].keys())
        pre_del_rules = []
        room_list = self.messsage_from_sub_some["room"]
        for room in room_list:
            for rule in list_rules:
                if room in rule:
                    pre_del_rules.append(rule)
        self.del_rules(pre_del_rules)

        ##pubish the config command to each rooms.
        try:
            building = self.messsage_from_sub_some["building"]
            del_rules = []
            if self.messsage_from_sub_some["scope"] == "local":
                for room_no in room_list:
                    for day, v in self.messsage_from_sub_some["payload"].items():
                        for devcommand, setting_time_dicts in v.items():
                            for setting_time, payload in setting_time_dicts.items():
                                setting_time_split = setting_time.split(":")
                                setting_hrs = int(setting_time_split[0])
                                setting_minutes = int(setting_time_split[1])
                                if payload:

                                    message = {"reply_to": "me/myself",
                                               "rid": "an id",
                                               "rules": {
                                                   f"schedule_{room_no}_{devcommand}_{setting_time}": {
                                                       "trigger": {"occurrence": "every",
                                                                   "value": {
                                                                       "repeat": "day of week",
                                                                       "day of week": f"{day}",

                                                                       "time": {
                                                                           "hour": setting_hrs,
                                                                           "minute": setting_minutes
                                                                       }
                                                                   }
                                                                   }

                                                       ,
                                                       "conditions": [],
                                                       "actions": [
                                                           [["location", building, room_no, devcommand], payload]]
                                                   }}
                                               }

                                    topic = f"config/scheduleagent/add_rules"
                                    self.vip.pubsub.publish(peer="pubsub",
                                                            topic=topic,
                                                            headers={'requesterID': self.core.identity,
                                                                     "message_type": "request"},
                                                            message=message)
                                    _log.debug(f"topic: {topic}, payload: {message}")
                                else:
                                    del_rules.append(
                                        f"schedule_{room_no}_{devcommand}_{setting_time}")
            ## if the dict is empty that means we want to delete them.
            ## we delete them here.
            if del_rules:
                self.del_rules(del_rules)
        except Exception as e:
            _log.debug(f"Error in config: {e}")

    # @PubSub.subscribe(peer='pubsub', prefix='app/configapp/checkinconfig/global')
    # def recieve_from_sub_some(self, peer, sender, bus, topic, headers, commsg):
    #     _log.debug(f"topic in recieve from sub some: {topic}")
    #     room_list = grep_rooms_from_vctl() ## get list of all rooms
    #     order_no = 1
    #     for schema, data in commsg["message"]:
    #
    #         ##JSON reformatting
    #         command = mapping_schema_to_command[schema]
    #         add_command_template["name"] = "check_in"
    #         add_command_template["command"] = command
    #         add_command_template["order"] = order_no
    #         add_command_template["device"] = data["devices"]
    #         add_command_template["payload"] = data["payload"]
    #         add_command_template["mapping"] = {}
    #         add_command_template["action"] = "add"
    #
    #         for room in room_list:
    #             self.del_commands(building, room,"check_in", order_no)
    #             self.vip.pubsub.publish(peer="pubsub",
    #                                     topic=f'config/{building}/{room}/map',
    #                                     headers={'requesterID': self.core.identity,
    #                                              "message_type": "request"},
    #                                     message=add_command_template)
    #         order_no+= 1
    ## recieve message from subiotagent to config checkin command for some rooms
    @PubSub.subscribe(peer='pubsub', prefix='app/configapp/roomconfig')
    def recieve_from_sub_some(self, peer, sender, bus, topic, headers, commsg):
        _log.debug(f"topic in recieve from sub some: {topic} with commsg:{commsg}")
        topic = topic.split("/")
        cmd_name = topic[3][:-6]
        if topic[4] == "local":
            room_list = commsg['room']  ## get list of all rooms

        elif topic[4] == "global":
            room_list = self.grep_rooms_from_vctl()
        order_no = 1
        building = commsg["building"]
        for schema, data in commsg["message"].items():
            _log.debug(f"schema {schema}")
            ##JSON reformatting
            command = mapping_schema_to_command[schema]
            add_command_template["name"] = cmd_name
            add_command_template["command"] = command
            add_command_template["order"] = order_no
            add_command_template["device"] = data["devices"]
            add_command_template["payload"] = data["payload"]
            add_command_template["mapping"] = {}
            add_command_template["action"] = "add"

            for room in room_list:
                self.del_commands(building, room, cmd_name, order_no)
                self.vip.pubsub.publish(peer="pubsub",
                                        topic=f'config/{building}/{room}/map',
                                        headers={'requesterID': self.core.identity,
                                                 "message_type": "request"},
                                        message=add_command_template)
            order_no += 1
    @PubSub.subscribe(peer='pubsub', prefix='app/globalconfig')
    def recieve_from_sub_global(self, peer, sender, bus, topic, headers, message):
        _log.debug(f"in recieve_from_sub adasfadfda topic: {topic}")
        topic = topic.split('/')
        if topic[2] == 'schedule' and topic[3] == 'add_rules':
            _log.debug("in recieve from sub add_rules")
            self.message = message
            self.vip.pubsub.publish(peer="pubsub",
                                    topic='action/scheduleagent/list_rules',
                                    headers={'requesterID': self.core.identity,
                                             "message_type": "request"},
                                    message={"reply_to":"app/globalconfig/next/add_rules","rid":"123"})
        elif topic[2] == 'schedule' and topic[3] == 'del_rules':
            self.vip.pubsub.publish(peer="pubsub",
                                    topic='action/scheduleagent/list_rules',
                                    headers={'requesterID': self.core.identity,
                                             "message_type": "request"},
                                    message={"reply_to": "app/globalconfig/next/del_rules", "rid": "123"})

    # @PubSub.subscribe(peer='pubsub', prefix='app/globalconfig/next')
    # def request_rules_name(self, peer, sender, bus, topic, headers, message):
    #     return message["rules"]

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix='app/globalconfig/next',
                                  callback=self._handle_message)


    def _handle_message(self, peer, sender, bus, topic, headers,
                                commsg):
        _log.debug(f"in _handle_message{commsg}")
        topic = topic.split('/')
        list_rules = list(commsg["rules"].keys())
        _log.debug(f"in _handle_message{self.message}")
        building = self.message["building"]
        self.vip.pubsub.publish(peer="pubsub",
                                topic='config/scheduleagent/del_rules',
                                headers={'requesterID': self.core.identity,
                                         "message_type": "request"},
                                    message={"reply_to": "app/globalconfig/response", "rid": "456", "rules": list_rules})
        _log.debug(f"in _handle_message topic : {topic}")
        if "add_rules" in topic[3] :
            room_list = self.grep_rooms_from_vctl()
            action_lists = {}

            for room in room_list:
                for day, v in self.message["payload"].items():
                    for devcommand, setting_time_dicts in v.items():
                        for setting_time, payload in setting_time_dicts.items():
                            action_lists[setting_time] = []
                            setting_time_split = setting_time.split(":")
                            setting_hrs = int(setting_time_split[0])
                            setting_minutes = int(setting_time_split[1])
                                # action_lists[setting_time].append([["location", building, room, devcommand],payload])

                            message = {"reply_to": "me/myself",
                                       "rid": "an id",
                                       "rules": {
                                           f"schedule_{room}_{devcommand}_{setting_time}": {
                                               "trigger": {"occurrence": "every",
                                                           "value": {
                                                               "repeat": "day of week",
                                                               "day of week": f"{day}",

                                                               "time": {
                                                                   "hour": setting_hrs,
                                                                   "minute": setting_minutes
                                                               }
                                                           }
                                                           }

                                               ,
                                               "conditions": [],
                                               "actions": [
                                                               [["location", building, room, devcommand], payload]]
                                           }}
                                       }
                            _log.debug(f"message in global : {message}")
                            topic = f"config/scheduleagent/add_rules"
                            self.vip.pubsub.publish(peer="pubsub",
                                                    topic=topic,
                                                    headers={'requesterID': self.core.identity,
                                                             "message_type": "request"},
                                                    message=message)

                            _log.debug(f"topic: {topic}, payload: {message}")

            # for day, v in self.message["payload"].items():
            #     for devcommand, setting_time_dicts in v.items():
            #         for setting_time, payload in setting_time_dicts.items():
            #             action_lists[setting_time] = []
            #             setting_time_split = setting_time.split(":")
            #             setting_hrs = int(setting_time_split[0])
            #             setting_minutes = int(setting_time_split[1])
            #             for room in room_list:
            #                 action_lists[setting_time].append([["location", building, room, devcommand],payload])
            #
            #             message = {"reply_to": "me/myself",
            #                        "rid": "an id",
            #                        "rules": {
            #                            f"schedule_global_{devcommand}_{setting_time}": {
            #                                "trigger": {"occurrence": "every",
            #                                            "value": {
            #                                                "repeat": "day of week",
            #                                                "day of week": f"{day}",
            #
            #                                                "time": {
            #                                                    "hour": setting_hrs,
            #                                                    "minute": setting_minutes
            #                                                }
            #                                            }
            #                                            }
            #
            #                                ,
            #                                "conditions": [],
            #                                "actions": action_lists[setting_time]
            #                            }}
            #                        }
            #             topic = f"config/scheduleagent/add_rules"
            #             self.vip.pubsub.publish(peer="pubsub",
            #                                     topic=topic,
            #                                     headers={'requesterID': self.core.identity,
            #                                              "message_type": "request"},
            #                                     message=message)
    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        #Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        #Exmaple RPC call
        #self.vip.rpc.call("some_agent", "some_method", arg1, arg2)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export  # expose RPC interface for other agents, can alto define capability
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method
        May be called from another agent via self.core.rpc.call """
        _log.debug('get called from another agent via RPC')
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(tester, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
