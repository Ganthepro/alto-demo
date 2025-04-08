import logging
from azure.eventhub import EventHubConsumerClient

from threading import Thread


def _azrec_thread():
    connection_str = 'Endpoint=sb://iothub-ns-betaiothub-13344990-073ef16d21.servicebus.windows.net/;SharedAccessKeyName=iothubowner;SharedAccessKey=9tv4A3cJpTzvy77f1WaLPxSRd8mMuLYN2Nd8f7nprFI=;EntityPath=betaiothubprod'
    # consumer_group = '<< CONSUMER GROUP >>'
    eventhub_name = 'betaiothubprod'
    client = EventHubConsumerClient.from_connection_string(connection_str, "$default")

    partition_ids = client.get_partition_ids()

    # connection_str = '<< CONNECTION STRING FOR THE EVENT HUBS NAMESPACE >>'
    # consumer_group = '<< CONSUMER GROUP >>'
    # eventhub_name = '<< NAME OF THE EVENT HUB >>'
    # client = EventHubConsumerClient.from_connection_string(connection_str, consumer_group, eventhub_name=eventhub_name)

    logger = logging.getLogger("azure.eventhub")
    logging.basicConfig(level=logging.INFO)

    def on_event(partition_context, event):
        logger.info("Received event from partition {}".format(partition_context.partition_id))
        logger.info("Event {}".format(event.body_as_json()["gatewayid"]))
        partition_context.update_checkpoint(event)

    try:
        with client:
            client.receive(
                on_event=on_event,
                starting_position="-1",  # "-1" is from the beginning of the partition.
            )
            # receive events from specified partition:
            # client.receive(on_event=on_event, partition_id='0')
    except KeyboardInterrupt:
        return

azrec_thread = Thread(target=_azrec_thread)
azrec_thread.setDaemon(True)
azrec_thread.start()

while True:
    pass
