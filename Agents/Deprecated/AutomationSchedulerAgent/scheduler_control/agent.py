# -*- coding: utf-8 -*-
from __future__ import absolute_import
import schedule
import logging
import settings
from volttron.platform.vip.agent import Agent, Core, PubSub, compat
from volttron.platform.agent import utils
import json
import psycopg2.extras
import psycopg2
import sys
from datetime import *

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '3.2'
DEFAULT_HEARTBEAT_PERIOD = 20
DEFAULT_MONITORING_TIME = 20
DEFAULT_MESSAGE = 'HELLO'


# Step1: Agent Initialization
def scheduler_agent(config_path, **kwargs):
    config = utils.load_config(config_path)

    def get_config(name):
        try:
            kwargs.pop(name)
        except KeyError:
            return config.get(name, '')

    agent_id = get_config('agent_id')

    # DATABASES
    try:    
        automation_id = get_config('agentid')
        db_host = settings.DATABASES['default']['HOST']
        db_port = settings.DATABASES['default']['PORT']
        db_database = settings.DATABASES['default']['NAME']
        db_user = settings.DATABASES['default']['USER']
        db_password = settings.DATABASES['default']['PASSWORD']

        conn = psycopg2.connect(host=db_host, port=db_port, database=db_database, user=db_user,
                                password=db_password)
        cur = conn.cursor()
        cur.execute("""SELECT * FROM automations WHERE automation_id = {}""".format(automation_id.replace('automation_' ,'')))
        rows = cur.fetchall()

        for row in rows:
            # print row[0]
            automation_id = automation_id.replace('automation_','')
            # print automation_id
            # if int(automation_id) == int(row[0]):
            trigger_device = row[3]  # In this case row[2] is 'SCHEDULER'
            condition_value = row[7]
            action_task = row[8]
    
        conn.close()
    except Exception as Err:
        print("Error : {}".format(Err))

    class AutomationSchedulerAgent(Agent):
        def __init__(self, config_path, **kwargs):
            super(AutomationSchedulerAgent, self).__init__(**kwargs)
            self.config = utils.load_config(config_path)
            self._agent_id = agent_id
            self.conn = None
            self.cur = None
            
            self.trigger_value = None
            self.trigger_device = trigger_device
            self.trigger_event = None

            self.condition_event = None
            self.condition_value = condition_value

            self.devicecontrols = action_task

            self.automation_id = automation_id

        @Core.receiver('onsetup')
        def onsetup(self, sender, **kwargs):
            # Demonstrate accessing a value from the config file
            _log.info(self.config.get('message', DEFAULT_MESSAGE))
            
        @Core.receiver('onstart')
        def onstart(self, sender, **kwargs):
            _log.debug("VERSION IS: {}".format(self.core.version()))
            self.load_config()
            self.schedule()
            
        @Core.periodic(10)  # Every 60 sec do a schedule.run_pending
        def scheduler_handle(self):
            print('Scheduler is handeling ...')
            schedule.run_pending()  # pending for next exec task
        
        def load_config(self):  # reload scene configuration to Agent Variable

            conn = psycopg2.connect(host=db_host, port=db_port, database=db_database, user=db_user,
                                    password=db_password)
            self.conn = conn
            self.cur = self.conn.cursor()
            self.cur.execute("""SELECT * FROM automations """)  # TODO : add where condition automation-ID matched
            rows = self.cur.fetchall()

            for row in rows:
                if int(self.automation_id) == int(row[0]):
                    self.trigger_device = row[3]
                    self.trigger_event = row[4]
                    self.trigger_value = row[5]
                    self.condition_event = row[6]
                    self.condition_value = row[7]
                    self.devicecontrols = (json.loads((row[8])))
                    # print(" trigger_device = {}".format(self.trigger_device))
                    # print(" trigger_event = {}".format(self.trigger_event))
                    # print(" trigger_value = {}".format(self.trigger_value))
                    # print(" condition_event  = {}".format(self.condition_event))
                    # print(" condition_value = {}".format(self.condition_value))
                    # print(" devicecontrols = {}".format(self.devicecontrols))

            self.conn.close() 
            
        def devicecontrol(self):
            
            try:
                for task in self.devicecontrols:
                    topic = str('/ui/agent/update/hive/999/') + str(task['device_id'])
                    print topic
                    message = json.dumps(task['command'])
                    print ("topic {}".format(topic))
                    print ("message {} \n".format(message))
                    self.vip.pubsub.publish(
                        'pubsub', topic,
                        {'Type': 'HiVE Scene Control'}, message)
            
            except Exception as Error:
                print('Reload Config to Agent')

        def schedule(self):
            print('Set Schedule Task')
            tmp = self.condition_value
            condition = json.loads(tmp)
            sche = condition.get('SCHEDULE')
            m1 = sche.get('time')

            if datetime.strptime(m1, '%I:%M %p'):
                time_trigger = [(datetime.strptime(m1, '%I:%M %p')).strftime('%H:%M')]
            else:
                time_trigger = [m1]

            on_dates = sche.get('day')
            date_set = {'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'}
            for time_ind in time_trigger:

                if date_set.__eq__(set(on_dates)):
                    # if True is mean it running on everyday
                    schedule.every().day.at(time_ind).do(self.devicecontrol)  # Time format is "13:00"
                else:  # Else Statement for not everyday in week execute.
                    for on_date in on_dates:
                        if on_date == 'MO':
                            schedule.every().monday.at(time_ind).do(self.devicecontrol)
                        elif on_date == 'TU':
                            schedule.every().tuesday.at(time_ind).do(self.devicecontrol)
                        elif on_date == 'WE':
                            schedule.every().wednesday.at(time_ind).do(self.devicecontrol)
                        elif on_date == 'TH':
                            schedule.every().thursday.at(time_ind).do(self.devicecontrol)
                        elif on_date == 'FR':
                            schedule.every().friday.at(time_ind).do(self.devicecontrol)
                        elif on_date == 'SA':
                            schedule.every().saturday.at(time_ind).do(self.devicecontrol)
                        elif on_date == 'SU':
                            schedule.every().sunday.at(time_ind).do(self.devicecontrol)
                        else:
                            print('Somthing went wrong on Scheduler Task')

    Agent.__name__ = 'schedulerAgent'
    return AutomationSchedulerAgent(config_path, **kwargs)


def main(argv=sys.argv):
    ''' Main method called by the eggsecutable. '''
    try:
        utils.vip_main(scheduler_agent, version=__version__)

    except Exception as e:
        _log.exception('unhandled exception')

if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
