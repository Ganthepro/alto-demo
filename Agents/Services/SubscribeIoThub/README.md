<details>
<summary>custom_event</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/RL4zQyGm3DtzAuJ7q1BwjGHQZblA3LbkBSKuYP8O4ZkrvGmzxhzNJaARWthHqvEUq9CFWRIdE0v2J0nCRIPj2VHtzAYC8zN72dG0XenkUaAicBsXPZSGUMTL5KDIpHo5MBLm_xP9e829ype6SgF26Iq9wmXXm9R463fuXOi0a6VyYXZerCW2vCFZq_EBl4iykSdKYTkFM4kw9kCirpuuI--onVJaqgX-vQtnWVA0jRDDthhegPTR-vNZvpAnvyq6LRi6a-JuVZwLfVohB6JdpJX2gOsLuYhGDf3yYCqk6q-7M6qNa6NxjRCi_sUD_Jqm1DrXkibkj3Wmv6_x0G00)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub custom_event
note left
msg = {
  "RequestId": "12345",
  "topic": "custom_event",
  "action": [
      {
          "event_topic": "first/second/fourth"
      }
  ],
  "hotel_code": "BGRIMM",
  "hotel": "Bgrimm Main"
}
end note
subiot -> vbus : pub: **custom_event**/first/second/fourth
note left
message = {}
end note

@enduml
```

</details>


<details>
<summary>manage_agent</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/ZL7BQiCm4BphAnPV32R5f8-BeINNNli3GbRNZa0FLre5qf9_xyeFS4xjGNWykxCx6fqIgKZPMI4c1aQRINa2zPqZIXD8ddCFAW53HdSzAVVCtb6NO8bYyBBFgQWk_1LYqSB3sog13YR-Tygh4IKVJy87Gh0ua71fX5Vu4G3L1tvbJFJ-MNLG7H-Vdb-gG-4fJ4ONRZzYASrGcbbXpO3wgYqkfQJFw5GfJ5RH4A9R9PfCyCoNdMMwYYFIEhJRwZA6i0YuHGV7gykI5K7RrebjrGUevqHhRho9cq2kbRk9zUeSGWbbYQ23fjcyD4sxUT-7WIanlGNobxL_6TkP4YU6vV5_0G00)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub manage_agent
note left
msg = {
  "RequestId": "12345",
  "topic": "manage_agent",
  "agent_id": "lifecycle",
  "schema": "platform",
  "action": {
    "target_agent": "action_room",
    "command": command //'stop', 'start'
  }
}
end note
subiot -> vbus : pub: **platform**/agent_id
note left
message = {
  "target_agent": "action_room",
  "command": command //'stop', 'start'
}
end note

@enduml
```

</details>


<details>
<summary>human_feedback!</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/LP7BJiCm44Nt_efHs1OrXT96bK25IZos2DQH7KzQ2ziJsKw5YlXtnYIbT9NhcNEjv6GTamofTrQ8ZeDfJ2Tz0dde0zQ6Khth5SW873cTCR5NF3qRxScc5CZNge-vjUUd44CNBk_62goWu_EkTzBNBQ9MilaGdXA2nJO95xTm2ry2e4ZKcQPOGN4E5vEy_3ln_eq8dYaL4xY0CKz-muQiph3gZTN6RpFyy1ICSypcnO4yvk6Z9GemWqr0cSmUuJwWb_1AT2IjyVYYC_jUBNLvLStrGYshwxPgbPhBjbAwl2cLdE5YR1pVS6ZDoqKXlWLw3VbZnMY3lMHFWvKL15it508sQJe0K_oKhhCuRSYn1FtV5COejyYssDdfOh7coF_q1m00)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub human_feedback
note left
msg = {
  "topic": "human_feedback",
  "feedback": "Too Hot", # Too Hot, Too Cold
  "building": "BGrimm", 
  "zone": "Floor 1 Creative Arena Room", 
  "lineId": "U87d0284d6b783f8fbb4af8bd050ba1e6", 
  "feedbackId": "406"
}
end note
subiot -> vbus : pub: rl_correct/subiot/example/command
note left
message = msg
end note

