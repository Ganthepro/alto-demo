# -*- coding: utf-8 -*-
import logging
import broadlink
import time
_log = logging.getLogger(__name__)

TYPE = 0x2714

class API:
    # 1. constructor : gets call every time when create a new class
    # requirements for instantiation1. model, 2.device_type, 3.api, 4. address, 5. port, 6.config (with discovery info)
    def __init__(self, **kwargs):
        # Initialized common attributes
        self.variables = kwargs
        self.debug = True
        self.set_variable('offline_count', 0)
        self.set_variable('connection_renew_interval', 6000)
        self.set_variable('last_command', '')

        self.ipadddress = self.get_variable('address')
        if ":" in self.get_variable('macaddr'):
            self.macadddr = "".join(self.macadddr[x]+self.macadddr[x+1] for x in range(0, len(self.macadddr), 2))
        else:
            self.macadddr = self.get_variable('macaddr')
        self.TYPE = TYPE
        self.device = broadlink.a1((self.ipadddress, 80), "".join(self.macadddr.split(":")[::-1]), self.TYPE)

        self.sensor_data = {}
        self.found = False

    def set_variable(self, k, v):  # set something you want k=key, v=value
        self.variables[k] = v

    def get_variable(self, k):     # get from init
        return self.variables.get(k, None)  # default of get_variable is none

    # 2. Attributes from Attributes table
    '''
    Attributes:
     ------------------------------------------------------------------------------------------
    air_quality     GET         
    light           GET    
    noise           GET     
    temperature     GET   
    humidity        GET   
     ------------------------------------------------------------------------------------------
    '''
    # 3. Capabilites (methods) from Capabilities table
    '''
    API3 available methods:
    1. getDeviceStatus() GET
    2. authDeviceStatus() GET
    3. discoveryDevices() GET 
    
    '''

    # ----------------------------------------------------------------------
    # getDeviceStatus(), getDeviceStatusJson(data), printDeviceStatus()

    def getDeviceStatus(self):
        try:
            self.sensor_data = "timed out"
            print("auth")
            self.device.auth()                   #raise Error if can not auth
            self.sensor_data = self.device.check_sensors()
            print("1. no error and return : ", self.sensor_data)
            self.getDeviceStatusJson(self.sensor_data)
        except Exception as e:
            print("Error: Something went wrong when querying data. Error was: {}".format(e))
            self.sensor_data = "timed out"
            print("....after assign self.sensor_data = 'timed out'")
            print("2. error and return :", self.sensor_data)
        finally:
            print("in finally")
            return self.sensor_data

    def authDeviceStatus(self):
        try:
            self.device.auth()
        except Exception as e:
            print("Error: Something went wrong when auth device. Error was: {}".format(e))
            return False
        else:
            return True

    def discoveryDevices(self, macdev=None, timeout = 2):
        macdev = macdev.lower()
        self.found = False
        devs = broadlink.discover(timeout=timeout)
        print("Found broadlink {} devices".format(len(devs)))
        all_mac_env = {}
        for dev in devs:
            if dev.type == "A1":
                mac = ''.join(format(x, '02x') for x in dev.mac)
                mac = "".join([mac[x] + mac[x + 1] for x in range(0, len(mac), 2)][::-1])
                ip = dev.host[0]
                all_mac_env[mac] = ip

        print("Found A1 {} devices --> {}".format(len(all_mac_env), all_mac_env))
        print("serch ip for mac : ", macdev, "len = ",len(macdev))
        if macdev == None:
            print("macdev == None")
            return all_mac_env
        elif (len(macdev) == 12):
            for findmac in all_mac_env.keys():
                print("loop findmac {} == {} ".format(findmac, macdev))
                if macdev == findmac:
                    print("macdev in all_mac_env")
                    self.foundip = True
                    return {macdev: all_mac_env[macdev]}
            if self.found == False:
                print('macdev: "ip_not_found"')
                return {macdev: "ip_not_found"}


    def getDeviceStatusJson(self, data):
        self.set_variable('air_quality', data['air_quality'])
        self.set_variable('light', data['light'])
        self.set_variable('noise', data['noise'])
        self.set_variable('temperature', data['temperature'])
        self.set_variable('humidity', data['humidity'])

    def printDeviceStatus(self):
        # now we can access the contents of the JSON like any other Python object
        # _log.debug(" the current status is as follows:")
        # _log.debug(" air_quality = {}".format(self.get_variable('air_quality')))
        # _log.debug(" light = {}".format(self.get_variable('light')))
        # _log.debug(" noise = {}".format(self.get_variable('noise')))
        # _log.debug(" temperature = {}".format(self.get_variable('temperature')))
        # _log.debug(" humidity = {}".format(self.get_variable('humidity')))
        # _log.debug("---------------------------------------------")
        # for debug
        print(" the current status is as follows:")
        print(" air_quality = {}".format(self.get_variable('air_quality')))
        print(" light = {}".format(self.get_variable('light')))
        print(" noise = {}".format(self.get_variable('noise')))
        print(" temperature = {}".format(self.get_variable('temperature')))
        print(" humidity = {}".format(self.get_variable('humidity')))
        print("---------------------------------------------")


# This main method will not be executed when this class is used as a module
def main():
    # create an object with initialized data from environmentagent
    # requirements for instantiation 1. model, 2.type, 3.api, 4. address

    BroadLink = API(model='A1', type='environment sensor', api='classAPI_broadlink_sensor', agent_id='A1sensor',
                    address='192.168.1.34', macaddr='b4430dfbf751')
    while True:
        print("\n")
        sensor_data = BroadLink.getDeviceStatus()
        if sensor_data == "timed out":
            print( "in api call timed out sensor_data == ", sensor_data)
            BroadLink = API(model='A1', type='environment sensor', api='classAPI_broadlink_sensor', agent_id='A1sensor',
                            address='192.168.1.34', macaddr='b4430dfbf751')

        else:
            print(sensor_data)

        # time.sleep()


    # print(BroadLink.discoveryDevices())
    # print(BroadLink.authDeviceStatus())
    # time.sleep(10)
    # print(BroadLink.getDeviceStatus())


if __name__ == "__main__":
    main()
