import os

from setuptools import setup, find_packages

requires = [
    'aiohttp>=3.0',
    'pyyaml>=3.12',
    # Need keys/values args to marshmallow.fields.Dict
    'marshmallow>=3.0.0b9',
]

setup(
    name='HarborPilot',
    version='0.0',
    description='A middleman for building Docker images',
    author='Colin Dunklau',
    author_email='colin.dunklau@gmail.com',
    packages=find_packages(include=['harborpilot']),
    include_package_data=True,
    zip_safe=False,
    install_requires=requires,
    entry_points="""\
    [console_scripts]
    harborpilot = harborpilot.cli:main
    """,
)
