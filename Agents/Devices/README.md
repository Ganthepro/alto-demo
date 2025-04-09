#### Device Data Flow Summary

![PlantUML model](https://www.planttext.com/api/plantuml/svg/fPTVRvim5CNV-HIyxQbgBlbVJLDJbccJbcfBelLnSk0kiKemjKssIllmjGCi6CUQX9-mxZc-nxRCZ-HUIC9bUSo2GZrfGWkIot3vHoBFIRP1Vg89XaI4A0B3ieYVw2UwI4cXhDgGWgbJViAKd9N8K1uMSOxoyuz5V1Q7XXWV2D_ZOezghDMHeNx4WgoNc-rP6XlIb-tgCcjYIAlls-qZ9VcUy6ezKrDcwQuKbyapGtr4IUIHFI6HXtgZSyEm9UB89BdCXu6fbwyapbYPnYMNXEQL1opFCZ-rUaIM_fKb97l8Q9vMZk5rXsfJwIEdliQCl5QcyNNJjwpSLuR9TSFcDvN9eR9CBSiA_zs9cILkMFACihLLypZhWxxeaNcSXFA4gViZrDL4FPISPIqtcDTqpTXH2rmzWm15-Fv6HOPt8SUN4eKCKoA9hjzyQEgov7bLLWLLrbELe2kXP0LDxWJcWl5RebD_qlGsHVsMw16ULAc9YHmnKJScyeePEcA6tPXXxvYcNS9EthtqaaUE9O-wInvvnOmTCUDkpDWhPkA8cNHZ9lrYtjKvKqUEhXVbxgyeTrNRNrn575-a37USFICFbCLdWpD7yAoxmPbNpDmHC-_6pFtE4GQkzt_m_vDK7fyzWfCzDdpyw0Ck_8357_034BW811Q2m8yRu087MEG0FtI0YnrWmGFyw04kV8353-W9a2R91P1QQ2Vv0GDSn00B6U3737110ongG4ziD5zp5pLgeVqzzsD4v694P34Ywi-8LaCLSovNk6j-OVNl7jnZdkh_56y0)


```
@startuml
participant ExternalService as es

participant ACWiFiAdapter as d1
participant Airveda as d2
participant BACnetHVAC as d3
participant ChargeAgent as d4
participant DepaREST as d5
participant ITMAgent as d6
participant MQTTNiangara as d7
participant ModbusAgent as d8
participant NetatmoWeather as d9
participant TasmotaAgent as d10
participant TuyaCloudCurtain as d11
participant TuyaEnvAgent as d12
participant TuyaLocalBlind as d13
participant TuyaLocalEnv as d14
participant TuyaLocalEnvRelay as d15
participant TuyaLocalPlug as d16
participant TuyaLocalSwitch as d17
participant TuyaMeter as d18
participant TuyaSocketAgent as d19
participant WeatherAgent as d20
participant airconetservercontrolAgent as d21

participant Room as room

es <- d1 : request data
es -> d1 : return data
d1 -> room : data topic:sensor/agent_id/device_id/event
es <- d2 : request data
es -> d2 : return data
d2 -> room : data topic:sensor/agent_id/device_id/event
es <- d3 : request data
es -> d3 : return data
d3 -> room : data topic:sensor/agent_id/device_id/event
es -> d3 : cov data
d3 -> room : data topic:sensor/agent_id/device_id/event
es <- d4 : request data
es -> d4 : return data
d4 -> room : data topic:sensor/agent_id/device_id/event
es <- d5 : request data
es -> d5 : return data
d5 -> room : data topic:sensor/agent_id/device_id/event
es <- d6 : request data
es -> d6 : return data
d6 -> room : data topic:sensor/agent_id/device_id/event
'es <- d7 : request data
es -> d7 : pub|sub data from mqtt broker
d7 -> room : data topic:sensor/agent_id/device_id/event
es <- d8 : request data
es -> d8 : return data
d8 -> room : data topic:sensor/agent_id/device_id/event
es <- d9 : request data
es -> d9 : return data
d9 -> room : data topic:sensor/agent_id/device_id/event
'es <- d10 : request data
es -> d10 : pub|sub data from mqtt broker
d10 -> room : data topic:sensor/agent_id/device_id/event
es <- d11 : request data
es -> d11 : return data
d11 -> room : data topic:sensor/agent_id/device_id/event
es <- d12 : request data
es -> d12 : return data
d12 -> room : data topic:sensor/agent_id/device_id/event
es <- d13 : request data
es -> d13 : return data
d13 -> room : data topic:sensor/agent_id/device_id/event
es <- d14 : request data
es -> d14 : return data
d14 -> room : data topic:sensor/agent_id/device_id/event
es <- d15 : request data
es -> d15 : return data
d15 -> room : data topic:sensor/agent_id/device_id/event
es <- d16 : request data
es -> d16 : return data
d16 -> room : data topic:sensor/agent_id/device_id/event
es <- d17 : request data
es -> d17 : return data
d17 -> room : data topic:sensor/agent_id/device_id/event
es <- d18 : request data
es -> d18 : return data
d18 -> room : data topic:sensor/agent_id/device_id/event
es <- d19 : request data
es -> d19 : return data
d19 -> room : data topic:sensor/agent_id/device_id/event
es <- d20 : request data
es -> d20 : return data
d20 -> room : data topic:sensor/agent_id/device_id/event
es <- d21 : request data
es -> d21 : return data
d21 -> room : data topic:sensor/agent_id/device_id/event
es -> d21 : rest event from airconet
d21 -> room : data topic:sensor/agent_id/device_id/event

@enduml

```