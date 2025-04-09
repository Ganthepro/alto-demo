import gevent.monkey
gevent.monkey.patch_all()

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from requests.exceptions import RequestException

import pyrebase
from volttron.platform.agent import utils

_log = logging.getLogger(__name__)
utils.setup_logging()


def alto_firebase_object_factory(object_type: str):
    if object_type == 'chiller_plant_site':
        return ChillerPlantSite
    else:
        raise NotImplementedError


@dataclass
class AltoFirebaseObject(ABC):
    firebase_config: dict
    firebase_path: str

    def __post_init__(self):
        self.data = dict()
        self._initialize_connection()

    def _initialize_connection(self):
        try:
            self.firebase_client = pyrebase.initialize_app(self.firebase_config)
            self.firebase_db = self.firebase_client.database()
        except RequestException as e:
            _log.error(f"Error connecting to Firebase: {e}")
            self.firebase_client = None
            self.firebase_db = None

    def get(self):
        try:
            return self.firebase_db.child(self.firebase_path).get().val() if self.firebase_db else None
        except RequestException as e:
            _log.error(f"Error getting data from Firebase: {e}")
            self._initialize_connection()
            return None

    def set(self):
        try:
            return self.firebase_db.child(self.firebase_path).set(self.data) if self.firebase_db else None
        except RequestException as e:
            _log.error(f"Error setting data to Firebase: {e}")
            self._initialize_connection()
            return None

    def update(self):
        try:
            return self.firebase_db.child(self.firebase_path).update(self.data) if self.firebase_db else None
        except RequestException as e:
            _log.error(f"Error updating data in Firebase: {e}")
            self._initialize_connection()
            return None

    def push(self):
        try:
            return self.firebase_db.child(self.firebase_path).push(self.data) if self.firebase_db else None
        except RequestException as e:
            _log.error(f"Error pushing data to Firebase: {e}")
            self._initialize_connection()
            return None

    @abstractmethod
    def check_config(self):
        raise NotImplementedError

    @abstractmethod
    def update_data(self, topic: str, message: dict):
        raise NotImplementedError

    @abstractmethod
    def subscribed_topics(self):
        raise NotImplementedError


