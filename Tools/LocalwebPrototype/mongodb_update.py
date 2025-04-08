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
mycol.update_many({}, newvalues, upsert=True) # patch

#print "customers" after the update:
for x in mycol.find():
  print(x)

# topic-like updating
# https://stackoverflow.com/questions/19603542/how-can-i-update-a-property-of-an-object-that-is-contained-in-an-array-of-a-pare
# partial update (patch)
# https://stackoverflow.com/questions/10290621/how-do-i-partially-update-an-object-in-mongodb-so-the-new-object-will-overlay