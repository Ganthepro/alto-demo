import os
import sys
import logging
import requests
import pendulum
from math import sin, cos, sqrt, atan2, radians

from evbikeabnormal.utils_postgres import PostgresManage
from evbikeabnormal.utils_firebase import FirebaseManage
from evbikeabnormal.utils_backend import rider_notify_anomaly, rider_notify_normal

from azure.eventhub import EventHubConsumerClient

# from volttron.platform.agent import utils
# from volttron.platform.messaging.health import STATUS_GOOD
# from volttron.platform.vip.agent import Agent, Core
# from volttron.platform.vip.agent.subsystems.query import Query
# from volttron.platform.scheduling import periodic, cron


class Agent:
    def __init__(self):
        self.psql = PostgresManage()
        self.firebase_manage = FirebaseManage()
        self.client = self.initiate_eventhub()

        self.relation_data = []  # update every 1 hour
        self.anomaly_devices = {  # listen for normal cases
            "battery": {},
            "ev_bike": {},
            "ltracker": {}
        }
        self.normal_devices = {
            "battery": {},
            "ev_bike": {},
            "ltracker": {}
        }
        self.device_parameters = {
            "battery": ['device_id', 'type', 'state_of_charge', 'timestamp'],
            "ev_bike": ['device_id', 'type', 'speed', 'timestamp'],
            "ltracker": ['device_id', 'type', 'lat', 'lon', 'timestamp']
        }
        self.tower_locations = []
        self.threshold_data = {
            "battery_percent": 40,
            "remaining_distance": 24,
            "speed": 60,
            "tower_location_radius": 24  # radius from every tower location
        }
        self.duration = 24  # unit: hour


    def initiate_eventhub(self):
        connection_str = 'Endpoint=sb://iothub-ns-betaiothub-13344990-073ef16d21.servicebus.windows.net/;SharedAccessKeyName=iothubowner;SharedAccessKey=9tv4A3cJpTzvy77f1WaLPxSRd8mMuLYN2Nd8f7nprFI=;EntityPath=betaiothubprod'
        eventhub_name = 'betaiothubprod'
        client = EventHubConsumerClient.from_connection_string(connection_str, "$default")
        return client


    def get_ev_rider(self):
        query = """SELECT id, person_id, line_id FROM ev_rider"""
        records = self.psql.execute_query(query)
        return records


    def get_ev_relations(self, rider_id):
        query = f'SELECT id, rider_id, battery_id, evbike_id, ltracker_id FROM ev_relations ' \
                f'WHERE rider_id={rider_id}'
        records = self.psql.execute_query(query)
        return records


    def get_station_location(self):
        query = "SELECT gateway_name, room_id, location FROM gateway \
                WHERE gateway_name like 'beta_ev_tower_%'"
        records = self.psql.execute_query(query)
        if len(records) > 0:
            records = [record for record in records if record.get('location') is not None]
            for record in records:
                location = record.get('location')
                record['lat'] = float(location.split(", ")[0])
                record['lon'] = float(location.split(", ")[-1])

        return records


    def get_relation_data(self):
        ev_riders = self.get_ev_rider()

        relation_data = []
        for ev_rider in ev_riders:
            rider_id = ev_rider['id']
            line_id = ev_rider['line_id']
            relation = self.get_ev_relations(rider_id)

            if len(relation) > 0:
                relation = relation[0]
                relation['line_id'] = line_id
                relation_data.append(relation)

        return relation_data


    def get_lat_lon_distance(self, location1, location2, earth_radius=6373):
        try:
            lat1 = radians(location1["lat"])
            lon1 = radians(location1["lon"])
            lat2 = radians(location2["lat"])
            lon2 = radians(location2["lon"])

            diff_lat = lat2 - lat1
            diff_lon = lon2 - lon1

            a = sin(diff_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(diff_lon / 2) ** 2
            c = 2 * atan2(sqrt(a), sqrt(1 - a))
            distance = earth_radius * c  # unit : km

            return distance

        except Exception as e:
            print(e)
            return None


    def battery_anomaly_detected(self, device_id, state_of_charge, timestamp):
        try:
            condition_name = "state_of_charge"
            current_value = state_of_charge
            threshold_max = None
            threshold_min = self.threshold_data.get('battery_percent')
            detect_value = None

            rider_notify_anomaly(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)

            self.anomaly_devices['battery'][str(device_id)] = timestamp
            if device_id in list(self.normal_devices['battery'].keys()):
                _ = self.normal_devices['battery'].pop(str(device_id))

        except Exception as e:
            print(e)


    def battery_normal_detected(self, device_id, state_of_charge, timestamp):
        try:
            condition_name = "state_of_charge"
            current_value = state_of_charge
            threshold_max = None
            threshold_min = self.threshold_data.get('battery_percent')
            detect_value = None

            rider_notify_normal(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)

            self.normal_devices['battery'][str(device_id)] = timestamp
            if device_id in list(self.anomaly_devices['battery'].keys()):
                _ = self.anomaly_devices['battery'].pop(str(device_id))

        except Exception as e:
            print(e)
    

    def evbike_anomaly_detected(self, device_id, speed, timestamp):
        try:
            condition_name = "speed"
            current_value = speed
            threshold_max = None
            threshold_min = self.threshold_data.get('speed')
            detect_value = None

            rider_notify_anomaly(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)

            self.anomaly_devices['ev_bike'][str(device_id)] = timestamp
            if device_id in list(self.normal_devices['ev_bike'].keys()):
                _ = self.normal_devices['ev_bike'].pop(str(device_id))

        except Exception as e:
            print(e)


    def evbike_normal_detected(self, device_id, speed, timestamp):
        try:
            condition_name = "speed"
            current_value = speed
            threshold_max = None
            threshold_min = self.threshold_data.get('speed')
            detect_value = None

            rider_notify_normal(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)

            self.normal_devices['ev_bike'][str(device_id)] = timestamp
            if device_id in list(self.anomaly_devices['ev_bike'].keys()):
                _ = self.anomaly_devices['ev_bike'].pop(str(device_id))

        except Exception as e:
            print(e)

    
    def ltracker_anomaly_detected(self, device_id, location, timestamp):
        try:
            condition_name = "location"
            current_value = location
            threshold_max = self.threshold_data.get('tower_location_radius')
            threshold_min = None
            detect_value = None

            rider_notify_anomaly(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)

            self.anomaly_devices['ltracker'][str(device_id)] = timestamp
            if device_id in list(self.normal_devices['ltracker'].keys()):
                _ = self.normal_devices['ltracker'].pop(str(device_id))

        except Exception as e:
            print(e)


    def ltracker_normal_detected(self, device_id, location, timestamp):
        try:
            condition_name = "location"
            current_value = location
            threshold_max = self.threshold_data.get('tower_location_radius')
            threshold_min = None
            detect_value = None

            rider_notify_normal(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)

            self.normal_devices['ltracker'][str(device_id)] = timestamp
            if device_id in list(self.anomaly_devices['ltracker'].keys()):
                _ = self.anomaly_devices['ltracker'].pop(str(device_id))

        except Exception as e:
            print(e)


    def listen_iothub_message(self, relation_data, tower_locations, device_parameters, threshold_data):
        """listen and filter only the input device_ids and parameters"""
        battery_devices = [str(user.get('battery_id')).strip() for user in relation_data]
        ev_bike_devices = [str(user.get('evbike_id')).strip() for user in relation_data]
        ltracker_devices = [str(user.get('ltracker_id')).strip() for user in relation_data]

        battery_parameters = device_parameters['battery']
        ev_bike_parameters = device_parameters['ev_bike']
        ltracker_parameters = device_parameters['ltracker']

        def on_event(partition_context, event):
            event_data = event.body_as_json()
            keys = list(event_data.keys())
            _now = pendulum.now(tz='Asia/Bangkok')

            try:
                # battery
                if event_data.get('gatewayid') == 'altopcbetatowermonitor' and event_data.get('device_id') in battery_devices:
                    if set(battery_parameters).issubset(keys):
                        parameter_type = event_data.get('type')
                        if parameter_type == 'electric':
                            device_id = event_data.get('device_id')
                            state_of_charge = event_data.get('state_of_charge')
                            timestamp = event_data.get('timestamp')
                            
                            device_data = {
                                "device_id": device_id, 
                                "state_of_charge": state_of_charge,
                                "timestamp": timestamp
                            }
                            print("data: ", device_data)

                            ## check anomaly cases
                            if state_of_charge <= threshold_data.get('battery_percent'):
                                if device_id not in list(self.anomaly_devices['battery'].keys()):
                                    ## check latest notification in firebase
                                    data = self.firebase_manage.db.child(f'EV/Beta_Energy_Solution/notification/anomaly/battery/{device_id}').get().val()
                                    if data is not None:
                                        notification_data = data.get('state_of_charge')
                                        if notification_data is not None:
                                            status = notification_data.get('status')
                                            datetime_string = notification_data.get('timestamp')
                                            print(status, datetime_string)

                                            dt = pendulum.parse(datetime_string, tz="Asia/Bangkok")

                                            if dt.diff(_now).in_hours() > self.duration or status == 'normal':
                                                print("send anomaly, set listening stream 1")
                                                self.battery_anomaly_detected(device_id, state_of_charge, timestamp)
                                            
                                            elif status == 'anomaly':
                                                print('update anomaly dict battery')
                                                self.anomaly_devices['battery'][str(device_id)] = datetime_string
                                            
                                            else:
                                                print("battery e1")
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `state_of_charge` node
                                            print("battery e2")
                                            pass

                                    else:
                                        print("send anomaly, set listening stream 2")
                                        self.battery_anomaly_detected(device_id, state_of_charge, timestamp)
                                
                                else:
                                    latest_notification = self.anomaly_devices['battery'][str(device_id)]
                                    dt = pendulum.parse(latest_notification, tz="Asia/Bangkok")
                                    if dt.diff(_now).in_hours() > self.duration:
                                        print("send anomaly, set listening stream 3")
                                        self.battery_anomaly_detected(device_id, state_of_charge, timestamp)
                                    else:
                                        print("battery e3")
                                        pass
                            
                            ## check back to normal cases
                            else:
                                if device_id in list(self.anomaly_devices['battery'].keys()):
                                    print("send normal 1")
                                    self.battery_normal_detected(device_id, state_of_charge, timestamp)
                                
                                elif device_id not in list(self.normal_devices['battery'].keys()):
                                    ## check latest notification in firebase
                                    data = self.firebase_manage.db.child(f'EV/Beta_Energy_Solution/notification/anomaly/battery/{device_id}').get().val()
                                    if data is not None:
                                        notification_data = data.get('state_of_charge')
                                        if notification_data is not None:
                                            status = notification_data.get('status')
                                            datetime_string = notification_data.get('timestamp')

                                            if status == 'anomaly':
                                                print("send normal 2")
                                                self.battery_normal_detected(device_id, state_of_charge, timestamp)
                                            
                                            elif status == 'normal':
                                                print('update normal dict battery 1')
                                                self.normal_devices['battery'][str(device_id)] = datetime_string
                                            
                                            else:
                                                print("battery n e1")
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `state_of_charge` node
                                            print("battery n e2")
                                            pass
                                    
                                    else:
                                        print('update normal dict battery 2')
                                        self.normal_devices['battery'][str(device_id)] = timestamp
                                
                                else:
                                    pass

                # ev_bike
                if event_data.get('gatewayid') == 'altopcbetatowermonitor' and event_data.get('device_id') in ev_bike_devices:
                    if set(ev_bike_parameters).issubset(keys):
                        parameter_type = event_data.get('type')
                        if parameter_type == 'device':
                            device_id = event_data.get('device_id')
                            speed = event_data.get('speed')
                            timestamp = event_data.get('timestamp')

                            device_data = {
                                "device_id": device_id,
                                "speed": speed,
                                "timestamp": timestamp
                            }
                            print("data: ", device_data)

                            ## check anomaly cases
                            if speed >= threshold_data.get('speed'):
                                if device_id not in list(self.anomaly_devices['ev_bike'].keys()):
                                    ## check latest notification in firebase
                                    data = self.firebase_manage.db.child(f'EV/Beta_Energy_Solution/notification/anomaly/ev_bike/{device_id}').get().val()
                                    if data is not None:
                                        notification_data = data.get('speed')
                                        if notification_data is not None:
                                            status = notification_data.get('status')
                                            datetime_string = notification_data.get('timestamp')

                                            dt = pendulum.parse(datetime_string, tz="Asia/Bangkok")

                                            if dt.diff(_now).in_hours() > self.duration or status == 'normal':
                                                print("send anomaly, set listening stream 1")
                                                self.evbike_anomaly_detected(device_id, speed, timestamp)
                                            
                                            elif status == 'anomaly':
                                                print('update anomaly dict evbike')
                                                self.anomaly_devices['ev_bike'][str(device_id)] = datetime_string
                                            
                                            else:
                                                print("evbike e1")
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `speed` node
                                            print("evbike e2")
                                            pass

                                    else:
                                        print("send anomaly, set listening stream 2")
                                        self.evbike_anomaly_detected(device_id, speed, timestamp)
                                
                                else:
                                    latest_notification = self.anomaly_devices['battery'][str(device_id)]
                                    dt = pendulum.parse(latest_notification, tz="Asia/Bangkok")
                                    if dt.diff(_now).in_hours() > self.duration:
                                        print("send anomaly, set listening stream 3")
                                        self.evbike_anomaly_detected(device_id, speed, timestamp)
                                    else:
                                        print("evbike e3")
                                        pass
                            
                            ## check back to normal cases
                            else:
                                if device_id in list(self.anomaly_devices['ev_bike'].keys()):
                                    print("send normal 1")
                                    self.evbike_normal_detected(device_id, speed, timestamp)
                                
                                elif device_id not in list(self.normal_devices['ev_bike'].keys()):
                                    ## check latest notification in firebase
                                    data = self.firebase_manage.db.child(f'EV/Beta_Energy_Solution/notification/anomaly/ev_bike/{device_id}').get().val()
                                    if data is not None:
                                        notification_data = data.get('speed')
                                        if notification_data is not None:
                                            status = notification_data.get('status')
                                            datetime_string = notification_data.get('timestamp')

                                            if status == 'anomaly':
                                                print("send normal 2")
                                                self.evbike_normal_detected(device_id, speed, timestamp)
                                            
                                            elif status == 'normal':
                                                print('update normal dict evbike 1')
                                                self.normal_devices['ev_bike'][str(device_id)] = datetime_string
                                            
                                            else:
                                                print("evbike n e1")
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `speed` node
                                            print("evbike n e2")
                                            pass
                                    
                                    else:
                                        print('update normal dict evbike 2')
                                        self.normal_devices['ev_bike'][str(device_id)] = timestamp
                                
                                else:
                                    pass

                # ltracker
                if event_data.get('gatewayid') == 'altopcbetatowermonitor' and event_data.get('device_id') in ltracker_devices:
                    if set(ltracker_parameters).issubset(keys):
                        parameter_type = event_data.get('type')
                        if parameter_type == 'location':
                            device_id = event_data.get('device_id')
                            lat = event_data.get('lat')
                            lon = event_data.get('lon')
                            timestamp = event_data.get('timestamp')

                            device_data = {
                                "device_id": device_id,
                                "lat": lat,
                                "lon": lon,
                                "timestamp": timestamp
                            }
                            print("data: ", device_data)

                            ## check anomaly cases
                            location_condition = True
                            tower_radius_threshold = self.threshold_data['tower_location_radius']

                            evbike_location = {
                                "lat": lat,
                                "lon": lon
                            }
                            current_location = f"{lat}, {lon}"

                            for tower_location in tower_locations:
                                distance = self.get_lat_lon_distance(evbike_location, tower_location)
                                if distance <= tower_radius_threshold and distance is not None:
                                    location_condition = False
                                    break

                            if location_condition == True:
                                if device_id not in list(self.anomaly_devices['ltracker'].keys()):
                                    ## check latest notification in firebase
                                    data = self.firebase_manage.db.child(f'EV/Beta_Energy_Solution/notification/anomaly/ltracker/{device_id}').get().val()
                                    if data is not None:
                                        notification_data = data.get('location')
                                        if notification_data is not None:
                                            status = notification_data.get('status')
                                            datetime_string = notification_data.get('timestamp')

                                            dt = pendulum.parse(datetime_string, tz="Asia/Bangkok")

                                            if dt.diff(_now).in_hours() > self.duration or status == 'normal':
                                                print("send anomaly, set listening stream 1")
                                                self.ltracker_anomaly_detected(device_id, current_location, timestamp)
                                            
                                            elif status == 'anomaly':
                                                print('update anomaly dict ltracker')
                                                self.anomaly_devices['ltracker'][str(device_id)] = datetime_string
                                            
                                            else:
                                                print("ltracker e1")
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `location` node
                                            print("ltracker e2")
                                            pass

                                    else:
                                        print("send anomaly, set listening stream 2")
                                        self.ltracker_anomaly_detected(device_id, current_location, timestamp)
                                
                                else:
                                    latest_notification = self.anomaly_devices['ltracker'][str(device_id)]
                                    dt = pendulum.parse(latest_notification, tz="Asia/Bangkok")
                                    if dt.diff(_now).in_hours() > self.duration:
                                        print("send anomaly, set listening stream 3")
                                        self.ltracker_anomaly_detected(device_id, state_of_charge, timestamp)
                                    else:
                                        print("ltracker e3")
                                        pass
                            
                            ## check back to normal cases
                            else:
                                if device_id in list(self.anomaly_devices['ltracker'].keys()):
                                    print("send normal 1")
                                    self.ltracker_normal_detected(device_id, current_location, timestamp)
                                
                                elif device_id not in list(self.normal_devices['ltracker'].keys()):
                                    ## check latest notification in firebase
                                    data = self.firebase_manage.db.child(f'EV/Beta_Energy_Solution/notification/anomaly/ltracker/{device_id}').get().val()
                                    if data is not None:
                                        notification_data = data.get('location')
                                        if notification_data is not None:
                                            status = notification_data.get('status')
                                            datetime_string = notification_data.get('timestamp')

                                            if status == 'anomaly':
                                                print("send normal 2")
                                                self.ltracker_normal_detected(device_id, current_location, timestamp)
                                            
                                            elif status == 'normal':
                                                print('update normal dict ltracker 1')
                                                self.normal_devices['ltracker'][str(device_id)] = datetime_string
                                            
                                            else:
                                                print("ltracker n e1")
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `state_of_charge` node
                                            print("ltracker n e2")
                                            pass
                                    
                                    else:
                                        print('update normal dict ltracker 2')
                                        self.normal_devices['ltracker'][str(device_id)] = timestamp
                                
                                else:
                                    pass
      
            except Exception as e:
                print(e)


        partition_0_prop = self.client.get_partition_properties("0")
        partition_1_prop = self.client.get_partition_properties("1")

        starting_position = {
            "0": partition_0_prop["last_enqueued_sequence_number"] - 0,
            "1": partition_1_prop["last_enqueued_sequence_number"] - 0
        }

        with self.client:
            self.client.receive(
                on_event=on_event,
                starting_position=starting_position,  # "-1" is from the beginning of the partition.
            )


    def run_all_methods(self):
        # Step 1 : get relation data from Postgres (ev_rider, ev_relations)
        self.relation_data = self.get_relation_data()
        print("relation_data:")
        for data in self.relation_data:
            print(data)

        # Step 2 : get all tower locations
        self.tower_locations = self.get_station_location()
        # print("tower_locations:")
        # for data in self.tower_locations:
        #     print(data)

        # Step 3 : check anomaly and normal cases
        print("listen to IOTEventHub...")
        self.listen_iothub_message(self.relation_data, self.tower_locations, self.device_parameters, self.threshold_data)


if __name__ == "__main__":
    agent = Agent()
    agent.run_all_methods()
