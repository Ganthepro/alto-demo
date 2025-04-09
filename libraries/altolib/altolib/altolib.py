#
# altolib
#
# Copyright (c) 2020 François Wautier
# Altolib defines various classes that are needed to implement
# the various schema to be used by the Volttron agents.
# Multiple inheritance is expected.
#

import logging
import irgen
import datetime as dt
import time
import paho.mqtt.client as mqtt
from typing import Any, List, Mapping, Union, Optional
from volttron.platform.vip.agent import Agent, Core
from volttron.platform.scheduling import periodic


# Logging setup will have to be done by the actual agent
_log = logging.getLogger(__name__)

#: Run periodical actions every 10 secs. This means like every _rate configuration
#: will be to the closest multiiple greater
TIMERESOLUTION = 2
RIDSEP = "_^_"


class AltoNotImpl(Exception):
    """
        Exception raised when a method must be overloaded but has not been.

    """

    pass


class AltoSchemaError(Exception):
    """
        Exception raised when a schema does not meet the specs.

    """

    pass


class AltoDevice(object):
    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> object:
        """
        Simply setting up the parameters that are common to all devices.

        Every inheriting class, if overloading this method, must call it using super(). E.g.

                def __init__(self, controller, devid, ip_address):
                    < do something >
                    super().__init__(controller, devid, 1)
                    < do more things >

        All subclasses must initialise attribute current_state. current_state is a dictionary of
        of something. The first key is the subdevice index. The second key is the name of the schema,
        the third key is the name of the state and the value is the actual state, a string "on" or
        "off" for a switch, a dictionary for a sensor,  ....

        :param controller: The Agent instance that manages this device (and possibly many others).
        :type controller: AltoAgent
        :param devid: The unique id of this device. (Unique within the Agent's namespace)
        :type devid: str
        :param nbsubdev: The total number of subdevices for this device. Subdevices here mean entity
                         following the same schema. For instance a power strip would have 1 subdevice
                         per plug, a sensor would have 1 subdevice per probe e.g. 3phases electric
                         sensor. The indeces of subdevices are between 0 and nbsubdev - 1

                         Note that if a device supports multiple schema, all schemas must be supported by
                         subdevice 0.
        :param nbsubdev: int

        :returns: The device itself
        :rtype: AltoDevice

        """
        self.controller = controller
        self.device_id = devid
        self.number_subdevices = nbsubdev
        self.name_subdevices = [f"subdev_{i}" for i in range(0, nbsubdev)]
        self.current_state = {}
        for idx in range(nbsubdev):
            self.current_state[idx] = {}
        self.info = {}
        self.is_online = False

    def set_subdevice_name(self, subdevice_idx: int, name: str) -> bool:
        """
        Set the name of a subdevice. From then on, the name can be used  instead of its index
        By default, subdevcies are named subdev_X, with X the index.

        :param subdevice_idx: The index of the subdevice to name
        :type subdevice_idx: int
        :param name: The name
        :type name: str

        :returns: True if everything OK. False if something went wrong, log an error/warning

        """
        if subdevice_idx in range(self.number_subdevices):
            if name not in self.name_subdevices:
                self.name_subdevices[subdevice_idx] = name
            elif self.name_subdevices.index(name) != subdevice_idx:
                _log.error(
                    f"Subdevice name must be unique. Subdevice {subdevice_idx} cannot be named {name} has it is already used for subdevice {self.name_subdevices.index(name)}"
                )
                return False
            return True
        else:
            _log.warning(
                f"Subdevice {subdevice_idx} does not exist. It cannot be named {name}"
            )
            return False

    def subdevice_name_to_idx(self, name: Union[str, int]) -> int:
        """
        Transform the name of the subdevice into its index. Returns 0 in case of failure

        :param name: The name of the subdevice, or its index
        :type name: str, int

        :returns: The index of the subdevice
        :rtype: int

        """
        try:
            if isinstance(name, str):
                return self.name_subdevices.index(name)
            else:
                return name  # must be int then, since we use type hints
        except Exception as e:
            _log.error(
                f"Could not find name {name} in {self.name_subdevices}. Exception error : {e}"
            )
            return 0

    def update_device(self, device):
        """
        Here we update the current device with the one we got from  discovery. It returns
        the device to be used. Could be an updated self, or any other device.

        For instance, this could be overloaded to keep trace of the targeted device IP address.

        :param device: The new device generated through discover (or by other mean)
        :type device: AltoDevice

        :returns: The device to use from now on
        :rtype: AltoDevice

        """
        return self  # By default use yourself

    def update_info(self, key, value):
        """
        Info are information about the device, e.g. IP address, F/W version, ...

        """
        self.info[key] = value

    @property
    def schema_supported(self):
        """
        Returns the schemas supported by this device

        """
        return [x for x in self.current_state[0].keys()]

    def online_status(self, value: bool) -> None:
        """
        This implement the online_status schema that must be implemented by all agents.

        """
        print("in online_status")
        if self.is_online == value:
            return

        self.is_online = value
        topic = self.controller.topic + "online_status/" + self.controller.agent_name
        topic += "/" + self.device_id
        self.controller.publish(topic, {"online": value}, "event")


class AltoSwitchDevice(AltoDevice):
    """
    This device is a simple switch with an On and an Off state.

    It sets up the default 'state' to None.

    When subclassed, the inheriting classs must implement 2 methods:

            turn_on: Tunr the actual relay onn
            turn_off: Turn the actual relay off

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        for idx in range(self.number_subdevices):
            self.current_state[idx]["switch"] = {"state": None}

    def turn_on(self, subdev):
        """
        Method that MUST be overloaded to turn on the actual switch

        """
        raise AltoNotImpl("Switch device turn_on method must be implemented")

    def turn_off(self, subdev):
        """
        Method that MUST be overloaded to turn off the actual switch

        """
        raise AltoNotImpl("Switch device turn_off method must be implemented")

    def update_switch_state(self, subdevice: Union[int, str], state: str) -> None:
        """
        Method to be invoked whenever a switch state information is received.
        This method will check if a change is detected and will broadcast the
        'relay' event if needed.

        :param subdevice: The name or index of the subdevice
        :type subevice: int or string
        :param state: The state, "on" or "off"
        :type state: str

        """
        subdevice_idx = self.subdevice_name_to_idx(subdevice)
        # _log.debug(f"\n\nSwitch current state {self.current_state[subdevice_idx]}")
        if self.current_state[subdevice_idx]["switch"]["state"] != state:
            _log.debug(
                f"Switch from {self.current_state[subdevice_idx]['switch']['state']} to {state}"
            )
            self.current_state[subdevice_idx]["switch"]["state"] = state
            self.event_switch_state_change(subdevice_idx)
            # _log.debug(f"Switch after state {self.current_state[subdevice_idx]}\n\n")

    def event_switch_state_change(self, subdevice_idx: int) -> None:
        """
        Method used to signal on the Volttron bus that a relay state change has
        been detected. In most cases, this should nopt be called directly, :func: update_switch_state
        should be used.

        """
        self.controller.emit_event_relay(
            self, subdevice_idx, self.current_state[subdevice_idx]["switch"]["state"]
        )


class AltoDimmerDevice(AltoSwitchDevice):
    """
    This device is a dimmer switch with an On and an Off state and control brightness.

    It sets up the default 'state' to None.

    When subclassed, the inheriting classs must implement 3 methods:

            turn_on: Turn the actual relay on
            turn_off: Turn the actual relay off
            set_bright_value: Control the actual switch brightness 

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        for idx in range(self.number_subdevices):
            self.current_state[idx]["switch"] = {
                "state": None,
                "bright_value": None
            }

    def turn_on(self, subdev):
        """
        Method that MUST be overloaded to turn on the actual switch

        """
        raise AltoNotImpl("Switch device turn_on method must be implemented")

    def turn_off(self, subdev):
        """
        Method that MUST be overloaded to turn off the actual switch

        """
        raise AltoNotImpl("Switch device turn_off method must be implemented")
    
    def set_bright_value(self, subdev):
        """
        Method that MUST be overloaded to control brightness on the actual switch

        """
        raise AltoNotImpl("Switch device set_bright_value method must be implemented")

    def update_switch_state(self, subdevice: Union[int, str], state: str) -> None:
        """
        Method to be invoked whenever a switch state information is received.
        This method will check if a change is detected and will broadcast the
        'relay' event if needed.

        :param subdevice: The name or index of the subdevice
        :type subevice: int or string
        :param state: The state, "on" or "off"
        :type state: str

        """
        subdevice_idx = self.subdevice_name_to_idx(subdevice)
        # _log.debug(f"\n\nSwitch current state {self.current_state[subdevice_idx]}")
        if self.current_state[subdevice_idx]["switch"]["state"] != state:
            _log.debug(
                f"Switch from {self.current_state[subdevice_idx]['switch']['state']} to {state}"
            )
            self.current_state[subdevice_idx]["switch"]["state"] = state
            self.event_switch_state_change(subdevice_idx)
            # _log.debug(f"Switch after state {self.current_state[subdevice_idx]}\n\n")

    def event_switch_state_change(self, subdevice_idx: int) -> None:
        """
        Method used to signal on the Volttron bus that a relay state change has
        been detected. In most cases, this should nopt be called directly, :func: update_switch_state
        should be used.

        """
        self.controller.emit_event_relay(
            self, subdevice_idx, self.current_state[subdevice_idx]["switch"]["state"]
        )
    
    def update_bright_value(self, subdevice: Union[int, str], value: int) -> None:
        """
        Method to be invoked whenever a switch bright value information is received.
        This method will check if a change is detected and will broadcast the
        'relay' event if needed.

        :param subdevice: The name or index of the subdevice
        :type subevice: int or string
        :param value: The value range 0 - 255
        :type state: int

        """
        subdevice_idx = self.subdevice_name_to_idx(subdevice)
        # _log.debug(f"\n\nSwitch current state {self.current_state[subdevice_idx]}")
        if self.current_state[subdevice_idx]["switch"]["bright_value"] != value:
            _log.debug(
                f"Switch from {self.current_state[subdevice_idx]['switch']['bright_value']} to {value}"
            )
            self.current_state[subdevice_idx]["switch"]["bright_value"] = value
            self.event_bright_value_change(subdevice_idx)
            # _log.debug(f"Switch after state {self.current_state[subdevice_idx]}\n\n")

    def event_bright_value_change(self, subdevice_idx: int) -> None:
        """
        Method used to signal on the Volttron bus that a relay state change has
        been detected. In most cases, this should nopt be called directly, :func: update_switch_state
        should be used.

        """
        self.controller.emit_event_bright_value(
            self, subdevice_idx, self.current_state[subdevice_idx]["switch"]["bright_value"]
        )


