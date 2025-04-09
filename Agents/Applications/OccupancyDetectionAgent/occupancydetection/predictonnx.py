import json
import logging
import os
import time
from datetime import datetime

import numpy as np  # we're going to use numpy to process input and output data
import onnxruntime  # to inference ONNX models, we use the ONNX Runtime

import pyrebase

from occupancy_utils import NetatmoData, create_image_tensor

# config firebase
config = {
  "apiKey": "AIzaSyAK836vY2NsAmAzfn1D3P6HbSbJLjTrWCM",
  "authDomain": "altohotel-b6ae5.firebaseapp.com",
  "databaseURL": "https://altohotel-b6ae5.firebaseio.com",
  "projectId": "altohotel-b6ae5",
  "storageBucket": "altohotel-b6ae5.appspot.com",
  "messagingSenderId": "599435241073",
  "appId": "1:599435241073:web:669288fd44d337f8f05dd0",
  "measurementId": "G-BH74T9JDCH"
}
firebase = pyrebase.initialize_app(config)
db = firebase.database()

# Netatmo configuration
device_id = '70:ee:50:19:bf:64'
config = {'client_id': '60af4d6f19d0d726b31fec6f',
          'client_secret': 'Mo5zu4eJjg86rCeSOxWfQd9Kr',
          'username': 'thakorn.swa@gmail.com',
          'password': 'EypNetatmo_123',
          'device': device_id
}
module = NetatmoData(config)

def load_labels(path):
  with open(path) as f:
      data = json.load(f)
  return np.asarray(data)

# Run the model on the backend
d=os.path.dirname(os.path.abspath(__file__))
modelfile=os.path.join(d , 'HumanNet.onnx')
labelfile=os.path.join(d , 'labels.json')

session = onnxruntime.InferenceSession(modelfile, None)
labels = load_labels(labelfile)

def predict_image_from_url():
  # get current generated image data from Netatmo
  img_tensor, data = create_image_tensor(module)
  latest_co2 = data["co2"][-1]
  latest_temp = data["temp"][-1]
  latest_ts = data["ts"][-1]

  # get the name of the first input of the model
  input_name = session.get_inputs()[0].name  

  # ONNX inference
  start = time.time()
  res = session.run([], {input_name: img_tensor.numpy()})
  end = time.time()

  res_new = res[0][0][0]

  inference_time = np.round((end - start) * 1000, 2)
  idx = int(np.round(res_new))

  response = {
    'created': datetime.utcnow().isoformat(),
    'prediction': labels[idx],
    'latency': inference_time,
    'confidence': res_new,
    'latest_co2' : latest_co2,
    'latest_temp' : latest_temp,
    'latest_ts' : latest_ts
  }
  
  dict_data = {
    'datetime': datetime.utcfromtimestamp(int(latest_ts)).strftime('%Y-%m-%d %H:%M:%S'),
    'prediction': res_new,
    'label': labels[idx],
    'latest_co2' : latest_co2,
    'latest_temp' : latest_temp,
    'latest_ts' : latest_ts
  }
  db.child("building").child("daikin").child("building_main").child("solutionplaza").child("CO2HumanPresence").update(dict_data)

  logging.info(f'returning {response}')
  return response

if __name__ == '__main__':
    print(predict_image_from_url())