@enduml
```

</details>

> **NOTE:** pls change
from: rl_correct/subiot/example/command
to: rl_correct/rl_correction/example/command
because
/command have to identify the target agent
/event have to identify the source agent


<details>
<summary>custom_action</summary>

> **NOTE:** this diagram is not complete yet

![PlantUML model](https://www.planttext.com/api/plantuml/svg/TP112uCm38Nl-HMXvmtlmeR_fDIkke8snQGY6_llYoYC7dRAooFVUv2EnIrIvWaWguW-PfS4tQiimKOI-omzEaQLggeRBhswbRNI9B9GidtXdLfr0XmiNkydWYrctNrXeTawBv4I99A0KnW4PXxnXcz0D48vUjEYgMxD1JuGqWDt1ivCJT_RZkmMFQKXZat5DNyR0xCRWxPks_PBXawblkOB)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub custom_action
note left
msg = {
  "topic": "custom_action",
}
end note
subiot -> vbus : pub: config/custom_action/custom_action
note left
message = xxx
end note

@enduml
```

</details>


<details>
<summary>devicecontrol</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/TLDDJyCm3BtdLrWvWxRn8Q5Ae04IY0CNZY1KfQdNHchYagG3CUs_uz2EjGDwIUBt73llkSiGbO-TROHeUMEqQPMBe3uxZxcXcDTT0Ie0RtatuOIkuEWajAOcHaykBxgGijQy2j7dml7La08Pj7mkSMqqQdASqGX74Q71LHGsL7096m40Cb9hjCpaX2kFlZ6beo4divTqucyph0dh-RafELVfVD6d3A2gqCKUAvIUrskb9pXt-PF_8RFvtvXJ5lc6Q-FXbbnfKZF6LJ2jvOdiZdhN47bOm3CvFA1fibOvxcZqYEzo6FE8jaMl8ZiYivEBeod3KfdkrhJJPG-j5AiZQrFLSWzi9w_HDLgLI4c30TYczRNN-0dVEWpn8McrE3azEn-qhzcj9jTzxPlxnt4uHIflh9LYAz2LaAmLW_Ky16ae-X788DMTxKoO9QTcWnJZWS0GsBEVeVXFbDzQZ2Ne0u4whnFf7OjTwC3kSTTYoLl-Exu0)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub devicecontrol
note left
msg = {
   "topic":"devicecontrol",
   "action":[
      {
         "device_id":"ac_1",
         "agent_id":"bac0hvac",
         "subdevice_idx":0,
         "subdevice_name":"Air Conditioning 1",
         "room_name":"Floor 1 Zone 1",
         "command":{
            "set_temperature":28,
            "mode":"cool",
            "fan":"high"
         },
         "schema":"hvac"
      }
   ],
   "RequestId":"12345",
   "hotel_code":"BGM",
   "hotel":"Bgrimm"
}
end note
subiot -> vbus : pub: hvac/bac0hvac/ac_1/command
note left
message = {
   "set_temperature":28,
   "mode":"cool",
   "fan":"high",
   "source":"web",
   "subdevice_idx":0
}
end note

