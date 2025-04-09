import os

import cv2
import matplotlib.pyplot as plt
import netatmo
import torchvision.transforms as transforms
from PIL import Image


class NetatmoData:
    def __init__(self, config_dict):
        self.config = config_dict
        self.device_id = self.config["device"]
        self.ws = netatmo.WeatherStation(config_dict)
        self.device_availability = self.ws.get_data(self.device_id)
        print(f"NetatmoData Object created\ndevice_availability : {self.device_availability}")

    def get_latest_timestamp(self):
        body = self.ws.get_measure(
              device_id=self.device_id,
              scale="max",
              mtype="CO2",
              module_id=self.device_id,
              date_begin=None,
              date_end="last",
              limit=None,
              optimize=False,
              real_time=False,
          )["body"]

        latest_timestamp = list(body.keys())[0]

        return latest_timestamp

    def get_start_timestamp(self, latest_timestamp):
        start_timestamp = int(latest_timestamp) - 6*60*60
        return start_timestamp

    def get_data(self, start_timestamp, last_timestamp, mtype="CO2,Temperature"):
        """return 2 lists : timestamp, val"""
        data = self.ws.get_measure(
              device_id=self.device_id,
              scale="max",
              mtype=mtype,
              module_id=self.device_id,
              date_begin=start_timestamp,
              date_end=last_timestamp,
              limit=None,
              optimize=False,
              real_time=False,
          )["body"]

        timestamp = list(data.keys())
        co2_val = [val[0] for val in list(data.values())]
        temp_val = [val[1] for val in list(data.values())]

        env_data = {
            "co2_val" : co2_val,
            "temp_val" : temp_val
        }

        return timestamp, env_data


def create_image_tensor(netatmo_module):
    last_timestamp = netatmo_module.get_latest_timestamp()
    start_timestamp = netatmo_module.get_start_timestamp(last_timestamp)
    duration = int(last_timestamp) - int(start_timestamp)

    print("Timestamp : {} - {}, {} mins".format(start_timestamp, last_timestamp, duration/60))

    ts, env_data = netatmo_module.get_data(start_timestamp, last_timestamp, mtype="CO2,Temperature")

    co2 = env_data["co2_val"]
    for idx, value in enumerate(co2):
        if value is None:
            co2[idx] = 0
    temp = env_data["temp_val"]

    folder = "created_images"

    if not os.path.exists(folder):
        os.mkdir(folder)

    img_co2_name = "{}/CO2_image.jpg".format(folder)
    img_temp_name = "{}/Temperature_image.jpg".format(folder)
    img_combine_name = "{}/Combine_image.jpg".format(folder)

    # create CO2 images
    fig = plt.figure(figsize=(50,20), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    plt.ylim([0, 2500])
    plt.fill_between(ts, co2)
    fig.savefig(img_co2_name)
    plt.cla()
    fig.clf()
    plt.close("all")

    # create Temperature images
    fig = plt.figure(figsize=(50,20), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    plt.ylim([0, 40])
    plt.fill_between(ts, temp)
    fig.savefig(img_temp_name)
    plt.cla()
    fig.clf()
    plt.close("all")

    # combine CO2 and Temperature images
    img_co2 = cv2.imread(img_co2_name)
    os.remove(img_co2_name)
    img_temp = cv2.imread(img_temp_name)
    os.remove(img_temp_name)
    img_combine = cv2.vconcat([img_co2, img_temp])
    cv2.imwrite(img_combine_name, img_combine)

    # create trasformed image tensor
    img_transforms = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])
    img = Image.open(img_combine_name)
    os.remove(img_combine_name)
    img_tensor = img_transforms(img).unsqueeze(0)

    data = {
        "ts" : ts,
        "co2" : co2,
        "temp" : temp
    }

    return img_tensor, data
