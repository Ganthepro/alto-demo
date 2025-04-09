from rlaction import (_log,
                      AltoNotImpl,
                      DataStore)


def manipulation_factory(dtype):
    if dtype == "arithmetic_ops":
        return ArithmeticOps
    if dtype == "statistic_ops":
        return StatisticOps

    raise Exception(f"Unknown manipulation {dtype}")


class BaseManipulation(DataStore):

    def __init__(self, data_id, input_source, expiration=600):
        """
        man_id: "ex_id" # The shorthand of manipulation identifier
        input_source: [[data_store_1, "parameter_1"], 3.4, [data_store_2, "parameter_1"], [derived_data_1, "parameter_2"], ...] # List of input sources
        """

        super().__init__(data_id, expiration)
        self._input_source = input_source
        # self._data_output = {}
        # self._is_updated = False

        _log.debug(f"BaseManipulation init {self._data_id} {self._input_source}")

    # @property
    # def data_output(self):
    #     return self._data_output

    # @property
    # def is_updated(self):
    #     return self._is_updated

    # def _set_is_updated(self):
    #     self._is_updated = True

    # def _reset_is_updated(self):
    #     self._is_updated = False

    def _is_input_source_updated_and_not_none(self):
        is_s_updated = True
        is_data_none = False
        if not self._input_source:
            return False
        for i in self._input_source:
            if isinstance(i, list):
                if not i[0].check_update():
                    is_s_updated = False
                    break
                if not i[0].data:
                    is_data_none = True
                    break
                if i[0].data[i[1]] is None:
                    is_data_none = True
                    break
            elif not isinstance(i, (float, int)):
                is_data_none = True
                break
        if is_s_updated and not is_data_none:
            return True
        return False

    def manipulate(self):
        """
        Method that MUST be overridden to manipulate the input source data
        """

        raise AltoNotImpl("manipulate method must be implemented")

    
class ArithmeticOps(BaseManipulation):

    def __init__(self, man_id, input_source, operator):
        """
        operator: "nop|add|sub|mul" # operator type, nop for no-operations, add for additions, sub for subtractions, mul for multiplications
        """

        super().__init__(man_id, input_source)
        self._operator = operator
        self._data = {
            "out1": None,
        }

    def manipulate(self):
        try:
            # self._reset_is_updated()
            if self._is_input_source_updated_and_not_none():
                if self._operator in ["nop", "add", "sub", "mul"]:
                    getattr(self, "_" + self._operator)()
                    # self._set_is_updated()
                    self._unix_timestamp = self._input_source[0][0].unix_timestamp
            _log.debug(f"ArithmeticOps manipulate {self._data_id} {self.check_update()} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"ArithmeticOps manipulate {self._data_id} {e}")

    def _nop(self):
        self._data["out1"] = self._input_source[0][0].data[self._input_source[0][1]]

    def _add(self):
        data_output = self._input_source[0][0].data[self._input_source[0][1]]
        for idx, i in enumerate(self._input_source):
            if idx > 0:
                if isinstance(i, (float, int)):
                    data_output += i
                else:
                    data_output += i[0].data[i[1]]
        self._data["out1"] = data_output

    def _sub(self):
        data_output = self._input_source[0][0].data[self._input_source[0][1]]
        for idx, i in enumerate(self._input_source):
            if idx > 0:
                if isinstance(i, (float, int)):
                    data_output -= i
                else:
                    data_output -= i[0].data[i[1]]
        self._data["out1"] = data_output

    def _mul(self):
        data_output = self._input_source[0][0].data[self._input_source[0][1]]
        for idx, i in enumerate(self._input_source):
            if idx > 0:
                if isinstance(i, (float, int)):
                    data_output *= i
                else:
                    data_output *= i[0].data[i[1]]
        self._data["out1"] = data_output


class StatisticOps(BaseManipulation):

    def __init__(self, man_id, input_source, operator):
        """
        statistics operation: "max|min|mean|mean_all" # operator type
        """

        super().__init__(man_id, input_source)
        self._operator = operator
        self._data = {
            "out1": None,
        }

    def manipulate(self):
        try:
            # self._reset_is_updated()
            if self._operator in ["mean_all"]: # "max_all", "min_all",
                if self._is_input_source_updated_and_not_none():
                    getattr(self, "_" + self._operator)()
                    # self._set_is_updated()
                    self._unix_timestamp = self._input_source[0][0].unix_timestamp
            elif self._operator in ["mean"]:
                getattr(self, "_" + self._operator)()
                # if self._data["out1"] is not None:
                #     self._unix_timestamp = self._input_source[0][0].unix_timestamp
            _log.debug(f"StatisticsOps manipulate {self._data_id} {self.check_update()} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"StatisticsOps manipulate {self._data_id} {e}")

    def _max(self):
        input_data = []
        for i in self._input_source:
            if isinstance(i, (float, int)):
                input_data.append(i)
            else:
                input_data.append(i[0].data[i[1]])
        self._data["out1"] = max(input_data)

    def _min(self):
        input_data = []
        for i in self._input_source:
            if isinstance(i, (float, int)):
                input_data.append(i)
            else:
                input_data.append(i[0].data[i[1]])
        self._data["out1"] = min(input_data)

    def _mean_all(self):
        input_data = []
        for i in self._input_source:
            if isinstance(i, (float, int)):
                input_data.append(i)
            else:
                input_data.append(i[0].data[i[1]])
        self._data["out1"] = sum(input_data)/len(input_data)
    
    def _mean(self):
        input_data = []
        for i in self._input_source:
            if isinstance(i, (float, int)):
                input_data.append(i)
            else:
                if i[0].check_update() and i[0].data and i[0].data[i[1]] is not None:
                    input_data.append(i[0].data[i[1]])
                    self._unix_timestamp = i[0].unix_timestamp
        if len(input_data):
            self._data["out1"] = sum(input_data)/len(input_data)
        else:
            self._data["out1"] = None

