import socketio
import json


class SocketIOClient():
        sio = socketio.Client()

        def __init__(self):
            pass

        def setup(self):
            self.call_backs()
            self.sio.connect('http://localhost:8050')

        def loop(self): 
            self.sio.wait()

        def call_backs(self):

            @self.sio.event
            def connect():
                # self.sio.emit('subscribe_one', {"topic": "a/b1"})
                self.sio.emit('subscribe_many', {"topic": ["a/b2", "aa/bb"]})
                self.sio.emit('subscribe_one', {"topic": "buildings/ananda/building_main/iot_devices/eb375e2edf132c03eecrkx/environment/subdev_0"})
                # self.sio.emit('subscribe_one', {"topic": "buildings/ananda/building_main/iot_devices"})
                self.sio.emit('subscribe_one', {"topic": "buildings/ananda/building_main/iot_devices/eb375e2edf132c03eecrkx"})
                print('connection established')
                
            @self.sio.on("docs")
            def raw_data(data):
                print(f"Data Received {data}")
            
            @self.sio.on("buildings/ananda/building_main/iot_devices/eb375e2edf132c03eecrkx/environment/subdev_0")
            def my_topic(data):
                print(f"my_topic {data}")
            
            @self.sio.on("buildings/ananda/building_main/iot_devices/eb375e2edf132c03eecrkx")
            def my_topic(data):
                print(f"my_topic {data}")

            @self.sio.event
            def auth(data):
                print(f"Data Received {data}")

            @self.sio.event
            def disconnect():
                print('disconnected from server')

        def run(self):
            self.setup()
            self.loop()


wrapper = SocketIOClient()
wrapper.run()
