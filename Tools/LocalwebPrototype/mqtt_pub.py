import paho.mqtt.client as paho
import time
import random


broker="127.0.0.1"
port=1883

def on_publish(client, userdata, result):
    print("Device 1 : Data published.")
    pass

client= paho.Client("test_pub")
client.on_publish = on_publish
client.connect(broker, port)

for i in range(20):
    d=random.randint(1,3)
    message="Device 1 : Data " + str(i)
    time.sleep(d)
    ret= client.publish("/data",message)

print("Stopped...")