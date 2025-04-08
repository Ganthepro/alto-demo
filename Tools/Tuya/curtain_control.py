import tinytuya

"""
OUTLET Device
"""
d = tinytuya.OutletDevice('00660024a4e57c13f633', '192.168.1.196', 'cf24d74a4aa7b908')
d.set_version(3.3)
data = d.status()  

# Show status and state of first controlled switch on device
print('Dictionary %r' % data)
print('State (bool, true is ON) %r' % data['dps']['1'])  

# Toggle switch state
# switch_state = data['dps']['1']
# data = d.set_status('open', switch=1)  # This requires a valid key
data = d.set_status('close', switch=1)  # This requires a valid key
if data:
    print('set_status() result %r' % data)

# # On a switch that has 4 controllable ports, turn the fourth OFF (1 is the first)
# data = d.set_status(False, 4)
# if data:
#     print('set_status() result %r' % data)
#     print('set_status() extra %r' % data[20:-8])