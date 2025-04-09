import warnings
import logging

from volttron.platform.agent import utils

from pythermalcomfort.models import pmv
from pythermalcomfort.utilities import v_relative


_log = logging.getLogger(__name__)
utils.setup_logging()


class AltoNotImpl(Exception):
    """
    Exception raised when a method must be overridden but has not been.
    """

    pass


class PMVCalculation:
    "The Singleton Class"

    @staticmethod
    def calc_pmv(tdb: float, rh: float, tr: float = None):
        warnings.warn("In PMVCalculation, this 'calc_pmv' method shall be removed soon.", DeprecationWarning)
        """
        Predicted Mean Vote (`PMV`) calculated in accordance to main thermal comfort Standards.
        tdb : float
            dry bulb air temperature, default in [°C] in [°F] if `units` = 'IP'
        tr : float
            mean radiant temperature, default in [°C] in [°F] if `units` = 'IP'
        vr : float
            relative air speed, default in [m/s] in [fps] if `units` = 'IP'

            Note: vr is the relative air speed caused by body movement and not the air
            speed measured by the air speed sensor.   
        rh : float
            relative humidity, [%]
        met : float
            metabolic rate, [met]
        clo : float
            clothing insulation, [clo]
        """

        met = 1.1  # 1.1 for typing (Ref: https://bit.ly/3gkt9nf)
        v_r = v_relative(v=0.1, met=met)

        """
        Clothing Insulation
        1. Trousers, long-sleeve shirt: 0.61 (Ref: https://bit.ly/3ufWhUR)
        2. Men's underwear: 0.04
        3. Women's underwear: 0.03
        4. Ankle socks: 0.02
        Sum = 0.7
        Ref: https://bit.ly/3IUoncj  
        """
        clo = 0.7
                
        return pmv(tdb=tdb, tr=tdb, vr=v_r, rh=rh, met=met, clo=clo)
    
    @staticmethod
    def calc_pmv_with_constant(tdb: float, rh: float, met: float, clo: float, v: float, tr: float = None):
        """
        Predicted Mean Vote (`PMV`) calculated in accordance to main thermal comfort Standards.
        tdb : float
            dry bulb air temperature, default in [°C] in [°F] if `units` = 'IP'
        tr : float
            mean radiant temperature, default in [°C] in [°F] if `units` = 'IP'
        vr : float
            relative air speed, default in [m/s] in [fps] if `units` = 'IP'

            Note: vr is the relative air speed caused by body movement and not the air
            speed measured by the air speed sensor.   
        rh : float
            relative humidity, [%]
        met : float
            metabolic rate, [met]
        clo : float
            clothing insulation, [clo]
        """

        # met = 1.1  # 1.1 for typing (Ref: https://bit.ly/3gkt9nf)
        # v_r = v_relative(v=0.1, met=met)
        v_r = v_relative(v=v, met=met)

        """
        Clothing Insulation
        1. Trousers, long-sleeve shirt: 0.61 (Ref: https://bit.ly/3ufWhUR)
        2. Men's underwear: 0.04
        3. Women's underwear: 0.03
        4. Ankle socks: 0.02
        Sum = 0.7
        Ref: https://bit.ly/3IUoncj  
        """
        # clo = 0.7
                
        return pmv(tdb=tdb, tr=tdb, vr=v_r, rh=rh, met=met, clo=clo)


class GlobalRLOutput:
    """
    This is global scope control of RLOutput
    """

    def __init__(self, controller, global_output_id, global_output_enable=True):
        self._controller = controller
        self._global_output_id = global_output_id
        self._global_output_enable = global_output_enable
    
    def enable_global_output(self):
        self._global_output_enable = True
        # self.emit_rl_global_output_state()
        # self._controller.update_output_devices_enable(self._output_id, self._output_enable)

    def disable_global_output(self):
        self._global_output_enable = False
        # self.emit_rl_global_output_state()
        # self._controller.update_output_devices_enable(self._output_id, self._output_enable)

    @property
    def global_output_enable(self):
        return self._global_output_enable
    
    def emit_rl_global_output_state(self):
        output_topic = f'''rein_global_output/{self._controller.core.identity}/{self._global_output_id}/event'''
        data = {
            "device_id": self._global_output_id,
            "subdevice_idx": 0,
            "subdevice_name": "subdev_0",
            "type": "rl_global_output_state",
            "timestamp": dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat(),
            "unix_timestamp": time.time(),
            "global_output_enable": self._global_output_enable,
        }
        _log.debug(f"GlobalRLOutput emit_rl_global_output_state {self._global_output_id} {data}")
        self._controller.publish(output_topic, data, "event")
