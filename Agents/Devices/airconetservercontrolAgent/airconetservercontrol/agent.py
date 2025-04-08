"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'
import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub
import importlib
import datetime as dt
import socket
import arpreq
from volttron.platform.scheduling import periodic
from threading import Thread

# initial Decryp heartbeat
from Crypto.Cipher import AES
from binascii import hexlify, unhexlify
key = unhexlify('FBC0F7811D0D3A1BA6494C927EECFDD9')
IV = unhexlify(('00' * 16))
mode = AES.MODE_CBC
decryptor = AES.new(key, mode, IV=IV)

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

def airconetserver(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Airconetserver
    :rtype: Airconetserver
    """
    try:
        config = utils.load_config(config_path)
        _log.debug(config)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    _log.debug(kwargs)
    model = config.get("model")
    airtype = config.get("airtype")
    api = config.get("api")
    agent_id = config.get("agent_id")
    station_info = config.get("station_info")
    devices_state = config.get("devices_state", {})

    return Airconetserver(model, airtype, api, agent_id, station_info, devices_state, **kwargs)

class Airconetserver(Agent):
    """
    Agent control AC
    """

    def __init__(self, model,
                 airtype,
                 api,
                 agent_id,
                 station_info,
                 devices_state,
                 **kwargs):

        super(Airconetserver, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)
        self.first_time = True                          # ------> use to flag periodic method.
        self.updatetype = {0: "irremote", 1: "apicontrol", 2: "laststatus"}   # 0 = irremote ,1 = apicontrol ,2 = laststatus
        self.model = model
        self.api = api
        self.device_type = airtype
        self.agent_id = agent_id
        self.station_info = station_info
        self.devices_state = devices_state              #----> device fix table for save status
        self.macip = {}                                 #----> for save mac and ip of all airconet before sending to cloud every 1 minutes
        self.zone = {"cc50e33b11aa": 4, "cc50e33b0f09": 1,"cc50e33b11ad": 1, "cc50e33b0c8c": 2,
                     "cc50e33b0e80": 3, "cc50e33b109f": 4, "cc50e33b10a1": 5, "cc50e33b0e12": 5 }
        # initialize device object
        self.apiLib = importlib.import_module("DeviceAPI.classAPI." + "classAPI_airconet")
        self.irdevice = self.apiLib.API(model=self.model,
                                        device_type=self.device_type,
                                        agent_id=self.agent_id, )
        self.server_thread = None
        self.server_die = False

        self.default_config = {"model": self.model,
                               "api": self.api,
                               "device_type": self.device_type,
                               "agent_id": self.agent_id,
                               "station_info": self.station_info,
                               "devices_state": self.devices_state }

        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)
        _log.debug("Configuring Agent")
        try:
            model = str(config["model"])
            api = str(config["api"])
            device_type = str(config["device_type"])
            agent_id = str(config["agent_id"])
            station_info = config["station_info"]
            devices_state = config["devices_state"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.model = model
        self.api = api
        self.device_type = device_type
        self.agent_id = agent_id
        self.station_info = station_info
        self.devices_state = devices_state

        self.default_config = {"model": self.model,
                               "api": self.api,
                               "device_type": self.device_type,
                               "agent_id": self.agent_id,
                               "station_info": self.station_info,
                               "devices_state": self.devices_state }


    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        #Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        #Exmaple RPC call
        #self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        _log.debug("VERSION IS: {}".format(self.core.version()))

        #---> start server airconet
        self.server_thread = Thread(target=self.airconet_server(), )
        self.server_thread.setDaemon(True)
        self.server_thread.start()

        #self.airconet_server()

    def airconet_server(self):
        """
        Airconet server port 9533 ,get status , Heartbeat
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("", 9533))
        _log.debug("Server TomMy Start --> Airconet IR !!!!!!!!!")

        while not self.server_die:
            try:
                packet, dev_addr = server.recvfrom(1024)            #----> packet = byte code , dev_addr = (ip,port)
                if arpreq.arpreq(dev_addr[0]):                      #----> check arp is not None (None == False)
                    dev_mac = str(arpreq.arpreq(dev_addr[0])).replace(":", "").lower()
                else:                                               #----> arp have problem with None data
                    dev_mac = None
                    for keymac in self.devices_state:               #---> search Oldmac from IP dev_addr[0].
                        if self.devices_state[keymac]["ip"] == dev_addr[0]:
                            _log.debug("arp get None ---> search mac from Database")
                            _log.debug("find mac from ip {} {}".format(dev_addr[0], keymac))
                            dev_mac = keymac
                            break

                _log.debug("received message from airconet : mac {} packet {} --> {} "
                           .format(str(dev_mac), str(packet), str(len(packet))))

                #---> Code for decode
                POWER = {"55": "ON", "AA": "OFF"}
                MODE = {"11": "cool", "22": "hot", "33": "auto", "44": "fan", "55": "dry"}
                FAN = {"01": "low", "02": "medium", "03": "high", "00": "auto", "04": "turbo"}
                ERROR = {"00": "No error"}

                #---> Decode bytearay to hex command
                self.commandRX = "".join("{:02x}".format(c) for c in packet).upper()      # ----> Bytearay can spriteby --> split = [packet[i] for i in range(0, len(packet))]
                #print('\n length ', len(self.commandRX), self.commandRX)

                if len(self.commandRX) == 42 and dev_mac is not None and dev_mac in self.devices_state:         #---> Status command detech And mac Not None.
                    # # todo flag last status change Action variable
                    # message['action'] = 'control from remote'

                    POWER_CODE = self.commandRX[8:10]
                    self.devices_state[dev_mac]['status'] = POWER[POWER_CODE].upper()
                    MODE_CODE = self.commandRX[16:18]
                    self.devices_state[dev_mac]['mode'] = MODE[MODE_CODE]
                    FAN_CODE = self.commandRX[20:22]
                    self.devices_state[dev_mac]['fan'] = FAN[FAN_CODE]
                    ERROR_CODE = self.commandRX[24:26]
                    self.devices_state[dev_mac]['error'] = ERROR[ERROR_CODE]
                    ROOMTEMP_CODE = self.commandRX[26:30]
                    self.devices_state[dev_mac]['temperature'] = str((int(ROOMTEMP_CODE, 16)) / 10)
                    SETTEMP_CODE = self.commandRX[30:34]
                    self.devices_state[dev_mac]['settemp'] = (int(SETTEMP_CODE, 16)) / 10

                    self.devices_state[dev_mac]["presence"] = 3

                    data = {"target": "devices", "device_id": "airconet_"+dev_mac, "data": self.devices_state[dev_mac].copy(),
                            "subdevice_idx":0}
                    _log.debug("Airconet get data --> {} ".format(data))
                    data["data"]["presence"] = "online"
                    data["data"]["datetime"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    data["type"] = "ac"

                    #---> Publish control status (from remote OR last_status)
                    _log.debug("Publishing in receive commandRX {} {} \n".format("hvac/airconet/airconet_" + str(dev_mac).replace(":", "") + "/status",data))
                    self.vip.pubsub.publish(peer="pubsub",
                                            topic= "hvac/airconet/airconet_" + str(dev_mac).replace(":", "") + "/event",
                                            headers={'requesterID': self.core.identity, "message_type" : "event"},
                                            message=data)
                    _log.debug("ok ok")

                    # if self.devices_state[dev_mac]["updatetype"] != "laststatus":
                    #     setzerozone = {"target": "zone", "device_id": str(self.zone[dev_mac]), "data": {"too_hot": 0, "too_cold": 0}}
                    #     _log.debug("Publishing in receive commandRX setzerozone setzerozone {} {} \n".format("devices/airconet_" + str(dev_mac).replace(":", "") + "/state", setzerozone))
                    #     self.vip.pubsub.publish(peer="pubsub",
                    #                             topic="devices/airconet_" + str(dev_mac).replace(":", "") + "/state",
                    #                             headers={'requesterID': self.core.identity},
                    #                             message=setzerozone)
                    # _log.debug("ok ok 2 2")
                    # _log.debug(self.devices_state)
                    self.devices_state[dev_mac]["updatetype"] = "irremote"

                elif len(self.commandRX) == 40:                                     #---> Heartbeat command detech
                    # -----> decryp Aes - 128 - cbc from self.commandRX = '00010010' + (encryp mac + suplybyte(ff))
                    # -----> (encryp mac + suplybyte(ff))  have to decode we call it heartbeatDecryp.
                    heartbeatencryp = self.commandRX[8:]                            #-----> Cut text 00010010
                    decryptor = AES.new(key, mode, IV=IV)
                    heartbeatDecryp = decryptor.decrypt(unhexlify(heartbeatencryp))
                    heartbeatDecryp = hexlify(heartbeatDecryp).decode("utf-8")
                    dev_mac = heartbeatDecryp[:12].lower()                         # -----> cut suplybyte(ff) and get mac.
                    _log.debug(dev_mac)

                    if dev_mac in self.devices_state.keys():                       # ----> Update device from heartbeat if IP change or not have data in devices_state.
                        self.devices_state[dev_mac]["presence"] = 3                # ----> status score online when HB come
                        if self.devices_state[dev_mac]['ip'] != dev_addr[0]:       # -----> Update IP if change.
                            self.devices_state[dev_mac]['ip'] = dev_addr[0]
                            _log.debug("*****Heartbeat IP change *****")
                    else:                                                           # -----> Update New Device.
                        self.devices_state[dev_mac] = {"ip": dev_addr[0], "port": dev_addr[1], 'status': "Unknown", 'mode': "Unknown",
                                                       'fan': "Unknown", 'settemp': "Unknown", 'temperature': "Unknown", 'error' : "Unknown",
                                                         "updatetype":"laststatus"}
                        _log.debug("*****Heartbeat New device found ---> update to store*****")
                        _log.debug("new dict create --> {}".format(self.devices_state[dev_mac]))
                        self.irdevice.setDeviceStatus({"settemp": 25,
                                                       "mode": "cool",
                                                       "fan": "low",
                                                       "status": 'LAST_STATUS',
                                                       "device_id": dev_mac,
                                                       "ip": self.devices_state[dev_mac]["ip"],
                                                       "port": self.devices_state[dev_mac]["port"]})
                        _log.debug("send last status for {}".format(key))

                    self.macip[dev_mac] = {"addr": dev_addr}  # ----> store mac ip room from heartbeat
                    _log.debug("*****Heartbeat All***** {} ".format(self.macip))

                else:
                    _log.debug("Control command come with can not define device Mac")

            except Exception as e:
                _log.error("ERROR Loop while: {}".format(e))

    # ----> method to send Heartbeat to IoTHub.
    @Core.schedule(periodic(30))
    def rundown(self):
        if not self.devices_state:
            return
        for dev_mac in self.devices_state:
            if self.devices_state[dev_mac]["presence"] > 0:
                self.devices_state[dev_mac]["presence"] -= 1
    
    # ----> method to send Heartbeat to IoTHub.
    @Core.schedule(periodic(60))
    def heartbeat(self):
        self.laststatus()
        # -----> check if first time start Agent Then Publish Heartbeat
        # -----> send Only offline
        if self.first_time != True :
            _log.debug("*****   HB Sent   *****")
            for amac in self.devices_state.keys():
                data = {"device_id": amac, "data": self.devices_state[amac].copy()}
                data["data"]["presence"] = "online" if data["data"]["presence"] > 0 else "offline"
                data["data"]["datetime"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if data["data"]["presence"] == "offline":
                    _log.debug("Publishing Offline devices/airconet_{}/state {}".format(amac, data))
                    self.vip.pubsub.publish(peer="pubsub", topic="devices/airconet_{}/state".format(amac),
                                            headers={'requesterID': self.core.identity},
                                            message=data)
            self.macip.clear()
        else:
            self.first_time = False

    def laststatus(self):
        for amac in self.devices_state.keys():
            self.devices_state[amac]["updatetype"] = "laststatus"
            self.irdevice.setDeviceStatus({"settemp": self.devices_state[amac]['settemp'], "mode": self.devices_state[amac]['mode'],
                                           "fan": self.devices_state[amac]['fan'], "status": 'last_status', "device_id": amac,
                                           "ip": self.devices_state[amac]["ip"], "port": self.devices_state[amac]["port"]})
            _log.debug("done send last status for {}".format(amac))

    #--->  listenning from IoTHubAgent V1
    @PubSub.subscribe(peer='pubsub', prefix='hvac/airconet/')
    def IoThubcontrol(self, peer, sender, bus, topic, headers, message):
        schema, agent_name, device_id, func = topic.split("/")
        if func == "command":
            _log.warning("!@!@!@!@!@#!@# subscribe IoThubcontrol :{}, sender:{}, bus:{}, topic:{}, message:{}".format(peer, sender, bus, topic, message))
            if self.irdevice:
                mac = device_id.split("_")[1]

                # ----> Updata status to devices_state
                for key in message.keys():
                    self.devices_state[mac][key] = message[key]

                self.devices_state[mac]["updatetype"] = "apicontrol"
                self.irdevice.setDeviceStatus({"settemp": self.devices_state[mac]['settemp'],
                                            "mode": self.devices_state[mac]['mode'],
                                            "fan": self.devices_state[mac]['fan'],
                                            "status": self.devices_state[mac]['status'],
                                            "device_id": mac,
                                            "ip": self.devices_state[mac]['ip'],
                                            "port": self.devices_state[mac]['port']})
                _log.debug(self.devices_state)
                _log.debug('Hi! I"m tom. I"m set airconet for you. !@#!@#!@#')

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        self.server_die = True

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(airconetserver,version=__version__)

if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
