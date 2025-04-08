import pymongo

myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

mydb = myclient["altofiredb"]
mycol = mydb["lastest_data_tree"]
# mycol = mydb["lastest_data"]

for x in mycol.find():
  print(x)
