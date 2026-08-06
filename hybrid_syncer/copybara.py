"""
Subprocess execution wrapper for Copybara workflows.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from hybrid_syncer.errors import CopybaraExecutionError
from hybrid_syncer.git_utils import IS_WINDOWS, normalize_path_for_git


def find_copybara_cmd() -> tuple[list[str] | None, str]:
    """
    Locates the Copybara binary or executable jar cross-platform and identifies the resolution mode.
    
    Resolution Order:
    1. Environment variables: COPYBARA_PATH or COPYBARA_JAR.
    2. System PATH via shutil.which ('copybara', 'copybara.bat', 'copybara.cmd', 'copybara.exe').
    3. Workspace relative 'bin' directory (bin/copybara, bin/copybara.bat, bin/copybara.ps1, bin/copybara_deploy.jar).
    4. Well-known fallback paths (e.g. C:\\tools\\copybara\\bin\\copybara_deploy.jar, /tools/copybara/bin/copybara_deploy.jar).

    Returns a tuple of (command_list, resolution_mode_string).
    """
    # 1. Environment variables
    env_path = os.getenv("COPYBARA_PATH")
    if env_path and Path(env_path).exists():
        return [env_path], f"Environment Variable (COPYBARA_PATH: {env_path})"

    env_jar = os.getenv("COPYBARA_JAR")
    if env_jar and Path(env_jar).exists():
        return ["java", "-jar", str(Path(env_jar))], f"Environment Variable (COPYBARA_JAR: {env_jar})"

    # 2. System PATH
    candidates = ["copybara"]
    if IS_WINDOWS:
        candidates.extend(["copybara.bat", "copybara.cmd", "copybara.exe"])

    for candidate in candidates:
        which_path = shutil.which(candidate)
        if which_path:
            return [which_path], f"System PATH ({which_path})"

    # 3. Workspace relative 'bin/' directory
    project_root = Path(__file__).resolve().parent.parent
    bin_dir = project_root / "bin"

    if bin_dir.exists():
        if IS_WINDOWS:
            for win_wrapper in ["copybara.bat", "copybara.cmd", "copybara.exe"]:
                wrapper_path = bin_dir / win_wrapper
                if wrapper_path.exists():
                    return [str(wrapper_path)], f"Workspace Local Wrapper ({wrapper_path})"

        bash_wrapper = bin_dir / "copybara"
        if bash_wrapper.exists() and (not IS_WINDOWS or shutil.which("bash")):
            return [str(bash_wrapper)], f"Workspace Local Wrapper ({bash_wrapper})"

        jar_in_bin = bin_dir / "copybara_deploy.jar"
        if jar_in_bin.exists():
            return ["java", "-jar", str(jar_in_bin)], f"Workspace Local Jar ({jar_in_bin})"

    # 4. Standard fallback paths
    fallback_jars = [
        "C:\\tools\\copybara\\bin\\copybara_deploy.jar",
        "C:\\tools\\copybara\\copybara_deploy.jar",
        "/tools/copybara/bin/copybara_deploy.jar",
        "/usr/local/bin/copybara_deploy.jar",
    ]
    for fallback in fallback_jars:
        if Path(fallback).exists():
            return ["java", "-jar", fallback], f"Fallback System Path ({fallback})"

    return None, "Not Found (Dry-run / Notice mode enabled)"


def run_workflows(workflows, sky_path: Path, args, workflow_last_revs=None):
    copybara_cmd, resolution_source = find_copybara_cmd()
    workflow_last_revs = workflow_last_revs or {}

    sky_path_str = normalize_path_for_git(sky_path)

    if args.verbose:
        print(f"[VERBOSE] Copybara binary resolution mode: {resolution_source}", file=sys.stderr)
        if copybara_cmd:
            print(f"[VERBOSE] Copybara command line: {' '.join(copybara_cmd)}", file=sys.stderr)
        print(f"[VERBOSE] Prepared Starlark spec at: {sky_path_str}", file=sys.stderr)
        print(f"[VERBOSE] Target workflows to run: {', '.join(workflows)}", file=sys.stderr)

    if not copybara_cmd:
        print(f"[NOTICE] Copybara binary 'copybara' or 'copybara_deploy.jar' was not found.", file=sys.stderr)
        print(f"[NOTICE] Resolution status: {resolution_source}", file=sys.stderr)
        print(f"Temporary Starlark file generated at: {sky_path_str}", file=sys.stderr)
        print("Would execute the following workflows:", file=sys.stderr)
        for wf in workflows:
            dry_flag = " --dry-run" if args.dry_run else ""
            init_flag = " --init-history" if getattr(args, "init_history", False) else ""
            last_rev_str = f" {workflow_last_revs.get(wf)}" if workflow_last_revs.get(wf) else ""
            print(f"  $ copybara migrate {sky_path_str} {wf}{last_rev_str}{dry_flag}{init_flag}", file=sys.stderr)
        return

    for wf in workflows:
        cmd = list(copybara_cmd) + ["migrate", sky_path_str, wf]

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
            use_shell = IS_WINDOWS and (cmd[0].endswith(".bat") or cmd[0].endswith(".cmd"))
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE if not args.verbose else None,
                stderr=subprocess.PIPE if not args.verbose else None,
                text=True,
                shell=use_shell
            )
            if result.returncode != 0:
                stdout_str = result.stdout or ""
                stderr_str = result.stderr or ""
                raise CopybaraExecutionError(wf, result.returncode, stdout_str, stderr_str)
        except CopybaraExecutionError:
            raise
        except (subprocess.SubprocessError, OSError) as e:
            raise CopybaraExecutionError(wf, -1, "", str(e))