@enduml
```

</details>


<details>
<summary>automation</summary>
<blockquote>

<details>
<summary>add time trigger</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/xLVTQzim47_tNo7qEDeuJLjA3HjTopRsK2YqJnl5oFBLrY9BdZwITYF_-qwMdTYXUrrX90-9T7UwxxiVkRAE6USRcIGj7WGNBLEEi5_UG2wqosjV46O97l4qaR6-GEg4jDBIEQDLNdWRNgtmDqdYMtByeNz2Cj86hTxfXZcXLQAq0oBXoIMDhSXxyZiXTCVEHSCge1cbHrEwOaqWZoWb4qkXSivv9-kCg2emD4E5-1dkkNjfmqFBQoYzX20xOOkWDxu9T8uXqUpxS0-anQ9_rD_FBwVtTzFhwPxqll1mU-mEcuHiWljSgrA4kBO1R2avh42vFYTJpef9tsMhry9uL17ztqLLmafmB78PKiZpnSX7YlbMBh8AnkVrYl4H5ykuVVnCi_bhdBus7uKXDuDhGbLaOiPetGoIdwNMXYp8Dws0N8o4k6uQfifHGJfBu787JGk6EUnLcYtE1_Pcv0zMk66elOiW6N7_deUpVvE7ixVEGq8Uk_QGKgzpd43n93YBhUACXy2RKliUx8WlkTEZaQ1hA4QkeYqXHtSf54IhZqSx9TkvhfrhRPQcw_LwjcHMBBLH1LFB6OQSkZh5BO8Ah4rj0-c3Rk-CBZrtwPqlfB0rflDhq6JJXzetXKBR-Vtjfni3cEvxZrapw6uz-z5MT6o-GPNH0QuN19uvG4bEZkRpEMdRPY8gU4Z0MpagbCMAy74LOaCeXyEzrn1ThZDwnQJJrhUjDcwwRM9nSFj5PYVeWDSp1Ow-qZkL5-L-bUAUnR1d6BK54rhz68pHvfZh4b9scawcRQXtCCYwlSKDZW9dSX9elvVZw0pxgqRlP1xK8klwootT4VkHkQwCQBg2qOevMBENRcHFneHUjEX4qK34aWxc9Wi0aw4yhvWfGQsnO279Hijzw0d2bnTd7SZeLl093D5aau0gIO2rfCSyHB-0XX7xCiBQDesBsHccRDfzI-QqIGtyz63T61HZenw0yG2C1s0y0EC160_0-1y0OtA5H_pd-GS0)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub automation
note left
msg = {
 "automation_image":"",
 "automation_name":"automation_daikin_ccc",
 "trigger":{
    "trigger_type":"schedule",
    "trigger_time":{
       "cron":[
          "22",
          "59",
          "*",
          "3",
          "5",
          "*"
       ]
    }
 },
 "condition":{
    "condition_event":"",
    "condition_value":""
 },
 "action":[
    {
       "device_id":"ac_23",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 23",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    },
    {
       "device_id":"ac_24",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 24",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    }
 ],
 "allow_notification":true,
 "notification":{
    "notify_to":[
       "web",
       "email",
       "line"
    ],
    "noti_image":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_message":"co2 exceed 1,000 ppm",
    "noti_icon":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_instruction":{
       "contact":{
          "line":"@altosupport",
          "email":"support@altotech.net"
       },
       "guide":"https://www.daikin.co.th/service-error-code/a3/"
    },
    "noti_important":"critical",
    "noti_type":"device"
 },
 "hotel_code":"BGM",
 "hotel_name":"Bgrimm",
 "gateway_id":1,
 "gateway_name":"bgrimmdev",
 "azure_device_id":"altonucgardenwingcontrol",
 "automation_id":974,
 "topic":"automation"
}
end note
subiot -> vbus : pub: app/actiontrans/translator/request
note left
message = {
 "automation_image":"",
 "automation_name":"automation_daikin_ccc",
 "trigger":{
    "trigger_type":"schedule",
    "trigger_time":{
       "cron":[
          "22",
          "59",
          "*",
          "3",
          "5",
          "*"
       ]
    }
 },
 "condition":{
    "condition_event":"",
    "condition_value":""
 },
 "action":[
    {
       "device_id":"ac_23",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 23",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    },
    {
       "device_id":"ac_24",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 24",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    }
 ],
 "allow_notification":true,
 "notification":{
    "notify_to":[
       "web",
       "email",
       "line"
    ],
    "noti_image":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_message":"co2 exceed 1,000 ppm",
    "noti_icon":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_instruction":{
       "contact":{
          "line":"@altosupport",
          "email":"support@altotech.net"
       },
       "guide":"https://www.daikin.co.th/service-error-code/a3/"
    },
    "noti_important":"critical",
    "noti_type":"device"
 },
 "hotel_code":"BGM",
 "hotel_name":"Bgrimm",
 "gateway_id":1,
 "gateway_name":"bgrimmdev",
 "azure_device_id":"altonucgardenwingcontrol",
 "automation_id":974,
 "topic":"automation"
}
end note

@enduml
```

</details>

