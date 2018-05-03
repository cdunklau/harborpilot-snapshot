import re
import pathlib
import subprocess
import os

import pytest

from harborpilot import git
from harborpilot import config


@pytest.mark.asyncio
@pytest.mark.parametrize('branch,use_sub', [
    ('master', False),
    ('master', True),
    ('other', False),
    ('other', True),
])
async def test_build_archive(request, tmpdir, branch, use_sub):
    root = pathlib.Path(tmpdir.strpath).resolve()
    repo_dir = root / 'source'
    repo_dir.mkdir()
    expected_commit_hash = _make_git_repo(repo_dir, ['sub'], [
        ('foo.txt', 'top level\n'),
        ('sub/bar.txt', 'inside inner dir\n'),
    ], branch=branch)
    extract_dir = root / 'extracted'
    extract_dir.mkdir()
    if use_sub:
        cfg = config.GitDockerBuildContextConfig(
            remote=str(repo_dir),
            branch=branch,
            context_relpath=pathlib.PurePosixPath('sub'),
        )
    else:
        cfg = config.GitDockerBuildContextConfig(
            remote=str(repo_dir),
            branch=branch,
            context_relpath=pathlib.PurePosixPath('.'),
        )
    commit_hash, tar_file_path = await git.build_archive(cfg)
    # Make sure the tar file is removed at the end of the test.
    @request.addfinalizer
    def remove_tarball():
        os.unlink(tar_file_path)

    assert commit_hash == expected_commit_hash
    _untar_to(tar_file_path, extract_dir)
    if use_sub:
        assert (
            (extract_dir / 'bar.txt').read_text(encoding='ascii')
        ) == 'inside inner dir\n'
    else:
        assert (
            (extract_dir / 'foo.txt').read_text(encoding='ascii')
        ) == 'top level\n'
        assert (
            (extract_dir / 'sub' / 'bar.txt').read_text(encoding='ascii')
        ) == 'inside inner dir\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('branch', ['master', 'other'])
async def test__clone(tmpdir, branch):
    root = pathlib.Path(tmpdir.strpath).resolve()
    repo_dir = root / 'source'
    repo_dir.mkdir()
    clone_dir = root / 'dest'
    commit_hash = _make_git_repo(repo_dir, ['sub'], [
        ('foo.txt', 'top level\n'),
        ('sub/bar.txt', 'inside inner dir\n'),
    ], branch=branch)
    await git._clone(str(repo_dir), branch, str(clone_dir))
    assert (clone_dir / 'foo.txt').read_text(encoding='ascii') == 'top level\n'
    assert (
        (clone_dir / 'sub' / 'bar.txt').read_text(encoding='ascii')
    ) == 'inside inner dir\n'


@pytest.mark.asyncio
async def test__revparse(tmpdir):
    root = pathlib.Path(tmpdir.strpath).resolve()
    repo_dir = root / 'test_repo'
    repo_dir.mkdir()
    commit_hash = _make_git_repo(repo_dir, ['sub'], [
        ('foo.txt', 'top level\n'),
        ('sub/bar.txt', 'inside inner dir\n'),
    ])
    revparsed = await git._revparse(str(repo_dir))
    assert revparsed == commit_hash


@pytest.mark.asyncio
async def test__archive_tars_at_given_root(tmpdir):
    root = pathlib.Path(tmpdir.strpath).resolve()
    tar_root = root / 'tar_root'
    tar_root.mkdir()
    fileinside = tar_root / 'foo.txt'
    fileinside.write_text('hello world\n', encoding='ascii')
    tar_file = root / 'tarball.tar'
    extract_dir = root / 'output'
    extract_dir.mkdir()
    await git._archive(str(tar_root), str(tar_file))
    subprocess.run(
        ['tar', '-x', '-f', str(tar_file), '-C', str(extract_dir)],
        check=True,
    )
    assert len(list(extract_dir.iterdir())) == 1
    file_contents = (extract_dir / 'foo.txt').read_text(encoding='ascii')
    assert file_contents == 'hello world\n'


@pytest.mark.asyncio
async def test__archive_rejects_symlinks(tmpdir):
    root = pathlib.Path(tmpdir.strpath).resolve()
    symlink_target = 'outside.txt'
    link_name = 'inside.txt'
    tar_root_path = root / 'tar_root'
    tar_root_path.mkdir()
    root.joinpath(symlink_target).write_text('foo\n')
    tar_root_path.joinpath(link_name).symlink_to(root / symlink_target)
    with pytest.raises(
            git.SymlinkDetected,
            match=re.escape('relative_path={0!r}'.format('./' + link_name)),
        ):
        await git._archive(str(tar_root_path), None)


def _make_git_repo(root, dirs, files_with_contents, *, branch='master'):
    """
    Create directories under ``root``, writing a file for each entry
    in ``files_with_contents``, initialize a Git repo and commit the
    contents. Return the commit hash as a str.

    Arguments:
        root (str or path-like):
            The path under which to create the repo.
        dirs (iterable of str or path-like):
            Directories to create. Parents must precede children.
        files_with_contents (iterable of 2-tuples):
            Elements are tuples comprising file path (str or path-like)
            and text (str) to write in the file.
        branch (str):
            Branch on which to make the commit (default ``'master'``).
    """
    root = pathlib.Path(root)
    for d in dirs:
        (root / d).mkdir()
    for filepath, contents in files_with_contents:
        (root / filepath).write_text(contents)
    runkwargs = dict(
        cwd=str(root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(['git', 'init'], **runkwargs)
    subprocess.run(['git', 'checkout', '-b', branch], **runkwargs)
    subprocess.run(['git', 'add', '.'], **runkwargs)
    subprocess.run(
        ['git', 'commit', '-m', 'initial commit'],
        **runkwargs
    )
    runkwargs['stdout'] = subprocess.PIPE
    return subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        **runkwargs,
    ).stdout.strip().decode('ascii')


def _untar_to(tar_file, extract_dir):
    subprocess.run(
        ['tar', '-x', '-f', str(tar_file), '-C', str(extract_dir)],
        check=True,
    )
