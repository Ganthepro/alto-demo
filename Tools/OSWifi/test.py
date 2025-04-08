import subprocess 


class WifiNetwork:
    "The Singleton Class"

    @staticmethod
    def execute_cmd(cmd, passw=''):
        output = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate(input=(f'{passw}\n').encode('UTF-8'))
        return output[0].decode('UTF-8'), output[1].decode('UTF-8')

    @staticmethod
    def wifi_list():
        return WifiNetwork.execute_cmd(['nmcli', 'dev', 'wifi'])

    @staticmethod
    def check_wifi_ip():
        return WifiNetwork.execute_cmd(['ifconfig'])

    @staticmethod
    def wifi_up(wname, passw):
        return WifiNetwork.execute_cmd(['sudo', '-S', 'nmcli', 'c', 'up', wname], passw)

    @staticmethod
    def wifi_down(wname, passw):
        return WifiNetwork.execute_cmd(['sudo', '-S', 'nmcli', 'c', 'down', wname], passw)


output, _ = WifiNetwork.check_wifi_ip()
print(output)
print(_)

w_ip = output[output.find("wlo1"):output.find("wlo1") + 120]
print(w_ip)
if w_ip.find("inet") > -1:
    print("Yes")
    tmp = WifiNetwork.wifi_down("Alto_Energybox2.4G", 'altotech')
else:
    print("No")
    tmp = WifiNetwork.wifi_up("Alto_Energybox2.4G", 'altotech')