class AltoCurtainDevice(AltoDevice):
    """
    This device is a simple curtain with an Open and an Close state.

    It sets up the default 'state' to None.

    When subclassed, the inheriting classs must implement 2 methods:

            open_curtain: Open the actual curtain
            close_curtain: Close the actual curtain

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        self._is_state_updated = {}
        for idx in range(self.number_subdevices):
            self.current_state[idx]["curtain"] = {
                "control_state": None
                }
            self._is_state_updated[idx] = False

    def open_curtain(self, subdev):
        """
        Method that MUST be overrided to turn on the actual curtain

        """
        raise AltoNotImpl("Curtain device open_curtain method must be implemented")

    def close_curtain(self, subdev):
        """
        Method that MUST be overrided to turn off the actual curtain

        """
        raise AltoNotImpl("Curtain device close_curtain method must be implemented")
    
    def stop_curtain(self, subdev):
        """
        Method that could be overrided to turn off the actual curtain (Optional)

        """
        pass

    def set_percent_position(self, subdev, position):
        """
        Method that could be overrided to turn off the actual curtain (Optional)

        """
        pass

    def _update_generic(self, subdevice_idx: int, prop: str, value: Any) -> bool:
        """
        Update the current value of prop if needed. Return True if actually updated and can be notified,
        False otherwise. This modifies the current_state[0]["hvac"] attribute
        The value is not checked against allowed values.
        """

        if self.current_state[subdevice_idx]["curtain"][prop] != value:
            self.current_state[subdevice_idx]["curtain"][prop] = value
            self._is_state_updated[subdevice_idx] = True

    def update_control_state(self, subdevice_idx, value):
        """ 
        Doc here 
        """
        return self._update_generic(subdevice_idx, "control_state", value)
        
    def status_data(self, subdevice_idx):
        data = {}
        for k, v in self.current_state[subdevice_idx]["curtain"].items():
            data[k] = v
        return data
    
    @property
    def is_state_updated(self):
        return self._is_state_updated


class AltoSensorDevice(AltoDevice):
    """
    This is the abstract class describing sensors. It is not meant to be subclassed directly
    unless you want to implement a new type of sensor device.

    Inheriting classes must define self.datapoint_supported, the list of data point name
    supported by the sensor device

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        self.data_map = {}
        self.datapoint_supported = {}
        for idx in range(self.number_subdevices):
            self.current_state[idx]["sensor"] = {}

    @property
    def sensor_type_supported(self) -> List[str]:
        """
        Which sensor types are supported: Environment, Electrical, Device,...
        """
        return [x for x in self.datapoint_supported.keys()]

    def initialise_data(self, sensor_type: str, datapoints: List[str]) -> None:
        """
        Set the initial data for all subdevice to None for all datapoint set in datapoints

        :param sensor_type: One of "environment","electric","device",
        :type sensor_type: str
        :param datapoints: the list of datapoint name supported by the device
        :type datapoints: list

        :returns: None
        :rtype: None

        """
        for idx in range(self.number_subdevices):
            if sensor_type in self.current_state[idx]["sensor"]:
                thissd = self.current_state[idx]["sensor"][sensor_type]
                for attr in set(self.datapoint_supported[sensor_type]).intersection(
                    set(datapoints)
                ):
                    thissd[attr] = None
                if "timestamp" not in thissd:
                    thissd["timestamp"] = None
            else:
                _log.error(f"This device does not support {sensor_type} sensors.")
        _log.debug(f"Devices initialised as {self.current_state[0]}.")

    def event_sensor_sample(
        self, subdevice_idx: int, sensor_type: str, datapoint: str
    ) -> None:
        """
        This is that method that sends the sensor data in a 'sample' event. By default, it simply
        sends the current value of the datapoints.

        :param subdevice_idx: The subdevice to target. Can bae 'all' for all subdevices.
        :type subdevice_idx: int.string
        :param sensor_type: What type of data to send. Can be 'all'.
        :type sensor_type: string
        :param datapoint: the datapoint to send. Can be 'all'
        :type datapoint: str

        """
        _log.debug(
            f"Running sensor sample for {self.device_id} on {subdevice_idx}, {sensor_type} and {datapoint}"
        )

        if subdevice_idx == "all":
            subdevice_idx = [x for x in range(0, self.number_subdevices)]
        else:
            if subdevice_idx >= self.number_subdevices:
                return
            subdevice_idx = [subdevice_idx]
        if sensor_type == "all":
            sensor_type = None
        if datapoint == "all":
            datapoint = None
        for sdev in subdevice_idx:
            if sensor_type:
                etype = [sensor_type]
            else:
                etype = [x for x in self.current_state[sdev]["sensor"].keys()]

            for st in etype:
                if datapoint:
                    dp = {}
                    if datapoint in self.current_state[sdev]["sensor"][st]:
                        dp[datapoint] = self.current_state[sdev]["sensor"][st][
                            datapoint
                        ]
                        dp["timestamp"] = self.current_state[sdev]["sensor"][st][
                            "timestamp"
                        ]
                else:
                    dp = {
                        x: y for x, y in self.current_state[sdev]["sensor"][st].items()
                    }
                if dp:
                    dp["type"] = st
                    self.controller.emit_event_sample(self, sdev, dp)

    def set_sensor_data(
        self,
        data: Mapping[str, Any],
        subdevice: Union[str, int] = 0,
        sensor_type: Optional[str] = None,
    ) -> List[str]:
        """
        Set the value for the data according to the data_map. It is the responsability of the application to
        disambiguate. For instance, "temperature" can be associated with "environment" or "device", in some case
        it could be that the same value is used for both (if both types are supported by the device).

        The attribute "data_map" must be set by the application. It is a dictionary, the key is the name of the
        data point as known to the sensor. The value is the matching name in the sensor's data

        If a transformation is needed, the device must have method with a name following the pattern

             to_<sensor type>_<data point>

        with <data point> the name of the data point in the sensor's namespace. This method shall transform the data
        to meet the required units/format. If it returns None, the data point shall not be set.

        The returned list indicates which datapoint in the application namespace have been used. They are used
        if and only if the value of the datapoint has changed.

        :param data: the data to be set in raw form
        :type data: dict
        :param subdevice: The subdevice name or index or "all", defaults to 0
        :type subdevice: str, int
        :param sensor_type: The type of sensor to set data for. If the type is not supported
                            by the device, it is simply ignored
        :type sensor_type: str

        :returns: The list of data points used (application's name). A data point used multiple times will
                  appear multiple times in the list
        :rtype: list

        """
        # _log.debug(f"set_sensor_data {data} {subdevice} {sensor_type}")
        used_data = []
        mytmstmp = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
        if subdevice == "all":
            lo_subdevices = [x for x in range(self.number_subdevices)]
        else:
            lo_subdevices = [self.subdevice_name_to_idx(subdevice)]
        if sensor_type is None:
            lo_sensor_type = [x for x in self.sensor_type_supported]
        elif sensor_type not in self.sensor_type_supported:
            _log.warning(f"Sensor type {sensor_type} not supported here.")
            return []  # What's that
        else:
            lo_sensor_type = [sensor_type]
        for subdevice_idx in lo_subdevices:
            for this_type in lo_sensor_type:
                was_updated = False
                current_type_val = self.current_state[subdevice_idx]["sensor"][
                    this_type
                ]
                tstmp_handled = False
                for datapoint in self.datapoint_supported[this_type] + ["timestamp"]:
                    # _log.debug(f"Handling data for {datapoint}")
                    if datapoint in self.data_map:
                        app_dname = self.data_map[datapoint]

                        if app_dname in data:
                            # _log.debug(f"Mapping {app_dname}  -->  {datapoint}")
                            if datapoint == "timestamp":
                                tstmp_handled = True
                            f = getattr(
                                self, "to_" + this_type + "_" + datapoint, lambda x: x
                            )  # idempotent if not defined
                            try:
                                nval = f(data[app_dname])
                            except Exception as e:
                                _log.error(
                                    f"Value for {app_dname} cannot be computed by \"{'to_' + this_type + '_' + datapoint} \"from value \"{data[app_dname]}\""
                                )
                                nval = data[app_dname]
                            if nval is not None:
                                if current_type_val[datapoint] != nval:
                                    # _log.debug(
                                    # f"{datapoint} was {current_type_val[datapoint]} now {nval}"
                                    # )
                                    current_type_val[datapoint] = nval
                                    if datapoint != "timestamp":
                                        used_data.append(app_dname)
                                        was_updated = True

                # _log.debug(f"set_sensor_data {was_updated} {self.controller.auto_send}")
                if was_updated and self.controller.auto_send:
                    if not tstmp_handled:
                        current_type_val["timestamp"] = mytmstmp
                    mydata = current_type_val.copy()
                    mydata["type"] = this_type
                    self.controller.emit_event_sample(self, subdevice_idx, mydata)

        return used_data

    def get_data(self):
        """
        Get the data for the device and send the info. By default it will simply publish the current
        values of the various sensors types.

        """
        self.event_sensor_sample("all", "all", "all")


class AltoEnvironSensor(AltoSensorDevice):
    """
    This is one of the various sensor's type. This one for environmental data.

    This is one of the class to be sub-classed by application devices. It defines the supported datapoints in
    datapoint_supported, the inheriting class will have to map, in data_map, it's own values to those in datapoint_supported.

            * temperature: in °C
            * temperature_sub: baby it's cold outside. Freezing, cold, comfortable,warm, hot, too hot
            * humidity: in percent
            * noise: in dB
            * noise_sub: quite, normal or load
            * luminosity: in lux
            * luminosity_sub: dark, dim, normal or bright
            * pressure: in mBar
            * acceleration: in mili g
            * acceleration_sub: still, moving, vibrating, shock
            * air_quality: in ppm
            * air_quality_sub: bad, normal, good
            * co2 : in ppm
            * co: in ppm

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        self.datapoint_supported["environment"] = [
            "temperature",
            "temperature_sub",
            "humidity",
            "noise",
            "noise_sub",
            "luminosity",
            "luminosity_sub",
            "pressure",
            "acceleration",
            "acceleration_sub",
            "air_quality",
            "air_quality_sub",
            "co2 ",
            "co",
            "movement",
        ]

        for idx in range(self.number_subdevices):
            self.current_state[idx]["sensor"]["environment"] = {}


class AltoDeviceSensor(AltoSensorDevice):
    """
    This is one of the various sensor's type. This one for device data.

    This is one of the class to be sub-classed by application devices. It defines the supported datapoints in
    datapoint_supported, the inheriting class will have to map, in data_map, it's own values to those in datapoint_supported.

        * temperature: device tempreature
        * overload: device is being overloaded
        * underload: more load please
        * vibrating: ddddevvicce is shhhhakking
        * error_condition: call the doctor.

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        self.datapoint_supported["device"] = [
            "temperature",
            "overload",
            "underload",
            "vibrating",
            "error_condition",
        ]

        for idx in range(self.number_subdevices):
            self.current_state[idx]["sensor"]["device"] = {}


class AltoElectricSensor(AltoSensorDevice):
    """
    This is one of the various sensor's type. This one for electrical data.

    This is one of the class to be sub-classed by application devices. It defines the supported datapoints in
    datapoint_supported, the inheriting class will have to map, in data_map, it's own values to those in datapoint_supported.


            * type:  ac/dc... Hell's bells
            * voltage: in volts
            * current:  in Ampers
            * frequency:  in hz
            * power: in kW
            * energy: in kWh
            * power_reactive: kvar
            * power_apparent: kVA
            * energy_to_grid: kWh
            * energy_reactive: ,kvarh
            * energy_reactive_to_grid: kvarh
        ]
    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        self.datapoint_supported["electric"] = [
            "type",
            "voltage",
            "current",
            "frequency",
            "power",
            "energy",
            "power_reactive",
            "power_apparent",
            "energy_to_grid",
            "energy_reactive",
            "energy_reactive_to_grid",
        ]

        for idx in range(self.number_subdevices):
            self.current_state[idx]["sensor"]["electric"] = {}


class AltoRemoteCDevice(AltoDevice):
    """
    This is the base class for remote control devices. Both for IR and RF.

    Subclasses must define 3 methods:

            command_send_code: This command takes either a raw code (if is_raw == True) to be sent as-is
                               byy the device, or a list of on/off duration pairs to be ttransformed and sent
                               by the device.

            command_learn_code_ir: Learning a n IR code via the device. Can be used with the raw mode

            command_learn_code_rf: Learning a n RF code via the device. Can be used with the raw mode

    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        for idx in range(self.number_subdevices):
            self.current_state[idx] = {"remotec": {}}

    def command_send_code(self, code: List[int], is_raw: bool = False) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_learn_code_ir(self, message: Mapping[str, Any]) -> None:
        """
        Can be overloaded by the application class, if the device can learn.

        """
        raise AltoNotImpl

    def command_learn_code_rf(self, message: Mapping[str, Any]) -> None:
        """
        Can be overloaded by the application class, if the device can learn.

        """
        raise AltoNotImpl

    def _command_send_code(self, message: Mapping[str, Any]) -> None:
        """
        Here we process the command and generate the required list of
        timing. The list is not signed and requires a even number of elements. The
        even numbered elements are positive (LED on) and the odd numbered ones are negatiive.

        """
        try:

            if message["type"].lower() == "rf":
                if message["format"] != "raw":
                    _log.error(
                        f"Sending Radio Frequency requires the raw mode, not {message['format']}"
                    )
                    return
                self.command_send_code(message, is_raw=True)
            elif message["type"].lower() == "ir":  # Infrared it is
                if message["format"] == "cdsf":
                    message["code"] = [
                        abs(x)
                        for x in irgen.gen_paired_from_raw(
                            irgen.gen_simplified_from_raw(
                                irgen.gen_raw_general(*message["code"])
                            )
                        )
                    ]
                    self.command_send_code(message, is_raw=False)
                elif message["format"] == "raw":
                    self.command_send_code(message, is_raw=True)
                elif message["format"] == "hex":
                    if "timing" in message:
                        message["code"] = self._to_timing(
                            message["code"], message["timing"]
                        )
                        return self.command_send_code(message, is_raw=False)
                    else:
                        _log.error("Timing must be provided for 'hex' format.")
                else:
                    _log.error(
                        f"Unsupported format {message['format']} for Infrared code."
                    )
            else:
                _log.error(f"Code type {message['type']} cannot be handled")
                return

        except Exception as e:
            _log.debug(f"Problem when  decoding send command {message}. Error was {e}")
            _log.exception(e)

    def _command_learn_code(self, message: Mapping[str, Any]) -> None:
        """
        Called by the agent when a learn command is received

        """
        if message["type"].lower() == "rf":
            self.command_learn_code_rf(message)
        elif message["type"].lower() == "ir":
            self.command_learn_code_ir(message)
        else:
            _log.error(f"Cannot learn code of type {message['type']}.")

    def _to_timing(self, code, timing):
        """
        Transform a list of frames into a LIRC compatible list of pulse timing pairs

        """
        timinglist = [timing["start frame"]]
        for x in [int(code[i : i + 2], 16) for i in range(0, len(code), 2)]:
            idx = 0x80
            while idx:
                timinglist.append(timing["mark"])
                if x & idx:
                    timinglist.append(timing["space 1"])
                else:
                    timinglist.append(timing["space 0"])
                idx >>= 1
        if "drop bits" in timing:
            timinglist = timinglist[
                : -2 * timing["drop bits"]
            ]  # Each bit is a pulse and a space
        timinglist += timing["end frame"]
        return timinglist


