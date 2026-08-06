"""
Argparse configuration and CLI entrypoint handlers for hybrid-syncer.
"""

import argparse
import sys
import tempfile
from pathlib import Path

from hybrid_syncer.config import (
    STARTER_MANIFEST,
    check_manifest_health,
    clean_path,
    generate_sky_config,
    load_manifest,
)
from hybrid_syncer.copybara import run_workflows
from hybrid_syncer.errors import ExitCode, ManifestError, RED, RESET, SyncerError
from hybrid_syncer.git_utils import (
    check_ancestry_history,
    check_clean_workspace,
    check_repo_exists,
    find_effective_sync_point,
    find_last_sync_info,
    format_path_display,
    get_new_commits_count,
    is_file_mapped,
    is_remote_url,
    resolve_repo_url,
    run_git,
)
from hybrid_syncer.guards import run_preflight_guards
from hybrid_syncer.logger import setup_logging
from hybrid_syncer.temp_manager import TempRepoCache


def handle_init(args, repo_cache=None):
    config_path = args.config
    if config_path.exists() and not args.force:
        raise ManifestError(f"File '{config_path}' already exists. Use -f / --force to overwrite.")

    try:
        if config_path.parent:
            config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(STARTER_MANIFEST, encoding="utf-8")
        print(f"Initialized starter sync manifest at: {config_path}", file=sys.stderr)
    except OSError as e:
        raise ManifestError(f"Error writing manifest to '{config_path}': {e}")


def handle_generate(args, repo_cache=None):
    manifest = load_manifest(args.config)
    sky_content = generate_sky_config(manifest, target_filter=args.target, config_path=str(args.config))

    if args.output:
        try:
            if args.output.parent:
                args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(sky_content, encoding="utf-8")
            print(f"Generated Starlark configuration written to: {args.output}", file=sys.stderr)
        except OSError as e:
            raise ManifestError(f"Error writing output to '{args.output}': {e}")
    else:
        sys.stdout.write(sky_content + "\n")


def handle_execution(args, repo_cache=None):
    manifest = load_manifest(args.config)
    targets = manifest.get("targets", {})

    if not args.target:
        config_path = Path(args.config).resolve()
        available_targets = list(targets.keys())
        available_str = "\n".join(f"  - {t}" for t in available_targets) if available_targets else "  (No targets defined in manifest)"
        sample_target = available_targets[0] if available_targets else "<target-name>"
        msg = (
            f"Target specification (-t / --target) is mandatory for '{args.command}' command.\n"
            f"Configuration manifest file: {config_path}\n"
            f"Available target(s) in manifest:\n{available_str}\n\n"
            f"Sample usage:\n  python hybrid-syncer.py {args.command} -t {sample_target}"
        )
        raise ManifestError(msg)

    if args.target not in targets:
        available = ", ".join(targets.keys()) or "none"
        raise ManifestError(f"Target '{args.target}' not found in manifest. Available targets: {available}")

    target_names = [args.target]
    command = args.command  # 'push' or 'pull'

    workflow_last_revs = {}
    base_dir = Path(args.config).parent.resolve()
    default_hybrid_url = manifest.get("hybrid_repo", "./hybrid")

    for target_name in target_names:
        t_cfg = targets[target_name]
        dirs_to_check = [command] if command in ("push", "pull") else []

        for direction in dirs_to_check:
            run_preflight_guards(target_name, direction, t_cfg, manifest, str(args.config), args, repo_cache)

            # Resolve effective last synced SHA for Copybara
            origin_cfg = t_cfg.get("origin", {})
            hybrid_cfg = t_cfg.get("hybrid", {})

            origin_url = resolve_repo_url(origin_cfg.get("url", ""), base_dir)
            origin_path = clean_path(origin_cfg.get("path", ""))
            hybrid_url = resolve_repo_url(hybrid_cfg.get("url", default_hybrid_url), base_dir)
            hybrid_path = clean_path(hybrid_cfg.get("path", ""))

            if direction == "push":
                src_url, src_path, dst_url, dst_path = origin_url, origin_path, hybrid_url, hybrid_path
            else:
                src_url, src_path, dst_url, dst_path = hybrid_url, hybrid_path, origin_url, origin_path

            last_sync_sha, _ = find_effective_sync_point(src_url, src_path, dst_url, dst_path, repo_cache)
            dest_has_revid, _ = find_last_sync_info(dst_url, dst_path, repo_cache)
            if last_sync_sha and not dest_has_revid:
                workflow_last_revs[f"{target_name}-{direction}"] = last_sync_sha

    # Determine workflows to run
    workflows = []
    if command == "push":
        workflows = [f"{t}-push" for t in target_names]
    elif command == "pull":
        workflows = [f"{t}-pull" for t in target_names]

    sky_content = generate_sky_config(manifest, target_filter=args.target, config_path=str(args.config))

    # Manage working directory for .sky file
    if args.workdir:
        workdir = args.workdir
        workdir.mkdir(parents=True, exist_ok=True)
        sky_path = workdir / "copy.bara.sky"
        sky_path.write_text(sky_content, encoding="utf-8")
        run_workflows(workflows, sky_path, args, workflow_last_revs)
    else:
        with tempfile.TemporaryDirectory(prefix="hybrid_syncer_") as tmp_dir:
            sky_path = Path(tmp_dir) / "copy.bara.sky"
            sky_path.write_text(sky_content, encoding="utf-8")
            run_workflows(workflows, sky_path, args, workflow_last_revs)


