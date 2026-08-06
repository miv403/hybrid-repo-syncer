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
    sky_content = generate_sky_config(
        manifest,
        target_filter=getattr(args, "target", "") or "",
        dest_filter=getattr(args, "destination", "") or "",
        config_path=str(args.config)
    )

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
        target_lines = []
        for t_name, t_cfg in targets.items():
            dests = t_cfg.get("destinations", [])
            if dests:
                d_info = ", ".join(f"{d['name']} (Repo: {d['repo']}, Path: {d['path'] or '.'})" for d in dests)
                target_lines.append(f"  - {t_name} (Destinations: {d_info})")
            else:
                target_lines.append(f"  - {t_name} (No destinations defined)")
        available_str = "\n".join(target_lines) if target_lines else "  (No targets defined in manifest)"
        sample_target = list(targets.keys())[0] if targets else "<target-name>"
        sample_dest = targets[sample_target].get("destinations", [{}])[0].get("name", "main") if (targets and targets[sample_target].get("destinations")) else "main"
        msg = (
            f"Target specification (-t / --target) is mandatory for '{args.command}' command.\n"
            f"Configuration manifest file: {config_path}\n"
            f"Available target(s) and destination(s) in manifest:\n{available_str}\n\n"
            f"Sample usage:\n  python hybrid-syncer.py {args.command} -t {sample_target} -d {sample_dest}"
        )
        raise ManifestError(msg)

    if args.target not in targets:
        available = ", ".join(targets.keys()) or "none"
        raise ManifestError(f"Target '{args.target}' not found in manifest. Available targets: {available}")

    t_cfg = targets[args.target]
    destinations = t_cfg.get("destinations", [])

    if not getattr(args, "destination", None):
        config_path = Path(args.config).resolve()
        d_str = "\n".join(f"  - {d['name']} (Repo: {d['repo']}, Path: {d['path'] or '.'})" for d in destinations) if destinations else "  (No destinations defined)"
        sample_dest = destinations[0]['name'] if destinations else "<destination-name>"
        msg = (
            f"Destination specification (-d / --destination) is mandatory for '{args.command}' command.\n"
            f"Configuration manifest file: {config_path}\n"
            f"Available destination(s) for target '{args.target}':\n{d_str}\n\n"
            f"Sample usage:\n  python hybrid-syncer.py {args.command} -t {args.target} -d {sample_dest}"
        )
        raise ManifestError(msg)

    dest_name = args.destination
    selected_dest = next((d for d in destinations if d.get("name") == dest_name), None)
    if not selected_dest:
        available_d = ", ".join(d["name"] for d in destinations) or "none"
        raise ManifestError(f"Destination '{dest_name}' not found for target '{args.target}'. Available destinations: {available_d}")

    command = args.command  # 'push' or 'pull'
    base_dir = Path(args.config).parent.resolve()

    run_preflight_guards(args.target, dest_name, command, t_cfg, manifest, str(args.config), args, repo_cache)

    origin_cfg = t_cfg.get("origin", {})
    origin_url = resolve_repo_url(origin_cfg.get("url", ""), base_dir)
    origin_path = clean_path(origin_cfg.get("path", ""))

    dest_url = resolve_repo_url(selected_dest.get("url", ""), base_dir)
    dest_path = clean_path(selected_dest.get("path", ""))

    if command == "push":
        src_url, src_path, dst_url, dst_path = origin_url, origin_path, dest_url, dest_path
    else:
        src_url, src_path, dst_url, dst_path = dest_url, dest_path, origin_url, origin_path

    workflow_last_revs = {}
    last_sync_sha, _ = find_effective_sync_point(src_url, src_path, dst_url, dst_path, repo_cache)
    dest_has_revid, _ = find_last_sync_info(dst_url, dst_path, repo_cache)

    wf_suffix = "push" if (len(destinations) == 1 and dest_name == "main") else f"{dest_name}-push"
    wf_pull_suffix = "pull" if (len(destinations) == 1 and dest_name == "main") else f"{dest_name}-pull"
    target_wf_name = f"{args.target}-{wf_suffix}" if command == "push" else f"{args.target}-{wf_pull_suffix}"

    if last_sync_sha and not dest_has_revid:
        workflow_last_revs[target_wf_name] = last_sync_sha

    workflows = [target_wf_name]

    sky_content = generate_sky_config(manifest, target_filter=args.target, dest_filter=dest_name, config_path=str(args.config))

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

    if getattr(args, "target", None):
        if args.target not in targets:
            available = ", ".join(targets.keys()) or "none"
            raise ManifestError(f"Target '{args.target}' not found in manifest. Available targets: {available}")
        targets_to_check = {args.target: targets[args.target]}
    else:
        targets_to_check = targets

    headers = ["Target", "Destination", "Origin Path", "Dest Path", "Origin Status", "Dest Status", "Sync Status"]
    rows = []

    for t_name, t_cfg in targets_to_check.items():
        origin_cfg = t_cfg.get("origin", {})
        origin_url = resolve_repo_url(origin_cfg.get("url", ""), base_dir)
        origin_path = clean_path(origin_cfg.get("path", ""))
        origin_path_display = format_path_display(origin_path)

        destinations = t_cfg.get("destinations", [])
        if getattr(args, "destination", None):
            destinations = [d for d in destinations if d.get("name") == args.destination]

        for d in destinations:
            d_name = d.get("name", "main")
            dest_url = resolve_repo_url(d.get("url", ""), base_dir)
            dest_path = clean_path(d.get("path", ""))
            dest_path_display = format_path_display(dest_path)

            origin_exists, _ = check_repo_exists(origin_url) if origin_url else (False, "")
            dest_exists, _ = check_repo_exists(dest_url) if dest_url else (False, "")

            if not origin_exists or not dest_exists:
                origin_status = "Missing Repo" if not origin_exists else "Clean"
                dest_status = "Missing Repo" if not dest_exists else "Clean"
                sync_status = "Repository Not Found"
                rows.append((t_name, d_name, origin_path_display, dest_path_display, origin_status, dest_status, sync_status))
                continue

            origin_uncommitted = check_clean_workspace(origin_url)
            dest_uncommitted = check_clean_workspace(dest_url)

            source_last_sync_sha, dest_commit_sha = find_effective_sync_point(origin_url, origin_path, dest_url, dest_path, repo_cache)

            if not source_last_sync_sha or not dest_commit_sha:
                origin_status = f"Dirty ({len(origin_uncommitted)})" if origin_uncommitted else "Untracked"
                dest_status = f"Dirty ({len(dest_uncommitted)})" if dest_uncommitted else "Untracked"
                sync_status = "Untracked / No Sync History"
            else:
                ancestry_ok = check_ancestry_history(origin_url, source_last_sync_sha, repo_cache) and check_ancestry_history(dest_url, dest_commit_sha, repo_cache)

                origin_ahead = get_new_commits_count(origin_url, source_last_sync_sha, origin_path, repo_cache)
                dest_ahead = get_new_commits_count(dest_url, dest_commit_sha, dest_path, repo_cache)

                diverged = origin_ahead > 0 and dest_ahead > 0

                orig_parts = []
                if origin_ahead > 0:
                    orig_parts.append(f"Ahead ({origin_ahead})")
                if origin_uncommitted:
                    orig_parts.append(f"Dirty ({len(origin_uncommitted)})" if not origin_ahead else "[Dirty]")
                origin_status = " ".join(orig_parts) if orig_parts else "Clean"

                dest_parts = []
                if dest_ahead > 0:
                    dest_parts.append(f"Ahead ({dest_ahead})")
                if dest_uncommitted:
                    dest_parts.append(f"Dirty ({len(dest_uncommitted)})" if not dest_ahead else "[Dirty]")
                dest_status = " ".join(dest_parts) if dest_parts else "Clean"

                if not ancestry_ok:
                    sync_status = "⚠️ History Rewritten"
                elif diverged:
                    sync_status = "⚠️ DIVERGED (Conflict)"
                elif origin_ahead > 0:
                    sync_status = "Ready to Push"
                elif dest_ahead > 0:
                    sync_status = "Ready to Pull"
                else:
                    sync_status = "In Sync"

            rows.append((t_name, d_name, origin_path_display, dest_path_display, origin_status, dest_status, sync_status))

    # Calculate column widths
    min_widths = [12, 12, 12, 12, 15, 15, 20]
    col_widths = [max(min_w, len(h)) for min_w, h in zip(min_widths, headers)]

    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    header_line = "  ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers)))
    sep_line = "-" * len(header_line)

    print(f"\n{header_line}", file=sys.stderr)
    print(sep_line, file=sys.stderr)
    for row in rows:
        row_line = "  ".join(f"{row[i]:<{col_widths[i]}}" for i in range(len(headers)))
        print(row_line, file=sys.stderr)
    print("", file=sys.stderr)

    if getattr(args, "check_unmapped", False):
        handle_unmapped_analysis(manifest, args, repo_cache)


