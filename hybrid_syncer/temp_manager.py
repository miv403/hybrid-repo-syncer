"""
Context manager and helper functions for cloning and cleaning temporary bare repositories.
"""

import shutil
import tempfile
from pathlib import Path


def get_repo_path(repo_url: str, temp_dirs: dict | None = None) -> tuple[Path | None, bool]:
    """
    Returns (Path_to_repo, is_temporary).
    If repo_url is remote, clones bare repository to a temporary directory (or reuses temp_dirs[repo_url]).
    """
    from hybrid_syncer.git_utils import is_remote_url, run_git

    if not repo_url:
        return None, False

    if not is_remote_url(repo_url):
        p = Path(repo_url)
        return (p if p.exists() else None), False

    if temp_dirs is not None and repo_url in temp_dirs:
        return temp_dirs[repo_url], False

    tmp_dir = tempfile.mkdtemp(prefix="syncer_remote_")
    rc, _, _ = run_git(["clone", "--bare", repo_url, tmp_dir])
    if rc != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None, False

    tmp_path = Path(tmp_dir)
    if temp_dirs is not None:
        temp_dirs[repo_url] = tmp_path
    return tmp_path, True


class TempRepoManager:
    """
    Context manager for managing temporary bare repository clones.
    Automatically cleans up created temporary directories upon exit.
    """

    def __init__(self, temp_dirs: dict | None = None):
        self.temp_dirs = temp_dirs if temp_dirs is not None else {}
        self._owned = temp_dirs is None

    def __enter__(self) -> dict:
        return self.temp_dirs

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owned:
            for p in self.temp_dirs.values():
                if p and p.exists():
                    shutil.rmtree(str(p), ignore_errors=True)
            self.temp_dirs.clear()
