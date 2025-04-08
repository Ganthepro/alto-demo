import netatmo


atmo = netatmo.WeatherStation(
    {
        "client_id": "60e1693a80a84a35410606fe",
        "client_secret": "FJpomDgDHNUQneItqlbS4oc368yuOvYqON",
        "username": "brown.worawut@altotech.net",
        "password": "Altotech@2021",
    }
)

try:
    atmo.get_data()
except Exception as e:
    print(e)
print(atmo.devices)
# if self.atmo.devices:
