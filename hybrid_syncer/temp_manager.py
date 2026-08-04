"""
Context manager and helper functions for cloning and cleaning temporary bare repositories.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from hybrid_syncer.errors import ManifestError, RepoAccessError


class TempRepoCache:
    """
    Manages temporary bare clones of remote repositories with context-managed auto-cleanup.
    Guarantees cleanup of all temporary directories created during its lifecycle upon exit.
    """

    def __init__(self, temp_dirs: dict | None = None):
        self._cache: dict[str, Path] = temp_dirs if isinstance(temp_dirs, dict) else {}
        self._ref_count = 0

    def get_repo_path(self, repo_url: str) -> Path:
        """
        Returns local Path to repository.
        Clones remote repos to temporary bare dirs if necessary and caches them.
        Raises ManifestError if repo_url is missing.
        Raises RepoAccessError if local repository path does not exist or remote clone fails.
        """
        if not repo_url:
            raise ManifestError("Repository URL or path is missing.")

        from hybrid_syncer.git_utils import is_remote_url, run_git

        if not is_remote_url(repo_url):
            p = Path(repo_url)
            if not p.exists():
                raise RepoAccessError(f"Local repository path '{repo_url}' does not exist.")
            return p

        # Return cached path if already cloned during this execution run
        if repo_url in self._cache:
            return self._cache[repo_url]

        tmp_dir = tempfile.mkdtemp(prefix="syncer_remote_")
        try:
            rc, _, err = run_git(["clone", "--bare", repo_url, tmp_dir])
            if rc != 0:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise RepoAccessError(f"Remote repository '{repo_url}' is not accessible or does not exist:\n{err.strip()}")
        except (subprocess.SubprocessError, OSError) as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RepoAccessError(f"Failed to clone remote repository '{repo_url}': {e}")

        tmp_path = Path(tmp_dir)
        self._cache[repo_url] = tmp_path
        return tmp_path

    def cleanup(self):
        """Removes all temporary bare repositories created during execution."""
        for repo_path in list(self._cache.values()):
            if repo_path and repo_path.exists():
                try:
                    shutil.rmtree(str(repo_path), ignore_errors=True)
                except OSError:
                    pass
        self._cache.clear()

    def __enter__(self):
        self._ref_count += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ref_count -= 1
        if self._ref_count <= 0:
            self.cleanup()

    # Dictionary-like compatibility methods for legacy callers
    @property
    def temp_dirs(self) -> dict[str, Path]:
        return self._cache

    def __getitem__(self, item: str) -> Path:
        return self._cache[item]

    def __setitem__(self, key: str, value: Path):
        self._cache[key] = value

    def __contains__(self, item: str) -> bool:
        return item in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def keys(self):
        return self._cache.keys()

    def values(self):
        return self._cache.values()

    def items(self):
        return self._cache.items()

    def get(self, key: str, default=None):
        return self._cache.get(key, default)


def get_repo_path(repo_url: str, repo_cache: TempRepoCache | dict | None = None) -> tuple[Path | None, bool]:
    """
    Legacy wrapper for get_repo_path.
    Returns (Path_to_repo, is_temporary).
    """
    if not repo_url:
        return None, False

    from hybrid_syncer.git_utils import is_remote_url

    if isinstance(repo_cache, TempRepoCache):
        try:
            path = repo_cache.get_repo_path(repo_url)
            return path, is_remote_url(repo_url)
        except (ManifestError, RepoAccessError):
            return None, False

    if not is_remote_url(repo_url):
        p = Path(repo_url)
        return (p if p.exists() else None), False

    if isinstance(repo_cache, dict) and repo_url in repo_cache:
        return repo_cache[repo_url], False

    tmp_dir = tempfile.mkdtemp(prefix="syncer_remote_")
    try:
        from hybrid_syncer.git_utils import run_git
        rc, _, stderr = run_git(["clone", "--bare", repo_url, tmp_dir])
        if rc != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RepoAccessError(f"Remote repository at '{repo_url}' is not accessible or clone failed: {stderr.strip()}")
    except (subprocess.SubprocessError, OSError) as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RepoAccessError(f"Failed to clone remote repository '{repo_url}': {e}")

    tmp_path = Path(tmp_dir)
    if isinstance(repo_cache, dict):
        repo_cache[repo_url] = tmp_path
    return tmp_path, True


# Alias for backward compatibility
TempRepoManager = TempRepoCache
