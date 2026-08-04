"""
Subprocess execution wrapper for Copybara workflows.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def run_workflows(workflows, sky_path: Path, args, workflow_last_revs=None):
    copybara_bin = shutil.which("copybara")
    workflow_last_revs = workflow_last_revs or {}

    if args.verbose:
        print(f"[VERBOSE] Prepared Starlark spec at: {sky_path}")
        print(f"[VERBOSE] Target workflows to run: {', '.join(workflows)}")

    if not copybara_bin:
        print(f"[NOTICE] Copybara binary 'copybara' was not found in PATH.")
        print(f"Temporary Starlark file generated at: {sky_path}")
        print("Would execute the following workflows:")
        for wf in workflows:
            dry_flag = " --dry-run" if args.dry_run else ""
            init_flag = " --init-history" if getattr(args, "init_history", False) else ""
            last_rev_str = f" {workflow_last_revs.get(wf)}" if workflow_last_revs.get(wf) else ""
            print(f"  $ copybara migrate {sky_path} {wf}{last_rev_str}{dry_flag}{init_flag}")
        return

    for wf in workflows:
        cmd = [copybara_bin, "migrate", str(sky_path), wf]

        # Append starting revision if a previous sync point exists and init_history is not set
        last_rev = workflow_last_revs.get(wf)
        if last_rev and not getattr(args, "init_history", False):
            cmd.append(last_rev)

        if args.dry_run:
            cmd.append("--dry-run")
        if getattr(args, "init_history", False):
            cmd.append("--init-history")

        if args.verbose:
            print(f"[VERBOSE] Executing: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            stdout=None if args.verbose else subprocess.PIPE,
            stderr=None if args.verbose else subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            print(f"Error executing Copybara workflow '{wf}' (exit code {result.returncode})", file=sys.stderr)
            if not args.verbose:
                if result.stdout:
                    print(f"Stdout:\n{result.stdout}", file=sys.stderr)
                if result.stderr:
                    print(f"Stderr:\n{result.stderr}", file=sys.stderr)
            sys.exit(result.returncode)
