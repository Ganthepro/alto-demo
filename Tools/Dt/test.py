import datetime as dt
import pytz

# from time import gmtime, strftime
# print(strftime("%z", gmtime()))

print(dt.datetime.now().astimezone().tzinfo)
tt = "2021-07-08 07:15:35.128338 +07:00".replace('+07:00','+0700') # for python 3.6.9

dn = dt.datetime.now()
d1 = dt.datetime.strptime(tt, "%Y-%m-%d %H:%M:%S.%f %z")
d2 = d1.astimezone(pytz.utc)
d3 = d2 + dt.timedelta(minutes=30)
print(dn)
print(dn.replace(tzinfo=dt.timezone(dt.timedelta(hours = 7))))
print(d1)
print(d2)
print(d3)
print(d3.hour)
print(d3.minute)