def handle_status(args, repo_cache=None):
    manifest = load_manifest(args.config)
    targets = manifest.get("targets", {})
    base_dir = Path(args.config).parent.resolve()
    default_hybrid_url = manifest.get("hybrid_repo", "./hybrid")

    if getattr(args, "target", None):
        if args.target not in targets:
            available = ", ".join(targets.keys()) or "none"
            raise ManifestError(f"Target '{args.target}' not found in manifest. Available targets: {available}")
        targets_to_check = {args.target: targets[args.target]}
    else:
        targets_to_check = targets

    headers = ["Target", "Origin Path", "Hybrid Path", "Origin Status", "Hybrid Status", "Sync Status"]
    rows = []

    for t_name, t_cfg in targets_to_check.items():
        origin_cfg = t_cfg.get("origin", {})
        hybrid_cfg = t_cfg.get("hybrid", {})

        origin_url = resolve_repo_url(origin_cfg.get("url", ""), base_dir)
        origin_path = clean_path(origin_cfg.get("path", ""))
        hybrid_url = resolve_repo_url(hybrid_cfg.get("url", default_hybrid_url), base_dir)
        hybrid_path = clean_path(hybrid_cfg.get("path", ""))

        origin_path_display = format_path_display(origin_path)
        hybrid_path_display = format_path_display(hybrid_path)

        # Check repository existence
        origin_exists, _ = check_repo_exists(origin_url) if origin_url else (False, "")
        hybrid_exists, _ = check_repo_exists(hybrid_url) if hybrid_url else (False, "")

        if not origin_exists or not hybrid_exists:
            origin_status = "Missing Repo" if not origin_exists else "Clean"
            hybrid_status = "Missing Repo" if not hybrid_exists else "Clean"
            sync_status = "Repository Not Found"
            rows.append((t_name, origin_path_display, hybrid_path_display, origin_status, hybrid_status, sync_status))
            continue

        # Check uncommitted local changes
        origin_uncommitted = check_clean_workspace(origin_url)
        hybrid_uncommitted = check_clean_workspace(hybrid_url)

        source_last_sync_sha, dest_commit_sha = find_effective_sync_point(origin_url, origin_path, hybrid_url, hybrid_path, repo_cache)

        if not source_last_sync_sha or not dest_commit_sha:
            origin_status = f"Dirty ({len(origin_uncommitted)})" if origin_uncommitted else "Untracked"
            hybrid_status = f"Dirty ({len(hybrid_uncommitted)})" if hybrid_uncommitted else "Untracked"
            sync_status = "Untracked / No Sync History"
        else:
            ancestry_ok = check_ancestry_history(origin_url, source_last_sync_sha, repo_cache) and check_ancestry_history(hybrid_url, dest_commit_sha, repo_cache)

            origin_ahead = get_new_commits_count(origin_url, source_last_sync_sha, origin_path, repo_cache)
            hybrid_ahead = get_new_commits_count(hybrid_url, dest_commit_sha, hybrid_path, repo_cache)

            diverged = origin_ahead > 0 and hybrid_ahead > 0

            # Origin Status string
            orig_parts = []
            if origin_ahead > 0:
                orig_parts.append(f"Ahead ({origin_ahead})")
            if origin_uncommitted:
                orig_parts.append(f"Dirty ({len(origin_uncommitted)})" if not origin_ahead else "[Dirty]")
            origin_status = " ".join(orig_parts) if orig_parts else "Clean"

            # Hybrid Status string
            hyb_parts = []
            if hybrid_ahead > 0:
                hyb_parts.append(f"Ahead ({hybrid_ahead})")
            if hybrid_uncommitted:
                hyb_parts.append(f"Dirty ({len(hybrid_uncommitted)})" if not hybrid_ahead else "[Dirty]")
            hybrid_status = " ".join(hyb_parts) if hyb_parts else "Clean"

            # Sync Status
            if not ancestry_ok:
                sync_status = "⚠️ History Rewritten"
            elif diverged:
                sync_status = "⚠️ DIVERGED (Conflict)"
            elif origin_ahead > 0:
                sync_status = "Ready to Push"
            elif hybrid_ahead > 0:
                sync_status = "Ready to Pull"
            else:
                sync_status = "In Sync"

        rows.append((t_name, origin_path_display, hybrid_path_display, origin_status, hybrid_status, sync_status))

    # Calculate column widths
    min_widths = [15, 15, 15, 15, 15, 20]
    col_widths = [max(min_w, len(h)) for min_w, h in zip(min_widths, headers)]

    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    # Format table to stderr
    header_line = "  ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers)))
    sep_line = "-" * len(header_line)

    print(f"\n{header_line}", file=sys.stderr)
    print(sep_line, file=sys.stderr)
    for row in rows:
        row_line = "  ".join(f"{row[i]:<{col_widths[i]}}" for i in range(len(headers)))
        print(row_line, file=sys.stderr)
    print("", file=sys.stderr)

    if getattr(args, "check_unmapped", False):
        analyze_unmapped_origin_paths(manifest, base_dir, target_filter=getattr(args, "target", ""))


