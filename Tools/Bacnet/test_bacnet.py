import BAC0
import time

# cmd = "192.168.0.10 analogInput 9 presentValue"
# cmd = "192.168.0.10 binaryInput 1026 presentValue"
# cmd = "192.168.0.10 binaryOutput 1 presentValue active - 1"
# cmd = "192.168.0.10 binaryOutput 1 presentValue inactive - 1"
# cmd = "192.168.0.10 analogValue 10 presentValue 25 - 1"
# cmd = "192.168.0.10 binaryOutput 1 presentValue"
# cmd = "192.168.0.10 binaryOutput 1 presentValue inactive - 1"
# cmd = "192.168.0.10 binaryInput 2 presentValue"

bacnet = BAC0.lite(ip="192.168.0.103", port=0xBAC0)

# res = bacnet.read(cmd)

# cmd = "192.168.0.10 multiStateOutput 5 presentValue 4 - 1"
# res = bacnet.write(cmd)
# print(res)

# time.sleep(4)
# cmd = "192.168.0.10 multiStateOutput 5 presentValue"
# res = bacnet.read(cmd)
# print(res)

cmd = "192.168.0.10 binaryValue 1297 presentValue"
res = bacnet.read(cmd)
print(res)

bacnet.disconnect()
