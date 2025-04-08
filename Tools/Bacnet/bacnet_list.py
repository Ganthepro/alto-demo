import BAC0
bacnet = BAC0.lite()
bacnet.whois()
# print(bacnet.devices)
# mycontroller = BAC0.device(bacnet)
mycontroller = BAC0.device('192.168.0.10', 70000, bacnet)

# # # Get the list of "registered" devices
print(bacnet.registered_devices)
# print(mycontroller.points)

# for i in mycontroller:
#     print(dir(i))
#     break

# for i in mycontroller.points_name:
#     print(mycontroller[i].properties.name)
#     break

# for i in mycontroller.points_name:
#     print(dir(mycontroller[i]))
#     break

# for i in mycontroller.points_name:
#     # print(mycontroller[i].bacnet_properties)
#     objectTypeList = ['binaryInput', 'binaryOutput', 'binaryValue', 'analogInput', 'analogOutput', 'analogValue']
#     mulObjType = ['multiStateInput', 'multiStateOutput', 'multiStateValue']
#     # if mycontroller[i].bacnet_properties['objectIdentifier'][0] not in objectTypeList:
#     if mycontroller[i].bacnet_properties['objectType'] in mulObjType:
#         print(mycontroller[i].bacnet_properties)
#         # break

for i in mycontroller.points_name:
    # objectNameList = ['AirConModeCommand_000', 'AirConModeStatus_000', 'AirFlowRateCommand_000', 'AirFlowRateStatus_000', 'RemoteControlAirConModeSet_000']
    # objectNameList = ['TempAdjust_000', 'RoomTemp_000', 'AirConModeCommand_000', 'AirConModeStatus_000', 'AirFlowRateCommand_000', 'AirFlowRateStatus_000', 'StartStopCommand_000']
    # objectNameList = ['RemoteControlStart_000', 'RemoteControlAirConModeSet_000', 'RemoteControlTempAdjust_000', 'CL_Rejection_005']
    # objectNameList = ['AirDirectionCommand_000', 'AirDirectionStatus_000', 'FilterSign_000', 'FilterSignReset_000']
    objectNameList = ['Alarm_000', 'MalfunctionCode_000', 'FilterSign_000', 'FilterSignReset_000', 'CommunicationStatus_000']
    if mycontroller[i].bacnet_properties['objectName'] in objectNameList:
        print(mycontroller[i].bacnet_properties)
        # if mycontroller[i].bacnet_properties['objectName'] == 'AirConModeCommand_000':
        #     print(str(mycontroller[i].bacnet_properties['priorityArray']))

# for name in mycontroller.points_name:
#     if mycontroller[name].units:
#         val = '{:>10.2f}'.format(mycontroller[name].lastValue)
#         units = mycontroller[name].units
#     else:
#         units = '({})'.format(mycontroller[name].properties.units_state)
#         val = '{:>10}'.format(mycontroller[name].lastValue)
#     print('{:<20} : {} {:<10}'.format(mycontroller[name].properties.name, val, units))


# print(bacnet.readMultiple('192.168.0.10 binaryOutput 1 all'))
# print(bacnet.readMultiple('192.168.0.10 binaryOutput 6 all'))

# bacnet.disconnect()
