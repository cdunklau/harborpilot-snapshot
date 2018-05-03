import os
import logging

from aiohttp import web as aweb

from harborpilot import docker
from harborpilot import git


log = logging.getLogger(__name__)


class ImagePushHookReceiver:
    def __init__(self, client_session, image_build_configs):
        self._client = client_session
        self._configs = image_build_configs

    async def build_image_from_git(self, request):
        # TODO: Verify credentials and permission (before the handler maybe?)
        # TODO: Get the image details from the DB or conf or whatever
        build_name = request.match_info['build_name']
        image_build_config = self._configs.get(build_name)
        if image_build_config is None:
            raise aweb.HTTPNotFound()

        # Do the git dance and make a tarball
        log.debug('Using config {0}'.format(image_build_config))
        log.debug('Building archive')
        commit_hash, tarball_path = await git.build_archive(image_build_config.git)
        try:
            with open(tarball_path, 'rb') as archive:
                # TODO: Trap known exceptions and provide a reasonable explanation
                #       in an error (500?) response.
                log.debug('Sending archive to Docker')
                # TODO: Label properly with commit hash and configured tag
                build = docker.ImageBuild(
                    self._client,
                    archive=archive,
                    image_name=image_build_config.image_name,
                )
                try:
                    await build.start()
                except docker.BuildNotAccepted as e:
                    raise aweb.HTTPInternalServerError(
                        text='Docker did not accept the build: {0}:{1}'.format(
                            e.reason, e.status_code)
                    )
        finally:
            os.remove(tarball_path)

        # The Docker engine accepted the build, so send the stream messages
        # it provides out to the client.
        response = aweb.StreamResponse()
        await response.prepare(request)
        build_message_consumer = docker.StreamOnlyConsumer(writeable=response)
        await build.dispatch_messages(build_message_consumer)
        # Maybe record the build results somewhere? This would be another
        # consumer though.
        # TODO: Need some way of detecting if the build actually completed
        #       successfully or not.
        await response.write_eof()
        return response
