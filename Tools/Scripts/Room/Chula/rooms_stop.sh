#!/bin/bash
my_dir="$(dirname "$0")"
source "$my_dir/rooms_header.sh"

for dev_id in "${arr[@]}" ; do
    echo $dev_id
    vctl stop --tag $room_id_prefix$rnumber
    sleep 1
    ((rnumber++))
done