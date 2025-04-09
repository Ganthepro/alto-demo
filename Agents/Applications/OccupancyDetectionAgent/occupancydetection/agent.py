import logging
import sys
import os

from line_notify import LineNotify
import onnxruntime
import pendulum

from occupancydetection.occupancy_utils import NetatmoData, create_image_tensor

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


# Netatmo configuration
device_id = '70:ee:50:19:bf:64'
config = {'client_id': '60af4d6f19d0d726b31fec6f',
          'client_secret': 'Mo5zu4eJjg86rCeSOxWfQd9Kr',
          'username': 'thakorn.swa@gmail.com',
          'password': 'EypNetatmo_123',
          'device': device_id
}
netatmo_module = NetatmoData(config)

# declare model path
model_path = "HumanNet.onnx"

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
        self.stored_data = {}

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


    def load_onnx_session(self):
        # Run the model on the backend
        d = os.path.dirname(os.path.abspath(__file__))
        modelfile = os.path.join(d, model_path)
        session = onnxruntime.InferenceSession(modelfile, None)
        return session


    def make_prediction(self, session, img_tensor):
        # get the name of the first input of the model
        input_name = session.get_inputs()[0].name
        # ONNX inference
        result = session.run([], {input_name: img_tensor.numpy()})
        result_new = result[0][0][0]
        return result_new


    def line_notify(self, pred, latest_co2, latest_temp, latest_datetime, start_time=8, stop_time=22):
        # declare Line-group target
        AltoTech_AI_Intern = LineNotify('HdvsoPG0hTHFgkKAuafGWbnyAywMiFiu8JzxpGTQrdE')
        # Alto_Intern = LineNotify('o85L8Fb6FD5AuhXQmctAKGXsBYKdmW0bJ1xMkzPQcsg')

        # a variable use for disabling BOT during night-time
        send_line = True

        # shorten datetime data
        latest_datetime = str(latest_datetime)
        stop_index = len(latest_datetime) - len(":00+7.00") - 1
        latest_datetime = latest_datetime[:stop_index]
        latest_datetime = latest_datetime.replace("T", " ")

        # get current time (hr)
        time = latest_datetime.split(" ")[-1]
        time_hr = int(time[:2])

        if pred >= 0.5:
            label = 'People in the room'
        else:
            label = 'No people in the room'

        # check for night-time
        if time_hr < start_time or time_hr > stop_time:
            send_line = False
            self.stored_data[str(latest_datetime)] = [pred, latest_co2, latest_temp]
            print("stored_data: ", self.stored_data)

        # create message
        text = ""
        if send_line:
            text = f"{label}\nPred: {str(pred)[:6]}\nData: {latest_co2}-{latest_temp}\nTime: {latest_datetime}"
            if time_hr == 22:
                text = f"{text}\n\nNote: this BOT will be disabled until {start_time}.30"
            AltoTech_AI_Intern.send(text)

            if time_hr == start_time and len(self.stored_data) != 0:
                text = "night-time summary"
                for idx, dt in enumerate(self.stored_data):
                    text = f"{text}\n- {dt}\n{str(self.stored_data[dt][0])[:6]}, {self.stored_data[dt][1]}, {self.stored_data[dt][2]}"
                self.stored_data = {}
                AltoTech_AI_Intern.send(text)
            print(text)


    def run_all_methods(self):
        # Step 1: Load onnx session
        session = self.load_onnx_session()

        # Step 2: Create CO2 Image, Get all latest data
        img_tensor, data = create_image_tensor(netatmo_module)
        latest_co2 = data["co2"][-1]
        latest_temp = data["temp"][-1]
        latest_ts = data["ts"][-1]

        # Step 3: Make prediction
        pred = self.make_prediction(session, img_tensor)

        # Step 4: Line notify
        latest_datetime = pendulum.from_timestamp(int(latest_ts), tz="Asia/Bangkok").to_atom_string()
        self.line_notify(pred, latest_co2, latest_temp, latest_datetime)


    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        _log.debug("VERSION IS: {}".format(self.core.version()))
        if self._heartbeat_period != 0:
            _log.debug(f"Heartbeat starting for {self.core.identity}, published every {self._heartbeat_period}s")
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)
        query = Query(self.core)
        _log.info('query: %r', query.query('serverkey').get())

        self.core.schedule(cron('*/30 * * * *'), self.run_all_methods)


    @Core.schedule(periodic(21600)) # run every 6 hours
    def occupancy_detection(self):
        if self.counter == 0:
            self.counter += 1
            return None

        try:
            print("Periodic Done!")

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