<details>
<summary>add device trigger</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/xLSxRzim4DxrAmWDdH8hTf8c5j8YJT3N4210FBK818gwIAmfKk73hblal_SeqRPak1swPB47c_hku_5u3ttmjR5KMrUBA6fmmHblgBI4_d8QCgviLhcSK4DmYQi1nxWSqG6qKC9QhMIME-DtBV0tYhgzvFXzs49IqdYlpggQMgva99K58k39HhKfoJloEoBnrfpncfOGft5yDCGbhJtSGmhAvrncZB6MQpKlIz1nYWxnitxExAhn6mjOS0QUsJS6DEpnbWx9U85x89-Um1GkON9smHZDBmktQ9w33q_6KANjkDQjQ6QXRZ2BDI9R4YPYu_Hdd9xiiuJRpT09cQ6JDr-y4pAUzlnefUeryPDGIfC9-QOaaF4koGTq-dOBmWB3x5sopG2U0ffQhFtGuerNSJgUzh2NzVgb5poheAOOYm5fb8wZGFIKc2bPS5-bJJasI1QY2L4TxPeNLBYs0O8hoZe_trlY_a9HbarEzzSbf-oaMb3sVmNvm3MvNOV6PKa6n_or8XSz4bDrJMMnatu3DXkKO7B-hnotDrXd-B5DYn1gcU4myIVEQ9SYgnrusn0D1MZ1LMRLEfKUN4BU2nNFugBtBBY4xjJ7ewsJpOXMrZOcJPBbSZcQKyFdIikSola8hvpOAi4N0Zem9Z4r93FLt6jLE6QJUvSBRYfCvrVloIGp79bSujdPmzt7MmsOxWU7MTCORZNwqPHn__WQNNO1z198hiZaZDmEY9pvwxzMc5mQh0Vhro0qkiMMtcc7DjDfV4s5LSOrZT9sMuTjQN3OEcDBjC2gaGGRx-cSql5YjqRT2nElFS9R6z2-qOz1QwMFcIeWeQT9wB5XjVs1j1rPfd4G61M3YuONB1FA5UkXhJ0uaNclQBdvV1TlmJ0lDwNcTTtY9RMmfAjsNiTz853pbeg3sMb2ArU3wSTSICTAgWkGIwoNpx5MObT2F7bwSTwAXMeu6yX97Br480lYvIaAseKgvbMjqx2KqAP9khUHrLIQfFqMr2gTQ7XsO6nVtBekFGZSGU1sp0U1EmZSGU0E0lUQ0XTTunB_2Vu1)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub automation
note left
msg = {
 "automation_image":"",
 "automation_name":"automation_daikin_ccc",
 "trigger":{
    "trigger_type":"device",
    "trigger_device":{
       "device_id":"eb90e9e8e247ccab8duvpq",
       "agent_id":"tuya_temp_humid",
       "subdevice_idx":0,
       "subdevice_name":"Tuya Temp&Humid 19",
       "room_name":"Floor 2 Zone 1",
       "room_id":36,
       "event":{
          "temperature":{
             "<":19
          }
       },
       "schema":"sensor"
    }
 },
 "condition":{
    "condition_event":"event",
    "condition_value":""
 },
 "action":[
    {
       "device_id":"ac_23",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 23",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    }
 ],
 "allow_notification":true,
 "notification":{
    "notify_to":[
       "web",
       "email",
       "line"
    ],
    "noti_image":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_message":"temperature < 24 C",
    "noti_icon":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_instruction":{
       "contact":{
          "line":"@altosupport",
          "email":"support@altotech.net"
       },
       "guide":"https://www.daikin.co.th/service-error-code/a3/"
    },
    "noti_important":"critical",
    "noti_type":"cloud"
 },
 "hotel_code":"BGM",
 "hotel_name":"Bgrimm",
 "gateway_id":1,
 "gateway_name":"bgrimmdev",
 "azure_device_id":"altonucgardenwingcontrol",
 "automation_id":975,
 "topic":"automation"
}
end note
subiot -> vbus : pub: app/actiontrans/translator/request
note left
message = {
 "automation_image":"",
 "automation_name":"automation_daikin_ccc",
 "trigger":{
    "trigger_type":"device",
    "trigger_device":{
       "device_id":"eb90e9e8e247ccab8duvpq",
       "agent_id":"tuya_temp_humid",
       "subdevice_idx":0,
       "subdevice_name":"Tuya Temp&Humid 19",
       "room_name":"Floor 2 Zone 1",
       "room_id":36,
       "event":{
          "temperature":{
             "<":19
          }
       },
       "schema":"sensor"
    }
 },
 "condition":{
    "condition_event":"event",
    "condition_value":""
 },
 "action":[
    {
       "device_id":"ac_23",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 23",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    }
 ],
 "allow_notification":true,
 "notification":{
    "notify_to":[
       "web",
       "email",
       "line"
    ],
    "noti_image":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_message":"temperature < 24 C",
    "noti_icon":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_instruction":{
       "contact":{
          "line":"@altosupport",
          "email":"support@altotech.net"
       },
       "guide":"https://www.daikin.co.th/service-error-code/a3/"
    },
    "noti_important":"critical",
    "noti_type":"cloud"
 },
 "hotel_code":"BGM",
 "hotel_name":"Bgrimm",
 "gateway_id":1,
 "gateway_name":"bgrimmdev",
 "azure_device_id":"altonucgardenwingcontrol",
 "automation_id":975,
 "topic":"automation"
}
end note

