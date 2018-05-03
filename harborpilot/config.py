"""
Configuration for the whole application.
"""
import pathlib

import attr
import yaml
import marshmallow as mm
import marshmallow.fields as mmf
import marshmallow.validate as mmv


def from_yaml_file(fileobj):
    structure = yaml.safe_load(fileobj)
    schema = HarborPilotConfigSchema()
    return schema.load(structure)


@attr.s
class HarborPilotConfig:
    # str, listening address
    address = attr.ib()
    # str, listening port
    port = attr.ib()
    # dict of build_name str -> ImageBuildConfig
    builds = attr.ib()


@attr.s
class ImageBuildConfig:
    # str, the URL component for VCS push notification endpoint
    build_name = attr.ib()
    # str, the name to use for the Docker image
    image_name = attr.ib()
    # str, the tag to use for the Docker image
    image_tag = attr.ib()
    # GitDockerBuildContextConfig
    git = attr.ib()


@attr.s
class GitDockerBuildContextConfig:
    remote = attr.ib()
    branch = attr.ib()
    context_relpath = attr.ib()


# Schemas
class _RelativePosixPath(mmf.String):
    default_error_messages = mmf.String.default_error_messages.copy()
    default_error_messages.update({
        'not_relative': 'Field must be a relative path.',
        'contains_uprefs': 'Field must not contain uprefs.',
    })

    def _deserialize(self, value, attr, obj):
        value = super()._deserialize(value, attr, obj)
        path = pathlib.PurePosixPath(value)
        if path.is_absolute():
            self.fail('not_relative')
        if '..' in path.parts:
            self.fail('contains_uprefs')
        return path


class GitDockerBuildContextConfigSchema(mm.Schema):
    remote = mmf.String(required=True)  # TODO: Add validation
    branch = mmf.String(missing='master')  # TODO: Add validation
    context_relpath = _RelativePosixPath(missing=pathlib.PurePosixPath('.'))

    @mm.post_load
    def convert_to_instance(self, data):
        return GitDockerBuildContextConfig(**data)


class ImageBuildConfigSchema(mm.Schema):
    """
    Does not include build_name, this is added from the key.
    """
    image_name = mmf.String(required=True)  # TODO: Add validation
    image_tag = mmf.String(missing='latest')  # TODO: Add validation
    git = mmf.Nested(GitDockerBuildContextConfigSchema, required=True)

    @mm.post_load
    def convert_to_instance(self, data):
        # Image ref is added later
        return ImageBuildConfig(build_name=None, **data)


class HarborPilotConfigSchema(mm.Schema):
    address = mmf.String(missing='127.0.0.1')
    port = mmf.Integer(
        validate=mmv.Range(min=0, max=0xFFFF),
        missing=18080,
    )
    builds = mmf.Dict(
        keys=mmf.String(),  # TODO: Add validation for proper build_name name
        values=mmf.Nested(ImageBuildConfigSchema),
        required=True,
        validate=mmv.Length(min=1, error='At least one build is required.'),
    )

    @mm.post_load
    def convert_to_instance(self, data):
        data['builds'] = {
            build_name: attr.evolve(image_build_obj, build_name=build_name)
            for build_name, image_build_obj
            in data['builds'].items()
        }
        return HarborPilotConfig(**data)
