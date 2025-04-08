# -*- coding: utf-8 -*-
import time
import json
import requests
import socket
from struct import pack

def drill(val, num_level):
    return val if (num_level == 0) else drill(list(val.values())[0], num_level-1)

class API:
    def __init__(self,**kwargs):
        # Initialized common attributes
        self.variables = kwargs
        self.debug = True
        self.set_variable('offline_count',0)
        self.set_variable('connection_renew_interval', 6000)
        self.only_white_bulb = None

    def renewConnection(self):
        pass

    def set_variable(self,k,v):  # k=key, v=value
        self.variables[k] = v

    def get_variable(self,k):
        return self.variables.get(k, None)  # default of get_variable is none

    def encrypt(self, string):
        key = 171
        result = pack('>I', len(string))
        for i in string:
            a = key ^ ord(i)
            key = a
            result += bytes([a])
        return result

    def decrypt(self, string):
        key = 171
        result = ""
        for i in string:
            a = key ^ i
            key = i
            result += chr(a)
        return result

    '''
    Attributes:
     ------------------------------------------------------------------------------------------
    label            GET          label in string
    status           GET          status
    unitTime         GET          time
    type             GET          type      
     ------------------------------------------------------------------------------------------

    '''

    '''
    API3 available methods:
    1. getDeviceStatus() GET
    2. setDeviceStatus() SET
    '''

    # ----------------------------------------------------------------------
    # getDeviceStatus(), getDeviceStatusJson(data), printDeviceStatus()
    def getDeviceStatus(self):
        getDeviceStatusResult = True
        try:
            ip = self.get_variable("ip")
            port = self.get_variable("port")
            energy = '{"emeter":{"get_realtime":{}}}'
            state = '{"system":{"get_sysinfo":{}}}'
            sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock_tcp.connect((ip, port))
            sock_tcp.send(self.encrypt(energy))
            data_energy = sock_tcp.recv(2048)
            sock_tcp.close()

            sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock_tcp.connect((ip, port))
            sock_tcp.send(self.encrypt(state))
            data_state = sock_tcp.recv(2048)
            sock_tcp.close()

            _data_energy = self.decrypt(data_energy[4:])
            _data_state = self.decrypt(data_state[4:])
            print(_data_state)
            try:
                self.getDeviceStatusJson(_data_energy)
                self.getDeviceStatusJson(_data_state)
                self.printDeviceStatus()
            except Exception as err:
                getDeviceStatusResult = False
                print("error with --> ", err)

            if getDeviceStatusResult == True:
                self.set_variable('offline_count', 0)
            else:
                self.set_variable('offline_count', self.get_variable('offline_count')+1)
        except Exception as er:
            print(er,'ERROR: classAPI_Tplink failed to getDeviceStatus')
            self.set_variable('offline_count',self.get_variable('offline_count')+1)
        
        status = "on" if int(self.get_variable("relay_state")) == 1 else "off"
        usedata = {"gang 0" : status,
                   "on_time": self.get_variable("on_time"),
                   "voltage": self.get_variable("voltage"),
                   "current": self.get_variable("current"),
                   "power": self.get_variable("power"),
                   "total": self.get_variable("total")}
        return usedata


    def getDeviceStatusJson(self, data):
        data_json = json.loads(data)
        data_json = list(list(data_json.values())[0].values())[0]
        print(isinstance(data_json, dict))
        print(data_json)
        for i, j in data_json.items():
            self.set_variable(i, j)

    def printDeviceStatus(self):
        # now we can access the contents of the JSON like any other Python object
        print(" the current status is as follows:")
        print("gang 0  =  {}".format(self.get_variable("relay_state")))
        print("on_time  =  {}".format(self.get_variable("on_time")))
        print("voltage  =  {}".format(self.get_variable("voltage")))
        print("current  =  {}".format(self.get_variable("current")))
        print("power  =  {}".format(self.get_variable("power")))
        print("total  =  {}".format(self.get_variable("total")))
        print("err_code  =  {}".format(self.get_variable("err_code")))
        print("---------------------------------------------")

    # setDeviceStatus(postmsg), isPostmsgValid(postmsg), convertPostMsg(postmsg)
    def setDeviceStatus(self, postmsg):
        setDeviceStatusResult = True
        ip = self.get_variable("ip")
        port = self.get_variable("port")
        if self.isPostMsgValid(postmsg) == True:  # check if the data is valid
            # _data = json.dumps(self.convertPostMsg(postmsg))
            _data = (self.convertPostMsg(postmsg))
            # _data = _data.encode(encoding='utf_8')  ##################################################
            try:
                print("sending command")
                sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock_tcp.connect((ip, port))
                sock_tcp.send(self.encrypt(_data))
                da = sock_tcp.recv(2048)
                sock_tcp.close()
                print("Sent:     ", _data)
                print("Received: ", self.decrypt(da[4:]))
            except:
                print("ERROR: classAPI_Tplink connection failure! @ setDeviceStatus")
                setDeviceStatusResult = False
        else:
            print("The POST message is invalid, try again\n")
        return setDeviceStatusResult

    def isPostMsgValid(self, postmsg):  # check validity of postmsg
        dataValidity = True
        # TODO algo to check whether postmsg is valid
        return dataValidity

    def convertPostMsg(self, postmsg):
        commands = {
            'info': '{"system":{"get_sysinfo":{}}}',
            'on': '{"system":{"set_relay_state":{"state":1}}}',
            'off': '{"system":{"set_relay_state":{"state":0}}}',
            'cloudinfo': '{"cnCloud":{"get_info":{}}}',
            'wlanscan': '{"netif":{"get_scaninfo":{"refresh":0}}}',
            'time': '{"time":{"get_time":{}}}',
            'schedule': '{"schedule":{"get_rules":{}}}',
            'countdown': '{"count_down":{"get_rules":{}}}',
            'antitheft': '{"anti_theft":{"get_rules":{}}}',
            'reboot': '{"system":{"reboot":{"delay":1}}}',
            'reset': '{"system":{"reset":{"delay":1}}}',
            'energy': '{"emeter":{"get_realtime":{}}}'
        }
        msgToDevice = {}
        if ('status' in postmsg.keys()):
            msgToDevice = commands[(postmsg['status'].lower())]
            print(postmsg['status'])
            print(msgToDevice)
        # if 'STATUS' in postmsg.keys():
        #     msgToDevice['command'] = str(postmsg['STATUS'].lower().capitalize())
        #     print msgToDevice
        return msgToDevice

    # ----------------------------------------------------------------------

# This main method will not be executed when this class is used as a module
def main():

    # -------------Kittchen----------------
    TpG = API(model='TPlinkPlug', api='API3', agent_id='TPlinkPlugAgent', types='plug', ip ='192.168.1.105',
                  port=9999)
    for i in range(1):
        # TpG.setDeviceStatus({"status": "Off"})
        # # time.sleep(5)
        # TpG.setDeviceStatus({"status": "info"})
        # # time.sleep(5)
        TpG.getDeviceStatus()
        # time.sleep(3)
        # TpG.setDeviceStatus({"status": "On"})
        # TpG.setDeviceStatus({"status": "info"})
        # time.sleep(5)

    # TpG.setDeviceStatus({"status": "cloudinfo"})

if __name__ == "__main__": main()