@enduml
```

</details>

<details>
<summary>delete automation</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/rP91IWGn44NtTOeYQsLM8ZOeWnjNda0af9EQJ22TD4cb1SMxM-aUcHblO3Rv_Fpwr8FiAvl2ROe0iuXWmsmIe_biXNJ8h8zjH5DHfAYhJ6sZk5VMaYDpoKcFhVQfHMw0RHPldquZEE3SMnldoN38oL4a9aYP2ICT6ARgyH6_014LvpbODQY_SNMpFfzj7PmQthefv-7-hgltBNIKvgXjTYH5po-lwj9EPbfjNy8q_RQk_8wMO6djLIPoJirwKnobZv2ypKbGeu9leEImBmydFY7jv1ldW98y1ByxRxeJ0brQf7h9JBKQJ_-I6_OYvHFz0000)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub automationdelete
note left
msg = {
   "topic":"automationdelete",
   "automation_id":[
      975
   ],
   "hotel_code":"BGM",
   "hotel_name":"Bgrimm",
   "azure_device_id":"altonucgardenwingcontrol"
}
end note
subiot -> vbus : pub: config/automation/del_rules
note left
message = {
   "topic":"automationdelete",
   "automation_id":[
      975
   ],
   "hotel_code":"BGM",
   "hotel_name":"Bgrimm",
   "azure_device_id":"altonucgardenwingcontrol"
}
end note

@enduml
```

</details>

<details>
<summary>add event trigger</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/xLTDRzim3BtxLmWwjt6ROYjcO4FNOXjsA52WFMqh35bMR2twy2GgMJVqlvUIxSGEUjyEIG17VgGewf5yGAuyC0T1gophS26vx9W1mlu49qffeMn3HPWdkCJLpCU72j4PjB4Am5bJLi77NHlypR9-BpdzC6mX1UbYr01MCv3MPCQ284gi8DE-8U_9tupGlRcKcZM25fIUp773T8GdY9O6X4f-u6JJ24SB38QVyRs4fovk4XjX83fERJqux8Y6bNH-2aJC2svDFGTJa5OwXEdA1WSjdLYViza2dyynmnX6nhHtEUwGCHFw0xzZbdlhXgaWHkiGZV4-rFValBz2BJQIOorZQeoNouiXNBGXhGPwKyNuMRjXV6B5Qkqs_wR5sMkMeGGVfICtOthID6HsZBDMZvwVbRMEBCatQmIvd3XngpKxv1N9XXA4xeHZW2r9Y-MR7PcJV7WhDCFewGOZoO-95gNijiG6aol9MK_HYYaled4E3qL8u5C9TkGoWbjHJNB5mwIQl2jfH7_iuya-oAvlMu3E5tc-tMuNQ-RbsZfJCRDUu9rpQ7ES4WpWVUwro1ziT-Ti7JZaTw5IqhV8vzSOoUSFRT2LmRFB-zjFDquWt_S1QNEORhlusJLqUhp6a7q2gG3BitCYFK6g-BgKPkOgUIJWNoKgZGSN-BGAGxy3TlL1HoIk2th555WVkiuws5TYNvo23iRa28At2oE0lj8yJP3rOPLg9jVIuBKNU6ilNEprK-6STQVSrY9d5_dGPlDwnmDP6bpkS1OuKxEB3jg32Q9C6MQu6AUtnHHL6MEZ_VhBBTs3m-1SDqvgdV26WTYofpIuvrDWSAsIAqveBvX9osSoW8oOm1lcQc6sMBN8jBFgK5-ZyxlBjqbDRIVvJ6jfzfm9KvEetTaWx2ZnKV9xWIy8wxgyboLmpFWyFHK3wt8dVWNXOQhyVRSUrV-e_XEoZ-f_LF-Z-l_dwfzTuHB_Gxm0)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub automation
note left
msg = {
 "automation_image":"",
 "automation_name":"automation_mintel",
 "trigger":{
    "trigger_type":"event",
    "trigger_event":{
       "first":{
          "second":{
             "third":"fourth"
          }
       }
    }
 },
 "condition":{
    "condition_event":"\"\"",
    "condition_value":"\"\""
 },
 "action":[
    {
       "device_id":"ac_23",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 23",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    }
 ],
 "allow_notification":false,
 "notification":{
    "notify_to":[
       "web",
       "email",
       "line"
    ],
    "noti_image":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_message":"room_201 is check_in",
    "noti_icon":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_instruction":{
       "contact":{
          "line":"@altosupport",
          "email":"support@altotech.net"
       },
       "guide":"https://www.daikin.co.th/service-error-code/a3/"
    },
    "noti_important":"critical",
    "noti_type":"maintenance"
 },
 "hotel_code":"BGM",
 "hotel_name":"Bgrimm",
 "gateway_id":1,
 "gateway_name":"bgrimmdev",
 "azure_device_id":"altonucgardenwingcontrol",
 "automation_id":976,
 "topic":"automation"
}
end note
subiot -> vbus : pub: app/actiontrans/translator/request
note left
message = {
 "automation_image":"",
 "automation_name":"automation_mintel",
 "trigger":{
    "trigger_type":"event",
    "trigger_event":{
       "first":{
          "second":{
             "third":"fourth"
          }
       }
    }
 },
 "condition":{
    "condition_event":"\"\"",
    "condition_value":"\"\""
 },
 "action":[
    {
       "device_id":"ac_23",
       "agent_id":"bac0hvac",
       "subdevice_idx":0,
       "subdevice_name":"Air Conditioning 23",
       "room_name":"Floor 2 Zone 7",
       "command":{
          "set_temperature":25
       },
       "schema":"hvac"
    }
 ],
 "allow_notification":false,
 "notification":{
    "notify_to":[
       "web",
       "email",
       "line"
    ],
    "noti_image":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_message":"room_201 is check_in",
    "noti_icon":"https://www.kasikornbank.com/th/business/sme/TopProduct/PublishingImages/Thumbnail_SMECreditSummary_th.jpg",
    "noti_instruction":{
       "contact":{
          "line":"@altosupport",
          "email":"support@altotech.net"
       },
       "guide":"https://www.daikin.co.th/service-error-code/a3/"
    },
    "noti_important":"critical",
    "noti_type":"maintenance"
 },
 "hotel_code":"BGM",
 "hotel_name":"Bgrimm",
 "gateway_id":1,
 "gateway_name":"bgrimmdev",
 "azure_device_id":"altonucgardenwingcontrol",
 "automation_id":976,
 "topic":"automation"
}
end note

