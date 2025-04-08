import tinytuya

d = tinytuya.OutletDevice('ebd57f4fd41b31dd1fdd7o', '192.168.111.110', 'f5df56057f97c507') # CO2 1
# d = tinytuya.OutletDevice('eb266cba7d62b9ac0a8pwm', '192.168.111.16', '34fff50250fb83a0') # Temp&Humid 1
# d = tinytuya.OutletDevice('00660024a4e57c9651f6', '192.168.111.46', 'ab42ae459f04f95b') # curtain 1

blind = tinytuya.CoverDevice('00660024a4e57c9651f6', '192.168.111.46', 'ab42ae459f04f95b')
d.set_version(3.3)
blind.set_version(3.3)
blind_data = blind.status()
# data = d.status() 
# print(f'status: {data}')
print(f"status: {blind_data}")