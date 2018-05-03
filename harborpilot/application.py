import asyncio

import aiohttp.web as aweb

from harborpilot import handlers
from harborpilot import docker


async def build_app(config):
    app = aweb.Application()
    app['push_receiver_client_session'] = docker.make_session()
    app.on_cleanup.append(dispose_push_receiver_client_session)
    push_receiver = handlers.ImagePushHookReceiver(
        app['push_receiver_client_session'],
        config.builds,
    )
    app.add_routes([
        aweb.post(
            '/apis/builds/{build_name}',
            push_receiver.build_image_from_git,
        ),
    ])
    return app


async def dispose_push_receiver_client_session(app):
    session = app['push_receiver_client_session']
    del app['push_receiver_client_session']
    # Zero-sleep to allow underlying connections to close
    await asyncio.sleep(0)
    await session.close()