def analyze_unmapped_origin_paths(manifest: dict, base_dir: Path, target_filter: str = ""):
    targets = manifest.get("targets", {})
    if target_filter:
        if target_filter in targets:
            targets_to_check = {target_filter: targets[target_filter]}
        else:
            targets_to_check = targets
    else:
        targets_to_check = targets

    # Group mapped origin paths by origin repository URL
    origin_mapped = {}  # origin_url -> set(mapped_paths)
    origin_targets = {}  # origin_url -> list(target_names)

    for t_name, t_cfg in targets_to_check.items():
        o_cfg = t_cfg.get("origin", {})
        o_url = resolve_repo_url(o_cfg.get("url", ""), base_dir)
        o_path = clean_path(o_cfg.get("path", ""))

        if not o_url:
            continue
        if o_url not in origin_mapped:
            origin_mapped[o_url] = set()
            origin_targets[o_url] = []

        origin_mapped[o_url].add(o_path)
        origin_targets[o_url].append(t_name)

    print("\n🔍 Unmapped & Orphan Path Analysis (Origin Repositories):", file=sys.stderr)
    print("-" * 80, file=sys.stderr)

    total_unmapped_tracked = 0
    total_unmapped_local = 0

    for o_url, mapped_paths in origin_mapped.items():
        if not o_url or is_remote_url(o_url):
            continue
        repo_path = Path(o_url)
        if not repo_path.exists():
            continue

        # Check if bare
        actual_repo_path = repo_path
        rc, out, _ = run_git(["-C", str(repo_path), "rev-parse", "--is-bare-repository"])
        if rc == 0 and out.strip() == "true" and str(repo_path).endswith(".git"):
            sibling = Path(str(repo_path)[:-4])
            if sibling.is_dir():
                actual_repo_path = sibling

        # 1. Check tracked files in repository
        rc, out, _ = run_git(["-C", str(actual_repo_path), "ls-files"])
        tracked_files = [line.strip() for line in out.strip().splitlines() if line.strip()] if rc == 0 and out.strip() else []

        unmapped_tracked = [f for f in tracked_files if not is_file_mapped(f, mapped_paths)]

        # 2. Check uncommitted local changes
        uncommitted_lines = check_clean_workspace(str(actual_repo_path))
        unmapped_local = []
        for line in uncommitted_lines:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                file_p = parts[1].strip()
                if " -> " in file_p:
                    file_p = file_p.split(" -> ")[-1].strip()
                if not is_file_mapped(file_p, mapped_paths):
                    unmapped_local.append((parts[0], file_p))

        if unmapped_tracked or unmapped_local:
            total_unmapped_tracked += len(unmapped_tracked)
            total_unmapped_local += len(unmapped_local)

            display_paths = ", ".join([f"{p}/" if p else "." for p in sorted(mapped_paths)]) or "."
            t_names = ", ".join(origin_targets[o_url])

            print(f"Repository: {o_url} (Targets: {t_names})", file=sys.stderr)
            print(f"  Mapped Target Paths : {display_paths}", file=sys.stderr)

            if unmapped_tracked:
                print(f"  Tracked Orphan Files ({len(unmapped_tracked)}):", file=sys.stderr)
                for uf in unmapped_tracked[:10]:
                    print(f"    • {uf}", file=sys.stderr)
                if len(unmapped_tracked) > 10:
                    print(f"    ... and {len(unmapped_tracked) - 10} more tracked file(s).", file=sys.stderr)

            if unmapped_local:
                print(f"  Uncommitted Orphan Files ({len(unmapped_local)}):", file=sys.stderr)
                for st, uf in unmapped_local[:10]:
                    print(f"    • [{st}] {uf}", file=sys.stderr)
                if len(unmapped_local) > 10:
                    print(f"    ... and {len(unmapped_local) - 10} more uncommitted file(s).", file=sys.stderr)
            print("", file=sys.stderr)

    if total_unmapped_tracked == 0 and total_unmapped_local == 0:
        print(f"✔ No unmapped files or orphan paths detected across {len(origin_mapped)} origin repository(ies). All files match defined target paths.\n", file=sys.stderr)
    else:
        print(f"⚠️ Notice: Detected {total_unmapped_tracked} tracked and {total_unmapped_local} uncommitted orphan file(s) outside defined target paths.", file=sys.stderr)
        print("          These files are outside any target's origin.path and will NOT be synced to hybrid repository.\n", file=sys.stderr)


