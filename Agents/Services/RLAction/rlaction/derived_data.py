from metpy.calc import wet_bulb_temperature, dewpoint_from_relative_humidity
from metpy.units import units

from rlaction import (_log,
                      PMVCalculation,
                      DataStore)


def derived_data_factory(dtype):
    if dtype == "outdoor_weather_obs":
        return OutdoorWeatherObs
    if dtype == "indoor_weather_obs":
        return IndoorWeatherObs
    if dtype == "mean_radiant_temperature":
        return MeanRadiantTemperature
    if dtype == "energy_obs":
        return EnergyObs
    if dtype == "pmv":
        return PMV

    raise Exception(f"Unknown derived_data {dtype}")


class DerivedData(DataStore):

    def __init__(self, data_id, input_ds, expiration=600):
        """
        input_ds: [list of DataStore]
        """

        super().__init__(data_id, expiration)
        self._input_ds = input_ds
        """
        input_ds = [data_store_ins_1,] # directed map with DataStore
        """

        _log.debug(f"DerivedData init {self._data_id} {self._input_ds}")

    def _is_ds_updated_and_not_none(self):
        is_ds_updated = True
        is_data_none = False
        if not self._input_ds:
            return False
        for i in self._input_ds:
            if not i.check_update():
                is_ds_updated = False
                break
            if not i.data:
                is_data_none = True
                break
            for k, v in i.data.items():
                if v is None:
                    is_data_none = True
                    break
        if is_ds_updated and not is_data_none:
            return True
        return False


