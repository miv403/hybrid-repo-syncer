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
from hybrid_syncer.logger import logger


def format_copybara_cmd(p: Path) -> list[str]:
    suffix = p.suffix.lower()
    if suffix == ".jar":
        return ["java", "-jar", str(p)]
    elif suffix == ".ps1":
        if shutil.which("pwsh"):
            return ["pwsh", "-File", str(p)]
        elif shutil.which("powershell"):
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(p)]
        else:
            return [str(p)]
    else:
        return [str(p)]


def find_copybara_cmd(config_copybara_path: str | Path | None = None, base_dir: Path | None = None) -> tuple[list[str] | None, str]:
    """
    Locates the Copybara binary or executable jar cross-platform and identifies the resolution mode.
    
    Resolution Order:
    0. Manifest configuration: copybara_path defined in sync-manifest.yaml.
    1. Environment variables: COPYBARA_PATH or COPYBARA_JAR.
    2. System PATH via shutil.which ('copybara', 'copybara.bat', 'copybara.cmd', 'copybara.exe', 'copybara.ps1').
    3. Workspace relative 'bin' directory (bin/copybara, bin/copybara.bat, bin/copybara.ps1, bin/copybara_deploy.jar).
    4. Well-known fallback paths (e.g. C:\\tools\\copybara\\bin\\copybara_deploy.jar, /tools/copybara/bin/copybara_deploy.jar).

    Returns a tuple of (command_list, resolution_mode_string).
    """
    # 0. Manifest configuration
    if config_copybara_path:
        cp_path = Path(config_copybara_path)
        if not cp_path.is_absolute() and base_dir:
            resolved_cp = (base_dir / cp_path).resolve()
        else:
            resolved_cp = cp_path.resolve()

        if resolved_cp.exists() and resolved_cp.is_file():
            cmd = format_copybara_cmd(resolved_cp)
            return cmd, f"Manifest Configuration (copybara_path: {config_copybara_path})"
        else:
            logger.info("[NOTICE] Manifest copybara_path '%s' (resolved: '%s') was not found on disk. Falling back to default resolution options.", config_copybara_path, resolved_cp)

    # 1. Environment variables
    env_path = os.getenv("COPYBARA_PATH")
    if env_path:
        p_env = Path(env_path)
        if p_env.exists() and p_env.is_file():
            return format_copybara_cmd(p_env), f"Environment Variable (COPYBARA_PATH: {env_path})"

    env_jar = os.getenv("COPYBARA_JAR")
    if env_jar and Path(env_jar).exists():
        return ["java", "-jar", str(Path(env_jar))], f"Environment Variable (COPYBARA_JAR: {env_jar})"

    # 2. System PATH
    candidates = ["copybara"]
    if IS_WINDOWS:
        candidates.extend(["copybara.bat", "copybara.cmd", "copybara.exe", "copybara.ps1"])

    for candidate in candidates:
        which_path = shutil.which(candidate)
        if which_path:
            return format_copybara_cmd(Path(which_path)), f"System PATH ({which_path})"

    # 3. Workspace relative 'bin/' directory
    project_root = Path(__file__).resolve().parent.parent
    bin_dir = project_root / "bin"

    if bin_dir.exists():
        if IS_WINDOWS:
            for win_wrapper in ["copybara.bat", "copybara.cmd", "copybara.exe", "copybara.ps1"]:
                wrapper_path = bin_dir / win_wrapper
                if wrapper_path.exists():
                    return format_copybara_cmd(wrapper_path), f"Workspace Local Wrapper ({wrapper_path})"

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


def run_workflows(workflows, sky_path: Path, args, workflow_last_revs=None, copybara_path=None, base_dir=None):
    copybara_cmd, resolution_source = find_copybara_cmd(config_copybara_path=copybara_path, base_dir=base_dir)
    workflow_last_revs = workflow_last_revs or {}

    sky_path_str = normalize_path_for_git(sky_path)

    logger.info("[VERBOSE] Copybara binary resolution mode: %s", resolution_source)
    if copybara_cmd:
        logger.debug("Copybara command line: %s", " ".join(copybara_cmd))
    logger.info("[VERBOSE] Prepared Starlark spec at: %s", sky_path_str)
    logger.info("[VERBOSE] Target workflows to run: %s", ", ".join(workflows))

    if not copybara_cmd:
        logger.info("[NOTICE] Copybara binary 'copybara' or 'copybara_deploy.jar' was not found.")
        logger.info("[NOTICE] Resolution status: %s", resolution_source)
        logger.info("Temporary Starlark file generated at: %s", sky_path_str)
        logger.info("Would execute the following workflows:")
        for wf in workflows:
            dry_flag = " --dry-run" if args.dry_run else ""
            init_flag = " --init-history" if getattr(args, "init_history", False) else ""
            last_rev_str = f" {workflow_last_revs.get(wf)}" if workflow_last_revs.get(wf) else ""
            logger.info("  $ copybara migrate %s %s%s%s%s", sky_path_str, wf, last_rev_str, dry_flag, init_flag)
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

        logger.debug("Executing Copybara command: %s", " ".join(cmd))

        try:
            use_shell = IS_WINDOWS and (cmd[0].endswith(".bat") or cmd[0].endswith(".cmd"))
            is_verbose = getattr(args, "verbose", False) or getattr(args, "debug", False)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=use_shell,
                bufsize=1
            )

            stdout_lines = []
            stderr_lines = []

            def stream_output(pipe, lines_list, stream_dest):
                for line in iter(pipe.readline, ''):
                    lines_list.append(line)
                    if stream_dest:
                        stream_dest.write(line)
                        stream_dest.flush()
                pipe.close()

            import threading
            t_out = threading.Thread(target=stream_output, args=(process.stdout, stdout_lines, sys.stdout if is_verbose else None))
            t_err = threading.Thread(target=stream_output, args=(process.stderr, stderr_lines, sys.stderr if is_verbose else None))

            t_out.start()
            t_err.start()

            returncode = process.wait()
            t_out.join()
            t_err.join()

            stdout_str = "".join(stdout_lines)
            stderr_str = "".join(stderr_lines)

            if returncode != 0:
                raise CopybaraExecutionError(wf, returncode, stdout_str, stderr_str)
        except CopybaraExecutionError:
            raise
        except (subprocess.SubprocessError, OSError) as e:
            raise CopybaraExecutionError(wf, -1, "", str(e))
