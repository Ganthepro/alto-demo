import BAC0
import time


def got_cov(elements=None):
    # print(elements)
    addr = elements["object_changed"][1]
    if addr == 22:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    elif addr == 23:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
bacnet = BAC0.lite(ip="192.168.0.103", port=0xBAC0)

# res = bacnet.read(cmd)
# bacnet.cov("192.168.0.10", ("multiStateOutput", 5), lifetime=10, callback = got_cov) # lifetime=None
bacnet.cov("192.168.0.10", ("analogValue", 22), callback = got_cov) # lifetime=None
bacnet.cov("192.168.0.10", ("analogInput", 23), callback = got_cov)

# AirDirectionStatus_000 (23)

# AirDirectionCommand_000 (22)
# 0.0 - 3.0 = horizontal
# 4 = vertical
# 7 = swing
# 0.0, 1.0, 2.0, 3.0, 4.0 (no swing)
# 7.0 (swing)
cmd = f"192.168.0.10 analogValue 22 presentValue 4.0 - 1" # - 1
bacnet.write(cmd)

j = 2
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    bacnet.disconnect()
    print("End")


