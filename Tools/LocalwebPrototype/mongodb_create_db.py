import pymongo
# from pymongo import MongoReplicaSetClient

# myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636")
myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')
# myclient = pymongo.MongoClient("mongodb://root:Magicalmint636@127.0.0.1:27017/?replicaSet=rs0")
# myclient = pymongo.mongo_replica_set_client.MongoReplicaSetClient('127.0.0.1:27017', username="root", password="Magicalmint636", replicaSet='replicaSet01')

mydb = myclient["mytestdb"]
mycol = mydb["mytestcol"]
