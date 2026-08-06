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
from hybrid_syncer.logger import logger
from hybrid_syncer.temp_manager import TempRepoCache


def run_preflight_guards(
    target_name: str,
    dest_name: str,
    direction: str,
    target_cfg: dict,
    manifest: dict,
    config_path: str,
    args,
    repo_cache: TempRepoCache | dict | None = None,
) -> bool:
    if getattr(args, "skip_guards", False):
        logger.info("[VERBOSE] Guard checks explicitly skipped via --skip-guards for %s [%s] (%s)", target_name, dest_name, direction)
        return True

    base_dir = Path(config_path).parent.resolve()

    origin_cfg = target_cfg.get("origin", {})
    origin_url = resolve_repo_url(origin_cfg.get("url", ""), base_dir)
    origin_path = clean_path(origin_cfg.get("path", ""))

    destinations = target_cfg.get("destinations", [])
    selected_dest = next((d for d in destinations if d.get("name") == dest_name), None)
    if not selected_dest and destinations:
        selected_dest = destinations[0]

    if not selected_dest:
        dest_url = resolve_repo_url(manifest.get("hybrid_repo", "./hybrid"), base_dir)
        dest_path = ""
    else:
        dest_url = resolve_repo_url(selected_dest.get("url", ""), base_dir)
        dest_path = clean_path(selected_dest.get("path", ""))

    if direction == "push":
        source_url, source_path = origin_url, origin_path
        dest_url, dest_path = dest_url, dest_path
        source_label, dest_label = "Origin", f"Destination[{dest_name}]"
    else:  # pull
        source_url, source_path = dest_url, dest_path
        dest_url, dest_path = origin_url, origin_path
        source_label, dest_label = f"Destination[{dest_name}]", "Origin"

    # --- Guard Check 0: Clean Workspace Check ---
    for r_url, r_label in [(source_url, source_label), (dest_url, dest_label)]:
        uncommitted = check_clean_workspace(r_url)
        if uncommitted:
            raise DirtyWorkspaceError(f"{target_name} [{dest_name}]", direction, r_label, r_url, uncommitted)

    source_last_sync_sha, dest_commit_sha = find_effective_sync_point(source_url, source_path, dest_url, dest_path, repo_cache)

    if not source_last_sync_sha or not dest_commit_sha:
        logger.info("[VERBOSE] No previous sync history (GitOrigin-RevId) found between %s and %s for '%s' [%s]. Skipping history/divergence checks.", source_label, dest_label, target_name, dest_name)
        return True

    # --- Guard Check 1: Ancestry & History Check ---
    is_ancestor = check_ancestry_history(source_url, source_last_sync_sha, repo_cache)
    if not is_ancestor:
        raise AncestryRewrittenError(f"{target_name} [{dest_name}]", direction, source_label, source_url, source_last_sync_sha)

    # --- Guard Check 2: Concurrent Fork Check (Divergence Guard) ---
    diverged, source_new, dest_new = check_divergence(
        source_url, source_path, source_last_sync_sha,
        dest_url, dest_path, dest_commit_sha,
        repo_cache
    )
    if diverged:
        raise DivergenceError(f"{target_name} [{dest_name}]", direction, source_label, source_path, dest_label, dest_path, source_last_sync_sha)

    # --- Guard Check 3: Pre-Apply Patch Check ---
    if source_new:
        patch_ok, patch_err = check_pre_apply_patch(
            source_url, source_path, source_last_sync_sha,
            dest_url, dest_path,
            repo_cache
        )
        if not patch_ok:
            raise PatchApplyError(f"{target_name} [{dest_name}]", direction, source_label, dest_label, patch_err)

    logger.info("[VERBOSE] All pre-flight guard checks PASSED for '%s' [%s] (%s).", target_name, dest_name, direction)

    return True
