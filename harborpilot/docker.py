"""
Wrappers for accessing Docker Engine.
"""
import json
import logging
import uuid
import asyncio
import concurrent.futures

import aiohttp


log = logging.getLogger(__name__)


# See https://docs.docker.com/engine/api/v1.37/#operation/ImageBuild
# The response body format isn't documented (as of 2018-04-26), but appears
# to be line-delimited JSON objects. See also
# https://github.com/docker/docker.github.io/issues/6530
class ImageBuild:
    """
    A task container for triggering and obtaining output from a single
    build of a Docker image.

    Call and await :meth:`start` to initiate the build, then call and
    await :meth:`dispatch_messages` to receive build messages from the
    Engine API's /build endpoint.
    """
    def __init__(
            self, client_session, archive, *,
            image_name, labels=None, base_url='http://dockerengine.local'
        ):
        """
        Arguments:
            client_session (aiohttp.ClientSession):
                The HTTP client. Assumed to be created with
                :func:`make_session`.
            archive:
                A binary-mode file-like object containing tar data.
                The archive must have a Dockerfile at its root, along
                with any necessary supporting files needed for the
                build.

        Keyword Arguments:
            image_name (str):
                The name to use for the image.
            labels (collections.abc.Mapping):
                A mapping (str -> str) of label names and values to
                apply to the image.
            base_url (str):
                The base URL (without trailing slash) to use for
                communication with the Docker Engine API. If
                ``client_session`` is configured to communicate with
                the UNIX socket, the host portion of the URL shouldn't
                matter, but it should still be there.
        """
        self.archive = archive
        self.image_name = image_name
        self.labels = labels or {}
        self.base_url = base_url

        self._session = client_session
        self._request_task = None
        self._status_received = asyncio.Event()
        self._not_accepted_error = None
        self._is_ready_to_dispatch = True
        self._ready_to_receive = asyncio.Event()
        self._messages_consumer = None

    async def start(self):
        """
        Send the request for the build, raise :exc:`.BuildNotAccepted`
        if the Docker API responds other than 200.

        This does not consume the response body, use
        :meth:`dispatch_messages` for that.
        """
        if self._request_task is not None:
            raise Exception('Already started!')
        self._request_task = asyncio.ensure_future(self._invoke())
        await self._status_received.wait()
        if self._not_accepted_error is not None:
            self._request_task.cancel()
            raise self._not_accepted_error
        self._is_ready_to_dispatch = True

    async def dispatch_messages(self, consumer):
        """
        Read the response JSON lines and dispatch their decoded
        structures to the consumer's ``message_received`` method.

        When there are no more messages, the consumer's
        ``last_message_received`` *coroutine* method will be called
        and awaited.
        """
        if not self._is_ready_to_dispatch:
            raise Exception('Must start() before dispatching!')
        assert self._status_received.is_set()
        assert self._not_accepted_error is None
        assert not self._ready_to_receive.is_set()
        assert self._messages_consumer is None
        self._messages_consumer = consumer
        self._ready_to_receive.set()
        await self._request_task

    async def _invoke(self):
        try:
            async with self._make_request() as response:
                await self._process_response(response)
        except:
            log.exception('Unhandled error in request to Docker Engine')

    def _make_request(self):
        params = {'t': self.image_name}
        if self.labels:
            params['labels'] = json.dumps(self.labels)
        headers = {'Content-Type': 'application/x-tar'}
        url = self.base_url + '/build'
        return self._session.post(
            url,
            params=params,
            headers=headers,
            data=self.archive,
        )

    async def _process_response(self, response):
        log.debug('Response status {r.status}, headers {r.headers!r}'.format(
            r=response))
        build_accepted = response.status == 200
        if not build_accepted:
            error_info = await response.json()
            self._not_accepted_error = BuildNotAccepted(
                error_info['message'], response.status)
            self._status_received.set()
            return

        self._status_received.set()
        await self._ready_to_receive.wait()
        assert self._messages_consumer is not None

        while True:
            line = await response.content.readline()
            if not line:
                await self._messages_consumer.last_message_received()
                break
            linetext = line.decode('utf-8')
            message = json.loads(linetext)
            self._messages_consumer.message_received(message)


class BuildNotAccepted(Exception):
    def __init__(self, reason, status_code):
        self.reason = reason
        self.status_code = status_code

    def __str__(self):
        fmt = '{class_name}(reason={reason!r}, status_code={status_code!r})'
        return fmt.format(
            class_name=type(self).__name__,
            reason=self.reason,
            status_code=self.status_code,
        )


class StreamOnlyConsumer:
    def __init__(self, writeable):
        self._writeable = writeable
        self._stream_chunks = asyncio.Queue()
        self._write_task = asyncio.ensure_future(self._write_messages())
        self._closed = False

    def message_received(self, message):
        if self._closed:
            raise Exception('Cannot add after last_message_received() called')
        stream_chunk = message.get('stream')
        if stream_chunk is not None:
            if not isinstance(stream_chunk, str):
                raise TypeError(
                    "For message['stream'] expected str but got {0}".format(
                        type(stream_chunk)))
            self._stream_chunks.put_nowait(stream_chunk)

    async def last_message_received(self):
        self._closed = True
        await self._stream_chunks.join()
        self._write_task.cancel()

    async def _write_messages(self):
        while True:
            chunk = await self._stream_chunks.get()
            await self._writeable.write(chunk.encode('utf-8'))
            self._stream_chunks.task_done()


def make_session():
    conn = aiohttp.UnixConnector(path='/var/run/docker.sock')
    return aiohttp.ClientSession(connector=conn)
