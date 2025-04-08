# **TuyaLocalSwitch**
## Description
An agent that monitor and control Tuya Wifi Switch. This Agent use `tinytuya` python library to get state and set command.

# **Config**
key | description | type |
---|---|---|
agent_name | agent identity | string |
topic | prefix topic of the message | string |
sampling_rate | interval rate of getting status | integer |
devices* | device id and prop of device data | dict |

> **Noted*: In devices key of this config contain dict of device_id and list of data of:
- device type
- number of subdevices
- ip_address of device
- local key of device

**Example config**
```JSON
{
    "agent_name": "tuya_switch",
    "topic": "",
    "sampling_rate": 10,
    "devices": {
        "device_id": [
            "tuya_switch",
            1, // number_subdevices
            "ip_address",
            "local_key",
            "device_name"
        ]
    }
}
```

# **Diagram**
## Monitor
![PlantUML model](https://www.planttext.com/api/plantuml/svg/PLBBJiD03BplLrWvWzfA850aK95uNE02lKURn4bNoZxOTTf6Y7_7cwJjLboYU6OyzZXP1vAUUjq9GOewXASM3S67DOgiLwQ5PoLRBxKGZeMgKauol-a7-MuhsNtj5LLRa072lf2nzvykbLoGdzRgQHnpdeiBzbLvB6N0I3Qb4E8u0AuVsIa7Zzyz1e8MgU0Kr0TXB25urMufXvU3r8u3hU1DSemmRi4cK_ja5Ks2iuQdf0uTDYJWp3t03vS0MUr2bi_52AoutFWUhyxG7KFBf5xTC91frDOFMOhVHjpPa6Bt4Sjcu5TCJpGrnBqkBX3lbOFhoqw5BMWCWQda0DnBrgcAby-cx0lYZr7CxpNk2bKlSCTsSTvia4J5dQgGDN6ZIJrlduM-FB67Sze4Dr9Zx9kGOddgv2EFX3L7Y0Ot8XuxESHDahmnOypQb34fnwmbIOu5pVnl2B5cCV-zVm00)

```plantuml
@startuml

title Agent Monitoring Diagram

participant TuyaLocalSwitch as sw_agent
participant TuyaSwitch as sw
participant RoomAgent as room
participant Firebase as fb


sw_agent -> sw: request get_status
note right: Example 1 Gang switch
sw -> sw_agent: response status
note left
  response = {
    "dps": {
        "1": True,
        "7": 0,
        "14": "memory",
        "15": "pos,
        "18": ""
      }
    }
end note
sw_agent -> room: publish message
note right
  topic = "switch/tuya_switch/dev_id/event"
  message = {
    "device_id": "dev_id",
    "subdevice_idx": 0,
    "subdevice_name": "subdev_0",
    "state": "on",
    "type": "relay"
  }
end note
room -> fb: push data to firebase

@enduml
```

## Web Control
![PlantUML model](https://www.planttext.com/api/plantuml/svg/PP71JiCm38RlVWg_02_G0zg4X43YnX17vARU5gcDI-nGZQV78IhRc9HB_7-sFyaRDSfMfX70eesCktAY5maqlYxHmX4V95cM4RyYuS8zK339-AQS4MPlZI7Eb0pVFRlyRxzBvcVPFPKUIJ6A7SiryN-JKxfyq86JtN2No5Nu63Ftf5oZVG_mAtPtNtKwt0QBaj1VDVTIJPf9Xyffm8bLVIEQO7E55bTmbRb53sIyq0bXHHhUOURFmcgAGQQ9qk306ZMNly8wEhFEajp_t74UkNVDCW--3VrCnW0RD_5Z_G00)

```plantuml
@startuml

title TuyaLocalSwitch Control via web
actor User 
participant Web
participant AzureIoTHub as iothub
participant TuyaLocalSwitch as sw_agent
participant TuyaSwitch as sw
participant Firebase as fb

User -> Web: Action on web
Web -> iothub: send message to IoTHub
iothub -> sw_agent: send message to gateway 
sw_agent -> sw: requests command
sw -> sw: Action
sw -> sw_agent: response command
sw_agent -> fb: update state

@enduml
```

## Mannual Control
![Plant UML](https://www.planttext.com/api/plantuml/svg/PP1B3i8m34JtFeKlm0MwG9MGMC4AM2CtTI5IceJOQSNjIQdAHrs_D-EHQr5Acdi7e5OTupa_wH0CkTDerTnn5xocu72mX3rvJza16Gq9By898PQuDJQIrrMM16MyqeszhhnVvG_kRUA6X2VKDG3lCvjjqIeybW6Pt38AblQ59tva5YsTIfgby9dCriGb1b-wF_oRxveASsn9Pye0DVksVEO5)

```plantuml
@startuml

title TuyaLocalSwitch Control via mannaul
actor User 
participant TuyaLocalSwitch as sw_agent
participant TuyaSwitch as sw
participant Firebase as fb

User -> sw: Mannual Control
sw_agent -> sw: requests status
sw -> sw_agent: response status
sw_agent -> fb: update state

@enduml
```