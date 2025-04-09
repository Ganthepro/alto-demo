#### Data Flow

![PlantUML model](https://www.planttext.com/api/plantuml/svg/RPD1JuGm48Nl_8e9TxDwzM0MIOm7JvheaGobkpP2fsdBhlhhVGNMjIuNsipttj2-WMs8xECuz4NXi37AEBQHtdHB7EYeswnyp-f3sowXLcVaPMoDn0G2rWoLbV5KY-rCD6ArBvEAkxnnLLiT7r-hEi6EC_WiCgIonvg11-Droq4_oNwlVPBisZvJx1P5uxnyViqAjwgOMORSxvtS_plnz-XrWshpFav9CTQYG5vqTOTiw9Qy3f6K30CZi2WKHsz9B5Lr0GvL2WewF5CFl2nJPuP92al7C1oaZz43_BMy7rXjMbRNquPLSxDPK04JhDp16jBmZjv4JUMvVKbZC7PFi6C8XAYYAEalZ5vZpuhmoKHTO7yw4QxgnAOCLw2Imxa-jqo31D63YJIw3c314u00OrpbgJvX1-maN60tuzE9LvkxEVVBxcv9ESqo7qmcAxPeZJ_c1m00)

```
@startuml

participant Web as web
participant Backend as be
participant Subiot as siot
participant "Air Conditioner" as ad
participant BACnetHVAC as da
participant Room as room
participant FirebaseLogger as fbl
participant firebase_proxy as fbp
participant firebase as fb
participant pubiot as piot
participant azure_iot_hub as ahub

web -> be : rest command to turn on AC
be -> siot : iothub pub command to to turn on AC
siot -> da : volttron pub command hvac/bac0hvac/ac_1/command
da -> ad : send write "turn on AC" using bacnet protocol
da -> ad : send read ac state
ad -> da : response ac state
ad -> da : cov ac state
da -> room : emit update state
room -> fbl : emit update state
fbl -> fbp : post update state
fbp -> fb : send update state
room -> piot : emit update state
piot -> ahub : iothub pub update state

@enduml
```


#### Class Diagram

![PlantUML model](https://www.planttext.com/api/plantuml/svg/VP913i8W44NtSufUWCG362Eb9kwRk4SwQT4AoHIxyl1QcnQe4tV3V_E7uOVZ43I5vwC7yDSRcb3iNq8KiW--mj4QX5X6TBv8zGVNw0PFIKCgnBQJ6orvDqFuKUR6IjkxTLKfLGtvrJndHgWEfpDhJnbdrKGMIIhUl5AGBReak-yHrceR3KUcuPnUacrQZ0FJzKfjTjsepReT8oV-3LsAGeX3bcC6beHoCRxyYAxv_9yt)


```
@startuml

object <|-- AltoDevice
AltoDevice <|-- AltoHVACDevice
AltoDevice <|-- AltoSensorDevice
AltoSensorDevice <|-- AltoEnvironSensor
AltoEnvironSensor <|-- DaikinDBACS
AltoHVACDevice <|-- DaikinDBACS
AltoEnvironSensor <|-- ChenSen
AltoHVACDevice <|-- ChenSen
AltoEnvironSensor <|-- CarrierAC
AltoHVACDevice <|-- CarrierAC

Agent <|-- AltoAgent
AltoAgent <|-- AltoSensor
AltoAgent <|-- AltoHVAC
AltoAgent <|-- AltoBridgeAgent
AltoSensor <|-- Bac0hvac
AltoHVAC <|-- Bac0hvac
AltoBridgeAgent <|-- Bac0hvac
Bac0hvac --> DaikinDBACS
Bac0hvac --> ChenSen
Bac0hvac --> CarrierAC

@enduml
```