def handle_unmapped_analysis(manifest: dict, args, repo_cache=None):
    targets = manifest.get("targets", {})
    base_dir = Path(args.config).parent.resolve()

    origin_mapped = {}  # o_url -> set of relative mapped target paths
    origin_targets = {}  # o_url -> list of target names

    for t_name, t_cfg in targets.items():
        o_url = resolve_repo_url(t_cfg.get("origin", {}).get("url", ""), base_dir)
        o_path = clean_path(t_cfg.get("origin", {}).get("path", ""))

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
        exists, _ = check_repo_exists(o_url)
        if not exists:
            continue

        rc_t, out_t, _ = run_git(["-C", o_url, "ls-tree", "--name-only", "-r", "HEAD"])
        if rc_t != 0:
            rc_t, out_t, _ = run_git(["-C", o_url, "ls-files"])
        tracked_files = [f.strip() for f in out_t.splitlines() if f.strip()] if rc_t == 0 else []

        unmapped_tracked = [f for f in tracked_files if not is_file_mapped(f, mapped_paths)]
        raw_uncommitted = check_clean_workspace(o_url)
        parsed_uncommitted = [(line[:2].strip(), line[3:].strip()) for line in raw_uncommitted if len(line) >= 3]
        unmapped_local = [(st, f) for st, f in parsed_uncommitted if not is_file_mapped(f, mapped_paths)]

        total_unmapped_tracked += len(unmapped_tracked)
        total_unmapped_local += len(unmapped_local)

        t_names = ", ".join(origin_targets[o_url])
        display_paths = ", ".join(f"'{p}/'" if p else "root" for p in sorted(mapped_paths))

        if unmapped_tracked or unmapped_local:
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


