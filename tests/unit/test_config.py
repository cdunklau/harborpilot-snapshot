import pathlib

import attr
import pytest
import marshmallow as mm

from harborpilot import config


# TODO: Add tests for unknown fields rejected


_LOCAL_REMOTE = '/path/to/remote'
_REMOTE_REMOTE = 'git@git.example.com'
_IMAGE_NAME = 'some_image_name'
_BUILD_NAME = 'some_build_name'


def _minimal_GitDockerBuildContextConfig_structure(remote):
    return {'remote': remote}


def _default_GitDockerBuildContextConfig(remote):
    return config.GitDockerBuildContextConfig(
        remote=remote,  
        branch='master',
        context_relpath=pathlib.PurePosixPath('.'),
    )


def _minimal_ImageBuildConfig_structure(image_name, git_remote):
    return {
        'image_name': image_name,
        'git': _minimal_GitDockerBuildContextConfig_structure(git_remote),
    }


def _default_ImageBuildConfig(image_name, git_remote):
    return config.ImageBuildConfig(
        build_name=None,
        image_name=image_name,
        image_tag='latest',
        git=_default_GitDockerBuildContextConfig(git_remote),
    )


def _minimal_HarborPilotConfig_structure(
        build_name, image_name, image_git_remote
    ):
    return {
        'address': '127.0.0.1',
        'port': 18080,
        'builds': {
            build_name: _minimal_ImageBuildConfig_structure(
                image_name, image_git_remote
            ),
        }
    }


def _default_HarborPilotConfig(build_name, image_name, image_git_remote):
    image_build_obj = _default_ImageBuildConfig(image_name, image_git_remote)
    image_build_obj = attr.evolve(image_build_obj, build_name=build_name)
    return config.HarborPilotConfig(
        address='127.0.0.1',
        port=18080,
        builds={
            build_name: image_build_obj,
        },
    )


# TODO: Add tests for valid/invalid remote and branch names.
class TestGitDockerBuildContextConfigSchema:

    def test_remote_is_required(self):
        schema = config.GitDockerBuildContextConfigSchema()
        with pytest.raises(mm.ValidationError) as exc_info:
            schema.load({
                'branch': 'master',
                'context_relpath': '.',
            })
        exception = exc_info.value
        assert exception.field_names == ['remote']
        assert exception.messages == {
            'remote': ['Missing data for required field.']
        }


    def test_defaults(self):
        structure = \
            _minimal_GitDockerBuildContextConfig_structure(_LOCAL_REMOTE)
        expected_result = \
            _default_GitDockerBuildContextConfig(_LOCAL_REMOTE)
        schema = config.GitDockerBuildContextConfigSchema()
        result = schema.load(structure)
        assert result == expected_result


    @pytest.mark.parametrize('provided,expected', [
        ('', pathlib.PurePosixPath('.')),
        ('.', pathlib.PurePosixPath('.')),
        ('./', pathlib.PurePosixPath('.')),
        ('subdir', pathlib.PurePosixPath('./subdir')),
        ('subdir/subsub', pathlib.PurePosixPath('./subdir', 'subsub')),
    ])
    def test_valid_context_relpaths(self, provided, expected):
        schema = config.GitDockerBuildContextConfigSchema()
        result = schema.load({
            'remote': _LOCAL_REMOTE,
            'branch': 'master',
            'context_relpath': provided,
        })
        assert result.context_relpath == expected


    @pytest.mark.parametrize('provided_invalid,error_message', [
        ('/absolute/path', 'Field must be a relative path.'),
        ('./../refs/higher/level', 'Field must not contain uprefs.'),
        ('./relative/with/../upref', 'Field must not contain uprefs.'),
    ])
    def test_invalid_context_relpaths(self, provided_invalid, error_message):
        schema = config.GitDockerBuildContextConfigSchema()
        with pytest.raises(mm.ValidationError) as exc_info:
            schema.load({
                'remote': _LOCAL_REMOTE,
                'branch': 'master',
                'context_relpath': provided_invalid,
            })
        exception = exc_info.value
        assert exception.field_names == ['context_relpath']
        assert exception.messages == {'context_relpath': [error_message]}


# TODO: Add tests for valid/invalid image_name and image_tag.
class TestImageBuildConfigSchema:

    @pytest.mark.parametrize('structure,missing_field_name', [
        (
            {'git': _minimal_GitDockerBuildContextConfig_structure(
                _LOCAL_REMOTE)},
            'image_name',
        ),
        ({'image_name': _IMAGE_NAME}, 'git'),
    ])
    def test_required_fields(self, structure, missing_field_name):
        schema = config.ImageBuildConfigSchema()
        with pytest.raises(mm.ValidationError) as exc_info:
            schema.load(structure)
        exception = exc_info.value
        assert exception.field_names == [missing_field_name]
        assert exception.messages == {
            missing_field_name: ['Missing data for required field.']
        }

    def test_defaults(self):
        structure = _minimal_ImageBuildConfig_structure(
            _IMAGE_NAME, _LOCAL_REMOTE)
        expected_result = _default_ImageBuildConfig(
            _IMAGE_NAME, _LOCAL_REMOTE)
        schema = config.ImageBuildConfigSchema()
        result = schema.load(structure)
        assert result == expected_result


# TODO: Add tests for entire config error message structure.
# TODO: Add tests for valid/invalid address and port.
class TestHarborPilotConfigSchema:
    def test_requires_builds(self):
        schema = config.HarborPilotConfigSchema()
        with pytest.raises(mm.ValidationError) as exc_info:
            schema.load({})
        exception = exc_info.value
        assert exception.field_names == ['builds']
        assert exception.messages == {
            'builds': ['Missing data for required field.']
        }

    def test_requires_at_least_one_build(self):
        schema = config.HarborPilotConfigSchema()
        with pytest.raises(mm.ValidationError) as exc_info:
            schema.load({'builds': {}})
        exception = exc_info.value
        assert exception.field_names == ['builds']
        assert exception.messages == {
            'builds': ['At least one build is required.']
        }

    def test_defaults(self):
        structure = _minimal_HarborPilotConfig_structure(
            _BUILD_NAME, _IMAGE_NAME, _LOCAL_REMOTE)
        expected_result = _default_HarborPilotConfig(
            _BUILD_NAME, _IMAGE_NAME, _LOCAL_REMOTE)
        schema = config.HarborPilotConfigSchema()
        result = schema.load(structure)
        assert result == expected_result
