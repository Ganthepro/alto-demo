import pymongo

# myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636")
# myclient = pymongo.MongoClient("mongodb://root:Magicalmint636@localhost:27017/?replicaSet=rs0")
myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636", replicaSet='rs0')

mydb = myclient["mytestdb"]
mycol = mydb["mytestcol"]

myquery = { "altotest": "test" }
# newvalues = { "$set": { "altotest2": "test3" } }
# newvalues = { "$set": { "altotest3.in2.in2": {"a": "aa", "c": "cc"} } }
# newvalues = [{ "$set": { "altotest3.in2.in2": {"a": "aa", "c": "cc2"} } }] # patch
newvalues = [{ "$set": { "altotest2.in2.in2": {"d": "dd3"} } }] # patch

# mycol.update_one(myquery, newvalues, upsert=True)
# mycol.update_one({}, newvalues, upsert=True)
# mycol.update_many({"_id": {"$in": ["aa/bb/cc"]}}, newvalues, upsert=True) # patch
mycol.update_many({"_id": {"$in": ["aa/bb/cc3"]}}, newvalues, upsert=True) # patch

#print "customers" after the update:
for x in mycol.find():
  print(x)
