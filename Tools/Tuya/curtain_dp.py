import tinytuya

d = tinytuya.OutletDevice('00660024a4e57c13f633', '192.168.1.196', 'cf24d74a4aa7b908') # curtain 1
# d = tinytuya.OutletDevice('00660024a4e57c95faf5', '192.168.1.xxx', 'b18e5ad592b8bfd3') # curtain 2

d.set_version(3.3)
data = d.status() 
print('set_status() result %r' % data)