def handle_doctor(args, repo_cache=None):
    manifest = load_manifest(args.config)
    num_errors, _ = check_manifest_health(manifest, config_path=args.config)
    if num_errors > 0:
        raise ManifestError(f"Manifest health check failed with {num_errors} error(s).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hybrid-syncer",
        description="A lightweight wrapper to generate Starlark configs and execute Copybara syncs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("sync-manifest.yaml"),
        help="Path to sync manifest YAML"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose output and raw Copybara execution logs"
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Enable debug mode to show executed Git, Copybara, and low-level commands"
    )
    parser.add_argument(
        "-w", "--workdir",
        type=Path,
        default=None,
        help="Custom directory for temporary .sky files and working files"
    )

    subparsers = parser.add_subparsers(dest="command", required=True, title="subcommands")

    # Reusable flags for execution subcommands (push, pull)
    exec_parent = argparse.ArgumentParser(add_help=False)
    exec_parent.add_argument(
        "-t", "--target",
        type=str,
        help="Run sync only for a specific mapping name (e.g. repo-1-a)"
    )
    exec_parent.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Pass --dry-run to Copybara without modifying remotes"
    )
    exec_parent.add_argument(
        "--init-history",
        action="store_true",
        help="Pass --init-history to Copybara for first-time migration setup"
    )
    exec_parent.add_argument(
        "--skip-guards",
        action="store_true",
        help="Skip pre-flight safety circuit breaker guard checks"
    )

    # Subcommand: push
    push_parser = subparsers.add_parser(
        "push",
        parents=[exec_parent],
        help="Sync changes from origin repositories -> hybrid repo"
    )
    push_parser.set_defaults(func=handle_execution)

    # Subcommand: pull
    pull_parser = subparsers.add_parser(
        "pull",
        parents=[exec_parent],
        help="Sync changes from hybrid repo -> origin repositories"
    )
    pull_parser.set_defaults(func=handle_execution)

    # Subcommand: status
    status_parser = subparsers.add_parser(
        "status",
        help="Show synchronization state and workspace status for all targets"
    )
    status_parser.add_argument(
        "-t", "--target",
        type=str,
        help="Filter status check to a specific target"
    )
    status_parser.add_argument(
        "--check-unmapped",
        action="store_true",
        help="Analyze origin repositories for unmapped/orphan files outside defined target paths"
    )
    status_parser.set_defaults(func=handle_status)

    # Subcommand: doctor / detector
    doctor_parser = subparsers.add_parser(
        "doctor",
        aliases=["detector"],
        help="Run manifest health check to detect path clashes, overlaps, and missing repositories"
    )
    doctor_parser.set_defaults(func=handle_doctor)

    # Subcommand: generate
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate copybara.sky configuration file without executing sync"
    )
    gen_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output path for .sky file (prints to stdout if omitted)"
    )
    gen_parser.add_argument(
        "-t", "--target",
        type=str,
        help="Filter generation to specific target"
    )
    gen_parser.set_defaults(func=handle_generate)

    # Subcommand: init
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a starter sync-manifest.yaml"
    )
    init_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force overwrite of existing sync-manifest.yaml"
    )
    init_parser.set_defaults(func=handle_init)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    debug = getattr(args, "debug", False)
    verbose = getattr(args, "verbose", False) or debug
    setup_logging(verbose=verbose, debug=debug)

    try:
        with TempRepoCache() as repo_cache:
            args.func(args, repo_cache)

    except SyncerError as e:
        print(f"\n{RED}❌ [{e.category}]{RESET} {e.message}", file=sys.stderr)
        sys.exit(e.exit_code)

    except KeyboardInterrupt:
        print("\n\nOperation aborted by user.", file=sys.stderr)
        sys.exit(ExitCode.GENERAL_ERROR)

    except Exception as e:
        print(f"\n{RED}❌ [UNHANDLED ERROR]{RESET} An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(ExitCode.GENERAL_ERROR)


if __name__ == "__main__":
    main()
