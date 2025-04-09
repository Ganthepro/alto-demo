import requests
import json
from evbikeabnormal.utils_firebase import FirebaseManage

firebase_manage = FirebaseManage()
db = firebase_manage.db

def get_token(link_path=None):
    try:
        response = requests.post(
            url="https://altoiotbackend.azurewebsites.net/api/v2.0/login",
            headers={
                "content-type": "application/json",
            },
            data=json.dumps({
                "username": "betaadmin",
                "password": "betaadmin"
            })
        )
        print('Response HTTP Status Code: {status_code}'.format(
            status_code=response.status_code))
        token = json.loads((response.content).decode())

        if link_path:
            db.child(link_path).set(token['token'])

        return token['token']

    except requests.exceptions.RequestException:
        print('HTTP Request failed')


def rider_notify_anomaly(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value):
    # POST: NOTIFICATIONS
    # POST https://altoiotbackend.azurewebsites.net/api/v2.0/notification

    if condition_name == "state_of_charge":
        notification_message = "evbike has low battery percent"
    elif condition_name == "speed":
        notification_message = "evbike speed over limit"
    elif condition_name == "location":
        notification_message = "evbike out of service area"
    else:
        return None

    notification_image = ""

    try:
        token_path = "EV/Beta_Energy_Solution/other/token"
        token_node = db.child(token_path).get()

        if token_node is None:
            token = get_token(token_path)
        else:
            token = token_node.val()

        response = requests.post(
            url="https://altoiotbackend.azurewebsites.net/api/v2.0/notification",
            headers={
                "Authorization": "Token {token}".format(token=token),
                "Content-Type": "application/json; charset=utf-8"
            },
            data=json.dumps({
                "trigger": [
                    {
                        str(device_id): {
                            "anomaly": {
                                str(condition_name): {
                                    "current_value": str(current_value),
                                    "notification_message": str(notification_message),
                                    "notification_image": str(notification_image),
                                    "notify_to": "rider",
                                    "detect_value": detect_value,
                                    "threshold_max": str(threshold_max),
                                    "threshold_min": str(threshold_min)
                                }
                            },
                            "normal": {}
                        }
                    }
                ]
            })
        )
        print('Response HTTP Status Code: {status_code}'.format(status_code=response.status_code))
        print('Response HTTP Response Body: {content}'.format(content=response.content))

        if response.status_code == 401:
            _ = get_token(token_path)
            rider_notify_anomaly(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)
            print('REPEATED')

    except requests.exceptions.RequestException:
        print('HTTP Request failed')


def rider_notify_normal(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value):
    # POST: NOTIFICATIONS
    # POST https://altoiotbackend.azurewebsites.net/api/v2.0/notification

    if condition_name == "state_of_charge":
        notification_message = "battery percent: normal"
    elif condition_name == "speed":
        notification_message = "evbike speed: normal"
    elif condition_name == "location":
        notification_message = "evbike location: normal"
    else:
        return None

    notification_image = ""

    try:
        token_path = "EV/Beta_Energy_Solution/other/token"
        token_node = db.child(token_path).get()

        if token_node is None:
            token = get_token(token_path)
        else:
            token = token_node.val()

        response = requests.post(
            url="https://altoiotbackend.azurewebsites.net/api/v2.0/notification",
            headers={
                "Authorization": "Token {token}".format(token=token),
                "Content-Type": "application/json; charset=utf-8"
            },
            data=json.dumps({
                "trigger": [
                    {
                        str(device_id): {
                            "normal": {
                                str(condition_name): {
                                    "current_value": str(current_value),
                                    "notification_message": str(notification_message),
                                    "notification_image": str(notification_image),
                                    "notify_to": "rider",
                                    "detect_value": detect_value,
                                    "threshold_max": str(threshold_max),
                                    "threshold_min": str(threshold_min)
                                }
                            },
                            "anomaly": {}
                        }
                    }
                ]
            })
        )
        print('Response HTTP Status Code: {status_code}'.format(status_code=response.status_code))
        print('Response HTTP Response Body: {content}'.format(content=response.content))

        if response.status_code == 401:
            _ = get_token(token_path)
            rider_notify_normal(device_id, condition_name, current_value, threshold_max, threshold_min, detect_value)
            print('REPEATED')

    except requests.exceptions.RequestException:
        print('HTTP Request failed')


if __name__ == "__main__":
    rider_notify_normal(device_id="location_tracker002", condition_name="location", 
        current_value="13, 110", threshold_max="r10", threshold_min=None, detect_value=None)
