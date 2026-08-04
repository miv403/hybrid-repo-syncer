"""
Subprocess execution wrapper for Copybara workflows.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from hybrid_syncer.errors import CopybaraExecutionError


def run_workflows(workflows, sky_path: Path, args, workflow_last_revs=None):
    copybara_bin = shutil.which("copybara")
    workflow_last_revs = workflow_last_revs or {}

    if args.verbose:
        print(f"[VERBOSE] Prepared Starlark spec at: {sky_path}", file=sys.stderr)
        print(f"[VERBOSE] Target workflows to run: {', '.join(workflows)}", file=sys.stderr)

    if not copybara_bin:
        print(f"[NOTICE] Copybara binary 'copybara' was not found in PATH.", file=sys.stderr)
        print(f"Temporary Starlark file generated at: {sky_path}", file=sys.stderr)
        print("Would execute the following workflows:", file=sys.stderr)
        for wf in workflows:
            dry_flag = " --dry-run" if args.dry_run else ""
            init_flag = " --init-history" if getattr(args, "init_history", False) else ""
            last_rev_str = f" {workflow_last_revs.get(wf)}" if workflow_last_revs.get(wf) else ""
            print(f"  $ copybara migrate {sky_path} {wf}{last_rev_str}{dry_flag}{init_flag}", file=sys.stderr)
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
            print(f"[VERBOSE] Executing: {' '.join(cmd)}", file=sys.stderr)

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE if not args.verbose else None,
                stderr=subprocess.PIPE if not args.verbose else None,
                text=True
            )
            if result.returncode != 0:
                stdout_str = result.stdout or ""
                stderr_str = result.stderr or ""
                raise CopybaraExecutionError(wf, result.returncode, stdout_str, stderr_str)
        except CopybaraExecutionError:
            raise
        except (subprocess.SubprocessError, OSError) as e:
            raise CopybaraExecutionError(wf, -1, "", str(e))
