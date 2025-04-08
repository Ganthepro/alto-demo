import classAPI_airconet
import socket
from threading import Thread

def airconet_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("", 9533))
    print("Server TomMy Start --> Airconet IR !!!!!!!!!")
    while True:
        try:
            packet, dev_addr = server.recvfrom(1024)  # ----> packet = byte code , dev_addr = (ip,port)
            print(f"packet: {packet}")  ## tbd
        except Exception as e:
            print(f"error in server receiveing packet {e}")

server_thread = Thread(target=airconet_server(), )
server_thread.setDaemon(True)
server_thread.start()

Airconet = API(model='airconet', type='aircondiner', api='classAPI_airconet', agent_id='airconet1')
Airconet.setDeviceStatus({"settemp": 17, "mode": "fan", "fan": "high", "status": "on", "mac": "c82b962c7e1e",
                              "ip": "172.27.100.237", "port": 62980 })

