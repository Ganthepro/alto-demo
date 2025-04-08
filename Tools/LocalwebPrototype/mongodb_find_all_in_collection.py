import pymongo

myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636")

mydb = myclient["mytestdb"]
mycol = mydb["mytestcol"]

for x in mycol.find():
  print(x)
