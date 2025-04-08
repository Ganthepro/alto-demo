#!/bin/bash
my_dir="$(dirname "$0")"
source "$my_dir/rooms_header.sh"

for dev_id in "${arr[@]}" ; do
    echo $dev_id
    /home/alto/alto_os-brown/scripts/install-agent.py -s Agents/Room -i $room_id_prefix$rnumber -t $room_id_prefix$rnumber --enable --start
    sleep 1
    cat /home/alto/alto_os-brown/Agents/Room/$config_template | sed "s/atmo_device_id/$dev_id/g" | sed "s/Nnumber/$rnumber/g" | sed "s/^M//g" > /tmp/tbd
    vctl config store $room_id_prefix$rnumber config /tmp/tbd
    sleep 1
    ((rnumber++))
done