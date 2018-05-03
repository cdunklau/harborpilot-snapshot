import sys
import asyncio
import pathlib
import logging

import aiohttp.web as aweb

from harborpilot import docker
from harborpilot import config
from harborpilot import application


log = logging.getLogger(__name__)


def serve(config_path):
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    with open(config_path, 'r') as conffile:
        cfg = config.from_yaml_file(conffile)
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(application.build_app(cfg))
    aweb.run_app(app, host=cfg.address, port=cfg.port)


def main():
    serve('harborpilot.conf')
