# -*- coding: utf-8 -*-
from __future__ import absolute_import
from datetime import datetime
import logging
import settings
from pprint import pformat
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
import json
import sys
from os.path import expanduser
import sqlite3
import ast
import os
utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '3.2'
DEFAULT_HEARTBEAT_PERIOD = 20
DEFAULT_MONITORING_TIME = 20
DEFAULT_MESSAGE = 'HELLO'

# Step1: Agent Initialization
def automationcontrol_agent(config_path, **kwargs):
    config = utils.load_config(config_path)

    def get_config(name):
        try:
            kwargs.pop(name)
        except KeyError:
            return config.get(name, '')
    agent_id = get_config('agent_id')

    # DATABASES
    automation_id = str(get_config('agentid')).split('_')[-1]
    _log.debug(f"automation_id {automation_id}")
    # db_host = settings.DATABASES['default']['HOST']
    # db_port = settings.DATABASES['default']['PORT']
    # db_database = settings.DATABASES['default']['NAME']
    # db_user = settings.DATABASES['default']['USER']
    # db_password = settings.DATABASES['default']['PASSWORD']
    topic_tricker = ''
    # gg = expanduser("~")
    path = '/home/alto/workspace/alto_os/sqlite.db'
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    query = f'SELECT * FROM automations WHERE automation_id is {automation_id}'
    cur.execute(f"""{query}""")
    row = cur.fetchone()
    automation = list(row)
    automation_id = automation[0]
    device_type = automation[2]
    triger_device = ast.literal_eval(automation[3])[0]
    trigger_event = automation[4]
    trigger_value = automation[6]
    topic_tricker = f"{triger_device}/{trigger_event}/{trigger_value}"
    _log.debug("<<<< subscribe topic >>>>>")
    _log.debug(topic_tricker)
    conn.close()

    class AutomationControlAgent(Agent):
        def __init__(self, config_path, **kwargs):
            super(AutomationControlAgent, self).__init__(**kwargs)
            self.config = utils.load_config(config_path)
            self._agent_id = agent_id
            self.conn = None
            self.cur = None
            self.sceneconf = None
            self.num_of_scene = None
            self.token = None
            self.url = None
            self.status_old = None
            self.triger_value = None
            self.triger_device = None
            self.triger_event = None
            self.triger_value = None
            self.condition_event = None
            self.condition_value = None
            self.devicecontrols = None
            self.automation_id = automation_id
            # self.reload_config()  # Reload Scene when Agent Start

            _log.info("init attribute to Agent")

        @Core.receiver('onsetup')
        def onsetup(self, sender, **kwargs):
            # Demonstrate accessing a value from the config file
            _log.info(self.config.get('message', DEFAULT_MESSAGE))
            # self._agent_id = self.config.get('agentid')
            # self.url = self.config.get('backend_url') + self.config.get('scene_api')
            # self.token = self.config.get('token')

        @Core.receiver('onstart')
        def onstart(self, sender, **kwargs):
            _log.debug("VERSION IS: {}".format(self.core.version()))
            self.load_config()
            self.status_old = ""

        @PubSub.subscribe('pubsub', topic_tricker)
        def match_agent_reload(self, peer, sender, bus, topic, headers, message):
            convert_msg = message
            _log.debug(convert_msg)
            triger_event_now = convert_msg[(self.triger_event)]
            # _log.debug(" value reading now is value = {}".format(convert_msg[(self.triger_event)]))
            if self.triger_value == 'CLOSE':
                self.triger_value = 'CLOSED'

            _log.debug("<<<<<< step 1 subscribe triger >>>>>>>>")
            _log.debug("--------------------")
            # _log.debug(" Automation set device = {}".format(self.triger_device))
            # _log.debug(" Automation set event = {}".format(self.triger_event))
            _log.debug(" Automation set value = {}".format(self.triger_value))
            _log.debug(" triger_event_now = {}".format(triger_event_now))
            if triger_event_now == self.triger_value:
                _log.debug(" Automation set value == value reading now ")
                _log.debug(" go to step [[[  2  ]]] check condition event ")

                # if self.status_old != self.triger_value:
                if str(self.condition_event) == '[]':
                    self.devicecontrol()
                elif str(self.condition_event) == '["SCENE"]':
                    self.conditionevent()
                # else:
                #     _log.debug(f"same status was sent {self.triger_value}")

            self.status_old = triger_event_now

        def load_config(self): # reload scene configuration to Agent Variable
            # gg = expanduser("~")
            path = '/home/alto/workspace/alto_os/sqlite.db'
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            query = f'SELECT * FROM automations WHERE automation_id is {automation_id}'
            cur.execute(f"""{query}""")
            row = cur.fetchone()
            _log.debug(row)
            automation = list(row)
            if int(self.automation_id) == int(row[0]):
                self.triger_device = ast.literal_eval(automation[3])[0]
                self.triger_event = automation[4]
                self.triger_value = automation[6]
                self.condition_event = automation[7]
                self.condition_value = automation[5]
                self.devicecontrols = json.loads(automation[8])
                _log.debug(" triger_device = {}".format(self.triger_device))
                _log.debug(" triger_event = {}".format(self.triger_event))
                _log.debug(" triger_value = {}".format(self.triger_value))
                _log.debug(" condition_event  = {}".format(self.condition_event))
                _log.debug(" condition_value = {}".format(self.condition_value))
                _log.debug(" devicecontrols = {}".format(self.devicecontrols))
            conn.close()

        def conditionevent(self):
            _log.debug("<<<<<< step 2 check condition event>>>>>>>>")
            _log.debug('>> condition value == condition now')
            _log.debug(" go to step [[[  3  ]]] device control ")

            # gg = expanduser("~")
            path = '/home/alto/workspace/alto_os/sqlite.db'
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("""SELECT * FROM active_scene """)
            rows = cur.fetchall()
            loadcondition_value = json.loads(self.condition_value)
            sceneidcondition = loadcondition_value.get('SCENE')

            for row in rows :
                if str(row[0]) == str(sceneidcondition):
                    _log.debug(" condition now = {}".format(row[0]))
                    _log.debug(" condition in automation seting  = {}".format(sceneidcondition))
                    _log.debug('>> condition value == condition now')
                    _log.debug(" go to step [[[  3  ]]] device control ")
                    self.devicecontrol()
            conn.close()

        def devicecontrol(self):
            _log.debug("<<<<<<step 3 device control >>>>>>>>")
            try:
                for task in self.devicecontrols:
                    # TODO fix this
                    if str(task['device_id']) == "78:0F:77:D6:44:01":
                        topic = "alto/blremote/78:0F:77:D6:44:01/send"
                        message = "toggle"
                    else:
                        topic = f"alto/device/{str(task['device_id'])}/power"
                        message = json.dumps(task['command'])
                    _log.debug("topic {}".format(topic))
                    _log.debug("message {} \n".format(message))
                    self.vip.pubsub.publish(
                        'pubsub', topic,
                        {'Type': 'HiVE Scene Control'}, message)
            except Exception as er:
                _log.debug(f'Reload Config to Agent: {er}')

    Agent.__name__ = 'automationcontrol'
    return AutomationControlAgent(config_path, **kwargs)

def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(automationcontrol_agent, version=__version__)

    except Exception as e:
        _log.exception('unhandled exception')

if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
