# Activity Diagram

# Sequence Diagram

![Mermiad Image](https://mermaid.ink/img/pako:eNqNk9FO4zAQRX9l5Kddif2BPCCldGGRyi6klfoSCTnOtLVIPFnbASrEv-_YTpsuKRJ-STI-d3Rzx34TimoUmXD4t0ejcK7l1sq2NMCrk9ZrpTtpPCyK9eNP8wzSwYIKuc5_A39qS6ZF3l6icWTPy27Wp6ob6fFF7qfo3cNqFcD4rCw9oYVvDSnZfD_fNx_a5tw2WMu37GSKFgksiNpPiPu-0uQDxG-NdrtbWv3qqyl4PXtsaLtlY8xea4uVdLiIlXPwKTXdv7qbR-KKXEtuPitNYg5J_7i8HOLLjuHdW_KkqHEjmkcwhJbBsq-csrpC8JRynMUcR5pnEfCBH373LB0LBw95BgUqjc9YQy29hI2lNiIfjQz0hmwrPbxov4O84f5_luDUDlv5UVAE_GAk9D4mFSfH0jSeVA6rGJSpnkFe1xDOiddkQJoautRtVAwDDqKQegYOGePWadBRxKk2qDxoczKRIA6bg5Pj_Kdmjltf8TOeoyQdDR2OC3SWXvdR3XecCufOxv4_TCwRF6JFTlrXfIffQrkUnlPGUmT8WuNG9o0vRWneGZW9p-XeKJF52-OFSJ2HKy-yjWwcvv8DKYVQ3w?type=png)

```text
sequenceDiagram
    participant LRW_Env as LoRaWAN Environment Sensor
    participant LRW_GW as LoRaWAN Gateway
    participant MQTT as MQTT broker (local)
    participant LRW_A as LoRAWANEnv Agent
    participant R_A as RoomAgent
    participant Pubiot as PublishIoTHub
    participant FB_logger as FirebaseLogger
    participant FB as Firebase
    participant CMDB as CosmosDB

    LRW_Env ->> LRW_GW: LoRaWAN Protocols
    LRW_A ->> MQTT: Subscribe to MQTT Broker
    LRW_GW ->>  MQTT: Publish to MQTT Broker
    MQTT ->> LRW_A: Recieved data from MQTT
    LRW_A ->> LRW_A: format with Alto OS schema
    LRW_A ->> R_A: Publish data
    par R_A to Pubiot
        R_A ->> Pubiot: Add location and publish
        Pubiot ->> CMDB: send to IoTHub and collect in CosmosDB
    and R_A to FB_logger
        R_A ->> FB_logger: Add location and publish
        FB_logger ->> FB: send to Firebase proxy and updated in Firebase
    end
```

# Configuration format

