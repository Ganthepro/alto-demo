from azure.eventhub import EventHubConsumerClient

## initialize IOTHub event message client
connection_str = 'Endpoint=sb://iothub-ns-betaiothub-13344990-073ef16d21.servicebus.windows.net/;SharedAccessKeyName=iothubowner;SharedAccessKey=9tv4A3cJpTzvy77f1WaLPxSRd8mMuLYN2Nd8f7nprFI=;EntityPath=betaiothubprod'
# consumer_group = '<< CONSUMER GROUP >>'
eventhub_name = 'betaiothubprod'
client = EventHubConsumerClient.from_connection_string(connection_str, "$default")


## function that will trigger everytime that recieve message
def on_event(partition_context, event):
    # logger.info("Received event from partition {}".format(partition_context.partition_id))
    # logger.info("Event {}".format(event.body_as_json()["gatewayid"]))
    # partition_context.update_checkpoint(event)
    event_data = event.body_as_json()
    device_id = event_data.get('device_id')
    if not device_id.startswith('beta_ev_tower_'):
        print(event_data)


## set the start index of each partitions
partition_0_prop = client.get_partition_properties("0")
partition_1_prop = client.get_partition_properties("1")
print(partition_0_prop)
print(partition_1_prop)
starting_position = {
    "0": partition_0_prop["last_enqueued_sequence_number"] - 3,
    "1": partition_1_prop["last_enqueued_sequence_number"] - 3
}

## start the event listener
with client:
    client.receive(
        partition_id="0",
        on_event=on_event,
        starting_position=starting_position,  # "-1" is from the beginning of the partition.
    )
