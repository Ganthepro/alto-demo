import paho.mqtt.client as mqtt

broker="127.0.0.1"
port=1883
timelive=60

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    # client.subscribe("/data")
    client.subscribe("buildings/ananda/building_main/iot_devices/eb375e2edf132c03eecrkx/environment/subdev_0")
    client.subscribe("buildings/ananda/building_main/iot_devices/eb8df3eb77c9aba40dmhx7/environment/subdev_0")
    # client.subscribe("buildings/ananda/building_main/iot_devices/eb375e2edf132c03eecrkx")
    # client.subscribe("buildings/ananda/building_main/iot_devices/eb8df3eb77c9aba40dmhx7")

def on_message(client, userdata, msg):
    print(msg.payload.decode())

client = mqtt.Client()
client.connect(broker, port, timelive)
client.on_connect = on_connect
client.on_message = on_message
client.loop_forever()