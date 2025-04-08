

from __future__ import absolute_import
from datetime import datetime
import logging
import sys
import settings
import os
import json
from pprint import pformat
import subprocess as sp
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from os.path import expanduser
import sqlite3

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '3.2'
DEFAULT_MESSAGE = 'Automation Message'
DEFAULT_AGENTID = "automation_control"
DEFAULT_HEARTBEAT_PERIOD = 5


def automation_manager_agent(config_path, **kwargs):
    config = utils.load_config(config_path)

    def get_config(name):
        try:
            kwargs.pop(name)
        except KeyError:
            return config.get(name, '')

    agent_id = get_config('agent_id')
    message = get_config('message')
    heartbeat_period = get_config('heartbeat_period')
    topic_automation_create = 'alto/Mintel/automationcreate'
    topic_automation_delete = 'alto/Mintel/automationdelete'
    topic_automation_update = 'alto/Mintel/automationupdate'
    topic_update_agent = 'agent/update/hive/999/updateagent'

    # DATABASES
    # db_host = settings.DATABASES['default']['HOST']
    # db_port = settings.DATABASES['default']['PORT']
    # db_database = settings.DATABASES['default']['NAME']
    # db_user = settings.DATABASES['default']['USER']
    # db_password = settings.DATABASES['default']['PASSWORD']

    class AutomationAgent(Agent):

        def __init__(self, config_path, **kwargs):
            super(AutomationAgent, self).__init__(**kwargs)
            self.config = utils.load_config(config_path)
            self._agent_id = self.config.get('agentid', DEFAULT_AGENTID)
            self._message = self.config.get('message', DEFAULT_MESSAGE)
            self._heartbeat_period = self.config.get('heartbeat_period',
                                                     DEFAULT_HEARTBEAT_PERIOD)
            self.conn = None
            self.cur = None
            self.automation_control_path = None

        @Core.receiver('onsetup')
        def onsetup(self, sender, **kwargs):
            # Demonstrate accessing a value from the config file
            print('on-setup event occur')

        @Core.receiver('onstart')
        def onstart(self, sender, **kwargs):
            print("On Start Event")
            # self.build_automation_agent(55)  #  Uncomment for Test Create new agent event
            # self.publish_agentupdate_topic()

        @PubSub.subscribe('pubsub', topic_automation_create)  # On Automation create
        def match_topic_create(self, peer, sender, bus,  topic, headers, message):
            print("Match Topic Create Automation")
            msg = message['message']
            print('msg: {}'.format(msg))
            conf = msg.get('automationconfig', None)
            print('conf: {}'.format(conf))
            self.insertdb(conf)

            if str(conf.get('condition_event')).__contains__('SCHEDULE'):
                self.build_scheduler_agent(automation_id=str(conf.get('automation_id')))
            else:
                self.build_automation_agent(automation_id=str(conf.get('automation_id')))
            self.publish_agentupdate_topic()  # Pub Message to Agent

        @PubSub.subscribe('pubsub', topic_automation_delete)  # On Automation delete
        def match_topic_delete(self, peer, sender, bus,  topic, headers, message):
            print("Match Topic Delete Automation")
            msg = json.loads(message)
            conf = msg.get('automationconfig', None)
            print('conf: {}'.format(conf))
            self.deletedb(conf)
            self.remove_automation_agent(conf.get('automation_id'))
            self.publish_agentupdate_topic()  # Pub Message to HiVEPlatfom Agent

        @PubSub.subscribe('pubsub', topic_automation_update)
        def match_topic_update(self, peer, sender, bus,  topic, headers, message):
            print("Match Topic Update Automation")
            msg = json.loads(message)
            conf = msg.get('automationconfig', None)
            automation_id = conf.get('automation_id')
            self.updatedb(conf)
            self.remove_automation_agent(automation_id)

            print(f"msg: {msg['automationconfig']}")

            if str(conf.get('condition_event')).__contains__('SCHEDULE'):
                self.build_scheduler_agent(automation_id=str(conf.get('automation_id')))
            else:
                self.build_automation_agent(automation_id=str(conf.get('automation_id')))

            self.publish_agentupdate_topic()  # Pub Message to HiVEPlatfom Agent

        def updatedb(self, conf):
            if conf is not None:
                # Update Record Attibute where match automation ID
                automation_id = str(conf.get('automation_id'))
                automation_name = conf.get('automation_name')
                condition_event = conf.get('condition_event')
                condition_value = conf.get('condition_value')
                trigger_device = conf.get('trigger_device')
                trigger_event = conf.get('trigger_event')
                trigger_value = conf.get('trigger_value')
                action_tasks = conf.get('action_tasks')

                gg = expanduser("~")
                path = '/workspace/hive_os/volttron/hive_lib/sqlite.db'
                conn = sqlite3.connect(gg + path)
                cur = conn.cursor()
                cur.execute("""
                               UPDATE automations
                               SET automation_name=?,
                                    condition_event=?, condition_value=?,
                                    trigger_device=?, trigger_event=?,
                                    trigger_value=?, action_tasks=?
                               WHERE automation_id=?
                            """, (automation_name, condition_event,condition_value, trigger_device,trigger_event, trigger_value,action_tasks, automation_id))
                conn.commit()
                conn.close()
                print('ff')

        def deletedb(self, conf):
            if conf is not None:
                gg = expanduser("~")
                path = '/workspace/hive_os/volttron/hive_lib/sqlite.db'
                conn = sqlite3.connect(gg + path)
                cur = conn.cursor()
                cur.execute("""
                               DELETE FROM automations
                               WHERE automation_id=?
                            """, (conf.get('automation_id')))

                conn.commit()
                conn.close()
            else:
                pass

        def insertdb(self, conf):

            if conf is not None :
                # 1.Unpack Message from Backend
                automation_id = str(conf.get('automation_id'))
                automation_name = conf.get('automation_name')
                condition_event = str(conf.get('condition_event'))
                condition_value = str(conf.get('condition_value'))
                trigger_device = str(conf.get('trigger_device'))
                trigger_event = conf.get('trigger_event')
                trigger_value = conf.get('trigger_value')
                action_tasks = str(conf.get('action_tasks'))
                # gg = expanduser("~")
                path = '/home/kwarodom/workspace/alto_os/sqlite.db'
                conn = sqlite3.connect(path)
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO automations (automation_id, automation_name, condition_event, 
                                                condition_value, trigger_device, trigger_event, 
                                                trigger_value, action_tasks) VALUES (?, ?, ?,?, ?, ?,?, ?);""",
                    (automation_id, automation_name, condition_event, condition_value,
                     trigger_device, trigger_event, trigger_value, action_tasks))
                conn.commit()
                conn.close()

            else:
                pass

        def publish_agentupdate_topic(self):  # Pub Message to HiVEPlatform Agent
            msg = {}
            print("New Agent Registered")
            self.vip.pubsub.publish('pubsub', topic_update_agent, message=msg)

        def build_automation_agent(self, automation_id):
            print(' >>> Build Agent Process')
            #  get PATH Environment
            # home_path = expanduser("~")
            json_path = '/home/kwarodom/workspace/alto_os/Agents/AutomationControlAgent/automationcontrolagent.launch.json'
            self.automation_control_path = json_path
            launcher = json.load(open(json_path, 'r'))  # load config.json to variable
            #  Update new agentID to variable (agentID is relate to automation_id)
            launcher.update({'agentid': 'automation_{}'.format(automation_id)})
            #  dump new config to file
            json.dump(launcher, open(json_path, 'w'), sort_keys=True, indent=4)
            print(" >>> Change config file successful")

            os.chdir('/home/kwarodom/workspace/alto_os')
            os.system(f"scripts/install-agent.py -s Agents/AutomationControlAgent/ -i automationcontrol{automation_id} -t automationcontrol{automation_id} " +
                      " -c Agents/AutomationControlAgent/automationcontrolagent.launch.json;")
                      # ";vctl --tag automation_{}".format(automation_id))

            # TODO save automationconfig to config store
            newconfig = {"frequency": 20,
                         "topic": 'test',
                         "devices": 'device'}
            json_path = '/home/kwarodom/workspace/alto_os/Agents/AutomationControlAgent/newconfig.json'
            json.dump(newconfig, open(json_path, 'w'), sort_keys=True, indent=4)

            os.system(f"vctl config store newconfig2 config {json_path} --json;" +
                      " vctl config list")
            print("done adding new config")

            print(f"retrieved: {self.vip.config.list()}")

            # print(f"retrieved: {self.vip.config.get('newconfig')}")

        def build_scheduler_agent(self, automation_id):
            print("Schedule Agent Building")
            #  get PATH Environment
            home_path = expanduser("~")
            json_path = '/workspace/hive_os/volttron/Agents/AutomationSchedulerAgent/automationscheduleragent.launch.json'
            self.automation_control_path = home_path + json_path
            launcher = json.load(open(home_path + json_path, 'r'))  # load config.json to variable
            #  Update new agentID to variable (agentID is relate to automation_id)
            launcher.update({'agentid': 'automation_{}'.format(automation_id)})
            #  dump new config to file
            json.dump(launcher, open(home_path + json_path, 'w'), sort_keys=True, indent=4)
            print(" >>> Change config file successful")

            os.system("volttron-pkg package /home/hive/workspace/hive_os/volttron/Agents/AutomationSchedulerAgent;" +
                      "volttron-pkg configure /home/hive/.volttron/packaged/scheduler_controlagent-3.2-py2-none-any.whl" +
                      " /home/hive/workspace/hive_os/volttron/Agents/AutomationSchedulerAgent/automationscheduleragent.launch.json" +
                      ";volttron-ctl install " +
                      "/home/hive/.volttron/packaged/scheduler_controlagent-3.2-py2-none-any.whl " +
                      "--tag automation_{}".format(automation_id) +
                      ";volttron-ctl enable --tag automation_{}".format(automation_id) +
                      ";volttron-ctl start --tag automation_{}".format(automation_id))

        def remove_automation_agent(self, automation_id):
            print("check status automation agent")
            os.system("volttron-ctl stop --tag automation_{}".format(automation_id))
            os.system("volttron-ctl remove --tag automation_{}".format(automation_id))
            self.automation_control_path = None

    Agent.__name__ = 'automationmanager'
    return AutomationAgent(config_path, **kwargs)


def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''

    try:
        utils.vip_main(automation_manager_agent, version=__version__)

    except Exception as e:
        _log.exception('unhandled exception')


if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