@enduml
```

</details>

</blockquote>
</details>


<details>
<summary>guest checkin, checkout, and room transfer</summary>
<blockquote>

<details>
<summary>guestcheckin</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/TLHjJzim4Fwy_0hBNqSWRwKaqYPOaL0bQD48seTfgfp4RImIEoJd8eRuxxkybCOjYwhcVCzpEP_Fzrmsm6hGPM5P5HeY5HMJGDXVNVELKB3ATK9OGz14o-0qEa6luTgg0g1MSfNefetQujko-bXYVnz2I4GgN6yqRo3DUVeaf2KLS5BmDLXbio7Vo9j52A6WAf7IY8wfzAI3hXam6lrkRNpUXdUBpAzfvBiJTteoSlxagQgpUKOZDvm6hW4fLIuKPWdSW1u2yMl54Nful3UWMRkNkKJ4SppFTWBR3MCtY1m7VyVCfOOHrNDYr_k4UizLLM0sR-oyodG11xvPBWgin35uoHezfuRlfbQwcgcihS38zA2ImVsB5KzaBWtqfZtjjl214nyKnAJanIx-wjOyCmQxiDdopZoq7qfX_pRzaHejc2a9B8K5A_TxMXYn2x79uI2gAs-8EIxWLZImlo3zysQikfFWp-PNnv_ehelZ-k5_y25tZ2QPAw37j9dI4kfN92qXv_KdZ0K3eIGh1BIiE6U26fpt_UhFyOL-00QweT7K6h5x7ZAUTqNGq6FhPEtvjk_uYHruwSGEdOiBcuSXdwRy8Zjtis6mSfp4OfNsFRpRjM5moxxYEo5nDKOEdRs0P7mhKjIHTWkIlx02bDHfsH5Jx7cjTdpevwmRzBwenoh3kpJ0kk7raBkFPbdv8GM8RNaTYmxUpoDntIXmeidvgUDFN3_uwam_9kwJeQThKJSWzoqTt0NxyBOzjjujBZFIwfKro1aAMojqlQpXNzcSzPiygp7B2ZESTTgrCdMEDmtRy4xhlj2EG2D2iQfn2kiIJPJdVm00)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub guestcheckin
note left
msg = {
   "topic":"guestcheckin",
   "Data":[
      {
         "ID":31517,
         "RecordId":19741,
         "RoomNo":"414",
         "RoomType":"SUP",
         "CheckIn":"2022-04-19T14:00:00",
         "CheckOut":"2022-04-20T12:00:00",
         "People":2,
         "Adult":2,
         "Child":0,
         "Abf":0.0,
         "GroupCode":"",
         "SobCode":"Walk In",
         "GuestTypeCode":"T",
         "ChannelCode":"WAL",
         "RateCode":"COMP",
         "BookingType":1,
         "ContactName":"Walk IN",
         "Night":1,
         "GroupName":"",
         "GuestList":[
            {
               "Seq":1,
               "GuestId":10139,
               "GuestName":"Test Iot",
               "Country":"Other",
               "Nationality":"Thai"
            }
         ],
         "RecordStatus":7
      }
   ],
   "RequestId":"92afbf23-303b-42c5-9088-e99e7ce8d61d",
   "hotel_code":"MIN",
   "hotel_name":"Mintel",
   "hotel":"Mintel",
   "azure_device_id":"newaltonucmintelcontrol",
   "type":"guestStatusUpdate",
   "username":"minteladmin",
   "serverTime":"2022-04-19 11:40:56.035134+07:00",
   "RoomNo":"414",
   "firstname":"Test",
   "lastname":"Iot"
}
end note
subiot -> vbus : pub: pms/mintel/room_414/check_in
note left
message = {
	"check": "in"
}
end note

@enduml
```

