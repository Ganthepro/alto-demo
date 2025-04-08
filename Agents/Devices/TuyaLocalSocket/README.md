#### Data Flow

![PlantUML model](https://www.planttext.com/api/plantuml/svg/TPDBJyCm48Jl_XLMxgXt3gX2Y5DF58bZvCHkQk74Mp_wuDSpwmHKqtA9e_rcn_Piiev9XPH79mJXnVQMr9JaX-caYl9akghyhFfFCsb6dQd8DdVM9mOHQuMQztnHyiKSRMyQLYXTSSORtoktzN0l7bfLYZVlHou7h1LujS5qAfgD7mOJMBBhNANOBOgMWZzVPWNTLSoiGlHxAVfxAVMLWsbHRVUvHAMm2e70vCCJmf6FCfYOPE_7KI6nv6NAOP9-akJo8A20ZhE24azsmNR_wQKeKhHeXOQZToa5PbSjyMHJlrybnDawphFbpfKvgv6SQNKPG6lrQcaGi8AXqkMiXyp7RQutRMIETXhAW2JoIxxtJa3_SmpSaFo4wCeHyIKbivZof20meqqoamPOS04GO4vtETSB9c3oyGRJZ44ZVubtpMcEzTQTbX1vM7NkbKoiOOr_uXi0)

```plantuml
@startuml

participant Web as web
participant Backend as be
participant Subiot as siot
participant "Tuya Device" as ad
participant TuyaLocalSocket as da
participant Room as room
participant FirebaseLogger as fbl
participant firebase_proxy as fbp
participant firebase as fb
participant pubiot as piot
participant azure_iot_hub as ahub

web -> be : rest command to turn on plug
be -> siot : iothub pub command to turn on plug 
siot -> da : volttron pub command switch/tuya_local_plug/example_device_id/command
da -> ad : request "turn on plug" using Tuya protocol
ad -> da : response plug state
da -> room : emit update state
room -> fbl : emit update state
fbl -> fbp : post update state
fbp -> fb : send update state
room -> piot : emit update state
piot -> ahub : iothub pub update state

@enduml
```


#### Class Diagram

![PlantUML model](https://www.planttext.com/api/plantuml/svg/VP9H2W8X48RVFOKNy0OHkr7lGLt0tC4iKz2n23fyoqevYVasl_ytplpY4546J3VBc3zTG25VlOJWeqM_XRjHm4fPhCF3e3ht073H1mBGWuBjx3mn69NT3fWrmNuxCtXCJxctINyyLdTsC9he3yP63OwypoBPjwh3DvrbIilP13DfA5SINTQnNaaRlRe2agKxVfMQ-fNcGgmRaGTmq_mvtW00)


```plantuml
@startuml

object <|-- AltoDevice
AltoDevice <|-- AltoSwitchDevice
AltoDevice <|-- AltoSensorDevice
AltoSensorDevice <|-- AltoElectricSensor
AltoSensorDevice <|-- AltoDeviceSensor
AltoElectricSensor <|-- TuyaPlugElectric
AltoDeviceSensor <|-- TuyaPlugElectric
AltoSwitchDevice <|-- TuyaPlugElectric

Agent <|-- AltoAgent
AltoAgent <|-- AltoSensor
AltoAgent <|-- AltoSwitch
AltoAgent <|-- AltoBridgeAgent
AltoBridgeAgent <|-- Tuyalocalsocket
AltoSwitch <|-- Tuyalocalsocket
AltoSensor <|-- Tuyalocalsocket
Tuyalocalsocket --> TuyaPlugElectric

@enduml
```
