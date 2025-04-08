# **Example**

### **Case: Add new device**

#### **Input Devices**

*This example added the Airveda device*

1. Add this new type to config on `in_out_agent`. Prepare for the config of airveda input data

```JSON
{
    "in_out_agent": {
        "in": {
            .
            .
            .
            "airveda_data": "airveda"
        },
        .
        .
        .
    },
}
```

2. Add sensor handle of airveda data from subscription on controller.

```python
def _handle_sub_sensor(self, peer, sender, bus, topic, headers, message):
    .
    .
    .
    if topic_sec[3] == "event":
        .
        .
        .
        if topic_sec[1] == self.in_out_agent["in"]["airvedata_data"]:
            if "airveda_data" in self.data_stores_ins:
                if topic_sec[2] in self.data_stores_ins["airveda_data"]:
                    self._add_job({
                        "instance": self.data_stores_ins["airveda_data"][topic_sec[2]],
                        "data": copy.deepcopy(message)
                    })
```

3. Create a Datastore class.<br>
Add new class that inherit DataStore class for supported device data. In this case we create `AirvedaData` class. then,
add the class in the `data_store_factory` function.

```python
class AirvedaData(DataStore):

    def __init__(self, data_id):
        super().__init__(data_id)
        self._data = {
            "temperature": None,
            "humidity": None,
            "co2": None
        }

    def update_data(self, data):
        try:
            if data is not None:
                if data["subdevice_idx"] == 0 and data["type"] == "environment":
                    self._data["temperature"] = data["temperature"]
                    self._data["humidity"] = data["humidity"]
                    self._data["co2"] = data["co2"]
                    self._update_time()
                    _log.debug(f"AirvedaData update_data {self._data_id} {self._unix_timestamp} {self._data}")
        except Exception as e:
            _log.error(f"AirvedaData update_data {self._data_id} {e}")
```

4. Add a data store type in the `data_store_factory` method.

```python
def data_store_factory(dtype):
    .
    .
    .
    if dtype == "airveda_data":
        return AirvedaData
```

### **Output devices**

*this example added the ITM OAU device*

1. Add new output type in config on `in_out_agent`. Prepare for the config of itm oau output

```JSON
{
    "in_out_agent": {
        .
        .
        .
        "out": {
            .
            .
            "itm_oau_out_1": "itm_oau"
        },
    },
}
```

2. Create `emit_itm_oau_state` method on controller class. Change a topic and message to the correct command format.

```python
def emit_itm_oau_state(self, device_id, subdevice_idx, state):
        topic = f'''hvac/{self.in_out_agent["out"]["itm_oau_out_1"]}/{device_id}/command'''
        message = {"subdevice_idx": subdevice_idx, "mode": state}
        self.vip.pubsub.publish(peer="pubsub",
                                topic=topic,
                                headers={'requesterID': self.core.identity,
                                         "message_type": "command",
                                         },
                                message=message)
        _log.debug(f"RLAction set_itm_oau_state: {topic}, message : {message}")
```

3. Create a class.<br>
Add new class that inherit `OutputDevice` class for control device. In this case we create `ITMOAUOutput` class. then,
add the class in the `output_device_factory` function.

```python
class ITMOAUOutput(OutputDevice):

    def __init__(self, controller, input_rl, output_id, output_enable):
        super().__init__(controller, input_rl, output_id, output_enable)
        self._output_state = None

    def __str__(self):
        return "itm_oau_output"

    def process_output(self):
        """
        process output from rl input data
        """
        try:
            if self._is_rl_updated() and len(self._input_rl[0].rl_output)>0:
                self._output_state =  self._input_rl[0].rl_output[self._input_rl[1]]
                if isinstance(self._output_state, str):
                    if self._output_state == "on" or self._output_state == "off":
                        self.emit_output()
                self.emit_rl_output(True)
            else:
                self._output_state = "on" # default on
                self.emit_output()
                self.emit_rl_output(False)
            self.emit_rl_output_state()
        except Exception as e:
            _log.error(f"ITMOAUOutput process_output {self._output_id} {e}")

    def emit_output(self):
        if self._output_enable:
            self._controller.emit_itm_oau_state(self._output_device_id, self._subdev_number, self._output_state)

    def emit_rl_output(self, is_data_updated):
        output_topic = f'''rein_output/{self._controller.core.identity}/{self._output_id}/event'''
        data = {
            "device_id": self._output_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_output",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "is_data_updated": is_data_updated,
            "output_state": self._output_state,
        }
        _log.debug(f"ITMOAUOutput process_output {self._output_id} {data}")
        self._controller.publish(output_topic, data, "event")
```

4. Add output device type in the `output_device_factory` method

```python
def output_device_factory(dtype):
    .
    .
    .
    if dtype == "itm_oau_output":
        return ITMOAUOutput
```

5. Add output_type `itm_oauu_output` on `_ahu_period_signal` method at `self._process_rl_data_and_action(..., output_type=["itm_oau_output"])`.

```python
def _ahu_period_signal(self):
        self._process_rl_data_and_action(rl_type=["ahu_rl"], output_type=["ahu_output", "itm_oau_output"])
```

## **Case: Add new manipulation**

*this example added the Statistics manipulation*

1. Create a class. <br>
Add new class that inherit `BaseManipulation` class. In this case we create `StatisticOps` class. then,
add the class in the `manipulation_factory` function.

```python
class StatisticOps(BaseManipulation):

    def __init__(self, man_id, input_source, operator):
        """
        statistics operation: "max|min|mean" # operator type
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
                if self._operator in ["max", "min", "mean"]:
                    getattr(self, "_" + self._operator)()
                    # self._set_is_updated()
                    self._unix_timestamp = self._input_source[0][0].unix_timestamp
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

    def _mean(self):
        input_data = []
        for i in self._input_source:
            if isinstance(i, (float, int)):
                input_data.append(i)
            else:
                input_data.append(i[0].data[i[1]])
        self._data["out1"] = sum(input_data)/len(input_data)
```

2. Add output device type in the `manipulation_factory` method

```python
def manipulation_factory(dtype):
    .
    .
    .
    if dtype == "statistic_ops":
        return StatisticOps
```
