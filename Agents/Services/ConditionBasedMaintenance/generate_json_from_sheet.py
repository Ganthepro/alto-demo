import requests
import pandas as pd
from io import StringIO
import json


def read_google_sheet(doc_id):
    # URL for CSV format (replace 'xxxx' with your document ID)
    url = f'https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv'

    # Send HTTP GET request and fetch the data
    response = requests.get(url)

    # Check the response status code to see if the request was successful
    if response.status_code == 200:
        # Content of the response, in bytes
        data = response.content

        # Convert bytes to string
        csv_data = data.decode('utf-8')

        # Convert string to DataFrame
        df = pd.read_csv(StringIO(csv_data), names=['device_id', 'datapoint_name', 'condition', 'name', 'operation', 'value', 'period', 'between_start', 'between_end'])[1:]
        df.fillna(inplace=True, method='ffill')
        # Remove NA rows
        df.dropna(inplace=True)

    else:
        df = None
        print(f'Error: {response.status_code}')

    return df


def convert_to_json(sheet_records):
    output = {"condition_based_config": {}}

    for index, record in sheet_records.iterrows():
        device_id = record["device_id"]
        datapoint_name = record["datapoint_name"]
        condition = record["condition"]
        name = record["name"]
        operation = record["operation"]
        value = float(record["value"])
        period = int(record["period"])
        between_start = int(record["between_start"])
        between_end = int(record["between_end"])

        device = output["condition_based_config"].setdefault(device_id, {})
        datapoint = device.setdefault(datapoint_name, [])

        # Find existing condition dictionaries if any exists for the given datapoint and operation
        existing_conditions = [cond for cond in datapoint if all(k in cond for k in ['alert', 'alarm', 'critical']) and cond['alert'].get('operation') == operation]

        if existing_conditions:
            # Add the new condition to the existing dictionaries
            for existing_condition in existing_conditions:
                existing_condition[condition] = {
                    "name": name,
                    "operation": operation,
                    "value": value,
                    "period": period,
                    "between": [between_start, between_end]
                }
        else:
            # Create a new condition dictionary and add it to the list
            new_condition = {
                "alert": {},
                "alarm": {},
                "critical": {}
            }
            new_condition[condition] = {
                "name": name,
                "operation": operation,
                "value": value,
                "period": period,
                "between": [between_start, between_end]
            }
            datapoint.append(new_condition)

    return output


# Replace this with the ID of your Google Sheet
google_sheet_id = '16OL6IqtU88ZSwb_3X5u-GkPFSSMMv2okIb7PMpMtFig'

# Read data from the Google Sheet
sheet_records = read_google_sheet(google_sheet_id)

# Convert the data to JSON
output_json = convert_to_json(sheet_records)

# Convert dictionary to JSON
json_data = json.dumps(dict(output_json), indent=4)

# Write the JSON data to file
with open('test_generate_config.json', 'w') as f:
    f.write(json_data)
