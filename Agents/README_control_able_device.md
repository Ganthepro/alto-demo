#### Command-able Agents Overview

![PlantUML model](https://www.planttext.com/api/plantuml/svg/pPNVRjCm5CRl_HHMk86BmGjKqvgCmgHD6hG2YPlg93rBhJa-nN-s5SIxOsVf6jifN89LLOb_NuuTv_li2sD1MzT9Pkw5se66ZZk39LfOshr4RhL3DZFX-fnntzvs-z8P_hE_2Mr1obOaIVDIUcte-iLcxuP7M2F9RJZyS1hNWbRhhQk7lZkXiGQ31ucq9CZMqDoZsZ2ciR6WMZ-7uWDOV8HzmL_rTOR1-x-Zwb1klTFqj4zWets9JRqsbZIqo19SB54_Y0Rvl4LbZH_8orIBezU4G7WLwboMIUzY6FgQsXPr0czTBONPNj4gl7hCFXDrITVIrQRHeiR91rPQF0YG_JI7fNvPYkyE7V8EZV7QTUq_4XXUyF-rNQaxqXrOGOg_Vsgs_Ne7Qxt-XfhupQSt_twE9renvR_Y4cCBxK1Ygn5Lvg9vzLKin7m3EvlPfPnN2kt7B_CgjTuMT8l7BtyaLwkRgUuLc8uiJ2AtXogahdBQWb0J-9eQaAKKFeeduArqxIcsV1IssKxG9VbuswavWT0D-LStFeeOBgscoEZC_-9DWf-TdITR2ulYncT1COe46mASWpZ3EVzBtP3al3S9SouOvpcdR1pcdiREoV38F1aR-oU3BnRAIEIYdAP6cbICl7IQztOwZGT7JGh6fie4V_0LIuw5OQ66FJu-K9vPijCV906c1r3aoruGdmGn3yNJhPzTU8_xi_at)

```

@startuml
skinparam useBetaStyle true
<style>
    .myBus {
        FontColor Blue
    }
</style>

cloud azure_ioT_hub
cloud firebase
cloud altoiotbackend

rectangle "Gateway" #azure {
    
    rectangle firebase_proxy
    rectangle cratedb_storage

    rectangle "Service Agents" #orange {
        agent CrateDB
        agent FirebaseLogger
        agent PublishIoThub
        agent Room
        agent SubscribeIoThub
        agent TrivialAgent
    }
    
    queue message_bus as "                                                                                                                                                         Information Exchange Bus (Zero MQ)                                                                                                                                                         "
    
    rectangle "Device Agents" #palegreen {
        agent ACWiFiAdapter
        agent BACnetHVAC
        agent ChargeAgent
        agent ITMAgent
        agent TasmotaAgent
        agent TuyaCloudCurtain
        agent TuyaLocalBlind
        agent TuyaLocalPlug
        agent TuyaLocalSwitch
        agent TuyaSocketAgent
        agent airconetservercontrolAgent
    }

}

altoiotbackend --> azure_ioT_hub

PublishIoThub <--> message_bus
CrateDB <--> message_bus
FirebaseLogger <--> message_bus
PublishIoThub <--> message_bus
Room <--> message_bus
SubscribeIoThub <--> message_bus
TrivialAgent <--> message_bus

message_bus <--> ACWiFiAdapter
message_bus <--> BACnetHVAC
message_bus <--> ChargeAgent
message_bus <--> ITMAgent
message_bus <--> TasmotaAgent
message_bus <--> TuyaCloudCurtain
message_bus <--> TuyaLocalBlind
message_bus <--> TuyaLocalPlug
message_bus <--> TuyaLocalSwitch
message_bus <--> TuyaSocketAgent
message_bus <--> airconetservercontrolAgent

cratedb_storage <--> CrateDB
firebase_proxy <--> FirebaseLogger
firebase <-- firebase_proxy
azure_ioT_hub <-- PublishIoThub
azure_ioT_hub --> SubscribeIoThub

@enduml

```

#### Command-able Agents General Flow

**control from web**
![PlantUML model](https://www.planttext.com/api/plantuml/svg/VPDBJyCm48Jl_XKMTzGx1zGYn8aJ73X66tlRMYInvKTv_7fcxHJ9jE8IM_lDJkpPP9ionLpcIQc0ZJCkq9Br6u-QalxWiIi_a7ddnGeQkIElPNG-2qXOEtIpCxdGf1_vv0pVY8PifsXaT-2bEbZgw8ltivGZrWuykSWZ9NxsXmD7aUp7gLFiLyKGel_yQefmLT5OXyBlbSBVAz5tYJoWEXnB3OgmAeMuzEqzej5tEdBAslXv9kILFRPBZdxIjjvLGGEbP0KjdkA35_xJKRNeiOIEavyouDBr97FacJOaEGxERbgZx5Q5GYySoC8XrJcsoPmD90YhuRhMcu56UDaRFoaqdW-0wmM_83TyFxcarLb61CYpoxe4IxbnLXL0W05TvLAlE007dovmQFXyyAlceQLvwHxMw6HAVToTJ6rXBR_23m00)

```

@startuml

participant Web as web
participant Backend as be
participant Subiot as siot
participant "Actual Device" as ad
participant DeviceAgent as da
participant Room as room
participant FirebaseLogger as fbl
participant firebase_proxy as fbp
participant firebase as fb
participant pubiot as piot
participant azure_iot_hub as ahub

web -> be : rest command to control device
be -> siot : iothub pub command to control device
siot -> da : volttron pub command schema/agent_id/device_id/command
da -> ad : send actual command based on actual device protocol
ad -> da : response status
da -> room : emit update state
room -> fbl : emit update state
fbl -> fbp : post update state
fbp -> fb : send update state
room -> piot : emit update state
piot -> ahub : iothub pub update state

@enduml


```

**control from trivial agent**
![PlantUML model](https://www.planttext.com/api/plantuml/svg/RP8zQyGm38Pt_mfnUxdzXd87fLEdqZqejYzdS2BZZt3jhwza9mNJJ9Brl7gHb5nJnfZBx9KAd3Zj0YuPlg9R7VhRPFc12J9s-7JJkQ27DxiwRK-YGDCf6ldhDtt_9z4ivSYn0-yksX6J_Q1fib4azz5tYlkc64AavtTJX4D5OnqAPNHK1meSEuG_9Tg1gyEZZ7KXZafbX9TN7Xyki9BFET8YBg1fdd4naFJ3pdX6MNHmvcpgtf9j2cMg0nfsI9Oxi9rkDv193R3hLcy6mDjbqkGLD-u3H9i2BRmOVxDSqkOiDsHePvUX18EvSQigO05Vy91BlUB0E53wXqF3--27vdB7G_SAP74vvmNu9OcShfEfArlBx_SB)

```

@startuml

participant TrivialAgent as ta
participant "Actual Device" as ad
participant DeviceAgent as da
participant Room as room
participant FirebaseLogger as fbl
participant firebase_proxy as fbp
participant firebase as fb
participant pubiot as piot
participant azure_iot_hub as ahub

ta -> da : volttron pub command schema/agent_id/device_id/command
da -> ad : send actual command based on actual device protocol
ad -> da : response status
da -> room : emit update state
room -> fbl : emit update state
fbl -> fbp : post update state
fbp -> fb : send update state
room -> piot : emit update state
piot -> ahub : iothub pub update state

@enduml

```
