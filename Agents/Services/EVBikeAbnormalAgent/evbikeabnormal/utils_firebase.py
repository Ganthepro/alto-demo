import pyrebase
import time

class FirebaseManage:
    def __init__(self):
        self.db = self.initiate_connection()


    def initiate_connection(self):
        try:
            print(f"Connecting to Firebase ...")
            firebaseConfig = {
                "apiKey": "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM",
                "authDomain": "altohotel-b6ae5.firebaseapp.com",
                "databaseURL": "https://altohotel-b6ae5.firebaseio.com",
                "projectId": "altohotel-b6ae5",
                "storageBucket": "altohotel-b6ae5.appspot.com",
                "messagingSenderId": "599435241073",
                "appId": "1:599435241073:web:669288fd44d337f8f05dd0",
                "measurementId": "G-BH74T9JDCH"
            }
            fb = pyrebase.initialize_app(firebaseConfig)
            db = fb.database()
            print("Successfully connected to Firebase")
            return db

        except Exception as e:
            print("Error while connecting to Firebase", e)
            return None


    def get_battery_data(self, battery_id):
        try:
            if self.db is not None:
                battery = self.db.child(f'EV/Beta_Energy_Solution/battery/{battery_id}/electric/subdev_0').get()

                data = battery.val()
                if data is None:
                    return None

                state_of_charge = data.get('state_of_charge')
                timestamp = data.get('timestamp')

                state_of_charge = {
                    "value": state_of_charge,
                    "timestamp": timestamp
                }

                return state_of_charge

            else:
                return None

        except Exception as e:
            print(e)
            return None


    def get_evbike_data(self, evbike_id):
        try:
            if self.db is not None:
                evbike = self.db.child(f'EV/Beta_Energy_Solution/ev_bike/{evbike_id}/device/subdev_0').get()

                data = evbike.val()
                if data is None:
                    return None

                speed = data.get('speed')
                timestamp = data.get('timestamp')

                speed = {
                    "value": speed,
                    "timestamp": timestamp
                }

                return speed

            else:
                return None

        except Exception as e:
            print(e)
            return None


    def get_ltracker_data(self, ltracker_id):
        try:
            if self.db is not None:
                ltracker = self.db.child(f'EV/Beta_Energy_Solution/ltracker/{ltracker_id}/location/subdev_0').get()

                data = ltracker.val()
                if data is None:
                    return None

                lat = data.get('lat')
                lon = data.get('lon')
                timestamp = data.get('timestamp')

                location = {
                    "lat": lat,
                    "lon": lon,
                    "timestamp": timestamp
                }

                return location

            else:
                return None

        except Exception as e:
            print(e)
            return None


# class demo
if __name__ == "__main__":
    firebase_manage = FirebaseManage()
    
    battery_data = firebase_manage.get_battery_data("ML60200718HCA1B0025")
    print("battery_data: ", battery_data)

    evbike_data = firebase_manage.get_evbike_data("LGTDW3BK0LH000008")
    print("evbike_data: ", evbike_data)

    ltracker_data = firebase_manage.get_ltracker_data("869405031202485")
    print("ltracker_data: ", ltracker_data)