@dataclass
class ChillerPlantSite(AltoFirebaseObject):
    config: dict

    def __post_init__(self):
        super().__post_init__()
        self.check_config()

        self.mapping = {  # Mapping from Volttron message to Firebase datapoint name
            'power': 'power',
            'efficiency': 'efficiency',
            'efficiency_ref': 'efficiencyRef',
            'efficiency_annual': 'efficiencyAnnual',
            'cooling_rate': 'coolingLoad',
            'cumulative_energy': 'cumulativeEnergy',
            'cumulative_cooling_energy': 'cumulativeCoolingEnergy',
            'cumulative_energy_saving': 'cumulativeEnergySaving',
            'cumulative_carbon_footprint': 'cumulativeCarbonFootprintReduction',  # this is not a typo
            'cumulative_carbon_footprint_reduction': 'cumulativeCarbonFootprintReduction',
            'cumulative_tree_saved': 'cumulativeTreeSaved',
            'plant_capacity': 'plantCapacity',
            'plant_capacity_percentage': 'plantCapacityPercentage',
            'available_capacity': 'availableCapacity',
            'available_capacity_percentage': 'availableCapacityPercentage',
            'running_capacity': 'runningCapacity',
            'running_capacity_percentage': 'runningCapacityPercentage',
            'ct_approach_temperature': 'CTApproachTemperature',
            'ct_approach_temperature_ref': 'CTApproachTemperatureRef',
            'ch_setpoint_read': 'chilledWaterSetpointTemperature',
            'alltime_cumulative_energy': 'allTimeCumulativeEnergy',
            'alltime_cumulative_cooling_energy': 'allTimeCumulativeCoolingEnergy'
        }

        # Initialize self.data
        self.data['timestamp'] = None
        self.data['datetime'] = None
        for v in self.mapping.values():  # For overall plant's points
            self.data[v] = None
        self.data['equipmentEfficiency'] = dict(ch=None, chp=None, pchp=None, schp=None, cdp=None, ct=None, ch_ref=None, chp_ref=None,
                                                cdp_ref=None, ct_ref=None, pchp_ref=None, schp_ref=None)
        self.data['outdoorWeather'] = dict(drybulb_temperature=None, wetbulb_temperature=None, humidity=None)
        self.data['condenserWaterLoop'] = {
            'condenserWaterSupplyTemperature': None,
            'condenserWaterReturnTemperature': None,
            'condenserWaterFlowRate': None,
        }
        self.data['chilledWaterLoop'] = {
            'chilledWaterSupplyTemperature': None,
            'chilledWaterReturnTemperature': None,
            'chilledWaterFlowRate': None,
        }
        self.data['equipments'] = [{
            'deviceId': device_id,
            'type': device_type,
            "status": None,
        } for device_id, device_type in self.config['equipments'].items()]

    def check_config(self):
        assert 'condenser_water_loop' in self.config.keys(), '"condenser_water_loop" is not defined in the config.'
        assert 'chilled_water_loop' in self.config.keys(), '"chilled_water_loop" is not defined in the config.'
        assert 'outdoor_weather' in self.config.keys(), '"outdoor_weather" config is not defined.'
        assert 'equipments' in self.config.keys(), '"equipments" config is not defined.'

    # TODO: make this function more generic and configurable through config file only
    def update_data(self, topic: str, message: dict):
        """
        Update the data dictionary with the message from Volttron. This includes
        - Overall plant datapoints such as efficiency, cooling_rate, etc.
        - Each type of equipment's efficiency
        - Each equipment's status
        - CDS temperature
        - Outdoor weather data
        """
        # Step 1: Retrieve device_id from topic
        if len(topic.split('/')) != 4:
            _log.error(f'Invalid topic format for the topic {topic}')
        _, _, device_id, _ = topic.split('/')

        # Step 2.1: Update overall plant's datapoints
        if device_id == 'plant':

            for volttron_point, fb_point in self.mapping.items():
                if volttron_point in message.keys():
                    self.data[fb_point] = message[volttron_point]

            if 'efficiency_ch' in message.keys():
                self.data['equipmentEfficiency']['ch'] = message['efficiency_ch']
            if 'efficiency_chp' in message.keys():
                self.data['equipmentEfficiency']['chp'] = message['efficiency_chp']
            if 'efficiency_pchp' in message.keys():
                self.data['equipmentEfficiency']['pchp'] = message['efficiency_pchp']
            if 'efficiency_schp' in message.keys():
                self.data['equipmentEfficiency']['schp'] = message['efficiency_schp']
            if 'efficiency_cdp' in message.keys():
                self.data['equipmentEfficiency']['cdp'] = message['efficiency_cdp']
            if 'efficiency_ct' in message.keys():
                self.data['equipmentEfficiency']['ct'] = message['efficiency_ct']
            if 'efficiency_ch_ref' in message.keys():
                self.data['equipmentEfficiency']['ch_ref'] = message['efficiency_ch_ref']
            if 'efficiency_chp_ref' in message.keys():
                self.data['equipmentEfficiency']['chp_ref'] = message['efficiency_chp_ref']
            if 'efficiency_cdp_ref' in message.keys():
                self.data['equipmentEfficiency']['cdp_ref'] = message['efficiency_cdp_ref']
            if 'efficiency_ct_ref' in message.keys():
                self.data['equipmentEfficiency']['ct_ref'] = message['efficiency_ct_ref']

        # Step 2.2: Update Condenser loop information
        elif device_id == self.config['condenser_water_loop']['device_id']:
            if "supply_water_temperature" in message.keys():
                self.data['condenserWaterLoop']['condenserWaterSupplyTemperature'] = message['supply_water_temperature']
            if "return_water_temperature" in message.keys():
                self.data['condenserWaterLoop']['condenserWaterReturnTemperature'] = message['return_water_temperature']
            if "flow_rate" in message.keys():
                self.data['condenserWaterLoop']['condenserWaterFlowRate'] = message['flow_rate']
        
        # Step 2.2: Update Chilled loop information
        elif device_id == self.config['chilled_water_loop']['device_id']:
            if "supply_water_temperature" in message.keys():
                self.data['chilledWaterLoop']['chilledWaterSupplyTemperature'] = message['supply_water_temperature']
            if "return_water_temperature" in message.keys():
                self.data['chilledWaterLoop']['chilledWaterReturnTemperature'] = message['return_water_temperature']
            if "flow_rate" in message.keys():
                self.data['chilledWaterLoop']['chilledWaterFlowRate'] = message['flow_rate']

        # Step 2.3: Update outdoor weather data
        elif device_id == self.config['outdoor_weather']['device_id']:
            for k in self.data['outdoorWeather'].keys():
                if k in message.keys():
                    self.data['outdoorWeather'][k] = message[k]

        # Step 2.4: Update equipment's status
        elif device_id in self.config['equipments'].keys():
            # Diaplay priority: alarm > maintenance > running > standby(default)
            
            # Verify if the device type is defined
            device_type = self.config['equipments'].get(device_id, None)
            if device_type is None:
                _log.error(f'Device type for {device_id} is not defined in the config.')
                return

            if 'status_read' in message.keys():
                status = {0: 'standby', 1: 'running'}.get(int(message['status_read']), 'standby')
                    
                # Priority 1: check if the device is in `maintenance` state
                if 'maintenance' in message.keys() and message['maintenance']:
                    status = 'maintenance'
                # Priority 2: check if the device is in `alarm` state
                elif 'alarm' in message.keys() and message['alarm']:
                    status = 'alarm'
                
                # (hard-coded for VENCO) if a chiller is under `maintenance`, its CHP and CDP need to be set to `maintenance` as well
                if status == 'maintenance' and device_id.startswith('chiller_'):
                    chiller_id = device_id.split('_')[1]
                    for dev in self.data['equipments']:
                        # update CHP
                        if dev['deviceId'] == f'chp_{chiller_id}':
                            dev['status'] = status
                        # update CDP
                        if dev['deviceId'] == f'cdp_{chiller_id}':
                            dev['status'] = status
                
                # update equipment's status
                equipment_params: list = self.config['equipment_params'].get(device_type, list())
                for dev in self.data['equipments']:
                    if dev['deviceId'] == device_id:
                        dev['status'] = status
                        for param in equipment_params:
                            if param in message.keys():
                                dev[str(param)] = message[param]

        else:
            return  # Do not update timestamp/datetime if the device_id is not recognized

        # Step 3: Update timestamp and datetime
        self.data['timestamp'] = message['timestamp']
        self.data['datetime'] = message['datetime']

    @property
    def subscribed_topics(self):
        return ['datalogger']