class AltoLocationDevice(AltoDevice):
    """
    This is the base class for locations

    It is not really usefull, but is needed.

    """

    def __init__(self, controller: Agent, devid: str) -> AltoDevice:
        super().__init__(controller, devid, 1)
        for idx in range(self.number_subdevices):
            self.current_state[idx] = {"location": {}}

        self.occupation = 0

    def add_occupant(self, nb: int = 1) -> None:
        """
        Add a number of occupants to the location device.

        """
        self.occupation += nb

    def del_occupant(self, nb: int = 1) -> None:
        """
        Remove a number of occupants from the location device.

        """
        self.occupation -= nb
        if self.occupation < 0:
            _log.warning("Some people came through the window.")
            self.occupation = 0


class AltoLoggerDevice(AltoDevice):
    """
    This is the base class for datalogger

    It is not really usefull, but is needed.

    """

    def __init__(
        self, controller: Agent, devid: str, logtype: Optional[list] = None
    ) -> AltoDevice:
        super().__init__(controller, devid, 1)
        #: What data to log, a list of sensor types. If None means log everything
        self.datatype = logtype
        self.current_state[0]["datalogger"] = {}

    def log_data(self, data: dict) -> None:
        """
        Must be implemented by the actual AltoLoggerDevice

        """
        raise AltoNotImpl

    def _do_log_data(self, data: dict) -> None:
        """
        Used by the Agent.  Check if the data type is supported, before logging

        """
        try:
            if self.datatype is None or data["type"] in self.datatype:
                # loc = data["location"]
                return self.log_data(data)
            return False
        except:
            return False

    def flush_data(self):
        """
        This is called every TIMERESOLUTION secs by the agent.

        If log_data only store data, flush_data can be used to write to the database.

        Does nothing by default. Has to be overloaded if needs be.
        """
        return


