import pandas as pd
import requests
import time


def send_line_notify(msg: str):
    """
    Send notification to Line Notify
    Args:
        msg (str)   : message to be sent to Line Notify
    """

    url = 'https://notify-api.line.me/api/notify'
    token = 'qfWU4K4nPcq857cdwCDPvBQ1n06FloJz43Tu2TTjEBB'
    headers = {'content-type':'application/x-www-form-urlencoded','Authorization':'Bearer '+token}

    r = requests.post(url, headers=headers, data={'message':msg})


def check_anomaly_status(_df: pd.DataFrame, _x: list, thres: int):
    """
    Send notification to Web API and Line Notify
    Args:
        _df (pd.DataFrame)    : dataframe of data
        _x (list)             : timestamp of anomaly detection occurence
        thres (int)           : threshold number of how many of anomaly detection occurence count to consider send the notification

    Returns:
        abnormal_status       : status of anomaly detection (True if detected, otherwise False)
    """

    # Count the latest ... data points that are anomaly and decide whether to send the notification or not
    count = 0
    for i in _df.index[-60:]:
        if i in _x:
            count += 1

    if count > thres:
        abnormal_status = True

    else:
        abnormal_status = False

    return abnormal_status