class OutdoorWeatherObs(DerivedData):

    def __init__(self, data_id, input_ds, *args):
        """
        input_ds: [UndergroundData, OutdoorWeatherData]
        """

        super().__init__(data_id, input_ds)
        self._data = {
            "outdoor_db_temp": None,
            "outdoor_wb_temp": None
        }

    def update_data(self, data):
        try:
            # if data is None:
            if self._is_ds_updated_and_not_none():
                outdoor_db_temp, outdoor_wb_temp = self.get_outdoor_weather_obs(_outdoor_db_temp=self._input_ds[1].data["temperature"], _pressure=self._input_ds[0].data["pressure"], dewpoint_temp=self._input_ds[0].data["dew_point"])
                self._data["outdoor_db_temp"] = outdoor_db_temp
                self._data["outdoor_wb_temp"] = outdoor_wb_temp
                self._unix_timestamp = self._input_ds[1].unix_timestamp
            _log.debug(f"OutdoorWeatherObs update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"OutdoorWeatherObs update_data {self._data_id} {e}")

    def get_outdoor_weather_obs(self, _outdoor_db_temp, _pressure, dewpoint_temp):
        """
        Get outdoor weather observations from weather underground
        Returns:
            float: outdoor dry-bulb temperature
            float: outdoor wet-bulb temperature
        """

        _pressure = [_pressure] * units.mbar
        temperature = [_outdoor_db_temp] * units.degC
        dewpoint = [dewpoint_temp] * units.degC
        _outdoor_wb_temp = float(wet_bulb_temperature(_pressure, temperature, dewpoint).m)
        return _outdoor_db_temp, _outdoor_wb_temp


class IndoorWeatherObs(DerivedData):

    def __init__(self, data_id, input_ds, *args):
        """
        input_ds: [NetatmoData,]
        """

        super().__init__(data_id, input_ds)
        self._data = {
            "indoor_db_temp": None,
            "indoor_dewpoint_temp": None
        }

    def update_data(self, data):
        try:
            # if data is None:
            if self._is_ds_updated_and_not_none():
                indoor_db_temp, indoor_dewpoint_temp = self.get_indoor_weather_obs(_indoor_db_temp=self._input_ds[0].data["temperature"], indoor_relative_humidity=self._input_ds[0].data["humidity"])
                self._data["indoor_db_temp"] = indoor_db_temp
                self._data["indoor_dewpoint_temp"] = indoor_dewpoint_temp
                self._unix_timestamp = self._input_ds[0].unix_timestamp
            _log.debug(f"IndoorWeatherObs update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"IndoorWeatherObs update_data {self._data_id} {e}")

    def get_indoor_weather_obs(self, _indoor_db_temp, indoor_relative_humidity):
        _indoor_db_temp = [_indoor_db_temp] * units.degC
        indoor_relative_humidity = [indoor_relative_humidity] * units.percent
        _indoor_dewpoint_temp = float(dewpoint_from_relative_humidity(_indoor_db_temp, indoor_relative_humidity).m)
        return float(_indoor_db_temp.m), _indoor_dewpoint_temp


class MeanRadiantTemperature(DerivedData):

    def __init__(self, data_id, input_ds, *args):
        """
        input_ds: [OutdoorWeatherData,]
        """

        super().__init__(data_id, input_ds)
        self._data = {
            "mean_radiant_temp": None,
        }

    def update_data(self, data):
        try:
            # if data is None:
            if self._is_ds_updated_and_not_none():
                mean_radiant_temp = self.calculate_mrt(_outdoor_db_temp=self._input_ds[0].data["temperature"], _solar_irradiation=self._input_ds[0].data["solar_irradiance"], _wind_velocity=self._input_ds[0].data["wind_speed"])
                self._data["mean_radiant_temp"] = mean_radiant_temp
                self._unix_timestamp = self._input_ds[0].unix_timestamp
            _log.debug(f"MeanRadiantTemperature update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"MeanRadiantTemperature update_data {self._data_id} {e}")

    def calculate_mrt(self, _outdoor_db_temp, _solar_irradiation, _wind_velocity):
        """
        Args:
            _outdoor_db_temp: celsius
            _solar_irradiation:  # solar irradiation(watt/m2)
            _wind_velocity: # wind velocity(m/s)

        Returns:

        """

        Ta = _outdoor_db_temp
        S0 = _solar_irradiation
        V = _wind_velocity

        Tg = Ta + (S0 - 30) / (0.0252 * S0 + 10.5 * _wind_velocity + 25.5)  # global temperature (celsius)
        D = 0.15  # constant
        e = 0.95  # constant
        _mean_radiant_temp = ((Tg + 273) ** 4 + (1.10 * (10 ** 8) * (V ** 0.6) * (Tg - Ta)) / (e * (D ** 0.4))) ** 0.25 - 273
        return _mean_radiant_temp


class EnergyObs(DerivedData):

    def __init__(self, data_id, input_ds, *args):
        """
        input_ds: [ModbusMeterData1, ModbusMeterData2, ...]
        """

        super().__init__(data_id, input_ds)
        self._data = {
            "energy": None,
        }

    def update_data(self, data):
        try:
            # if data is None:
            if self._is_ds_updated_and_not_none():
                modbus_meter_power = 0.0
                for i in self._input_ds:
                    modbus_meter_power += i.data["power"]
                energy = self.get_energy_obs(power=modbus_meter_power)
                self._data["energy"] = energy
                self._unix_timestamp = self._input_ds[0].unix_timestamp
            _log.debug(f"EnergyObs update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"EnergyObs update_data {self._data_id} {e}")

    def get_energy_obs(self, power: float) -> float:
        """Convert power in kW to energy in joule

        Returns:
            float: energy in joule
        """

        kw_to_w = 1000  # kW to W
        w_to_j = 1800
        _energy = power * kw_to_w * w_to_j  # energy = 9e7
        return _energy


class PMV(DerivedData):

    def __init__(self, data_id, input_ds, met, clo, v, *args):
        """
        input_ds: [ModbusMeterData1, ModbusMeterData2, ...]
        """

        super().__init__(data_id, input_ds)
        self._data = {
            "pmv": None,
        }

        self.met = met
        self.clo = clo
        self.v = v

    def update_data(self, data: dict = None):
        try:
            # if data is None:
            if self._is_ds_updated_and_not_none():
                # pmv = PMVCalculation.calc_pmv(self._input_ds[0].data["temperature"], self._input_ds[0].data["humidity"])
                pmv = PMVCalculation.calc_pmv_with_constant(self._input_ds[0].data["temperature"], self._input_ds[0].data["humidity"], self.met, self.clo, self.v)
                self._data["pmv"] = pmv
                self._unix_timestamp = self._input_ds[0].unix_timestamp
            _log.debug(f"PMV update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"PMV update_data {self._data_id} {e}")
