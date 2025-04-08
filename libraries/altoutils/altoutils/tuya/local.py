import logging
import time

import tinytuya
from altoutils.tuya.cloud import TuyaAPI, TuyaAuth
from typing import Union

_log = logging.getLogger(__name__)
_log.setLevel(logging.INFO)
__version__ = 1.0

RETRY_LIMIT = 1
TIMEOUT = 5

class DeviceDiscover:

    @staticmethod
    def discover(want_local_key=False):
        _log.info(f"Start Discovery...")
        config_discover = {}
        discover = DeviceDiscover._scan()
        for ip, prop in discover.items():
            config_discover[prop['gwId']] = {
                "ip": ip,
                "version": prop['version']
            }
        if want_local_key:
            config_discover = DeviceDiscover.local_key(config_discover)
        _log.info(f"DeviceDiscover discovery: {config_discover}")
        return config_discover

    @staticmethod
    def _scan():
        return tinytuya.deviceScan()

    @staticmethod
    def local_key(config_discover: dict):
        config_with_local_key = config_discover
        try:
            for device_id in config_discover:
                device_info = TuyaAPI(
                    TuyaAuth(
                        "pddxg9hrax4gvxdj5r8i", 
                        "2b62d5b167eb4ff18624bda2895a09c0"
                        )).get_information(device_id)
                if device_info['success']:
                    config_with_local_key[device_id].update({
                        "local_key": device_info['result']['local_key']
                    })
                del device_info
            return config_with_local_key
        except Exception as e:
            _log.error(f"DeviceDiscover local_key Error: {e}")
            return config_discover


class LocalTuya:

    def __init__(self, device_id: str, ip_address: str, local_key: str, version: int = 3.3):
        self._device_id = device_id
        self._ip_address = ip_address
        self._local_key = local_key
        self._version = version
        self._tuya_device = None
        self._connect()

    def _connect(self):
        _log.info(f"{self._device_id} Connecting...")
        try:
            self._tuya_device = tinytuya.OutletDevice(self._device_id, self._ip_address, self._local_key)
            self._tuya_device.set_version(self._version)
            self._tuya_device.set_socketRetryLimit(RETRY_LIMIT)
            self._tuya_device.set_socketTimeout(TIMEOUT)
            _log.info(f"{self._device_id} Connected")
        except Exception as e:
            _log.error(f"Connecting Error: {self._device_id}, Error: {e}")

    def reconnect(self):
        self._connect()

    def update_device(self, device_id: str, ip_address: str, local_key: str, version: int = 3.3):
        self._device_id = device_id
        self._ip_address = ip_address
        self._local_key = local_key
        self._version = version
        self._connect()

    def get_status(self):
        status = self._tuya_device.status()
        if "Err" in status:
            _log.warning(f"LocalTuya get_status Error: {status['Error']}")
            return status
        _log.info(f"LocalTuya get_status: {status}")
        return status

    # TODO
    # handle command error 
    def set_command(self, index: str, value: Union[str, int, float]):
        response = self._tuya_device.set_value(index, value)
        _log.info(f"LocalTuya set_command: {response}")
        return response
