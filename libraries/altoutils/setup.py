import os

import setuptools
from altoutils import __version__


with open("README.md", "r") as fh:
    long_description = fh.read()

def find_packages(toplevel):
    return [directory.replace(os.path.sep, '.') for directory, subdirs, files in os.walk(toplevel) if '__init__.py' in files]


setuptools.setup(
    name='altoutils',
    version=__version__,
    author="Worawut Boonpeang",
    author_email="zz.enlighten.zz@gmail.com",
    description="Utilities for altotech",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=find_packages('altoutils'),
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "License :: OSI Approved :: MIT License"
    ],
    python_requires='>=3.7',
    install_requires=[],
)
