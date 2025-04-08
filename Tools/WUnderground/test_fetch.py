import requests
import pandas as pd
import pendulum
import json
from datetime import timedelta
import numpy as np
import threading


def get_outdoor_weather_data(station_key="", start_time=pendulum.datetime(2021, 6, 1, tz='Asia/Bangkok'), end_time=pendulum.now('Asia/Bangkok')):
    dt = pendulum.now('Asia/Bangkok')
    _valid_time = start_time
    _end_time = end_time
    Data = {}

    def worker(dt):
        a = requests.get("https://api.weather.com/v1/location/{}:9:TH/observations/historical.json?apiKey=6532d6454b8aa370768e63d6ba5a832e&units=e&startDate={}".format(station_key, dt))
        b = json.loads(a.text)
        c = pd.DataFrame(b["observations"])
        Data[dt] = c
        
    num_th = 20
    while _end_time > _valid_time:
        
        threads = []        
        for i in range(num_th):            
            if _end_time <= _valid_time:
                break
            
            dt = _valid_time.strftime("%Y%m%d")
            t = threading.Thread(target=worker, args=(dt,))
            threads.append(t)       
            _valid_time = _valid_time.add(days=1)
            
        for t in threads:
            t.start()           
        for t in threads:
            t.join()

    df = pd.concat([Data[k] for k in Data], axis=0)

    # Remove columns with NULL more than 90% data as null.
    cols_to_delete = df.columns[df.isnull().sum()/len(df) > .90]
    df.drop(cols_to_delete, axis = 1, inplace = True)

    df = df.sort_values(by="valid_time_gmt")

    df["datetime"] = pd.to_datetime(df["valid_time_gmt"].astype(int)*1e9) + timedelta(hours=7)
    df = df.reset_index(drop=True)
    df = df.set_index("datetime")

    # Drop irrelevant columns
    columns = ['key', 'class', 'expire_time_gmt', 'obs_id', 'obs_name']
    df.drop(columns=columns, inplace=True)

    return df

def fahrenheit_to_celsius(temperature):
    celsius = (temperature-32)*5/9
    return round(celsius, 2)

def pressure_inHg_to_mbar(pressure):
    mbar = pressure * 33.8639
    return round(mbar, 2)

def mph_to_kmh(wind_speed):
    kmh = wind_speed * 1.6
    return round(kmh, 2)

start_time = pendulum.yesterday('Asia/Bangkok')
end_time = pendulum.now('Asia/Bangkok')

# call API : get weather data
station_key = "VTBD"
df = get_outdoor_weather_data(station_key, start_time, end_time)

# declare neccessary columns and firebase node names
columns = ["wx_phrase", "temp", "dewPt", "rh", "pressure", "wspd", "wdir_cardinal", "valid_time_gmt"]

df = df[columns]

# convert data type from int64 to float64
data_to_convert = list(df.select_dtypes([np.number]).columns)
for name in data_to_convert:
    df[name] = df[name].astype(float)

last_row = df.iloc[-1]

# create dict to update to firebase
data = {
    "weather_condition": {"unit": "None", "value": last_row["wx_phrase"]}, 
    "temperature": {"unit": "celsius", "value": fahrenheit_to_celsius(last_row["temp"])},
    "dew_point": {"unit": "celsius", "value": fahrenheit_to_celsius(last_row["dewPt"])},
    "humidity": {"unit": "%", "value": last_row["rh"]},
    "pressure": {"unit": "mb", "value": pressure_inHg_to_mbar(last_row["pressure"])},
    "wind_speed": {"unit": "km/h", "value": mph_to_kmh(last_row["wspd"])},
    "wind_direction": {"unit": "None", "value": last_row["wdir_cardinal"]},
    "updated_at": int(last_row["valid_time_gmt"])
}

print(data)