# -*- coding: utf-8 -*-
'''
Copyright (c) 2016, Virginia Tech
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
 following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are those of the authors and should not be
interpreted as representing official policies, either expressed or implied, of the FreeBSD Project.

This material was prepared as an account of work sponsored by an agency of the United States Government. Neither the
United States Government nor the United States Department of Energy, nor Virginia Tech, nor any of their employees,
nor any jurisdiction or organization that has cooperated in the development of these materials, makes any warranty,
express or implied, or assumes any legal liability or responsibility for the accuracy, completeness, or usefulness or
any information, apparatus, product, software, or process disclosed, or represents that its use would not infringe
privately owned rights.

Reference herein to any specific commercial product, process, or service by trade name, trademark, manufacturer, or
otherwise does not necessarily constitute or imply its endorsement, recommendation, favoring by the United States
Government or any agency thereof, or Virginia Tech - Advanced Research Institute. The views and opinions of authors
expressed herein do not necessarily state or reflect those of the United States Government or any agency thereof.

VIRGINIA TECH – ADVANCED RESEARCH INSTITUTE
under Contract DE-EE0006352

#__author__ = "BEMOSS Team"
#__credits__ = ""
#__version__ = "2.0"
#__maintainer__ = "BEMOSS Team"
#__email__ = "aribemoss@gmail.com"
#__website__ = "www.bemoss.org"
#__created__ = "2014-09-12 12:04:50"
#__lastUpdated__ = "2016-03-14 11:23:33"
'''
#!/usr/bin/python3
'''
This API class is for an agent that want to communicate/monitor/control
devices that compatible with Prolon VC1000 or M1000
Avijit Saha 10/10/2014
'''

from pymodbus.client.sync import ModbusTcpClient
import csv
import os
import json

class API:
    #1. constructor : gets call everytime when create a new class
    #requirements for instantiation1. model, 2.type, 3.api, 4. address
    def __init__(self,**kwargs): #default color is white
        #Initialized common attributes
        self.variables = kwargs
        address_parts = self.get_variable('address').split(':')
        self.set_variable('address',address_parts[0])
        # self.set_variable('slave_id',int(address_parts[1]))
        self.set_variable('offline_count',0)
        self.set_variable('connection_renew_interval',6000) #nothing to renew
        self.client = '1'
        self.li_key = []
        self.li_val = []
        self.msg = ''
        self.msg_connect_fail = 'can not connect to Inverter'
        self.msg_get_fail = 'can not get Inverter status'
        self.result_fail = 'Fail'
        self.result_success = 'Success'
        self.li_factor = []

    def renewConnection(self):
        pass

    def set_variable(self,k,v): #k=key, v=value
        self.variables[k] = v

    def get_variable(self,k):
        return self.variables.get(k, None) #default of get_variable is none


    #2. Attributes from Attributes table
    '''
    Attributes:
    ------------------------------------------------------------------------------------------

    ------------------------------------------------------------------------------------------
    '''


    #3. Capabilites (methods) from Capabilities table
    '''
    API available methods:
    1. getDeviceStatus() Read
    2. setDeviceStatus(parameter,value) Write
    3. identifyDevice() Write
    '''

    #method1: GET Open the port and read the data

    def getDeviceStatus(self):

        try:
            self.connect(00, 1)
            register109 = float(self.request.getRegister(0))
            self.set_variable('energy_use_mode', register109)
            print(register109)

        except Exception as er:
            print(f"Error connect to inverter20109: {er}")

        # try:
        #     self.connect(20131, 1)
        #     register131 = float(self.request.getRegister(0))
        #     self.set_variable('battery_low_return_voltage', register131)
        #
        # except Exception as er:
        #     print "Error connect to inverter20131"
        #
        # try:
        #     self.connect(25206, 20)
        #     register1 = (self.request.getRegister(1) * 0.1)
        #     self.set_variable('grid_voltage', register1)
        #
        #     register2 = (self.request.getRegister(2) * 0.1)
        #     self.set_variable('load_voltage', register2)
        #
        #     register5 = (self.request.getRegister(5) * 0.1)
        #     self.set_variable('grid_current', register5)
        #
        #     register6 = int((self.request.getRegister(6)) * 0.1)
        #     self.set_variable('load_current', register6)
        #
        #     register7 = float(self.request.getRegister(7))
        #     self.set_variable('Inverter_activepower', register7)
        #
        #     register8 = float(self.request.getRegister(8))
        #     self.set_variable('grid_activepower', register8)
        #
        #     register9 = float(self.request.getRegister(9))
        #     self.set_variable('load_activepower', register9)
        #
        #     register11 = float(self.request.getRegister(11))
        #     self.set_variable('Inverter_apparentpower', register11)
        #
        #     register12 = float(self.request.getRegister(12))
        #     self.set_variable('grid_apparentpower', register12)
        #
        #     register13 = float(self.request.getRegister(13))
        #     self.set_variable('load_apparentpower', register13)
        #
        #     register10 = float(self.request.getRegister(15))
        #     self.set_variable('Inverter_reactivepower', register10)
        #
        #     register16 = float(self.request.getRegister(16))
        #     self.set_variable('grid_reactivepower', register16)
        #
        #     register17 = self.request.getRegister(17)
        #     self.set_variable('load_reactivepower', register17)
        #
        # except Exception as er:
        #     print "Error connect to register grid_voltage to load_reactivepower"
        #
        # try:
        #     self.connect(25273, 1)
        #     register73 = float(self.request.getRegister(0))
        #     self.set_variable('battery_power', register73)
        # except Exception as er:
        #     print "Error connect to register battery_power"
        #
        # try:
        #     self.connect(25245, 16)
        #     register46 = (self.request.getRegister(1))
        #     self.set_variable('accumulated_charger_power', register46)
        #
        #     register48 = (self.request.getRegister(3))
        #     self.set_variable('accumulated_discharge_power', register48)
        #
        #     register50 = (self.request.getRegister(5))
        #     self.set_variable('accumulated_buy_power', register50)
        #
        #     register52 = int((self.request.getRegister(7)))
        #     self.set_variable('accumulated_sell_power', register52)
        #
        #     register54 = float(self.request.getRegister(9))
        #     self.set_variable('accumulated_load_power', register54)
        #
        #     register56 = float(self.request.getRegister(11))
        #     self.set_variable('accumulated_self_use_power', register56)
        #
        #     register58 = float(self.request.getRegister(13))
        #     self.set_variable('accumulated_pv_sell_power', register58)
        #
        #     register60 = float(self.request.getRegister(15))
        #     self.set_variable('accumulated_grid_charger_power', register60)
        #
        # except Exception as er:
        #     print "Error connect to register accumulated"
        #
        #
        #     # register13 = gridActivePower before converse
        # try:
        #
        #     if register7 > 10000:
        #         register7 = (register7 - 65536)
        #         self.set_variable('Inverter_activepower', register7)
        #     else:
        #         print ("")
        #
        #     if register8 < 10000:
        #         register8 = (register8 * (-1))
        #         self.set_variable('grid_activepower', register8)
        #     else:
        #         self.set_variable('grid_activepower', (register8 - 65536))
        #
        #     # register73 = battPower before converse
        #     if register73 < 10000:
        #         # self.set_variable('Batterystatus', "Discharge")
        #         self.set_variable('battery_power', register73)
        #         # register73= solar+BattReativePower   , register00 = battPower before converse
        #         solarActivePower = float(register7 - register73)
        #         self.set_variable('solar_activepower', solarActivePower)
        #     else:
        #         # self.set_variable('Batterystatus', "Charge")
        #         batterypower = float(((-1) * (register73 - 65536)))
        #         self.set_variable('battery_power', batterypower)
        #         solarActivePower = register7 + batterypower
        #         self.set_variable('solar_activepower', solarActivePower)
        #
        # except Exception as er:
        #     print "Error connect to calculate solarToGrid or gridToHome"
        #
        # self.printDeviceStatus()

    def printDeviceStatus(self):

        print(" the current status is as follows:")

        print(" energy_use_mode = {}".format(self.get_variable('energy_use_mode')))
        print(" battery_low_return_voltage = {}".format(self.get_variable('battery_low_return_voltage')))
        print("-----------------------------------------------------------")

        print(" grid_voltage = {}".format(self.get_variable('grid_voltage')))
        print(" load_voltage = {}".format(self.get_variable('load_voltage')))
        print(" grid_current = {}".format(self.get_variable('grid_current')))
        print(" load_current = {}".format(self.get_variable('load_current')))
        print(" Inverter_activepower = {}".format(self.get_variable('Inverter_activepower')))
        print(" grid_activepower = {}".format(self.get_variable('grid_activepower')))
        print(" load_activepower = {}".format(self.get_variable('load_activepower')))
        print(" Inverter_apparentpower = {}".format(self.get_variable('Inverter_apparentpower')))
        print(" grid_apparentpower = {}".format(self.get_variable('grid_apparentpower')))
        print(" load_apparentpower = {}".format(self.get_variable('load_apparentpower')))
        print(" Inverter_reactivepower = {}".format(self.get_variable('Inverter_reactivepower')))
        print(" grid_reactivepower = {}".format(self.get_variable('grid_reactivepower')))
        print(" load_reactivepower = {}".format(self.get_variable('load_reactivepower')))
        print("-----------------------------------------------------------")

        print(" battery_power = {}".format(self.get_variable('battery_power')))

        print(" accumulated_charger_power = {}".format(self.get_variable('accumulated_charger_power')))
        print(" accumulated_discharge_power = {}".format(self.get_variable('accumulated_discharge_power')))

        print(" accumulated_buy_power = {}".format(self.get_variable('accumulated_buy_power')))
        print(" accumulated_sell_power = {}".format(self.get_variable('accumulated_sell_power')))
        print(" accumulated_load_power = {}".format(self.get_variable('accumulated_load_power')))
        print(" accumulated_self_use_power= {}".format(self.get_variable('accumulated_self_use_power')))
        print(" accumulated_pv_sell_power = {}".format(self.get_variable('accumulated_pv_sell_power')))
        print(" accumulated_grid_charger_power = {}".format(self.get_variable('accumulated_grid_charger_power')))
        print("-------------------------        from pymodbus.client.sync import ModbusTcpClient--------------------")
        print(" solar_activepower = {}".format(self.get_variable('solar_activepower')))


    def setDeviceStatus(self, postmsg):
        _mode = 0
        if postmsg['mode'] == "PL":
            _mode = 0
        elif postmsg['mode'] == "FL":
            _mode = 1
        elif postmsg['mode'] == "FS":
            _mode = 2
        elif postmsg['mode'] == "UPS":
            _mode = 3
        elif postmsg['mode'] == "PO":
            _mode = 4

    def connect(self,start,num):
        client = ModbusTcpClient('192.168.1.14', port=26)
        self.request = client.read_holding_registers(start, num, unit=4)

#This main method will not be executed when this class is used as a module
def main():
    Inverter = API(model='VC1000',type='VAV',api='API',address='192.168.1.14:26',)
    Inverter.getDeviceStatus()

if __name__ == "__main__": main()