def handle_list(args, repo_cache=None):
    manifest = load_manifest(args.config)
    targets = manifest.get("targets", {})
    config_path = Path(args.config).resolve()

    target_name = getattr(args, "target_pos", None) or getattr(args, "target_flag", None) or getattr(args, "target", None)

    if target_name:
        if target_name not in targets:
            available_targets = list(targets.keys())
            available_str = "\n".join(f"  - {t}" for t in available_targets) if available_targets else "  (No targets defined in manifest)"
            msg = (
                f"Target '{target_name}' not found in manifest.\n"
                f"Configuration manifest file: {config_path}\n"
                f"Available target(s) in manifest:\n{available_str}"
            )
            raise ManifestError(msg)

        t_cfg = targets[target_name]
        destinations = t_cfg.get("destinations", [])
        origin_cfg = t_cfg.get("origin", {})

        print(f"\nTarget: {target_name}", file=sys.stdout)
        print(f"  Origin Repo : {origin_cfg.get('repo', 'N/A')} ({origin_cfg.get('url', '')})", file=sys.stdout)
        print(f"  Origin Path : {origin_cfg.get('path') or '.'}", file=sys.stdout)
        print(f"  Destinations ({len(destinations)}):", file=sys.stdout)
        if destinations:
            for d in destinations:
                d_name = d.get("name", "main")
                d_repo = d.get("repo", "hybrid")
                d_url = d.get("url", "")
                d_path = d.get("path") or "."
                d_branch = d.get("branch", "")
                print(f"    • {d_name}:", file=sys.stdout)
                print(f"        Repo   : {d_repo} ({d_url})", file=sys.stdout)
                print(f"        Path   : {d_path}", file=sys.stdout)
                if d_branch:
                    print(f"        Branch : {d_branch}", file=sys.stdout)
        else:
            print("    (No destinations defined)", file=sys.stdout)
        print("", file=sys.stdout)

    else:
        print(f"\nAvailable Target(s) and Destination(s) in manifest ({config_path}):", file=sys.stdout)
        print("-" * 80, file=sys.stdout)
        if not targets:
            print("  (No targets defined in manifest)", file=sys.stdout)
        else:
            for t_name, t_cfg in targets.items():
                origin_cfg = t_cfg.get("origin", {})
                destinations = t_cfg.get("destinations", [])
                d_str = "\n".join(f"        • {d['name']} (Repo: {d['repo']}, Path: {d['path'] or '.'})" for d in destinations) if destinations else "        (No destinations defined)"
                print(f"  Target: {t_name}", file=sys.stdout)
                print(f"      Origin       : Repo: {origin_cfg.get('repo', 'N/A')}, Path: {origin_cfg.get('path') or '.'}", file=sys.stdout)
                print(f"      Destinations :\n{d_str}", file=sys.stdout)
                print("", file=sys.stdout)


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
        "-d", "--destination",
        type=str,
        help="Run sync for a specific destination name (e.g. main)"
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
        "-d", "--destination",
        type=str,
        help="Filter status check to a specific destination name"
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
    gen_parser.add_argument(
        "-d", "--destination",
        type=str,
        help="Filter generation to specific destination"
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

    # Subcommand: list / targets
    list_parser = subparsers.add_parser(
        "list",
        aliases=["targets"],
        help="List available target mappings or inspect destinations for a specific target"
    )
    list_parser.add_argument(
        "target_pos",
        nargs="?",
        default=None,
        metavar="TARGET",
        help="Target name to inspect destinations for (optional)"
    )
    list_parser.add_argument(
        "-t", "--target",
        type=str,
        dest="target_flag",
        help="Target name to inspect destinations for"
    )
    list_parser.set_defaults(func=handle_list)

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
