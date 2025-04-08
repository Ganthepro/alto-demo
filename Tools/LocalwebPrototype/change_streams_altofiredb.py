import pymongo
from bson.json_util import dumps
import sys
import pprint

# myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636")
myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

# mydb = myclient["mytestdb"]
# mycol = mydb["mytestcol"]

# change_stream = mydb.changestream.collection.watch()
# for change in change_stream:
#     print(dumps(change))
#     print('') # for readability only

# Database: `team` # Collection: `players`
db = myclient['altofiredb']

# using `watch()` for change streams in pymongo
try:
    with db['lastest_data'].watch() as change_stream:
        for change in change_stream:
            # pprint.pprint(change) ## should pretty print the newly inserted doc
            # print(dumps(change))
            print(dumps(change["fullDocument"]))
            print('') # for readability only
except KeyboardInterrupt:
    myclient.close()
    sys.exit()
except Exception as e:
    print(e)
