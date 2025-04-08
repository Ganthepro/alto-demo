import BAC0
import time


def got_cov(elements=None):
    # print(elements)
    addr = elements["object_changed"][1]
    if addr == 1025:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
    elif addr == 1026:
        print(f"""addr {addr} {elements["properties"]["presentValue"]}""")
bacnet = BAC0.lite(ip="192.168.0.103", port=0xBAC0)

# res = bacnet.read(cmd)
# bacnet.cov("192.168.0.10", ("multiStateOutput", 5), lifetime=10, callback = got_cov) # lifetime=None
bacnet.cov("192.168.0.10", ("binaryOutput", 1025), callback = got_cov) # StartStopCommand_000
bacnet.cov("192.168.0.10", ("binaryInput", 1026), callback = got_cov) # StartStopStatus_000


# StartStopCommand_000
# active = on
# inactive = off
cmd = f"192.168.0.10 binaryOutput 1025 presentValue active - 1" # - 1
bacnet.write(cmd)

j = 2
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    bacnet.disconnect()
    print("End")


