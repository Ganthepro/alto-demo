#!/bin/bash
declare -a arr=("03:00:00:0a:b9:46" "70:ee:50:3d:19:e8" "03:00:00:0b:08:90" "03:00:00:0a:b7:3a" "70:ee:50:3d:14:9c" "03:00:00:04:55:42" "03:00:00:0a:b7:e6" "70:ee:50:3d:1d:c0" "03:00:00:0a:b9:5e" "03:00:00:0a:b9:70")

rnumber=1
for dev_id in "${arr[@]}" ; do
    echo $dev_id
    /home/alto/alto_os-brown/scripts/install-agent.py -s Agents/Room -i room_$rnumber -t room_$rnumber --enable --start
    sleep 1
    cat /home/alto/alto_os-brown/Agents/Room/config_rooms | sed "s/atmo_device_id/$dev_id/g" | sed "s/Nnumber/$rnumber/g" | sed "s/^M//g" > /tmp/tbd
    vctl config store room_$rnumber config /tmp/tbd
    sleep 1
    ((rnumber++))
done