#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

def handle_init(args):
    print(f"Initializing skeleton config at: {args.config}")
    # TODO: Write starter sync-manifest.yaml

def handle_generate(args):
    print(f"Loading config: {args.config}")
    print(f"Generating Starlark spec (Target filter: {args.target or 'ALL'})...")
    # TODO: Parse YAML, render Starlark template
    if args.output:
        print(f"Written to {args.output}")
    else:
        print("# --- Generated copybara.sky ---")

def handle_execution(args):
    """Handles push, pull, and sync subcommands."""
    command = args.command  # 'push', 'pull', or 'sync'
    print(f"Action: {command.upper()}")
    print(f"Config: {args.config}")
    print(f"Target filter: {args.target or 'ALL'}")
    print(f"Dry Run: {args.dry_run}")
    
    # 1. Parse manifest
    # 2. Generate temporary copybara.sky
    # 3. Call `copybara` sub-process with target workflow names
    # Example subprocess call:
    # copybara <path/to/generated.sky> <workflow_name> --dry-run

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

    subparsers = parser.add_subparsers(dest="command", required=True, title="subcommands")

    # Reusable flags for execution subcommands (push, pull, sync)
    exec_parent = argparse.ArgumentParser(add_help=False)
    exec_parent.add_argument(
        "-t", "--target",
        type=str,
        help="Run sync only for a specific mapping name (e.g. repo-1-a)"
    )
    exec_parent.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Pass --dry-run / --git-noop to Copybara without modifying remotes"
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

    # Subcommand: sync
    sync_parser = subparsers.add_parser(
        "sync",
        parents=[exec_parent],
        help="Perform bi-directional sync (push followed by pull)"
    )
    sync_parser.add_argument(
        "--strategy",
        choices=["push-first", "pull-first"],
        default="push-first",
        help="Order of sync operations"
    )
    sync_parser.set_defaults(func=handle_execution)

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
        help="Initialize a skeleton sync-manifest.yaml"
    )
    init_parser.set_defaults(func=handle_init)

    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
