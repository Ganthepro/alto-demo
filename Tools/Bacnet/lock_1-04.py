import BAC0
import time


def got_cov(elements=None):
    # print(elements)
    addr = elements["object_changed"][1]
    # if addr == 13:
    #     print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    # elif addr == 14:
    #     print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    # elif addr == 16:
    #     print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    # elif addr == 17:
    #     print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    if addr == 1041:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
bacnet = BAC0.lite(ip="192.168.0.103", port=0xBAC0)

# res = bacnet.read(cmd)
# bacnet.cov("192.168.0.10", ("multiStateOutput", 5), lifetime=10, callback = got_cov) # lifetime=None
# bacnet.cov("192.168.0.10", ("binaryValue", 13), callback = got_cov) # RemoteControlStart_000
# bacnet.cov("192.168.0.10", ("binaryValue", 14), callback = got_cov) # RemoteControlAirConModeSet_000
# bacnet.cov("192.168.0.10", ("binaryValue", 16), callback = got_cov) # RemoteControlTempAdjust_000

# bacnet.cov("192.168.0.10", ("binaryValue", 17), callback = got_cov) # CL_Rejection_000
bacnet.cov("192.168.0.10", ("binaryValue", 1041), callback = got_cov) # CL_Rejection_005


# RemoteControlStart_000 (ON/OFF)
# RemoteControlAirConModeSet_000 (cool, fan, dry)
# RemoteControlTempAdjust_000 (set temp)
# active = lock
# inactive = unlock
# cmd = f"192.168.0.10 binaryValue 13 presentValue inactive - 1" # - 1
# bacnet.write(cmd)
# time.sleep(1)
# cmd = f"192.168.0.10 binaryValue 14 presentValue inactive - 1" # - 1
# bacnet.write(cmd)
# time.sleep(1)
# cmd = f"192.168.0.10 binaryValue 16 presentValue inactive - 1" # - 1
# bacnet.write(cmd)
# time.sleep(1)

cmd = f"192.168.0.10 binaryValue 1041 presentValue inactive - 1" # - 1
bacnet.write(cmd)
time.sleep(1)

j = 2
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    bacnet.disconnect()
    print("End")


