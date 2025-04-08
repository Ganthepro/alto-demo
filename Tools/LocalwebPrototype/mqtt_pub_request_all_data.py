import paho.mqtt.client as paho
import time
import random
import json


broker="127.0.0.1"
port=1883

def on_publish(client, userdata, result):
    print("Device 1 : Data published.")
    pass

client= paho.Client("test_pub")
client.on_publish = on_publish
client.connect(broker, port)

message = {
    "path": "all"
}
ret = client.publish("alto_reserve_topic/request_all_data", json.dumps(message))

print("Stopped...")
