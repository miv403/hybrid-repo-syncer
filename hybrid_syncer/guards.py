"""
Pre-flight guard checks & safety circuit breakers.
"""

import sys
from pathlib import Path

from hybrid_syncer.config import clean_path
from hybrid_syncer.errors import (
    AncestryRewrittenError,
    DirtyWorkspaceError,
    DivergenceError,
    PatchApplyError,
)
from hybrid_syncer.git_utils import (
    check_ancestry_history,
    check_clean_workspace,
    check_divergence,
    check_pre_apply_patch,
    find_effective_sync_point,
    resolve_repo_url,
)


from hybrid_syncer.temp_manager import TempRepoCache


def run_preflight_guards(target_name: str, direction: str, target_cfg: dict, manifest: dict, config_path: str, args, repo_cache: TempRepoCache | dict | None = None) -> bool:
    if getattr(args, "skip_guards", False):
        if args.verbose:
            print(f"[VERBOSE] Guard checks explicitly skipped via --skip-guards for {target_name} ({direction})", file=sys.stderr)
        return True

    base_dir = Path(config_path).parent.resolve()

    origin_cfg = target_cfg.get("origin", {})
    hybrid_cfg = target_cfg.get("hybrid", {})

    default_hybrid_url = manifest.get("hybrid_repo", "./hybrid")

    origin_url = resolve_repo_url(origin_cfg.get("url", ""), base_dir)
    origin_path = clean_path(origin_cfg.get("path", ""))

    hybrid_url = resolve_repo_url(hybrid_cfg.get("url", default_hybrid_url), base_dir)
    hybrid_path = clean_path(hybrid_cfg.get("path", ""))

    if direction == "push":
        source_url, source_path = origin_url, origin_path
        dest_url, dest_path = hybrid_url, hybrid_path
        source_name, dest_name = "Origin", "Hybrid"
    else:  # pull
        source_url, source_path = hybrid_url, hybrid_path
        dest_url, dest_path = origin_url, origin_path
        source_name, dest_name = "Hybrid", "Origin"

    # --- Guard Check 0: Clean Workspace Check ---
    for r_url, r_label in [(source_url, source_name), (dest_url, dest_name)]:
        uncommitted = check_clean_workspace(r_url)
        if uncommitted:
            raise DirtyWorkspaceError(target_name, direction, r_label, r_url, uncommitted)

    source_last_sync_sha, dest_commit_sha = find_effective_sync_point(source_url, source_path, dest_url, dest_path, repo_cache)

    if not source_last_sync_sha or not dest_commit_sha:
        if args.verbose:
            print(f"[VERBOSE] No previous sync history (GitOrigin-RevId) found between {source_name} and {dest_name} for '{target_name}'. Skipping history/divergence checks.", file=sys.stderr)
        return True

    # --- Guard Check 1: Ancestry & History Check ---
    is_ancestor = check_ancestry_history(source_url, source_last_sync_sha, repo_cache)
    if not is_ancestor:
        raise AncestryRewrittenError(target_name, direction, source_name, source_url, source_last_sync_sha)

    # --- Guard Check 2: Concurrent Fork Check (Divergence Guard) ---
    diverged, source_new, dest_new = check_divergence(
        source_url, source_path, source_last_sync_sha,
        dest_url, dest_path, dest_commit_sha,
        repo_cache
    )
    if diverged:
        raise DivergenceError(target_name, direction, source_name, source_path, dest_name, dest_path, source_last_sync_sha)

    # --- Guard Check 3: Pre-Apply Patch Check ---
    if source_new:
        patch_ok, patch_err = check_pre_apply_patch(
            source_url, source_path, source_last_sync_sha,
            dest_url, dest_path,
            repo_cache
        )
        if not patch_ok:
            raise PatchApplyError(target_name, direction, source_name, dest_name, patch_err)

    if args.verbose:
        print(f"[VERBOSE] All pre-flight guard checks PASSED for '{target_name}' ({direction}).", file=sys.stderr)

    return True
