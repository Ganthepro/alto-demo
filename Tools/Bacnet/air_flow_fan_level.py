import BAC0
import time


def got_cov(elements=None):
    # print(elements)
    addr = elements["object_changed"][1]
    if addr == 5:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    elif addr == 6:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    elif addr == 7:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    elif addr == 8:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
bacnet = BAC0.lite(ip="192.168.0.103", port=0xBAC0)

# res = bacnet.read(cmd)
# bacnet.cov("192.168.0.10", ("multiStateOutput", 5), lifetime=10, callback = got_cov) # lifetime=None
bacnet.cov("192.168.0.10", ("multiStateOutput", 5), callback = got_cov) # lifetime=None
bacnet.cov("192.168.0.10", ("multiStateInput", 6), callback = got_cov)

bacnet.cov("192.168.0.10", ("multiStateOutput", 7), callback = got_cov) # AirFlowRateCommand_000
bacnet.cov("192.168.0.10", ("multiStateInput", 8), callback = got_cov) # AirFlowRateStatus_000


# AirFlowRateCommand_000
# 1 = low
# 2 = high
# 3 = mid
# 4 = auto
cmd = f"192.168.0.10 multiStateOutput 7 presentValue 1 - 1" # - 1
bacnet.write(cmd)

j = 2
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    bacnet.disconnect()
    print("End")


