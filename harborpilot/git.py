import os
import pathlib
import asyncio.subprocess
import tempfile


async def build_archive(config):
    """
    Create a tar archive of a Docker build context retrieved from
    a Git repository.

    Returns a tuple with two elements: the Git commit hash from the
    cloned repository, and the path of the created tar file.

    The caller is responsible for removing the file after use.

    Arguments:
        config (.config.GitDockerBuildContextConfig):
            The Git repo configuration to build the archive from.
    """
    with tempfile.TemporaryDirectory(suffix='.harborpilot') as clonedir:
        try:
            await _clone(config.remote, config.branch, clonedir)
        except _ProcFailed as e:
            e.config = config
            raise e

        try:
            commit_hash = await _revparse(clonedir)
        except _ProcFailed as e:
            e.config = config
            raise e

        tar_root = config.remote / config.context_relpath
        _, tar_file = tempfile.mkstemp(suffix='.harborpilot.tar')
        try:
            await _archive(str(tar_root), tar_file)
        except _ProcFailed as e:
            os.unlink(tar_file)
            e.config = config
            raise e
        except:
            # Clean up the tempfile if the archive fails.
            os.unlink(tar_file)
            raise

        return (commit_hash, tar_file)


async def _clone(remote, branch, clonedir):
    """
    Clone the Git repo into ``clonedir``.
    """
    clone_args = [
        'git', 'clone', '--depth=1', '--branch={0}'.format(branch),
        remote,
        clonedir,
    ]
    proc = await asyncio.create_subprocess_exec(
        *clone_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # TODO: Add a timeout
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise GitCloneFailed(proc.returncode, stdout, stderr)


async def _revparse(clonedir):
    """
    Return the HEAD commit hash for the Git repository located at
    ``clonedir``.
    """
    revparse_args = ['git', 'rev-parse', 'HEAD']
    # TODO: Figure out if we need to pass in the whole parent environment.
    revparse_env = os.environ.copy()
    revparse_env['GIT_DIR'] = str(pathlib.Path(clonedir) / '.git')
    proc = await asyncio.create_subprocess_exec(
        *revparse_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=revparse_env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise GitRevParseFailed(proc.returncode, stdout, stderr)
    return stdout.strip().decode('ascii')


async def _archive(tar_root, dest_file):
    # TODO: Check that a Dockerfile exists in the tar root?
    for dirpath, dirnames, filenames in os.walk(tar_root):
        for filename in filenames:
            link_path = os.path.join(dirpath, filename)
            if os.path.islink(link_path):
                relpath = os.path.relpath(link_path, tar_root)
                raise SymlinkDetected('./' + relpath)
    tar_args = ['tar', '-cf', dest_file, '-C', tar_root, '.']
    proc = await asyncio.create_subprocess_exec(
        *tar_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise ArchiveFailed(proc.returncode, stdout, stderr)
    

# To clone just the tip of the branch:
#   git clone --depth=1 --branch=$BRANCH $REMOTE $DESTDIR
# To get the commit hash:
#   GIT_DIR=$DESTDIR git rev-parse HEAD


class _ProcFailed(Exception):
    def __init__(self, exitcode, stdout, stderr):
        self.exitcode = exitcode
        self.stdout = stdout
        self.stderr = stderr
        self.config = 'UNKNOWN'  # Set later by build_archive

    def __str__(self):
        fmt = (
            '{classname}('
            'exitcode={s.exitcode}, '
            'stdout={s.stdout!r}, '
            'stderr={s.stderr!r}, '
            'config={s.config!r}'
            ')'
        )
        return fmt.format(classname=type(self).__name__, s=self)


class GitCloneFailed(_ProcFailed):
    pass


class GitRevParseFailed(_ProcFailed):
    pass


class ArchiveFailed(_ProcFailed):
    pass


class SymlinkDetected(Exception):
    def __init__(self, relative_path):
        self.relative_path = relative_path

    def __str__(self):
        fmt = '{classname}(relative_path={relative_path!r})'
        return fmt.format(
            classname=type(self).__name__,
            relative_path=self.relative_path,
        )