class AltoHVACDevice(AltoDevice):
    """
    This is the base class for hvac devices. Here there is only 1 sunbdevice.

    The capabilities attribute defines what is possible for that device.
        mode is "off", "auto", "cool", "fan", "dry", "heat"
        temperature is a 3-uple
            Minimum temperature (°C)
            Maximum temperature
            Increments 0.5 °C by default
        fan is "off", "auto", "highest", "high", "median", "low", "lowest"
        flow is off, auto, swing, 0, 15, 30, 45, 60, 75, 90. 0 is horizontal
        horizontal_flow is off, auto, swing, far_left, left, centre, right, far_right
            As seen from the point of vue of an observatore looking straight at the device.
        purifier is on, off
        economy is on, off
        lock is True
        read_lock is True
        alarm is the list of possible alarm targets

    Subclassing agents must set the capabilities attribute. Only supported properties/keys
    shall be present.

    subclassing agents must set the current_state[0]["hvac"]. The attribute current_state represent the true state of the device.
    The property current_hvac_state is the schema compliant device state. It is generate by getting the property current_state_xxx
    for every property available. By default this simply mirrors the current_state[0]["hvac"]. By overloading current_state_xxx
    one can perform more complex processing.

    Note that, by default, current_hvac_state cannot be set.

    For most properties, the default value should be a scalar.

    For lock it is a dictionary:
        key is the locked property
        value is the list of allowed values, an empty list means no change possible
              For temperature, it is a min max 2-uple

    For readlock it is a list of locked properties

    For alarm it is a dictionary:
        key is the target (must be specified in  self.capabilities["alarm"]
        the value is a dictionary with at least 2 keys
            level: the alarm level
            msg: an indication of what the alarm is.

    The attribute update_on_set can be set to True to indicate that the current value
    shall be updated when set.

    If update_on_set is False, the subclassing object must take care of updateing the current value.
    and notifying the bus using the controller method emit_event_state


    """

    def __init__(
        self, controller: Agent, devid: str, logtype: Optional[list] = None
    ) -> AltoDevice:
        self.update_on_set = False
        super().__init__(controller, devid, 1)
        #: By defaul we expect all possible value
        self.capabilities = {
            "mode": ["off", "auto", "cool", "fan", "dry", "heat"],
            "set_temperature": [16.0, 31.0, 0.5],  # Min, Max, Increment
            "room_temperature": [10.0, 45.0, 1.0],
            "fan": ["off", "auto", "highest", "high", "median", "low", "lowest"],
            "flow": ["off", "auto", "swing", "0", "15", "30", "45", "60", "75", "90"],
            "horizontal_flow": [
                "off",
                "auto",
                "swing",
                "far_left",
                "left",
                "centre",
                "right",
                "far_right",
            ],
            "purifier": ["off", "on"],
            "economy": ["off", "on"],  # can be an int
            "lock": True,
            "read_lock": True,
            "alarm": ["filter"],
        }
        self.current_state[0]["hvac"] = {
            "mode": "off",
            "set_temperature": 25.0,
            "room_temperature": 25.0,
            "fan": "off",
            "flow": "off",
            "horizontal_flow": "off",
            "purifier": "off",
            "economy": "off",
            "lock": {},
            "read_lock": [],
            "alarm": {},
        }

    @property
    def current_hvac_state(self):
        # _log.debug(f"hvac_state for {self.capabilities}")
        val = {}
        for k in self.capabilities:
            val[k] = getattr(self, "current_state_" + k)
        return val

    @property
    def current_state_mode(self):
        return self.current_state[0]["hvac"]["mode"]

    @property
    def current_state_set_temperature(self):
        return self.current_state[0]["hvac"]["set_temperature"]

    @property
    def current_state_room_temperature(self):
        return self.current_state[0]["hvac"]["room_temperature"]

    @property
    def current_state_fan(self):
        return self.current_state[0]["hvac"]["fan"]

    @property
    def current_state_flow(self):
        return self.current_state[0]["hvac"]["flow"]

    @property
    def current_state_horizontal_flow(self):
        return self.current_state[0]["hvac"]["horizontal_flow"]

    @property
    def current_state_purifier(self):
        return self.current_state[0]["hvac"]["purifier"]

    @property
    def current_state_economy(self):
        return self.current_state[0]["hvac"]["economy"]

    @property
    def current_state_lock(self):
        return self.current_state[0]["hvac"]["lock"]

    @property
    def current_state_read_lock(self):
        return self.current_state[0]["hvac"]["read_lock"]

    @property
    def current_state_alarm(self):
        return self.current_state[0]["hvac"]["alarm"]

    @property
    def current_state_source(self):
        return self.current_state[0]["hvac"]["source"]

    def command_set_mode(self, mode: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_set_temperature(self, temp: Union[int, float]) -> None:
        """
        Must be overloaded by the application class
        
        """
        raise AltoNotImpl
    
    def command_set_temperature(self, temp: Union[int, float]) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_fan(self, value: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_louver(self, mode: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_filter(self, mode: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_flow(self, value: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_horizontal_flow(self, value: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_purifier(self, value: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_economy(self, value: str) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_lock(self, value: dict) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_read_lock(self, value: list) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def command_set_alarm(self, value: dict) -> None:
        """
        Must be overloaded by the application class

        """
        raise AltoNotImpl

    def _command_set_generic(self, prop: str, value: Any) -> None:
        """
        Set the devcice property. Make sure it is valid and is not locked.

        Return a boolean to indicate if the value was updated or not

        """
        if prop not in self.capabilities:
            _log.error(f"{prop} is not supported.")
            return

        if value not in self.capabilities[prop]:
            _log.error(
                f"Mode {value} is not supported, must be one of {self.capabilities['fan']}"
            )
            return

        if (
            "lock" in self.capabilities
            and prop in self.current_hvac_state["lock"]
            and value not in self.current_hvac_state["lock"][prop]
        ):
            _log.warning(f"{prop} is locked and cannot be set to {value}")
            return

        try:
            getattr(self, "command_set_" + prop)(value)
        except Exception as e:
            _log.error(f"Could not set {prop}")
            _log.exception(e)

    def _command_set_free_generic(self, prop: str, value: Any) -> None:
        """
        Set the property. Make sure it is valid and is not locked. Here we deal with free form values,
        so we do not check that the value is in a list.

        """
        if prop not in self.capabilities:
            _log.error(f"{prop} is not supported.")
            return

        if (
            "lock" in self.capabilities
            and prop in self.current_hvac_state["lock"]
            and value not in self.current_hvac_state["lock"][prop]
        ):
            _log.warning(f"{prop} is locked and cannot be set to {value}")
            return

        try:
            getattr(self, "command_set_" + prop)(value)
        except Exception as e:
            _log.error(f"Could not set {prop}")
            _log.exception(e)

    def _command_set_mode(self, mode: str) -> None:
        """
        Set the mode. Make sure it is valid and is not locked.

        """
        self._command_set_generic("mode", mode)

    def _command_set_temperature(self, temp: Union[int, float]) -> None:
        """
        Set the temperature. Make sure it is valid and is not locked.

        We are not using _command_set_generic because the testes are differents

        """
        if "temperature" not in self.capabilities:
            _log.error("Mode is not supported.")

        if (
            temp < self.capabilities["temperature"][0]
            or temp > self.capabilities["temperature"][1]
        ):
            _log.error(
                f"Temperature {temp} is out of range. Must be between {self.capabilities['temperature'][0]} and {self.capabilities['temperature'][1]}."
            )

        if (
            "lock" in self.capabilities
            and "temperature" in self.current_hvac_state["lock"]
        ):
            if (
                temp < self.current_hvac_state["lock"]["temperature"][0]
                and temp > self.current_hvac_state["lock"]["temperature"][1]
            ):
                _log.warning(f"Temperature is locked and cannot be set to {temp}")

        # TODO Check the steps

        try:
            self.command_set_temperature(temp)
        except Exception as e:
            _log.error("Could not set temperature")
            _log.exception(e)
    
    def _command_set_set_temperature(self, temp: Union[int, float]) -> None:
        """
        Set the temperature. Make sure it is valid and is not locked.

        We are not using _command_set_generic because the testes are differents

        """
        if "temperature" not in self.capabilities:
            _log.error("Mode is not supported.")

        if (
            temp < self.capabilities["set_temperature"][0]
            or temp > self.capabilities["set_temperature"][1]
        ):
            _log.error(
                f"Temperature {temp} is out of range. Must be between {self.capabilities['set_temperature'][0]} and {self.capabilities['set_temperature'][1]}."
            )

        if (
            "lock" in self.capabilities
            and "set_temperature" in self.current_hvac_state["lock"]
        ):
            if (
                temp < self.current_hvac_state["lock"]["set_temperature"][0]
                and temp > self.current_hvac_state["lock"]["set_temperature"][1]
            ):
                _log.warning(f"Temperature is locked and cannot be set to {temp}")

        # TODO Check the steps

        try:
            self.command_set_set_temperature(temp)
        except Exception as e:
            _log.error("Could not set temperature")
            _log.exception(e)

    def _command_set_fan(self, value: str) -> None:
        """
        Set the fan. Make sure it is valid and is not locked.

        """

        self._command_set_generic("fan", value)

    def _command_set_louver(self, value: str) -> None:
        """
        Set the louver. Make sure it is valid and is not locked.

        """

        self._command_set_generic("louver", value)

    def _command_set_filter(self, value: str) -> None:
        """
        Set the filter. Make sure it is valid and is not locked.

        """

        self._command_set_generic("filter", value)

    def _command_set_flow(self, value: str) -> None:
        """
        Set the flow. Make sure it is valid and is not locked.

        """

        self._command_set_generic("flow", value)

    def _command_set_horizontal_flow(self, value: str) -> None:
        """
        Set the horizontal_flow. Make sure it is valid and is not locked.

        """

        self._command_set_generic("horizontal_flow", value)

    def _command_set_purifier(self, value: str) -> None:
        """
        Set the purifier. Make sure it is valid and is not locked.

        """

        self._command_set_generic("purifier", value)

    def _command_set_economy(self, value: Union[str, int]) -> None:
        """
        Set the economy. Make sure it is valid and is not locked.

        """

        self._command_set_generic("economy", value)

    def _command_set_lock(self, value: dict) -> None:
        """
        Set what can be modified. Essentially, the value is a dictionary where the key is the
        name of property, and the value is a list (or range for temperature) of acceptable values.
        An empty list means that it cannot be changed. For temperature, min and max s nust be equal

        """
        self._command_set_free_generic("lock", value)

    def _command_set_read_lock(self, value: list) -> None:
        """
        Set the list of properties for which the value shall not be reported.

        """
        self._command_set_free_generic("read_lock", value)

    def _command_set_alarm(self, value: dict) -> None:
        """
        The value is application dependent.

        """
        self._command_set_free_generic("alarm", value)

    def _command_set_source(self, value: dict) -> None:
        """
        The value is application dependent.

        """
        self._command_set_free_generic("source", value)

    def to_schema(self, prop: str, value: Any) -> Union[str, int, float]:
        """
        Translate values from the device into  schema defiend values

        By default, idempotent
        """
        return value

    def _update_generic(self, prop: str, dvalue: Any) -> bool:
        """
        Update the current value of prop if needed. Return True if actually updated and can be notified,
        False otherwise. This modifies the current_state[0]["hvac"] attribute

        The value is not checked against allowed values.
        """
        value = self.to_schema(prop, dvalue)
        if self.current_state[0]["hvac"][prop] != value:
            self.current_state[0]["hvac"][prop] = value
            if prop not in self.current_hvac_state["read_lock"]:
                return True
        return False

    def update_mode(self, mode: str) -> bool:
        """
        Update the current value of mode
        """
        return self._update_generic("mode", mode)

    def update_fan(self, value: str) -> bool:
        """
        Update the current value of fan
        """
        return self._update_generic("fan", value)

    def update_flow(self, value: str) -> bool:
        """
        Update the current value of flow
        """
        return self._update_generic("flow", value)

    def update_horizontal_flow(self, value: str) -> bool:
        """
        Update the current value of horizontal flow
        """
        return self._update_generic("horizontal_flow", value)

    def update_purifier(self, value: str) -> bool:
        """
        Update the current value of purifier
        """
        return self._update_generic("horizontal_flow", value)

    def update_room_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of temperature
        """
        return self._update_generic("room_temperature", value)

    def update_set_temperature(self, value: Union[int, float]) -> bool:
        """
        Update the current value of set temperature
        """
        return self._update_generic("set_temperature", value)

    def update_lock(self, value: dict) -> bool:
        """
        Update the current value of lock
        """
        return self._update_generic("lock", value)

    def update_read_lock(self, value: list) -> bool:
        """
        Update the current value of read_lock
        """
        return self._update_generic("read_lock", value)

    def update_alarm(self, value: dict) -> bool:
        """
        Update the current value of alarm
        """
        return self._update_generic("alarm", value)

    def status_data(self):
        data = {}
        for k, v in self.current_hvac_state.items():
            if k not in self.current_state[0]["hvac"]["read_lock"]:
                data[k] = v
        return data

    def command_was_sent(self):
        """
        In some cases on would want to specify when so send
        a state event
        """
        pass


class AltoBattery(AltoDevice):
    """
    This is the base class for batteries. Subdevice represent cells

    Subclasses must define 2 methods:

            _command_load:  This command indicated the battery is loaded

            _command_eject: The battery is ejected


    """

    def __init__(self, controller: Agent, devid: str, nbsubdev: int = 1) -> AltoDevice:
        super().__init__(controller, devid, nbsubdev)
        self.name_subdevices = [f"cell_{i}" for i in range(0, nbsubdev)]

    def _command_eject(selfself, message):
        raise AltoNotImpl

    def _command_load(selfself, message):
        raise AltoNotImpl


class AltoAgent(Agent):
    """
    Create an abstract agent. This is not meant to be subclassed directly.

    Configuration:
        * topic: a string that prefix the schema defined topic.
        * heartbeat_rate: How often to send the heartbeat. Check TIMERESOLUTION for resolution
        * agent_name: Name to use for the agent in the schema.

    :param topic: String to be prepended to the topic used
    :type topic: str
    :param kwargs: named arguments
    :type kwargs: dict

    :returns: AltoAgent
    :rtype: AltoAgent

    """

    def __init__(self, topic: str = "", **kwargs: int) -> Agent:
        _log.debug(f"Creating AltoAgent for topic {topic} with {kwargs}")
        pskiplist = [
            "identity",
            "address",
            "agent_uuid",
            "volttron_home",
            "version",
            "message_bus",
        ]
        super().__init__(**{k: v for k, v in kwargs.items() if k in pskiplist})
        # pskiplist.remove("identity")
        self.topic = topic
        self.schemas = set(["config"])
        self.device_list = {}
        self.heartbeat_rate = 90
        self.log_commands = False
        self._heartbeat_cd = 0
        self.heartbeat_status = "CONFIGURING"
        self._loattr = set(
            ["topic", "heartbeat_rate", "agent_name", "log_commands"]
        )  # This will keep the list of attributes in the config
        self._attrtypes = {"topic": str}  # Attributes types, if needed
        for k, v in kwargs.items():
            if k not in pskiplist:
                setattr(self, k, v)
                self._loattr.add(k)
        self.is_bridge = False
        if self.agent_name == "":
            self.agent_name = self.core.identity
        # A way to add thing to the configuration process
        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.current_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(
            self.configure, actions=["NEW", "UPDATE"], pattern="config"
        )

    def set_attr_types(self, **kwargs: int) -> None:
        """
        Set the class of the various configuration parametres. This can be used
        to verify that parametres have the correct type wwhen configuring. Parametres
        that do not match their type are ignored.

        Parametres for which no type is defined are accepted as-is.

        :param topic: String to be prepended to the topic used
        :type topic: str
        :param kwargs: named arguments
        :type kwargs: dict

        :returns: AltoAgent
        :rtype: AltoAgent

        """
        for k, v in kwargs.items():
            if isinstance(v, type):
                self._attrtypes[k] = v
            else:
                _log.debug(f"Problem, {v} is not a type.")
            if k not in self._loattr:
                # If we set a type, surely we want this config
                self._loattr.add(k)

    def set_heartbeat_status(self, msg: str) -> None:
        """
        Set the message to be sent during heartbeat. CONFIGURING, GOOD or FAREWELL

        :param msg: Message to send
        :type msg: str

        :returns: None
        :rtype: None

        """
        self.heartbeat_status = msg

    def register_new_device(self, dev: AltoDevice):
        """
        The new device is fully configured, we expect the new device to have
        at least the following attribures
               device_id: A unique id
               number_subdevices: int ... This is last_idx +1

        This method must be called by the actual agent.

        Event if the agent only control 1 device, this should be called to associate the device
        with the agent

        """
        if dev.device_id in self.device_list:
            # We know this device. No need to announce it
            self.device_list[dev.device_id] = self.device_list[
                dev.device_id
            ].update_device(dev)
        else:
            self.device_list[dev.device_id] = dev
            self.set_heartbeat_status("GOOD")
            self.announce_new_device(dev)

    def unregister_device(self, devid):
        """
        Unregister a known device

        """
        if devid in self.device_list:
            # We know this device. No need to announce it
            self.device_list[devid].online_status(False)
            del self.device_list[devid]

    @property
    def current_config(self) -> Mapping[str, Any]:
        """
        Returns the current configuration.

        """
        r = {}
        for x in self._loattr:
            try:
                r[x] = getattr(self, x)
            except Exception as e:
                _log.debug(f"This should not happen. No attribute for {x}")
        return r

    def save_config(self, name: str = "config") -> None:
        """
        Save the current configuration

        """

        _log.debug("fNew config updated with {self.current_config}")
        try:
            self.vip.config.set("config", self.current_config)
        except Exception as e:
            _log.debug(
                "Error: Something went wrong with setting config store Error was: {}".format(
                    e
                )
            )

    def configure(
        self, config_name: str, action: str, contents: Mapping[str, Any]
    ) -> None:
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.

        Here we handle only the configuration named "config". Others are handled to "configure_<config_name>"
        It is the responsability of the inheriting class to provide that method with 2 parametres: action and contents.


        :param config_name: name of the configuration
        :type config_name: str
        :param action: name of the  action: NEW, UPDATE
        :type action: str
        :param contents: The actual configuration
        :type kwargs: dict

        :returns: None
        :rtype: None

        """

        _log.debug(f"Configuring Agent ({action}) {config_name} {contents}")
        if config_name == "config":
            for k, v in contents.items():
                try:
                    if k in self._attrtypes:
                        assert isinstance(v, self._attrtypes[k])
                    self._loattr.add(k)
                    setattr(self, k, v)
                except:
                    _log.error(
                        f"Config error. Parametre {k} must be of type {self._attrtypes[k]}. Value {v} is of type {v.__class__}"
                    )
        else:
            f = getattr(self, "configure_" + config_name, None)
            if f:
                f(action, contents)
            else:
                _log.error(f"Do not know how to handle config {config_name}")

        if not self.is_bridge:
            if not self.device_list:
                self.register_self()
        else:
            self.build_devices()
        self._create_subscriptions()

    def register_self(self):
        """
        Needs to be defined for non-bridge agents

        """
        raise AltoNotImpl

    def build_devices(self):
        """
        Can be overloaded to create statically defined devices on a brodge
        """
        pass

    def _create_subscriptions(self) -> None:
        """
        Because of the regular pattern, we can asubscribe using the schema supported.
        We subsacribe to all the schema we need to subscribe to

        """
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for schema in self.schemas:
            topic = self.topic + schema + "/" + self.agent_name
            if not self.is_bridge:
                if not self.device_list:
                    return
                topic += (
                    "/" + [x for x in self.device_list.keys()][0]
                )  # There should be only one
            _log.debug(f"Subscribing to {topic}")
            self.vip.pubsub.subscribe(
                peer="pubsub", prefix=topic, callback=self._handle_message
            )

    def _handle_message(self, peer, sender, bus, topic, headers, message):
        """
        Here we handle as much as the message as we can. For any agent, the subclass can define a method
        following the format

                handle_<type>_<schema>

        For instance, 'handle_event_sensor', handle_response_switch',

        Those method require 2 parametres (3 for responses):
               The end of topic, that is the topic minus prefix, schema and agent.
               The payload from the message
               The headers, for responses only.

        """
        if sender != self.core.identity:  # Let's not bother with our own messages
            try:
                split_topic = topic.replace(self.topic, "").split("/")
                _log.debug(f"Split topic is {split_topic}")
                schema = split_topic[0]
                name = split_topic[1]
                assert name == self.agent_name
                mtype = headers["message_type"].lower().strip()
                _log.debug(f"Executing handle_{mtype}_{schema} ")
                if mtype == "response":
                    getattr(self, "handle_" + mtype + "_" + schema)(
                        split_topic[2:], message, headers
                    )
                else:
                    getattr(self, "handle_" + mtype + "_" + schema)(
                        split_topic[2:], message
                    )
                    if (
                        mtype == "command"
                        and self.log_commands
                        and len(split_topic) >= 4
                    ):
                        msgtopic = f"datalogger/{name}/{split_topic[3]}/command"
                        msgpayload = {
                            "sender": sender,
                            "command": split_topic[-1],
                            "type": "command",
                            "location": "",
                        }
                        msgpayload["timestamp"] = (
                            dt.datetime.utcnow()
                            .replace(tzinfo=dt.timezone.utc)
                            .isoformat(),
                        )
                        for k, v in message.items():
                            msgpayload[k] = v
                        self.publish(msgtopic, msgpayload, "event")
            except Exception as e:
                _log.debug(
                    f"Problem handling message from {sender}. \n\tHeader: {headers}, \n\ttopic: {topic}, \n\tmessage: {message},\n\terror: {e}"
                )
                _log.exception((e))

    def handle_request_config(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
        This implements the config schema that must be supported by all agents
        Check if it is a save or a show and act accordingly

        :param topic: The last 1 ot 2 bits in the topic
        :type topic: list
        :param message" The message payload
        :type message: dict

        :returns: None
        :rtype: None

        """
        if len(topic) > 2:
            raise Exception("Config request handler cannot parse topic")

        if len(topic) == 2:
            devid, func = topic
            assert devid in self.device_list
        else:
            func = topic[0]
            devid = None

        if func == "save":
            if "name" in message:
                cname = message["name"]
            else:
                cname = "config"
            notset = []
            for k, v in message["config"].items():
                if k in self._attrtypes:
                    if isinstance(v, self._attrtypes[k]):
                        self._loattr.add(k)
                        setattr(self, k, v)
                    else:
                        notset.append(k)
                else:
                    self._loattr.add(k)
                    setattr(self, k, v)

            if self.save_config(cname):
                errmsg = ""
                if notset:
                    errmsg = "Could not set " + ",".join(notset)
                    if len(message["config"]) == len(notset):
                        res = False
                    else:
                        res = "partial"
                else:
                    res = True

            else:
                errmsg = "Configuration could not be saved"
                res = False

            msg = {
                "rid": message["rid"],
                "save": res,
                "error": notset,
                "error_message": errmsg,
            }
            if "reply_to" in message and message["reply_to"]:
                self.publish(message["reply_to"], msg, "response")
            else:
                etopic = self.topic + "config/" + self.agent_name
                if self.devid:
                    etopic += "/" + self.devid
                etopic += "/" + func
                self.publish(etopic, msg, "event")
        elif func == "show":
            showcfg = {}
            for k, v in self.current_config.items():
                if "passwd" not in k and "password" not in k:
                    showcfg[k] = v

            msg = {"rid": message["rid"], "config": showcfg}
            self.publish(message["reply_to"], msg, "response")

    @Core.schedule(periodic(TIMERESOLUTION))
    def _heartbeat(self) -> None:
        """
        This implements the heartbeat schema that must be supported by all agents

        The message ccan be customised using set_heartbeat_status.

        Frequency is set via haertbeat_rate

        """
        self._heartbeat_cd -= TIMERESOLUTION
        if self._heartbeat_cd <= 0:
            self._heartbeat_cd = self.heartbeat_rate
            self.send_heartbeat()

    def send_heartbeat(self) -> None:
        """
        This actually send the heartbeat

        The message ccan be customised using set_heartbeat_status

        """
        try:
            topic = self.topic + "heartbeat/" + self.agent_name
            if not self.is_bridge:
                topic += "/" + [x for x in self.device_list.keys()][0]
            self.publish(topic, self.heartbeat_status, "event")
        except:
            pass

    def publish(self, topic: str, value: Any, mtype: str) -> None:
        """
        Publish to the Volttron bus

        :param topic: The topic to publish to.
        :type topic: string
        :param value: The message payload
        :type value: as needed
        :param mtype: The type to set in the header, command, evemt, request or response.

        :returns: None
        :rtype: None

        """

        value["unix_timestamp"] = time.time()

        self.vip.pubsub.publish(
            peer="pubsub",
            topic=topic,
            message=value,
            headers={
                "requesterID": self.core.identity,
                "message_type": mtype,
                "TimeStamp": dt.datetime.utcnow()
                .replace(tzinfo=dt.timezone.utc)
                .isoformat(),
            },
        )

    def send_response_devinfo(self, devid: str, message: List[Any]) -> None:
        """
        This send the response to the devinfo request that must be supported by most agents

        """
        # _log.debug(f"Checking {devid} in {self.device_list}")
        assert devid in self.device_list
        if "device_id" in message:
            devid = message["device_id"]

        msg = {"rid": message["rid"], "device_id": devid}
        msg["subdevice_last_idx"] = self.device_list[devid].number_subdevices - 1
        msg["schema"] = self.device_list[devid].schema_supported
        msg["agent"] = self.agent_name
        self.publish(message["reply_to"], msg, "response")

    def announce_new_device(self, dev: AltoDevice):
        """
        This implements the newdevice schema that must be supported by all schema

        """
        topic = self.topic + "newdevice/" + self.agent_name + "/" + dev.device_id
        payload = {
            "device_id": dev.device_id,
            "subdevice_last_idx": dev.number_subdevices - 1,
        }
        payload["schemas"] = dev.schema_supported
        self.publish(topic, payload, "event")
        dev.online_status(True)

    def last_rites(self):
        """
        Something to do upon imminent death

        Should be overloaded by agents needing it.
        """
        pass

    @Core.receiver("onstop")
    def rip(self, sender, **kwargs):
        # Time to die
        self.last_rites()
        self.heartbeat_status = "FAREWELL"
        self.send_heartbeat()


class AltoBridgeAgent(AltoAgent):
    """
    This class provide base support for bridge agents. These are agents
    that control multiple devices of the same type

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.is_bridge = True


class AltoDiscoverableAgent(AltoBridgeAgent):
    """
    This is the abstract implementation of the discovery scheme

    Here the actual agent MUST implement the start_discovery method

    Configuration
        discovery_rate  how often, in minutes, to run discovery
                        0 means do not run discovery autonatically
                        after initial run.

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoBridgeAgent:
        super().__init__(topic, **kwargs)
        self._loattr.add("discovery_rate")
        self._attrtypes["discovery_rate"] = int
        self.schemas.add("discovery")
        if getattr(self, "discovery_rate", None) is None:
            self.discovery_rate = 0  # Whe zero do not automatically run discovery
        self._discovery_rate_cd = self.discovery_rate

    def configure(
        self, config_name: str, action: str, contents: Mapping[str, Any]
    ) -> None:

        super().configure(config_name, action, contents)

        if not self.device_list:
            self.start_discovery()

    def handle_request_discovery(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        self.start_discovery()
        self.send_response_discovery(message)

    def start_discovery(self) -> None:
        """
        This must be implemented by the actual agent

        """
        raise AltoNotImpl("start_discovery must be implementd")

    def send_response_discovery(self, message: List[Any]) -> None:
        # _log.debug(f"Checking {devid} in {self.device_list}")

        msg = {"rid": message["rid"]}
        if "reply_to" in message:
            topic = message["reply_to"]
            rtype = "response"
        else:
            topic = "discovery/" + self.agent_name
            rtype = "event"
        self.publish(topic, msg, rtype)

    @Core.schedule(periodic(60))
    def _do_discovery(self) -> None:
        if self.discovery_rate:
            self._discovery_rate_cd -= 1
            if self._discovery_rate_cd <= 0:
                self._discovery_rate_cd = self.discovery_rate
                self.start_discovery()


class AltoMQTTAgent(AltoBridgeAgent):
    """ Define an Agent that uses MQTT to communicate with the devices

    Here the actual agent MUST implement the process_mqtt_message method

    Configuration

        * mqtt_topics:  MQTT topics to subscribe to
        * mqtt_server: Where is ourt MQTT server
        * mqtt_port:  What port
        * mqtt_user: If needed user t login as
        * mqtt_password: If needed, password for login
        * mqtt_prefix: If needed, topic prefix to use when sending MQTT messages

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.mqtt_client = None
        for attr, attr_type in zip(
            [
                "mqtt_topics",
                "mqtt_server",
                "mqtt_port",
                "mqtt_user",
                "mqtt_password",
                "mqtt_prefix",
            ],
            [list, str, int, str, str, str],
        ):
            self._loattr.add(attr)
            self._attrtypes[attr] = attr_type
            if getattr(self, attr, None) is None:
                if attr == "mqtt_server":
                    setattr(self, attr, "localhost")
                elif attr == "mqtt_port":
                    setattr(self, attr, 1883)
                else:
                    setattr(self, attr, "")

            setattr(self, attr, attr_type())
        # Make sure mqtt_prefix ends with a '/'
        if self.mqtt_prefix:
            if self.mqtt_prefix[-1] != "/":
                self.mqtt_prefix += "/"

    def on_mqtt_connect(self, client, myself, flags, rc):
        _log.debug(f"Connected with result code {rc}")

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        # _log.debug(f"Connected to MQTT, subscribing to {self.mqtt_topics}")
        self.set_heartbeat_status("READY")
        for topic in self.mqtt_topics:
            client.subscribe(topic)
            _log.debug("MQTT: Subscribe to '{}'".format(topic))

    def process_mqtt_message(self, client, msg):
        _log.debug(f"Processing message {msg}")
        # raise AltoNotImpl("process_mqtt_message must be implemented")

    def send_mqtt_message(self, topic, payload):
        """
        Simply pass on to the MQTT bus

        """
        if self.mqtt_client:
            self.mqtt_client.publish(self.mqtt_prefix + topic, payload=payload)
        else:
            _log.warning(
                f"MQTT connection not available. Cannot send to MQTT topic {topic}"
            )

    @Core.receiver("onstart")
    def mqttstart(self, sender: str, **kwargs: int) -> None:
        """
        Here we start the mqtt client only if we actually have data to do something

        """
        _log.debug("Connecting to MQTT ")
        if self.mqtt_topics and self.mqtt_server:
            # Only if woth it
            self.mqtt_client = mqtt.Client(userdata=self)
            if self.mqtt_user:
                self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_message = self.process_mqtt_message
            self.mqtt_client.connect_async(
                self.mqtt_server, port=self.mqtt_port
            )  # Should we bind?
            self.mqtt_client.loop_start()
            _log.debug("\t\t... Connected")
        else:
            _log.debug("\t\t... NOT")

    @Core.receiver("onstop")
    def mqttstop(self, sender: str, **kwargs: int) -> None:
        """
        Here we stop the mqtt client.

        """
        _log.debug("Disconnecting from MQTT ")
        if self.mqtt_client:
            self.mqtt_client.disconnect()
            self.mqtt_client.loop_stop()
            self.mqtt_client = None

    def configure(
        self, config_name: str, action: str, contents: Mapping[str, Any]
    ) -> None:
        """
        We need to overload it in the MQTT bridge, because we need to (re)start the
        MQTT client when someparametres change

        :param config_name: name of the configuration
        :type config_name: str
        :param action: name of the  action: NEW, UPDATE
        :type action: str
        :param contents: The actual configuration
        :type kwargs: dict

        :returns: None
        :rtype: None

        """

        _log.debug(f"Configuring Agent ({action}) {config_name} {contents}")
        hardreset = False
        for attr in [
            "mqtt_server",
            "mqtt_port",
            "mqtt_topics",
            "mqtt_user",
            "mqtt_password",
        ]:
            if attr in contents and contents[attr] != getattr(self, attr):
                hardreset = True
                break

        super().configure(config_name, action, contents)

        if hardreset:
            self.mqttstop("self")

        if self.mqtt_client is None:
            self.mqttstart("self")


class AltoSwitch(AltoAgent):
    """
    This implement the switch schema. The registered device(s) must have methods:

        turn_on
        turn_off

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("switch")

    def handle_command_switch(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle the commands meant for the switch schema. Essentially the 'relay' command.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Switch command handler cannot parse topic")

        devid, func = topic
        if func == "command":
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev == "all":
                losubdev = range(0, self.device_list[devid].number_subdevices)
            else:
                losubdev = [self.device_list[devid].subdevice_name_to_idx(subdev)]
                # _log.debug(f"Switch {losubdev}")
            if message["state"].lower() == "on":
                for subdev in losubdev:
                    # _log.debug(f"Switch on {subdev}")
                    self.device_list[devid].turn_on(subdev)
            elif message["state"].lower() == "off":
                for subdev in losubdev:
                    self.device_list[devid].turn_off(subdev)
            else:
                raise AltoSchemaError(
                    f"Error: {message['state']} is not a valid value for a switch state"
                )
        else:
            _log.warning(f"Command {func} is not know to the switch schema")

    def handle_request_switch(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle devinfo schema

        """
        if len(topic) != 2:
            raise AltoSchemaError("Switch command handler cannot parse topic")
        _log.debug(f"Switch Request with {message}")
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the switch schema")
        except Exception as e:
            _log.debug("\n\nOpps in switch request: {}".format(e))
            _log.exception(e)

    def emit_event_relay(
        self, dev: AltoSwitchDevice, subdevice_idx: int, state: str
    ) -> None:

        topic = (
            self.topic + "switch/" + self.agent_name + "/" + dev.device_id + "/event"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "state": state,
            "type" : "relay"
        }
        self.publish(topic, payload, "event")


class AltoDimmer(AltoSwitch):
    """
    This implement the dimmer switch schema. The registered device(s) must have methods:

        turn_on
        turn_off
        bright_value

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("switch")

    def handle_command_switch(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle the commands meant for the switch schema. Essentially the 'relay' command.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Switch command handler cannot parse topic")

        devid, func = topic
        if func == "command":
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev == "all":
                losubdev = range(0, self.device_list[devid].number_subdevices)
            else:
                losubdev = [self.device_list[devid].subdevice_name_to_idx(subdev)]
                # _log.debug(f"Switch {losubdev}")
            if 'state' in message:
                if message["state"].lower() == "on":
                    for subdev in losubdev:
                        # _log.debug(f"Switch on {subdev}")
                        self.device_list[devid].turn_on(subdev)
                elif message["state"].lower() == "off":
                    for subdev in losubdev:
                        self.device_list[devid].turn_off(subdev)
                else:
                    raise AltoSchemaError(
                        f"Error: {message['state']} is not a valid value for a switch state"
                    )
            elif 'bright_value' in message:
                for subdev in losubdev:
                    self.device_list[devid].set_bright_value(subdev, message['bright_value'])
        else:
            _log.warning(f"Command {func} is not know to the switch schema")

    def handle_request_switch(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle devinfo schema

        """
        if len(topic) != 2:
            raise AltoSchemaError("Switch command handler cannot parse topic")
        _log.debug(f"Switch Request with {message}")
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the switch schema")
        except Exception as e:
            _log.debug("\n\nOpps in switch request: {}".format(e))
            _log.exception(e)

    def emit_event_relay(
        self, dev: AltoDimmerDevice, subdevice_idx: int, state: str
    ) -> None:

        topic = (
            self.topic + "switch/" + self.agent_name + "/" + dev.device_id + "/event"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "state": state,
            "type" : "relay"
        }
        self.publish(topic, payload, "event")
    
    def emit_event_bright_value(
        self, dev: AltoDimmerDevice, subdevice_idx: int, value: int
    ) -> None:

        topic = (
            self.topic + "switch/" + self.agent_name + "/" + dev.device_id + "/event"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "bright_value": value,
            "type": "dimmer"
        }
        self.publish(topic, payload, "event")


class AltoCurtain(AltoAgent):
    """
    This implement the curtain schema. The registered device(s) must have methods:

        open_curtain
        close_curtain

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("curtain")

    def handle_command_curtain(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle the commands meant for the curtain schema. Essentially the 'motor' command.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Curtain command handler cannot parse topic")

        devid, func = topic
        if func == "command": # should be motor
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev == "all":
                losubdev = range(0, self.device_list[devid].number_subdevices)
            else:
                losubdev = [self.device_list[devid].subdevice_name_to_idx(subdev)]
            control_state = message.get("control_state", None)
            if control_state is not None:
                if control_state.lower() == "open":
                    for subdev in losubdev:
                        self.device_list[devid].open_curtain(subdev)
                elif control_state.lower() == "close":
                    for subdev in losubdev:
                        self.device_list[devid].close_curtain(subdev)
                elif control_state.lower() == "stop":
                    for subdev in losubdev:
                        self.device_list[devid].stop_curtain(subdev)
                else:
                    raise AltoSchemaError(
                        f"Error: {message['state']} is not a valid value for a curtain state"
                    )
            percent_position = message.get("percent_position", None)
            if percent_position is not None:
                for subdev in losubdev:
                    self.device_list[devid].set_percent_position(subdev, percent_position)
        else:
            _log.warning(f"Command {func} is not know to the curtain schema")

    def handle_request_curtain(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle devinfo schema

        """
        if len(topic) != 2:
            raise AltoSchemaError("Curtain command handler cannot parse topic")
        _log.debug(f"Curtain Request with {message}")
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the curtain schema")
        except Exception as e:
            _log.debug("\n\nOpps in curtain request: {}".format(e))
            _log.exception(e)

    def emit_event_motor(self, dev: AltoCurtainDevice) -> None:
        for idx in range(dev.number_subdevices):
            if dev.is_state_updated[idx]:
                sdata = dev.status_data(idx)
                topic = self.topic + "curtain/" + self.agent_name + "/" + dev.device_id + "/event"
                payload = {
                    "device_id": dev.device_id,
                    "subdevice_idx": idx,
                    "subdevice_name": dev.name_subdevices[idx],
                    "type" : "motor"
                }
                payload.update(sdata)
                self.publish(topic, payload, "event")
                dev.is_state_updated[idx] = False
                

class AltoCharger(AltoAgent):
    """
    This implement the charger schema. The registered device(s) will mostly be battery devices:or
    some form of proxy. The devices associated are exoected to have the attributes
             battery_id
             online_status
        and methods
            _command_online
            _command_load
            _command_eject

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("charger")

    def handle_command_charger(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Let charge batteries

        """
        if len(topic) != 2:
            raise AltoSchemaError("Sensor command handler cannot parse topic")

        # devid, func = topic
        devid = topic[0]
        func = message["command"]
        _log.debug(f"handle_command_charger {devid} {func}")
        if devid in self.device_list:
            try:
                if func == "load":
                    payload = self.device_list[devid]._command_load(message)
                    self.emit_event_load(devid, payload)
                elif func == "eject":
                    extras_msg = {
                        "message": message.copy()
                    }
                    self.device_list[devid].eject(message["subdevice_idx"], **extras_msg)
                    payload = self.device_list[devid]._command_eject(message["subdevice_idx"])
                    self.emit_event_eject(devid, payload)
                elif func == "online":
                    payload = self.device_list[devid]._online_status(message)
                    self.emit_event_online(devid, payload)
                elif func == "charging":
                    payload = self.device_list[devid]._charging_status(message)
                    self.emit_event_charging(devid, payload)
            except:
                pass
        else:
            _log.warning(f"Charger unknown slot {devid}")

    def handle_request_charger(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handles devinfo request for the schema.

        """
        _log.debug(f"lCharger Request for {topic} with {message}")
        if len(topic) != 2:
            raise AltoSchemaError(
                f"Remote Control command handler cannot parse topic {topic}"
            )
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the remotec schema")
        except Exception as e:
            _log.debug("\n\nOpps in remote control request: {}".format(e))
            _log.exception(e)

    def emit_event_online(self, devid: str, payload: Any) -> None:
        """
        Send the 'online' event.

        """
        if payload:
            topic = self.topic + "charger/" + self.agent_name + "/" + devid + "/online"
            self.publish(topic, payload, "event")

    def emit_event_load(self, devid: str, payload: Any) -> None:
        """
        Emit the event through the controller
        """
        if payload:
            topic = self.topic + "charger/" + self.agent_name + "/" + devid + "/load"
            self.publish(topic, payload, "event")

    def emit_event_eject(self, devid: str, payload: Any):
        """
        Emit the event through the controller
        """
        if payload:
            topic = self.topic + "charger/" + self.agent_name + "/" + devid + "/eject"
            self.publish(topic, payload, "event")


    def emit_event_charging(self, devid: str, payload: Any):
        """
        Emit event charging status through controller
        """
        if payload:
            topic = self.topic + "charger/" + self.agent_name + "/" + devid + "/charging"
            self.publish(topic, payload, "event")

class AltoButton(AltoAgent):
    """
    To be implemented. The button schema.

    """

    pass


class AltoRemoteC(AltoAgent):
    """
    Implements the remotec schema.

    Handles most things for the remotec schema. The devices in device_list are expected
    to subclass AltoRemoteCDevice.

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("remotec")

    def handle_command_remotec(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Proxy commands send, learn to the devices.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Sensor command handler cannot parse topic")

        devid, func = topic
        if devid in self.device_list:
            if func == "learn":
                self.device_list[devid]._command_learn_code(message)
            elif func == "command":
                self.device_list[devid]._command_send_code(message)
        else:
            _log.warning(f"Sampling unknown sensor {devid}")

    def handle_request_remotec(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handles devinfo request for the schema.

        """
        _log.debug(f"Remote Control Request for {topic} with {message}")
        if len(topic) != 2:
            raise AltoSchemaError(
                f"Remote Control command handler cannot parse topic {topic}"
            )
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the remotec schema")
        except Exception as e:
            _log.debug("\n\nOpps in remote control request: {}".format(e))
            _log.exception(e)

    def emit_event_sent(
        self, dev: AltoRemoteCDevice, subdevice_idx: int, cid: str, result: bool
    ) -> None:
        """
        Send the 'sent' event.

        """

        topic = (
            self.topic + "remotec/" + self.agent_name + "/" + dev.device_id + "/event"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "cid": cid,
            "sent": result,
        }
        self.publish(topic, payload, "event")

    def emit_event_next(
        self, dev: AltoRemoteCDevice, subdevice_idx: int, cid: str
    ) -> None:
        """
        Send the 'next' event for cases where learning is a 2 steps process.

        """

        topic = (
            self.topic + "remotec/" + self.agent_name + "/" + dev.device_id + "/next"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "cid": cid,
        }
        self.publish(topic, payload, "event")

    def emit_event_learnt(
        self, dev: AltoRemoteCDevice, subdevice_idx: int, cid: str, code: bytearray
    ) -> None:
        """
        Send the 'learnt' event with the code learnt..

        """

        topic = (
            self.topic + "remotec/" + self.agent_name + "/" + dev.device_id + "/learnt"
        )
        payload = {
            "device_id": dev.device_id,
            "subdevice_idx": subdevice_idx,
            "subdevice_name": dev.name_subdevices[subdevice_idx],
            "cid": cid,
            "code": code,
        }
        self.publish(topic, payload, "event")


class AltoSensor(AltoAgent):
    """
    This is the base class  for all sensor agents. It is not expected to be sub-classed directly
    by real agent.

    Here we add an auto_send attribute. The auto_send attribute is used as follow:

         if True, this means that 'sample' events are emited each time the device updates its data
         if False, this means that the agent will send the current data at sampling_rate intervals

         Use case.

             If you have a sensor updating  values at high frequency, you can process
             and update the data wwith the sensors set_sensor_data method  and have this agent
             send event at sampling sampling_rate intervals
                  set auto_sent -> False

            You poll your device for data and sends event as soon as received
                  set auto_sent -> True
                  overload send_samples, so that it get calls at sampling_rate
                                         and poll you devices

            It is HIGhLY recommended that your devices use set_sensor_data for updating the values

    Configuration

        sampling_rate   How often, in seconds to sample data. Actual time is a multiple of TIMERESOLUTION

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:

        self.sampling_rate = 120  # How often should we sample and send data
        # If the sensor broadcast data, how oftten to send the event
        self._sampling_rate_cd = 120
        super().__init__(topic, **kwargs)
        self.schemas.add("sensor")
        """
        Here, sensor_support
        """
        self.auto_send = True

    @Core.schedule(periodic(TIMERESOLUTION))
    def _do_send_samples(self) -> None:
        self._sampling_rate_cd -= TIMERESOLUTION
        if self._sampling_rate_cd <= 0:
            self._sampling_rate_cd = self.sampling_rate
            self.send_samples()

    def send_samples(self) -> None:
        if not self.auto_send:
            for dev in self.device_list.values():
                dev.event_sensor_sample("all", "all", "all")

    def handle_command_sensor(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handles the 'sample' command.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Sensor command handler cannot parse topic")

        devid, func = topic
        if devid in self.device_list:
            if func == "event":
                if message["subdevice_idx"] == "all":
                    sdev = "all"
                else:
                    sdev = self.device_list[devid].subdevice_name_to_idx(
                        message["subdevice_idx"]
                    )
                etype, dimension = message["data"].split(":")

                self.device_list[devid].event_sensor_sample(sdev, etype, dimension)
        else:
            _log.warning(f"Sampling unknown sensor {devid}")

    def emit_event_sample(
        self, dev: AltoSensorDevice, subdev: int, data: Mapping[str, Any]
    ) -> None:
        """
        Only send if we have something to send.

        """
        # _log.debug(f"emit_event_sample {dev} {subdev} {data}")
        if {x: y for x, y in data.items() if y != None if x != "type"}:
            topic = (
                self.topic
                + "sensor/"
                + self.agent_name
                + "/"
                + dev.device_id
                + "/event"
            )
            payload = {
                "device_id": dev.device_id,
                "subdevice_idx": subdev,
                "subdevice_name": dev.name_subdevices[subdev],

            }
            payload.update({x: y for x, y in data.items() if y != None})

            self.publish(topic, payload, "event")

    def handle_request_sensor(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handles devinfo.

        """
        if len(topic) != 2:
            raise AltoSchemaError("Sensor request handler cannot parse topic")
        _log.debug(f"Switch Request with {message}")
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the sensor schema")
        except Exception as e:
            _log.debug("\n\nOpps in switch request: {}".format(e))
            _log.exception(e)


class AltoHVAC(AltoAgent):
    """
    Agent class for the HVAC schema


    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("hvac")

    def handle_command_hvac(self, topic: List[str], message: Mapping[str, Any]) -> None:
        """
             Handle the commands meant for the switch schema. Essentially the 'relay' command.

        """
        if len(topic) != 2:
            raise AltoSchemaError("HVAC command handler cannot parse topic")

        devid, func = topic
        # if func == "set":
        if func == "command":
            assert devid in self.device_list
            if "device_id" in message:
                devid = message["device_id"]
            subdev = message["subdevice_idx"]
            if subdev == "all":
                losubdev = range(0, self.device_list[devid].number_subdevices)
            else:
                losubdev = [self.device_list[devid].subdevice_name_to_idx(subdev)]
            targetdev = self.device_list[devid]
            donotify = False
            # _log.debug(f'''hvac message["mode"] {message["mode"]}''')
            for subdev in losubdev:
                for prop in targetdev.capabilities.keys():
                    if prop in message:
                        # _log.debug(f'''hvac _command_set_{prop}''')
                        getattr(targetdev, "_command_set_" + prop)(message[prop])
                        if targetdev.update_on_set:
                            donotify = donotify or getattr(targetdev, "update_" + prop)(
                                message[prop]
                            )
                targetdev.command_was_sent()
            if donotify:
                _log.debug("before emit event state")
                self.emit_event_state(devid)
        else:
            _log.warning(f"HVAC cannot handle command {func}")

    def handle_request_hvac(self, topic: List[str], message: Mapping[str, Any]) -> None:
        """
             Handle the requests meant for the hvac schema. Essentially the 'status' request.

        """
        if len(topic) != 2:
            raise AltoSchemaError("HVAC request handler cannot parse topic")

        devid, req = topic
        if req == "event":
            if devid in self.device_list:
                msg = {"rid": message["rid"], "device_id": devid}
                msg.update(self.device_list[devid].current_hvac_state)
                self.publish(message["reply_to"], msg, "response")
        elif req == "devinfo":
            self.send_response_devinfo(devid, message)

    def emit_event_state(self, devid):
        payload = {"device_id": devid, "subdevice_idx": 0, "type": "ac"}
        sdata = self.device_list[devid].status_data()
        if sdata:
            payload.update(sdata)
            topic = self.topic + "hvac/" + self.agent_name + "/" + devid + "/event"
            self.publish(topic, payload, "event")

    def send_response_devinfo(self, devid: str, message: List[Any]) -> None:
        """
        This send the response to the devinfo request that must be supported by most agents

        """
        # _log.debug(f"Checking {devid} in {self.device_list}")
        assert devid in self.device_list
        if "device_id" in message:
            devid = message["device_id"]

        msg = {"rid": message["rid"], "device_id": devid}
        msg["subdevice_last_idx"] = self.device_list[devid].number_subdevices - 1
        msg["schema"] = self.device_list[devid].schema_supported
        msg["agent"] = self.agent_name
        msg["capabilities"] = self.device_list[devid].capabilities
        self.publish(message["reply_to"], msg, "response")


class AltoLight(AltoAgent):
    """
    To be implemented. The light schema.

    """

    pass


class AltoLocation(AltoAgent):
    """
    This schema is for location. Location can be organized in a tree-like structure.

    configuration:

        * location_name:  The name of the location
        * parent_location: If needed, the list of all ancestors' name
        * children_locations: If needed, the list of children locations' name
        * commands: List of application defines commands via the 'map' request.
        * associated_devices: devices associated wqith this location.
        * named_devices: a dictionary of 4uple, key is name, 4uple schema, agent, device_id, subdevice_idx
        * track_events: a dictionary of list of 2-uple. The key is the name of the event. The 2uple i
                        'name' of the data dictionary to load with '::' separting keys.
                        list of data to log, if empty means all

                        To access nested values, use '::' to separete keys. For instance 'data::ac' would
                        access payload['data']['ac']. Note that this MUST be a dictionary

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("location")

        for attr, attr_type in zip(
            [
                "location_name",
                "parent_location",
                "children_locations",
                "commands",
                "associated_devices",
                "named_devices",
                "device_prefix",
            ],
            [str, list, list, dict, dict, dict, str],
        ):
            self._loattr.add(attr)
            self._attrtypes[attr] = attr_type
            if getattr(self, attr, None) is None:
                setattr(self, attr, attr_type())

        for attr, attr_type, dfl_val in zip(
            ["track_events"], [dict], [{"event": ["data", []]}]
        ):
            self._loattr.add(attr)
            self._attrtypes[attr] = attr_type
            if getattr(self, attr, None) is None:
                setattr(self, attr, dfl_val)

        self.to_be_added = {}
        self._resubscribe = False
        self._pending_reponses = {}

    def _create_subscriptions(self) -> None:
        """
        Subscribe to all the schema supported by the location, but also by its associated devices.

        """
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for schema in self.schemas:
            topic = self.topic + schema + "/" + self.agent_name
            if not self.is_bridge:
                if not self.device_list:
                    return
                topic += (
                    "/" + [x for x in self.device_list.keys()][0]
                )  # There should be only one
            _log.debug(f"Subscribing to {topic}")
            self.vip.pubsub.subscribe(
                peer="pubsub", prefix=topic, callback=self._handle_message
            )
        # Let'sd also subscribe to our devices
        # seendevs = set()
        for schema in self.associated_devices:
            for agent in self.associated_devices[schema]:
                if "#" not in self.associated_devices[schema][agent]:
                    for dev in self.associated_devices[schema][agent]:
                        topic = self.topic + schema + "/" + agent + "/" + dev + "/"
                        _log.debug(f"Subscribing to {topic}")
                        self.vip.pubsub.subscribe(
                            peer="pubsub", prefix=topic, callback=self.handle_device_message
                        )
                else:
                    topic = self.topic + schema + "/" + agent + "/"
                    _log.debug(f"Subscribing to {topic}")
                    self.vip.pubsub.subscribe(
                        peer="pubsub", prefix=topic, callback=self.handle_device_message
                    )

    def name_device(
        self,
        name: str,
        schema: str,
        agent: str,
        device_id: str,
        subdevice_idx: Union[int, str],
    ) -> bool:
        """
        Name a device/subdevice at a location. The name can then be used in commands

        """
        self.named_devices[name] = (schema, agent, device_id, subdevice_idx)
        self.save_config()
        return True

    def add_device(self, schema: str, agent: str, device_id: str) -> bool:
        """
        Add a device to a location

        """

        if schema in self.associated_devices:
            if agent in self.associated_devices[schema]:
                if device_id in self.associated_devices[schema][agent]:
                    return False

        topic = self.topic + schema + "/" + agent + "/" + device_id
        # Let's query this device
        self.publish(
            topic + "/devinfo",
            {
                "reply_to": self.topic
                + "location/"
                + self.agent_name
                + "/"
                + [x for x in self.device_list.values()][0].device_id
                + "/devinfo",
                "rid": [x for x in self.device_list.values()][0].device_id,
            },
            "request",
        )
        return True

    def del_device(self, device_id):
        """
        Remove device from location

        """
        sc = False
        for schema in [x for x in self.associated_devices.keys()]:
            for agent in [x for x in self.associated_devices[schema].keys()]:
                if device_id in self.associated_devices[schema][agent]:
                    # topic = self.topic + schema + "/" + agent + "/" + device_id
                    # self.vip.pubsub.unsubscribe("pubsub", topic, None) #Does not like to be unsubscribed in here
                    self.associated_devices[schema][agent].remove(device_id)
                    sc = True
                if len(self.associated_devices[schema][agent]) == 0:
                    del self.associated_devices[schema][agent]
            if len(self.associated_devices[schema]) == 0:
                del self.associated_devices[schema]
        if sc:
            self._resubscribe = True
            self.save_config()
        return sc

    def handle_response_location(
        self, topic: List[str], message: Mapping[str, Any], headers: Mapping[str, Any]
    ) -> None:
        """
        When a device is added, the location will request a devinfo for the said device.
        Here we handle the information returned.

        """
        if topic[-1] == "devinfo":
            agent = message["agent"]
            device_id = message["device_id"]
            for schema in message["schema"]:
                if schema not in self.associated_devices:
                    self.associated_devices[schema] = {agent: []}

                if agent not in self.associated_devices[schema]:
                    self.associated_devices[schema][agent] = []

                if device_id not in self.associated_devices[schema][agent]:
                    self.associated_devices[schema][agent].append(device_id)
                    topic = self.topic + schema + "/" + agent + "/" + device_id
                    self._resubscribe = True
                    # Apparently it is an error to subscribe when handling a message
                    # self.vip.pubsub.subscribe(
                    # peer="pubsub", prefix=topic, callback=self.handle_device_message
                    # )
            self.save_config()
            if device_id in self.to_be_added:
                rt, rid, tstmp = self.to_be_added[device_id]
                msg = {"rid": rid, "status": "ok"}
                self.publish(rt, msg, "response")
                del self.to_be_added[device_id]

        elif topic[-1] == "set_parent":
            sm = message["rid"].split(RIDSEP)
            rid = RIDSEP.join(sm[:-1])
            child = sm[-1]
            try:
                self._pending_reponses[rid][0].remove(child)
            except:
                _log.debug(
                    f"Tried to remove pending child {child} for {rid} from {self._pending_reponses[rid]}"
                )
            _log.debug(
                f"Got set_parent response for {topic} with {message} and {self._pending_reponses[rid]} remaining"
            )
            if self._pending_reponses[rid][0] == []:
                loc, rto, tstmp, cnt = self._pending_reponses[rid]
                del self._pending_reponses[rid]
                self.publish(
                    rto, {"rid": rid, "set": True}, "response",
                )

    def handle_device_message(self, peer, sender, bus, topic, headers, message):
        """
            The default implementation simply look for sample and  send them as datalogger
            events
        """
        _log.debug(f"Got device message with topic {topic} and message {message}")
        if headers["message_type"].lower().strip() != "event":
            return
        if len(topic.split("/")) != 4:
            return  # Ignore
        _a, _b, devid, func = topic.split("/")
        _log.debug(f"Room logging: {func} vs {self.track_events}")
        if func not in self.track_events:
            _log.debug(f"Ignoring because '{func}' not in {self.track_events}")
            return  # Ignore
        else:
            data, lok = self.track_events[func]
        _log.debug(f"proceeding with {data} and {lok}")
        try:
            flatmsg = {}
            if "timestamp" not in message:  # It should
                flatmsg["timestamp"] = (
                    dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
                )
            else:
                flatmsg["timestamp"] = message["timestamp"]
            if "device_id" not in message:
                flatmsg["device_id"] = devid
            else:
                flatmsg["device_id"] = message["device_id"]
            if "subdevice_idx" not in message:
                flatmsg["subdevice_idx"] = 0
            else:
                flatmsg["subdevice_idx"] = message["subdevice_idx"]
            if "subdevice_name" not in message:
                flatmsg["subdevice_name"] = ""
            else:
                flatmsg["subdevice_name"] = message["subdevice_name"]

            flatmsg["location"] = ""
            # if self.parent_location:
            # flatmsg["location"] += self.parent_location
            flatmsg["location"] += self.location_name
            if self.device_prefix:
                didit = False
                for k in self.associated_devices:
                    for t, val in self.associated_devices[k].items():
                        if "#" not in val:
                            if message["device_id"] in val:
                                if self.device_prefix[0] != "/":
                                    flatmsg["location"] += "/"
                                flatmsg["location"] += self.device_prefix
                                didit = True
                                break
                        else:
                            if self.device_prefix[0] != "/":
                                flatmsg["location"] += "/"
                            flatmsg["location"] += self.device_prefix
                            didit = True
                            break
                    if didit:
                        break
            logdata = message
            for k in [x for x in data.split("::") if x]:
                logdata = logdata[k]

            for k, v in logdata.items():
                if k in ["timestamp", "device_id", "subdevice_idx"]:
                    continue
                if lok == [] or k in lok:
                    flatmsg[k] = v
            if "type" not in flatmsg:
                flatmsg["type"] = func
            _log.debug(f"Publishing {flatmsg}")
            self.publish(
                "datalogger/" + self.location_name + "/" + devid + "/" + func,
                flatmsg,
                "event",
            )
        except Exception as e:
            _log.debug(f"Problem with device event: {e}")

    def handle_command_location(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
        Check if it is realy a command

        Commands supported here are:
            * occupamcy, generating an event with payload True of False
            * any functions defined by a map request.

        """

        _log.debug(f"Location command {topic}")

        if len(topic) != 2:
            raise AltoSchemaError("Location command handler cannot parse topic")

        devid, func = topic
        # First the known commands
        if devid != self.device_list[devid].device_id:
            _log.debug(
                f"That was not meant for me! {devid} instead of {self.device_list[0].device_id}"
            )
            return
        if func == "occupancy":
            payload = {"subdevice_idx": 0, "device_id": devid}
            payload["occupancy"] = self.device_list[devid].occupation > 0
            self.publish(
                self.topic + "location/" + devid + "/occupancy", payload, "event"
            )

        elif func in self.commands:
            _log.debug(f"Executing defined command {func}")
            loc = self.commands[func]
            loc.sort(key=lambda x: x["order"])
            for action in loc:
                for adev in action["device"]:
                    # for dev, subdev in action["device"]:
                    try:
                        if isinstance(adev, str):
                            if adev not in self.named_devices:
                                _log.error(
                                    f"Command {func}, device {adev} is not known."
                                )
                                continue
                            schema, agent, dev, subdev = self.named_devices[adev]
                        else:
                            dev, subdev = adev
                            schema, agent, dev = dev.split("/")
                        payload = {"subdevice_idx": subdev, "device_id": dev}
                        for k, v in message.items():
                            if k == "broadcast":
                                continue
                            if k in action["mapping"]:
                                nk, map = action["mapping"][k]
                                if map is None:
                                    payload[nk] = v
                                else:
                                    for av, sv in map:
                                        if av == v:
                                            payload[nk] = sv
                                            break
                            else:
                                payload[k] = v
                        if "payload" in action:
                            payload.update(action["payload"])
                        self.publish(
                            self.topic
                            + schema
                            + "/"
                            + agent
                            + "/"
                            + dev
                            + "/"
                            + action["command"],
                            payload,
                            "command",
                        )
                    except Exception as e:
                        _log.error(f"Problem with command {func}: {e}")
        if "broadcast" in message and message["broadcast"]:
            for child in self.children_locations:
                self.publish(
                    self.topic
                    + "location/"
                    + self.agent_name
                    + "/"
                    + child
                    + "/"
                    + func,
                    message,
                    "command",
                )

    def handle_request_location(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:

        """
        Handling add_device, del_device, add_children, set_parent and map for the location.

        """

        if len(topic) == 2:
            devid, func = topic
            assert devid in self.device_list
        else:
            func = topic[0]
            devid = None

        if func == "add_device":
            self.to_be_added[message["device_id"]] = (
                message["reply_to"],
                message["rid"],
                dt.datetime.now(),
            )
            if not self.add_device(
                message["schema"], message["agent"], message["device_id"]
            ):
                del self.to_be_added[message["device_id"]]
                self.publish(
                    message["reply_to"],
                    {"rid": message["rid"], "status": "ok"},
                    "response",
                )

        elif func == "del_device":
            if self.del_device(message["device_id"]):
                self.publish(
                    message["reply_to"],
                    {"rid": message["rid"], "status": "ok"},
                    "response",
                )
            else:
                self.publish(
                    message["reply_to"],
                    {"rid": message["rid"], "status": "unknown"},
                    "response",
                )

        elif func == "name_device":
            if self.name_device(
                message["device_name"],
                message["schema"],
                message["agent"],
                message["device_id"],
                message["subdevice_idx"],
            ):

                self.publish(
                    message["reply_to"],
                    {"rid": message["rid"], "status": "ok"},
                    "response",
                )

        elif func == "add_children":
            self._pending_reponses[message["rid"]] = [
                [],
                message["reply_to"],
                dt.datetime.now(),
                0,
            ]
            for child in message["children"]:
                if child not in self.children_locations:
                    self.children_locations.append(child)
                    self.children_locations.sort()
                    self._pending_reponses[message["rid"]][0].append(f"{child}")
                    self._pending_reponses[message["rid"]][-1] += 1
                    self.publish(
                        f"location/{self.agent_name}/{child}/set_parent",
                        {
                            "rid": f"{message['rid']}{RIDSEP}{child}",
                            "reply_to": f"location/{self.agent_name}/{self.location_name}/set_parent",
                            "parent": self.parent_location + [self.location_name],
                        },
                        "request",
                    )

            self.save_config()

        elif func == "del_children":
            self._pending_reponses[message["rid"]] = [
                [],
                message["reply_to"],
                dt.datetime.now(),
                0,
            ]
            for child in message["children"]:
                if child in self.children_locations:
                    self.children_locations.remove(child)
                    self.children_locations.sort()
                    self._pending_reponses[message["rid"]][0].append(f"{child}")
                    self._pending_reponses[message["rid"]][-1] += 1
                    self.publish(
                        f"location/{self.agent_name}/{child}/set_parent",
                        {
                            "rid": f"{message['rid']}{RIDSEP}{child}",
                            "reply_to": f"location/{self.agent_name}/{self.location_name}/set_parent",
                            "parent": [],
                        },
                        "request",
                    )

            self.save_config()

        elif func == "set_parent":
            self.parent_location = message["parent"]
            if self.children_locations:
                self._pending_reponses[message["rid"]] = [
                    [],
                    message["reply_to"],
                    dt.datetime.now(),
                    0,
                ]
                for child in self.children_locations:
                    self._pending_reponses[message["rid"]][0].append(f"{child}")
                    self._pending_reponses[message["rid"]][-1] += 1
                    self.publish(
                        f"location/{self.agent_name}/{child}/set_parent",
                        {
                            "rid": f"{message['rid']}{RIDSEP}{child}",
                            "reply_to": f"location/{self.agent_name}/{self.location_name}/set_parent",
                            "parent": self.parent_location + [self.location_name],
                        },
                        "request",
                    )
            else:
                self.publish(
                    message["reply_to"],
                    {"rid": message["rid"], "set": True},
                    "response",
                )
            self.save_config()

        elif func == "map":
            try:
                msg = {"rid": message["rid"], "status": "ok"}
                if message["action"] == "add":
                    cmd = {
                        x: y
                        for x, y in message.items()
                        if x in ["order", "device", "command", "mapping", "payload"]
                    }
                    if message["name"] not in self.commands:
                        self.commands[message["name"]] = []
                    self.commands[message["name"]].append(cmd)
                elif message["action"] == "update":
                    idx = -1
                    for x in range(len(self.commands[message["name"]])):
                        if x["order"] == self.commands[message["name"]][x]["order"]:
                            idx = x
                            for k in ["device", "command", "mapping", "payload"]:
                                self.commands[message["name"]][x][k] = message[k]
                            idx = x
                            break
                    if idx == -1:
                        self.commands[message["name"]].append(
                            {
                                x: y
                                for x, y in message.items()
                                if x
                                in ["order", "device", "command", "mapping", "payload"]
                            }
                        )
                elif message["action"] == "delete":
                    if "order" in message:
                        for x in range(len(self.commands[message["name"]]))[::-1]:
                            if (
                                message["order"]
                                == self.commands[message["name"]][x]["order"]
                            ):
                                del self.commands[message["name"]][x]
                        if not self.commands[message["name"]]:
                            del self.commands[message["name"]]
                    else:
                        del self.commands[message["name"]]
                else:
                    msg = {
                        "rid": message["rid"],
                        "status": "error",
                        "errmsg": f"Unknown map action {message['action']}",
                    }

                self.save_config()
                self.publish(message["reply_to"], msg, "response")
            except Exception as e:
                msg = {"rid": message["rid"], "status": "error", "errmsg": str(e)}
                self.publish(message["reply_to"], msg, "response")

        else:
            super().handle_request_location(topic, message)

    def handle_event_location(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:

        """
        Handling 'entering' and 'leaving' events for the location.

        """

        if len(topic) == 2:
            devid, func = topic
            assert devid in self.device_list
        else:
            _log.debug("This should not have happened")
            return

        if func == "entering":
            _log.debug(f"{message['count']} stuffs entering the location")
            self.device_list[message["device_id"]].add_occupant(message["count"])
        elif func == "leaving":
            _log.debug(f"{message['count']} stuffs exiting the location")
            self.device_list[message["device_id"]].del_occupant(message["count"])

    @Core.schedule(periodic(30))
    def _clean_up(self) -> None:
        """
        Clean up when an added device is not online.

        """

        if self._resubscribe:
            self._resubscribe = False
            self._create_subscriptions()
        if self.to_be_added:
            to = dt.datetime.now() - dt.timedelta(seconds=5)
            for device_id in [x for x in self.to_be_added]:
                rt, ri, tstmp = self.to_be_added[device_id]
                if tstmp < to:
                    self.publish(rt, {"rid": ri, "status": "unknown"}, "response")
                    del self.to_be_added[device_id]

    @Core.schedule(periodic(3))
    def _add_parent_response_clean_up(self) -> None:
        now = dt.datetime.now()
        toremove = []
        for rid, needed_resp in self._pending_reponses.items():
            loc, rto, tstmp, cnt = needed_resp
            if (loc == [] and (tstmp + dt.timedelta(seconds=1) > now)) or (
                tstmp + dt.timedelta(seconds=5) < now
            ):
                toremove.append(rid)
                _log.debug(f"Cleaning set_parent with {loc} for {rid}")
                if loc == []:
                    self.publish(
                        rto, {"rid": rid, "set": True}, "response",
                    )
                elif len(loc) == cnt:
                    self.publish(
                        rto,
                        {
                            "rid": rid,
                            "set": False,
                            "error_msg": "Children did not respond",
                        },
                        "response",
                    )
                else:
                    self.publish(
                        rto,
                        {
                            "rid": rid,
                            "set": "partial",
                            "error_msg": "Some children did not respond",
                            "error": loc,
                        },
                        "response",
                    )
        for rid in toremove:
            del self._pending_reponses[rid]


class AltoDatalogger(AltoAgent):
    """
    This schema is for datalogger.

    By default, these are only interrested in datalogger events

    Configuration:

        * data_to_log: list of string specifying what to log. By default 'sample'

    """

    def __init__(self, topic: str = "", **kwargs: int) -> AltoAgent:
        super().__init__(topic, **kwargs)
        self.schemas.add("datalogger")
        self._loattr.add("data_to_log")
        self._attrtypes["data_to_log"] = list
        if getattr(self, "data_to_log", None) is None:
            setattr(self, "data_to_log", ["event"])

    def _create_subscriptions(self) -> None:
        """
        The schema "datalogger" is treated a tad differently

        """
        # Unsubscribe from everything.
        self.schemas.remove("datalogger")
        super()._create_subscriptions()
        self.schemas.add("datalogger")

        self.vip.pubsub.subscribe(
            peer="pubsub", prefix="datalogger", callback=self._handle_message
        )

    def _handle_message(self, peer, sender, bus, topic, headers, message):
        """
        Needs overloading because datalogger should not check the agent name

        """
        if sender != self.core.identity:  # Let's not bother with our own messages
            try:
                split_topic = topic.replace(self.topic, "").split("/")
                _log.debug(f"Split topic is {split_topic}")
                schema = split_topic[0]
                mtype = headers["message_type"].lower().strip()
                _log.debug(f"Executing handle_{mtype}_{schema} ")
                if mtype == "response":
                    getattr(self, "handle_" + mtype + "_" + schema)(
                        split_topic[2:], message, headers
                    )
                else:
                    getattr(self, "handle_" + mtype + "_" + schema)(
                        split_topic[2:], message
                    )
            except Exception as e:
                _log.debug(
                    f"Problem handling message from {sender}. \n\tHeader: {headers}, \n\ttopic: {topic}, \n\tmessage: {message},\n\terror: {e}"
                )
                _log.exception((e))

    def handle_event_datalogger(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        _log.debug(f"Checking {topic} vs {self.data_to_log}")
        if topic[-1] not in self.data_to_log:
            return
        try:
            if "location" in message:
                loc = message["location"]
            else:
                loc = "Sol System"
            devid = message["device_id"]
            subdev = message["subdevice_idx"]
            tmstmp = message["timestamp"]
            dtype = message["type"]
            for datapoint in message.keys():
                if datapoint not in [
                    "timestamp",
                    "device_id",
                    "subdevice_idx",
                    "location",
                    "type",
                    "device_name",
                    "subdevice_name",
                ]:
                    sample = {
                        "location": loc,
                        "device_id": devid,
                        "subdevice_idx": subdev,
                        "timestamp": tmstmp,
                        "type": dtype,
                    }
                    sample["datapoint"] = datapoint
                    sample["value"] = message[datapoint]

                    for logger in self.device_list.values():
                        logger._do_log_data(sample)
        except Exception as e:
            _log.debug(f"Error whilst logging data: {e}")

    def handle_request_datalogger(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:
        """
             Handle query and devinfo schema

        """
        if len(topic) != 2:
            raise AltoSchemaError("Datalogger request handler cannot parse topic")
        _log.debug(f"Datalogger Request with {message}")
        devid, func = topic
        try:
            if func == "devinfo":
                self.send_response_devinfo(devid, message)
            elif func == "query":
                self.handle_query_request(devid, message)
            else:
                _log.warning(f"Request {func} is not know to the switch schema")
        except Exception as e:
            _log.debug("\n\nOpps in datalogger request: {}".format(e))
            _log.exception(e)

    def handle_query_request(self, devid, message):
        """
        Query the database and return the results in a response.
        """
        if devid in self.device_list:
            if "reply_to" in message and "rid" in message:
                msg = {"rid": message["rid"], "status": "error"}
                msg["errmsg"] = "Query request not supported."
                topic = message["reply_to"]
                self.publish(topic, msg, "response")

    @Core.schedule(periodic(TIMERESOLUTION))
    def _flush_all_data(self) -> None:
        for logger in self.device_list.values():
            try:
                logger.flush_data()
            except:
                pass


if __name__ == "__main__":

    _log = logging.getLogger(__name__)
