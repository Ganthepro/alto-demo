from setuptools import setup, find_packages

MAIN_MODULE = "agent"

# Find the agent package that contains the main module
packages = find_packages(".")
agent_package = "broadlinkagent"

# Find the version number from the main module
agent_module = agent_package + "." + MAIN_MODULE
_temp = __import__(agent_module, globals(), locals(), ["__version__"], 0)
__version__ = _temp.__version__

# Setup
setup(
    name=agent_package + "agent",
    version=__version__,
    author="François Wautier",
    author_email="fwautier61@gmail.com",
    description="Controlling Broadlink devices, both sensors and remote control",
    install_requires=["volttron"],
    packages=packages,
    entry_points={
        "setuptools.installation": ["eggsecutable = " + agent_module + ":main"]
    },
)
