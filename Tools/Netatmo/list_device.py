import netatmo


atmo = netatmo.WeatherStation(
    {
        "client_id": "60e1f4fee7d31a6b83091198",
        "client_secret": "t3ZtqGRccXmGdQEvzWL9SYObp9Kyj",
        "username": "brown.worawut@altotech.net",
        "password": "Altotech@2021",
    }
)

try:
    atmo.get_data()
except Exception as e:
    print(e)

# print(dir(atmo))
print(atmo.devices)
# exit()
for i in atmo.devices:
    try:
        print("type", i["type"], i["_id"], i["module_name"])
        # print(i)
        for j in i["modules"]:
            print("type", j["type"], j["_id"], j["module_name"])
    except:
        pass
