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

from volttron.platform.agent import utils
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.vip.agent.subsystems.query import Query
from volttron.platform.scheduling import periodic, cron


utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '0.1'
DEFAULT_MESSAGE = 'Listener Message'
DEFAULT_AGENTID = "listener"
DEFAULT_HEARTBEAT_PERIOD = 5


class ListenerAgent(Agent):
    """Listens to everything and publishes a heartbeat according to the
    heartbeat period specified in the settings module.
    """

    def __init__(self, config_path, **kwargs):
        super().__init__(**kwargs)
        self.config = utils.load_config(config_path)
        self._agent_id = self.config.get('agentid', DEFAULT_AGENTID)
        self._message = self.config.get('message', DEFAULT_MESSAGE)
        self._heartbeat_period = self.config.get('heartbeat_period', DEFAULT_HEARTBEAT_PERIOD)
        self.counter = 0

        # set PostgresSQL, Firebase, IOTEventHub
        self.psql = PostgresManage()
        self.firebase_manage = FirebaseManage()
        self.client = self.initiate_eventhub()

        # declare variables for storing data
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

        # declare variable for setting anomaly conditions
        self.threshold_data = {
            "battery_percent": 40,
            "remaining_distance": 24,
            "speed": 60,
            "tower_location_radius": 24  # radius from every tower location
        }
        self.duration = 24  # unit: hour


        try:
            self._heartbeat_period = int(self._heartbeat_period)
        except:
            _log.warning('Invalid heartbeat period specified setting to default')
            self._heartbeat_period = DEFAULT_HEARTBEAT_PERIOD
        log_level = self.config.get('log-level', 'INFO')
        if log_level == 'ERROR':
            self._logfn = _log.error
        elif log_level == 'WARN':
            self._logfn = _log.warn
        elif log_level == 'DEBUG':
            self._logfn = _log.debug
        else:
            self._logfn = _log.info


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


    def calculate_remaining_distance(self, battery_percent, maximum_distance=60):
        """caculate the remaining travel distance from the current remaining battery capacity"""
        battery_percent = battery_percent / 100
        remaining_distance = battery_percent * maximum_distance

        return remaining_distance


    def get_lat_lon_distance(self, location1, location2, earth_radius=6373):
        """get distance in KM from 2 location coordinate (lat, lon)"""
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
        """trigger when new battery anomaly case is detected
        send Line notification to rider and update data in Firebase"""
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
        """trigger when new battery normal case is detected
        send Line notification to rider and update data in Firebase"""
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
        """trigger when new evbike anomaly case is detected
        send Line notification to rider and update data in Firebase"""
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
        """trigger when new evbike normal case is detected
        send Line notification to rider and update data in Firebase"""
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
        """trigger when new tracker anomaly case is detected
        send Line notification to rider and update data in Firebase"""
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
        """trigger when new tracker normal case is detected
        send Line notification to rider and update data in Firebase"""
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
        """
        - listen to IOTHub event message and filter only the selected device_ids 
        - use the config threshold_data to check whether the device is anomaly or normal
        - send Line notify to rider and update data in Firebase if there are new trigger detected

        Parameters
        ----------
        relation_data       : list of dict
                              contain all relational information of each rider

        tower_locations     : list of dict
                              contain name and location of each tower station

        device_parameters   : dict of list
                              contain list of selected keys in the event-message for each type of device
                              use for filtering the event-message

        threshold_data      : dict
                              contain the anomaly threshold for each conditions
        """
        battery_devices = [str(user.get('battery_id')).strip() for user in relation_data]
        ev_bike_devices = [str(user.get('evbike_id')).strip() for user in relation_data]
        ltracker_devices = [str(user.get('ltracker_id')).strip() for user in relation_data]

        battery_parameters = device_parameters['battery']
        ev_bike_parameters = device_parameters['ev_bike']
        ltracker_parameters = device_parameters['ltracker']

        def on_event(partition_context, event):
            """
            Outline for each device type
            ----------------------------
            1. filter event-message by device_id and gatewayid
            2. check all neccessary parameters in the message for each device type comparing to `device_parameters`
            3. check the message `type` for each message to be in the right condition
            4. check the anomaly/normal condition by comparing to `threshold_data`
            
            5. IF the current value is in anomaly condition
                IF the device isn't store in `anomaly_devices`
                    - get notification data in Firebase
                    IF there are data in Firebase
                        IF the latest notification is 'normal' or more than 24hr apart
                            - store device_id and timestamp to `anomaly_devices`
                            - send ANOMALY_REQUEST
                        ELSE
                            - store device_id and timestamp to `anomaly_devices`
                    ELSE
                        - store device_id and timestamp to `anomaly_devices`
                        - send ANOMALY_REQUEST
                ELSE
                    IF the latest notification is more than 24hr apart
                        - store device_id and timestamp to `anomaly_devices`
                        - send ANOMALY_REQUEST
            
            6. IF the current value is in normal condition
                IF device_id is in `anomaly_devices`
                    - store device_id and timestamp to `normal_devices`
                    - send NORMAL_REQUEST
                ELIF device_id not in `normal_devices`
                    - get notification data in Firebase
                    IF there are data in Firebase
                        IF latest status is 'anomaly'
                            - store device_id and timestamp to `normal_devices`
                            - send NORMAL_REQUEST
                        ELIF latest status is 'normal'
                            - store device_id and timestamp to `normal_devices`
                    ELSE
                        - store device_id and timestamp to `normal_devices`

            Note:
            - `anomaly_devices` and `normal_devices` are use to store device_id and timestamp so that we only need to get notification status from Firebase once
            """
            event_data = event.body_as_json()
            keys = list(event_data.keys())
            _now = pendulum.now(tz='Asia/Bangkok')

            try:
                # battery check anomaly / normal
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

                                            dt = pendulum.parse(datetime_string, tz="Asia/Bangkok")

                                            if dt.diff(_now).in_hours() > self.duration or status == 'normal':
                                                self.battery_anomaly_detected(device_id, state_of_charge, timestamp)
                                            
                                            elif status == 'anomaly':
                                                self.anomaly_devices['battery'][str(device_id)] = datetime_string
                                            
                                            else:
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `state_of_charge` node
                                            pass

                                    else:
                                        self.battery_anomaly_detected(device_id, state_of_charge, timestamp)
                                
                                else:
                                    latest_notification = self.anomaly_devices['battery'][str(device_id)]
                                    dt = pendulum.parse(latest_notification, tz="Asia/Bangkok")
                                    if dt.diff(_now).in_hours() > self.duration:
                                        self.battery_anomaly_detected(device_id, state_of_charge, timestamp)
                                    else:
                                        pass
                            
                            ## check back to normal cases
                            else:
                                if device_id in list(self.anomaly_devices['battery'].keys()):
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
                                                self.battery_normal_detected(device_id, state_of_charge, timestamp)
                                            
                                            elif status == 'normal':
                                                self.normal_devices['battery'][str(device_id)] = datetime_string
                                            
                                            else:
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `state_of_charge` node
                                            pass
                                    
                                    else:
                                        self.normal_devices['battery'][str(device_id)] = timestamp
                                
                                else:
                                    pass

                # ev_bike check anomaly / normal
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
                                                self.evbike_anomaly_detected(device_id, speed, timestamp)
                                            
                                            elif status == 'anomaly':
                                                self.anomaly_devices['ev_bike'][str(device_id)] = datetime_string
                                            
                                            else:
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `speed` node
                                            pass

                                    else:
                                        self.evbike_anomaly_detected(device_id, speed, timestamp)
                                
                                else:
                                    latest_notification = self.anomaly_devices['battery'][str(device_id)]
                                    dt = pendulum.parse(latest_notification, tz="Asia/Bangkok")
                                    if dt.diff(_now).in_hours() > self.duration:
                                        self.evbike_anomaly_detected(device_id, speed, timestamp)
                                    else:
                                        pass
                            
                            ## check back to normal cases
                            else:
                                if device_id in list(self.anomaly_devices['ev_bike'].keys()):
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
                                                self.evbike_normal_detected(device_id, speed, timestamp)
                                            
                                            elif status == 'normal':
                                                self.normal_devices['ev_bike'][str(device_id)] = datetime_string
                                            
                                            else:
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `speed` node
                                            pass
                                    
                                    else:
                                        self.normal_devices['ev_bike'][str(device_id)] = timestamp
                                
                                else:
                                    pass

                # ltracker check anomaly / normal
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
                                                self.ltracker_anomaly_detected(device_id, current_location, timestamp)
                                            
                                            elif status == 'anomaly':
                                                self.anomaly_devices['ltracker'][str(device_id)] = datetime_string
                                            
                                            else:
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `location` node
                                            pass

                                    else:
                                        self.ltracker_anomaly_detected(device_id, current_location, timestamp)
                                
                                else:
                                    latest_notification = self.anomaly_devices['ltracker'][str(device_id)]
                                    dt = pendulum.parse(latest_notification, tz="Asia/Bangkok")
                                    if dt.diff(_now).in_hours() > self.duration:
                                        self.ltracker_anomaly_detected(device_id, state_of_charge, timestamp)
                                    else:
                                        pass
                            
                            ## check back to normal cases
                            else:
                                if device_id in list(self.anomaly_devices['ltracker'].keys()):
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
                                                self.ltracker_normal_detected(device_id, current_location, timestamp)
                                            
                                            elif status == 'normal':
                                                self.normal_devices['ltracker'][str(device_id)] = datetime_string
                                            
                                            else:
                                                pass
                                        
                                        else:
                                            ## TODO: case when there are no `state_of_charge` node
                                            pass
                                    
                                    else:
                                        self.normal_devices['ltracker'][str(device_id)] = timestamp
                                
                                else:
                                    pass
      
            except Exception as e:
                print(e)

        # set the event listener to start at the latest index
        partition_ids = self.client.get_partition_ids()
        starting_position = {}
        for partition_id in partition_ids:
            partition_prop = self.client.get_partition_properties(partition_id)
            starting_position[str(partition_id)] = partition_prop["last_enqueued_sequence_number"] - 0

        # start listen to IOTHub event message
        with self.client:
            self.client.receive(
                on_event=on_event,  # `on_event` is the function when the new event message is detected
                starting_position=starting_position,  # "-1" is from the beginning of the partition.
            )


    def restart_variables(self):
        self.anomaly_devices = {
            "battery": {},
            "ev_bike": {},
            "ltracker": {}
        }
        self.normal_devices = {
            "battery": {},
            "ev_bike": {},
            "ltracker": {}
        }


    def run_all_methods(self):
        # Step 1 : get relation data from PostgresSQL (ev_rider, ev_relations)
        self.relation_data = self.get_relation_data()

        # Step 2 : get all tower locations
        self.tower_locations = self.get_station_location()

        # Step 3 : check anomaly and normal cases
        self.listen_iothub_message(self.relation_data, self.tower_locations, self.device_parameters, self.threshold_data)


    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        _log.debug("VERSION IS: {}".format(self.core.version()))
        if self._heartbeat_period != 0:
            _log.debug(f"Heartbeat starting for {self.core.identity}, published every {self._heartbeat_period}s")
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)
        query = Query(self.core)
        _log.info('query: %r', query.query('serverkey').get())

        # restart the all variables everyday
        self.core.schedule(cron('59 23 * * *'), self.restart_variables)


    @Core.schedule(periodic(1*60*60)) # trigger every 1 hours
    def update_relation_data(self):
        if self.counter == 0:
            self.counter += 1

            # start the pipeline on-start
            self.run_all_methods()
            
            return None

        try:
            # update `relation_data` and `tower_locations` data
            self.relation_data = self.get_relation_data()
            self.tower_locations = self.get_station_location()

            print("finished periodic data update")

        except Exception as e:
            print(f"[Error] Periodic: {e}")


def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(ListenerAgent, version=__version__)
    except Exception as e:
        _log.exception('unhandled exception')


if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