</details>

<details>
<summary>guestcheckout</summary>

![PlantUML model](https://www.planttext.com/api/plantuml/svg/TLHHRvim47uUlyBowqeBX8G4QLExL9eYjKcrfjh3D4K6t62Ls1JEcRgg_trdS9euwL0KplTzn_bylk-o1TQ0tbIULwCXSb4p2OJzrGrV2GMhKcU4jGHDj1nEgpFqEgwjgW0Q9LUPRatK5j-UrySI_wiD8IcfSRtMl8MyvFcJqk191PnK_16yJRicNyYhHmYXe6gHqvGwN7hMOTSC64r_6HkVL_isoEoQfeDm64Ld1yuVF5TDCIje6awIE7GWfJPpXMdYCAR7mFAbvWZTFzmvqDHiPYOHYO8eyeFO3oVBC4w307-dp0LkswL67r3lkAehpEPi_AhG5HpvfgMei9B0uMMFw3btVDyRfUkfAam5JgPxbLdtJrOz4Ip42JF7RGgtdELHGKnANktYhsxSCsEm2vikRjr3-wRKav3h_aYT5aoL19R3d6tsUvexiNEnBk4egYlFnfmMS2DQs5-G_dbrLjr9y6VtguUVwAvB40uc_y5jxYMQPAQ0djAcIajeNf2qW98t7p3c38IIh19WMCkI2UfmtlQhtwSN-XuOw9QcO--0tVEGyRmhWYQ3d6KvI_mepWe_BfBC7u_7p1_nOfGKeo0S3knTf2MEOhNA-nxUxjfWtRAl-5P8N1qYnyvUGWg-5JagYTc2v7zO1KhgVDCHS-nvetPywEUic_I-g8UwmBjaOTtonkRkerc1RmiYjkNDKdJmViX86AR398sYyybm74n6duFaVU8-67hwA9eMvBwbrbsnTw_fiVVcSLaG8rYU5JIKDYDrlR3XtwQzw3TvqM2M5MQuwCHhTQHql6tPcdTgzubs39eIQYJkC8btYIPAz3y0)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub guestcheckout
note left
msg = {
   "topic":"guestcheckout",
   "Data":[
      {
         "ID":31522,
         "RecordId":19741,
         "RoomNo":"414",
         "RoomType":"SUP",
         "CheckIn":"2022-04-19T14:00:00",
         "CheckOut":"2022-04-19T12:00:00",
         "People":2,
         "Adult":2,
         "Child":0,
         "Abf":0.0,
         "GroupCode":"",
         "SobCode":"Walk In",
         "GuestTypeCode":"T",
         "ChannelCode":"WAL",
         "RateCode":"COMP",
         "BookingType":1,
         "ContactName":"Walk IN",
         "Night":1,
         "GroupName":"",
         "GuestList":[
            {
               "Seq":1,
               "GuestId":10139,
               "GuestName":"Test Iot",
               "Country":"Other",
               "Nationality":"Thai"
            }
         ],
         "RecordStatus":8
      }
   ],
   "RequestId":"73cabca7-24bd-4d7b-888a-6ed67d601530",
   "hotel_code":"MIN",
   "hotel_name":"Mintel",
   "hotel":"Mintel",
   "azure_device_id":"newaltonucmintelcontrol",
   "type":"guestStatusUpdate",
   "username":"minteladmin",
   "serverTime":"2022-04-19 11:57:22.958096+07:00",
   "RoomNo":"414",
   "firstname":"Test",
   "lastname":"Iot"
}
end note
subiot -> vbus : pub: pms/mintel/room_414/check_out
note left
message = {
	"check": "out"
}
end note

@enduml
```

</details>

<details>
<summary>normal room transfer</summary>

> **NOTE:** pls check why "RoomNo" is not appear in "Data->0"

![PlantUML model](https://www.planttext.com/api/plantuml/svg/xPNHQjim58QlgwSGkfv9v3ckOzWeR6pa8bb9tAjHZ6AV9gQMv5foIbVwxZsoFOZQZ6wxhX7MaVx_I4VM1xumLhIsapKX3GPLKJL2MIf-TItabRRvljjIOIY667aUqsrnrfiwwDhQLgjysncNTS2Ua26N1f_759hI1iUx3emjzb3SwiuIfItG6cuiaMP7Fz57GYbbLZTLmLBcUTc7Nligh63fJnVZypZsJibQeLOQqzRBR8hFR7u-v8pwvi5Oa9WFw0cdOHXCeu3FCnwc8K-Zo3D_QxLSQotx1ID-MimU6hVMvkhIax-xibT2EYt3a2wqzGnVt94M2cKiamTzmvBJlhrs_i33lstDz56zyGdf3zMkGOhs5WMBfR9HU7BzzV35rt3d3hGeqGDb8iA89y7v36w2A88uI3xE8U09Jn8-Y-TybemNjSUhhVD2bsxJvMBbJQlXwomhXQDZvUNaW6G9Xwf0Cbq92kv5RRNg2jaR2wqGljz-xyx84m5LKWSP6I5471sU0upuacOoB3DfCJF7h4aFNFw2JZ16xA0dz8pr3fPIvh0ytkHjw2lrrynNwXtvT-J_2Vdulv2FH-HzDayJZr1wm5zWYF-HPm00)

```
@startuml

participant azure_iot_hub as iothub
participant subiot
participant volttron_bus as vbus

iothub -> subiot : pub guestcheckout
note left
msg = {
   "topic":"guestcheckout",
   "Data":[
      {
         "TranNo":"RMT0000597",
         "SystemDate":"2022-04-19T12:21:44",
         "FromRoomNo":"414",
         "FromRoomType":"SUP",
         "GuestName":"Test Iot",
         "CheckIn":"0001-01-01T00:00:00",
         "CheckOut":"0001-01-01T00:00:00",
         "ToRoomNo":"416",
         "ToRoomType":"SUP",
         "Remark":"test"
      }
   ],
   "RequestId":"ed8a2418-75ef-44e6-839e-181881569158",
   "hotel_code":"MIN",
   "hotel_name":"Mintel",
   "hotel":"Mintel",
   "azure_device_id":"newaltonucmintelcontrol",
   "RoomNo":"414"
}
end note
subiot -> vbus : pub: pms/mintel/room_414/check_out
note left
message = {
	"check": "out"
}
end note

iothub -> subiot : pub guestcheckin
note left
msg = {
   "topic":"guestcheckin",
   "Data":[
      {
         "TranNo":"RMT0000597",
         "SystemDate":"2022-04-19T12:21:44",
         "FromRoomNo":"414",
         "FromRoomType":"SUP",
         "GuestName":"Test Iot",
         "CheckIn":"0001-01-01T00:00:00",
         "CheckOut":"0001-01-01T00:00:00",
         "ToRoomNo":"416",
         "ToRoomType":"SUP",
         "Remark":"test"
      }
   ],
   "RequestId":"ed8a2418-75ef-44e6-839e-181881569158",
   "hotel_code":"MIN",
   "hotel_name":"Mintel",
   "hotel":"Mintel",
   "azure_device_id":"newaltonucmintelcontrol",
   "RoomNo":"416"
}
end note
subiot -> vbus : pub: pms/mintel/room_416/check_in
note left
message = {
	"check": "in"
}
end note

@enduml
```

</details>

</blockquote>
</details>

