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
db = myclient['mytestdb']

pipeline = [
    {'$match': {'fullDocument.altotest3': 'mark'}}
    # {'$addFields': {'newField': 'this is an new field!'}}
]

# using `watch()` for change streams in pymongo
try:
    with db['mytestcol'].watch() as change_stream:
        for change in change_stream:
            pprint.pprint(change) ## should pretty print the newly inserted doc
except KeyboardInterrupt:
    myclient.close()
    sys.exit()
except Exception as e:
    print(e)


# 
# https://www.mongodb.com/community/forums/t/local-replica-set-on-docker-compose/135106
#
# https://www.mongodb.com/docs/manual/tutorial/convert-standalone-to-replica-set/
#
# https://stackoverflow.com/questions/59571945/the-changestream-stage-is-only-supported-on-replica-sets-error-while-using-mo
#
# https://github.com/docker-library/mongo/issues/475
#
# https://stackoverflow.com/questions/17852641/pymongo-mongoclient-connect-to-replicaset
#
# https://zgadzaj.com/development/docker/docker-compose/turning-standalone-mongodb-server-into-a-replica-set-with-docker-compose
#
# https://medium.com/@shantanoodesai/using-change-streams-in-mongodb-with-docker-desktop-for-windows-10-and-pymongo-96f0dbd2d59c
