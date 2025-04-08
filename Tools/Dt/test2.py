import datetime as dt
import pytz
# import dateutil.parser
# import arrow
# 
from time import gmtime, strftime
print(strftime("%z", gmtime()))

print(dt.datetime.now().astimezone().tzinfo)
