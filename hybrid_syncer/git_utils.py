"""
Low-level git wrappers & status checks.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from hybrid_syncer.errors import ManifestError, RepoAccessError
from hybrid_syncer.temp_manager import TempRepoCache, get_repo_path


IS_WINDOWS = sys.platform == "win32" or sys.platform == "cygwin"


def normalize_path_for_git(path: str | Path) -> str:
    """
    Normalizes a file system path for Git CLI and Starlark specs.
    
    On Windows (and cross-platform), converts backslashes '\\' to forward slashes '/' 
    so Git CLI and Starlark parser handle paths cleanly without misinterpreting 
    backslashes as escape sequences (e.g. \\t, \\n).
    Remote URLs (http://, https://, git@, ssh://) are left untouched.
    """
    if not path:
        return ""
    path_str = str(path)
    if is_remote_url(path_str):
        return path_str
    # Convert Windows backslashes to POSIX-style forward slashes for clean Git & Starlark handling
    return path_str.replace("\\", "/")


def sanitize_git_arg(arg: str | Path) -> str:
    """
    Sanitizes an argument for Git command execution.
    Converts Path objects or Windows backslash paths into clean POSIX forward-slash strings.
    """
    if isinstance(arg, Path):
        return arg.as_posix()
    arg_str = str(arg)
    if not is_remote_url(arg_str) and "\\" in arg_str:
        return arg_str.replace("\\", "/")
    return arg_str


def run_git(args: list, cwd=None) -> tuple[int, str, str]:
    """Helper to execute git commands and return (returncode, stdout, stderr)."""
    sanitized_args = [sanitize_git_arg(arg) for arg in args]
    
    if cwd:
        cwd = sanitize_git_arg(cwd)
        
    try:
        res = subprocess.run(
            ["git"] + sanitized_args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return res.returncode, res.stdout, res.stderr
    except (subprocess.SubprocessError, OSError) as e:
        return -1, "", str(e)


def is_remote_url(url: str) -> bool:
    if not url:
        return False
    return url.startswith(("http://", "https://", "git@", "ssh://"))


def check_remote_repo_exists(url: str) -> bool:
    """Checks if a remote repository exists and is accessible via git ls-remote."""
    rc, _, _ = run_git(["ls-remote", url])
    return rc == 0


def check_repo_exists(url: str) -> tuple[bool, str]:
    """
    Checks whether a repository exists on disk (if local) or via git ls-remote (if remote URL).
    Returns (exists, error_message_suffix).
    """
    if is_remote_url(url):
        if check_remote_repo_exists(url):
            return True, ""
        return False, "is not accessible or does not exist."
    else:
        if Path(url).exists():
            return True, ""
        return False, "does not exist on disk."


def resolve_repo_url(url: str, base_dir: Path) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://", "git@", "ssh://")):
        return url
    if url.startswith("file://"):
        url = url[7:]
    p = Path(url)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
        
    return normalize_path_for_git(p)


def check_clean_workspace(repo_url: str) -> list[str]:
    """
    Checks if a local non-bare git workspace has uncommitted changes.
    Returns list of porcelain status lines if uncommitted changes exist.
    """
    if not repo_url or is_remote_url(repo_url):
        return []
    repo_path = Path(repo_url)
    if not repo_path.is_dir():
        return []

    # Check if bare
    rc, out, _ = run_git(["-C", str(repo_path), "rev-parse", "--is-bare-repository"])
    if rc == 0 and out.strip() == "true":
        if str(repo_path).endswith(".git"):
            sibling_working_dir = Path(str(repo_path)[:-4])
            if sibling_working_dir.is_dir():
                return check_clean_workspace(str(sibling_working_dir))
        return []

    rc, out, _ = run_git(["-C", str(repo_path), "status", "--porcelain"])
    if rc == 0 and out.strip():
        return [line for line in out.strip().splitlines() if line.strip()]

    return []


def _parse_log_for_revid(log_out: str) -> tuple[str | None, str | None]:
    blocks = log_out.split("\x00")
    revid_pattern = re.compile(r"GitOrigin-RevId:\s*([0-9a-fA-F]{7,40})")

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        commit_sha = lines[0].strip()
        body = "\n".join(lines[1:])
        match = revid_pattern.search(body)
        if match:
            return commit_sha, match.group(1)
    return None, None


def _extract_sync_info_from_dir(repo_dir: Path, dest_path: str = "") -> tuple[str | None, str | None]:
    cmd = ["-C", str(repo_dir), "log", "--grep=GitOrigin-RevId:", "-n", "500", "--format=%H%n%B%x00"]
    if dest_path:
        cmd_with_path = cmd + ["--", dest_path]
        rc, out, _ = run_git(cmd_with_path)
        if rc == 0 and out.strip():
            sha, rev = _parse_log_for_revid(out)
            if sha and rev:
                return sha, rev

    rc, out, _ = run_git(cmd)
    if rc == 0 and out.strip():
        return _parse_log_for_revid(out)

    return None, None


def find_last_sync_info(dest_repo_url: str, dest_path: str = "", repo_cache: TempRepoCache | dict | None = None) -> tuple[str | None, str | None]:
    """
    Searches dest_repo commit log for the last Copybara sync commit containing GitOrigin-RevId.
    Supports both local file paths and remote HTTP/HTTPS URLs.
    Returns (dest_commit_sha, source_origin_sha) or (None, None).
    """
    if not dest_repo_url:
        return None, None

    cache = repo_cache if isinstance(repo_cache, TempRepoCache) else TempRepoCache(temp_dirs=repo_cache if isinstance(repo_cache, dict) else None)
    with cache:
        try:
            repo_dir = cache.get_repo_path(dest_repo_url)
        except (ManifestError, RepoAccessError):
            return None, None
        return _extract_sync_info_from_dir(repo_dir, dest_path)


def find_effective_sync_point(source_url: str, source_path: str, dest_url: str, dest_path: str, repo_cache: TempRepoCache | dict | None = None) -> tuple[str | None, str | None]:
    """
    Finds the most recent sync point (source_last_sync_sha, dest_last_sync_sha) between source and dest repositories.
    Checks GitOrigin-RevId in both dest log (push) and source log (pull) to find the newest sync point.
    Returns (source_sync_sha, dest_sync_sha) or (None, None).
    """
    cache = repo_cache if isinstance(repo_cache, TempRepoCache) else TempRepoCache(temp_dirs=repo_cache if isinstance(repo_cache, dict) else None)
    with cache:
        dest_commit_sha1, source_rev_id1 = find_last_sync_info(dest_url, dest_path, cache)
        source_commit_sha2, dest_rev_id2 = find_last_sync_info(source_url, source_path, cache)

        if not (dest_commit_sha1 and source_rev_id1) and not (source_commit_sha2 and dest_rev_id2):
            return None, None

        if (dest_commit_sha1 and source_rev_id1) and not (source_commit_sha2 and dest_rev_id2):
            return source_rev_id1, dest_commit_sha1

        if not (dest_commit_sha1 and source_rev_id1) and (source_commit_sha2 and dest_rev_id2):
            return source_commit_sha2, dest_rev_id2

        # Compare which sync point is newer in source repository history
        try:
            source_dir = cache.get_repo_path(source_url)
            rc, _, _ = run_git(["-C", str(source_dir), "merge-base", "--is-ancestor", source_rev_id1, source_commit_sha2])
            if rc == 0:
                return source_commit_sha2, dest_rev_id2
        except (ManifestError, RepoAccessError):
            pass

        return source_rev_id1, dest_commit_sha1


def check_ancestry_history(source_repo_url: str, last_sync_source_sha: str, repo_cache: TempRepoCache | dict | None = None) -> bool:
    """
    Checks if last_sync_source_sha is still an ancestor of HEAD in source_repo.
    Returns False if history was rewritten / rebased / force-pushed.
    Supports both local file paths and remote HTTP/HTTPS URLs.
    """
    if not source_repo_url:
        return True

    cache = repo_cache if isinstance(repo_cache, TempRepoCache) else TempRepoCache(temp_dirs=repo_cache if isinstance(repo_cache, dict) else None)
    with cache:
        try:
            source_dir = cache.get_repo_path(source_repo_url)
        except (ManifestError, RepoAccessError):
            return True

        # Check commit existence
        rc, _, _ = run_git(["-C", str(source_dir), "cat-file", "-e", f"{last_sync_source_sha}^{{commit}}"])
        if rc != 0:
            return False

        rc, _, _ = run_git(["-C", str(source_dir), "merge-base", "--is-ancestor", last_sync_source_sha, "HEAD"])
        return rc == 0


def get_new_commits_count(repo_url: str, from_sha: str, path_filter: str = "", repo_cache: TempRepoCache | dict | None = None) -> int:
    if not repo_url:
        return 0

    cache = repo_cache if isinstance(repo_cache, TempRepoCache) else TempRepoCache(temp_dirs=repo_cache if isinstance(repo_cache, dict) else None)
    with cache:
        try:
            repo_dir = cache.get_repo_path(repo_url)
        except (ManifestError, RepoAccessError):
            return 0

        cmd = ["-C", str(repo_dir), "rev-list", f"{from_sha}..HEAD"]
        if path_filter:
            cmd.extend(["--", path_filter])

        rc, out, _ = run_git(cmd)
        if rc == 0 and out.strip():
            return len([line for line in out.strip().splitlines() if line.strip()])
        return 0


def check_divergence(source_repo_url: str, source_path: str, last_sync_source_sha: str,
                     dest_repo_url: str, dest_path: str, dest_sync_commit_sha: str,
                     repo_cache: TempRepoCache | dict | None = None) -> tuple[bool, bool, bool]:
    cache = repo_cache if isinstance(repo_cache, TempRepoCache) else TempRepoCache(temp_dirs=repo_cache if isinstance(repo_cache, dict) else None)
    with cache:
        source_new = get_new_commits_count(source_repo_url, last_sync_source_sha, source_path, cache) > 0
        dest_new = get_new_commits_count(dest_repo_url, dest_sync_commit_sha, dest_path, cache) > 0
        diverged = source_new and dest_new
        return diverged, source_new, dest_new


def check_pre_apply_patch(source_repo_url: str, source_path: str, last_sync_source_sha: str,
                          dest_repo_url: str, dest_path: str,
                          repo_cache: TempRepoCache | dict | None = None) -> tuple[bool, str]:
    cache = repo_cache if isinstance(repo_cache, TempRepoCache) else TempRepoCache(temp_dirs=repo_cache if isinstance(repo_cache, dict) else None)
    with cache:
        try:
            source_dir = cache.get_repo_path(source_repo_url)
            dest_dir = cache.get_repo_path(dest_repo_url)
        except (ManifestError, RepoAccessError):
            return True, ""

        if not source_dir or not dest_dir:
            return True, ""

        dest_path_obj = dest_dir
        if str(dest_path_obj).endswith(".git"):
            sibling_working_dir = Path(str(dest_path_obj)[:-4])
            if sibling_working_dir.is_dir():
                dest_path_obj = sibling_working_dir

        source_path_obj = source_dir
        if str(source_path_obj).endswith(".git"):
            sibling_working_dir = Path(str(source_path_obj)[:-4])
            if sibling_working_dir.is_dir():
                source_path_obj = sibling_working_dir

        # Skip git apply check if target destination is bare (including remote bare repos)
        rc, out, _ = run_git(["-C", str(dest_path_obj), "rev-parse", "--is-bare-repository"])
        if rc == 0 and out.strip() == "true":
            return True, ""

        diff_cmd = ["-C", str(source_path_obj), "diff", f"{last_sync_source_sha}..HEAD"]
        if source_path:
            diff_cmd.extend(["--", source_path])

        rc, patch_text, _ = run_git(diff_cmd)
        if rc != 0 or not patch_text.strip():
            return True, ""

        clean_src_path = source_path.strip("/")
        src_parts = [p for p in clean_src_path.split("/") if p]
        strip_level = 1 + len(src_parts)

        clean_dst_path = dest_path.strip("/")

        apply_cmd = ["-C", str(dest_path_obj), "apply", "--check", f"-p{strip_level}"]
        if clean_dst_path:
            apply_cmd.append(f"--directory={clean_dst_path}")

        try:
            res = subprocess.run(
                ["git"] + apply_cmd,
                input=patch_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip() or f"exit code {res.returncode}"
                return False, err_msg
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)

        return True, ""


def is_file_mapped(file_path: str, mapped_paths: set[str]) -> bool:
    if "" in mapped_paths or "." in mapped_paths:
        return True
    from hybrid_syncer.config import clean_path
    clean_f = clean_path(file_path)
    for mp in mapped_paths:
        clean_m = clean_path(mp)
        if not clean_m:
            return True
        if clean_f == clean_m or clean_f.startswith(clean_m + "/"):
            return True
    return False


def format_path_display(path_str: str) -> str:
    if not path_str or path_str == ".":
        return "."
    if not path_str.endswith("/") and "/" not in path_str:
        return path_str + "/"
    return path_str
