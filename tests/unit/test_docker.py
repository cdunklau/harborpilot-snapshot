import io
import collections
import asyncio
import json

import pytest
import attr
import aiohttp.web

from harborpilot import docker


@attr.s
class BuildResponse:
    messages = attr.ib()  # iterable of JSON-serializable dicts
    status_code = attr.ib(default=200)


class FakeBuildEndpoint:
    def __init__(self, build_response, message_delay=0.25):
        self._build_response = build_response
        self._used = False
        self.received_content = None
        self._message_delay = message_delay

    async def handle_request(self, request):
        if self._used:
            raise aiohttp.web.HTTPInternalServerError(
                reason='Already handling')
        self._used = True
        self.received_content = await request.read()
        response = aiohttp.web.StreamResponse(
            status=self._build_response.status_code,
        )
        response.content_type = 'application/json'
        response.enable_chunked_encoding()
        await response.prepare(request)
        for message in self._build_response.messages:
            await asyncio.sleep(self._message_delay)
            await response.write(json.dumps(message).encode('utf-8') + b'\n')
        await response.write_eof()
        return response


class StoringConsumer:
    def __init__(self):
        self.messages = []
        self.closed = False

    def message_received(self, message):
        self.messages.append(message)

    async def last_message_received(self):
        self.closed = True


# TODO: Probably refactor these tests to avoid the massive code duplication.

async def test_imagebuild_success(aiohttp_server):
    messages = [
        {'stream': 'some data'},
        {'stream': '\n'},
        {'stream': 'some more data'},
        {'stream': '\n'},
    ]
    build_endpoint = FakeBuildEndpoint(BuildResponse(messages))
    app = aiohttp.web.Application()
    app.add_routes([
        aiohttp.web.post('/build', build_endpoint.handle_request),
    ])
    server = await aiohttp_server(app)

    fake_tar_data = b'this would be tar data'

    async with aiohttp.ClientSession() as session:
        build = docker.ImageBuild(
            session,
            io.BytesIO(fake_tar_data),
            image_name='harborpilottest/someimage',
            base_url='http://{0}:{1}'.format(server.host, server.port),
        )
        await build.start()

        build_message_consumer = StoringConsumer()
        await build.dispatch_messages(build_message_consumer)

    assert build_endpoint.received_content == fake_tar_data
    assert build_message_consumer.messages == messages
    assert build_message_consumer.closed


async def test_imagebuild_failure(aiohttp_server):
    messages = [
        {'message': 'the server had a problem'},
    ]
    build_endpoint = FakeBuildEndpoint(BuildResponse(messages, 500))
    app = aiohttp.web.Application()
    app.add_routes([
        aiohttp.web.post('/build', build_endpoint.handle_request),
    ])
    server = await aiohttp_server(app)

    fake_tar_data = b'this would be tar data'

    async with aiohttp.ClientSession() as session:
        build = docker.ImageBuild(
            session,
            io.BytesIO(fake_tar_data),
            image_name='harborpilottest/someimage',
            base_url='http://{0}:{1}'.format(server.host, server.port),
        )
        with pytest.raises(docker.BuildNotAccepted) as exc_info:
            await build.start()
        assert exc_info.value.reason == 'the server had a problem'
        assert exc_info.value.status_code == 500

    assert build_endpoint.received_content == fake_tar_data
