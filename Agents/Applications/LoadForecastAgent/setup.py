from setuptools import setup, find_packages

MAIN_MODULE = 'agent'

# Find the agent package that contains the main module
packages = find_packages('.')
agent_package = 'load_forecast'

# Find the version number from the main module
agent_module = agent_package + '.' + MAIN_MODULE
_temp = __import__(agent_module, globals(), locals(), ['__version__'], 0)
__version__ = _temp.__version__

# Setup
setup(
    name=agent_package + 'agent',
    version=__version__,
    author="Voramet Chunvattananon",
    author_email="voramet.c@altotech.ai",
    install_requires=['volttron'],
    packages=packages,
    package_data={"load_forecast.models": ["load_forecast_exp2_trainFromStart_testUntilEnd_trial3.pkl"]}, # TODO: Change this to using model from Wandb's model registry instead
    entry_points={
        'setuptools.installation': [
            'eggsecutable = ' + agent_module + ':main',
        ]
    }
)