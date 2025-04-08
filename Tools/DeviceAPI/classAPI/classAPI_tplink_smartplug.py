#!/usr/bin/env python2
#
# TP-Link Wi-Fi Smart Plug Protocol Client
# For use with TP-Link HS-100 or HS-110
#
# by Lubomir Stroetmann
# Copyright 2016 softScheck GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import socket
from struct import pack
import time
import requests
import json
# from hive_lib import rgb_cie





def encrypt(string):
	# key = 171
	# result = pack('>I', len(string))
	# for i in string:
	# 	a = key ^ ord(i)
	# 	key = a
	# 	result += chr(a)
	return bytes(string, 'utf-8')


def decrypt(string):
	key = 171
	result = ""
	for i in string:
		a = key ^ ord(i)
		key = ord(i)
		result += chr(a)
	return result

commands = {
				'info'     : '{"system":{"get_sysinfo":{}}}',
				'on'       : '{"system":{"set_relay_state":{"state":1}}}',
				'off'      : '{"system":{"set_relay_state":{"state":0}}}',
				'cloudinfo': '{"cnCloud":{"get_info":{}}}',
				'wlanscan' : '{"netif":{"get_scaninfo":{"refresh":0}}}',
				'time'     : '{"time":{"get_time":{}}}',
				'schedule' : '{"schedule":{"get_rules":{}}}',
				'countdown': '{"count_down":{"get_rules":{}}}',
				'antitheft': '{"anti_theft":{"get_rules":{}}}',
				'reboot'   : '{"system":{"reboot":{"delay":1}}}',
				'reset'    : '{"system":{"reset":{"delay":1}}}',
				'energy'   : '{"emeter":{"get_realtime":{}}}'
	}
# cmd = '{"system":{"get_sysinfo":{}}}'
cmd = commands['off']
ip = '192.168.22.61'
port = 9999
# Send command and receive reply
try:
	sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock_tcp.connect((ip, port))
	sock_tcp.send(encrypt(cmd))
	data = sock_tcp.recv(2048)
	sock_tcp.close()

	print("Sent:     ", cmd)
	print("Received: ", decrypt(data[4:]))


except socket.error:
	quit("Cound not connect to host " + ip + ":" + str(port))


# commands = {
# 				'info'     : '{"system":{"get_sysinfo":{}}}',
# 				'on'       : '{"system":{"set_relay_state":{"state":1}}}',
# 				'off'      : '{"system":{"set_relay_state":{"state":0}}}',
# 				'cloudinfo': '{"cnCloud":{"get_info":{}}}',
# 				'wlanscan' : '{"netif":{"get_scaninfo":{"refresh":0}}}',
# 				'time'     : '{"time":{"get_time":{}}}',
# 				'schedule' : '{"schedule":{"get_rules":{}}}',
# 				'countdown': '{"count_down":{"get_rules":{}}}',
# 				'antitheft': '{"anti_theft":{"get_rules":{}}}',
# 				'reboot'   : '{"system":{"reboot":{"delay":1}}}',
# 				'reset'    : '{"system":{"reset":{"delay":1}}}',
# 				'energy'   : '{"emeter":{"get_realtime":{}}}'
# 	}
