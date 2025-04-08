import pymongo

myclient = pymongo.MongoClient("127.0.0.1", 27017, username="root", password="Magicalmint636")

print(myclient.list_database_names())

mydb = myclient["mytestdb"]
print(mydb.list_collection_names())