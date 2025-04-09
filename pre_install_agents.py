import os
import yaml
import argparse

AGENT_NAME_TO_PATH = {
    "bacnet": "Devices/BACnet",
    "platform_agent": "Platforms/PlatformAgent", 
    "load_forecast": "Applications/LoadForecastAgent",
    "firebase": "Services/Firebase",
    "chillerplantoptimization": "Services/ChillerPlantOptimization",
    "mongodb": "Services/MongoDB",
    "afdd": "Applications/AFDD",
    "weathertmd": "Services/WeatherTMD",
    "weatherforecast": "Services/WeatherForecast",
    "chiller_prediction": "Services/ChillerPrediction",
    "timescaledb": "Services/TimescaleDB",
    "dataintegrity": "Services/DataIntegrity",
    "azureiothub": "Services/AzureIoTHub",
    "gatewaystatus": "Services/GatewayStatus",
    "ahu": "Devices/AHU",
    "chilleraddsubtract": "Applications/ChillerAddSubtract",
    "chillerplantschedule": "Applications/ChillerPlantSchedule",
    "chillersequence": "Applications/ChillerSequence",
    "schpcontrol": "Applications/SCHPControl",
    "linenotification": "Services/LineNotification",
    "uihelper": "Applications/UIHelper",
    "smartct": "Applications/SmartCT",
    "supabase": "Services/Supabase",
    "controlschedule": "Applications/ControlSchedule",
    "mockbacnet": "Devices/MockBACnet",
}

if __name__ == "__main__":
    #Set up argparse to accept the site_id and site_config_dir arguments
    parser = argparse.ArgumentParser(description='Install Volttron agents with specified configuration.')
    parser.add_argument('site_id', type=str, help='Id of the site configuration to use.')
    parser.add_argument('--site_config_dir', type=str, default=os.getcwd(),
                      help='Directory containing site config files (default: current directory)')

    # Parse the arguments and load config file
    args = parser.parse_args()
    SITE_ID = args.site_id
    SITE_CONFIG_DIR = args.site_config_dir
    SITE_CONFIG_PATH = os.path.join(SITE_CONFIG_DIR, f"{SITE_ID}.yaml")
    
    if not os.path.exists(SITE_CONFIG_PATH):
        print(f"Error: Site config file not found at {SITE_CONFIG_PATH}")
        exit(1)
        
    site_config = yaml.safe_load(open(SITE_CONFIG_PATH, 'r'))

    print(f"Installing Volttron agents with config: {SITE_CONFIG_PATH}")

    # Iterate over the agent_list and install each agent
    installed_agents = site_config['deployment_config']['installed_agents']
    agents_config = site_config['volttron_agents']

    with open("./platform_config.yml", 'r') as f:
        config_data = yaml.safe_load(f)
        
    # print(config_data)
    agents = config_data.setdefault('agents', {})

    for agent_name, enabled in installed_agents.items():
        agent_name = agent_name.upper().replace('AGENT', '-AGENT')
        if enabled:
            print(f"✅ {agent_name}")
        else:
            print(f"❌ {agent_name}")

    for agent_name, enabled in installed_agents.items():
        if not enabled:
            print(f"Skipping {agent_name} because it is not enabled....")
            continue

        agent_path = AGENT_NAME_TO_PATH.get(agent_name, None)
        if agent_path is None:
            print(f"Agent {agent_name} not found in AGENT_NAME_TO_PATH")
            continue
        
        agents[agent_name] = {
            'source': f"$VOLTTRON_ROOT/Agents/{agent_path}",
            'config': f"$VOLTTRON_ROOT/site_configs/{SITE_ID}.yaml",
            'tag': agent_name
        }
    
    with open("./platform_config.yml", 'w') as f:
        yaml.dump(config_data, f)
    
