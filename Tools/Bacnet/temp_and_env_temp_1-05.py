import BAC0
import time


def got_cov(elements=None):
    # print(elements)
    addr = elements["object_changed"][1]
    if addr == 1289:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    elif addr == 1290:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
bacnet = BAC0.lite(ip="192.168.0.103", port=0xBAC0)

# res = bacnet.read(cmd)
# bacnet.cov("192.168.0.10", ("multiStateOutput", 5), lifetime=10, callback = got_cov) # lifetime=None

bacnet.cov("192.168.0.10", ("analogInput", 1289), callback = got_cov) # RoomTemp_000
bacnet.cov("192.168.0.10", ("analogValue", 1290), callback = got_cov) # TempAdjust_000


# TempAdjust_000
# it can be 23.5 but just 23
cmd = f"192.168.0.10 analogValue 1290 presentValue 20 - 1" # - 1
bacnet.write(cmd)

j = 2
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    bacnet.disconnect()
    print("End")


