"""
Error handling, ExitCode schema, and custom exceptions for hybrid-syncer.
"""

from enum import IntEnum

RED = "\033[91m\033[1m"
RESET = "\033[0m"


class ExitCode(IntEnum):
    SUCCESS = 0
    GENERAL_ERROR = 1             # Unhandled exceptions, CLI parsing errors
    CONFIG_ERROR = 2              # Invalid sync-manifest.yaml, missing targets, path clashes
    DIRTY_WORKSPACE = 3           # Pre-flight Guard 0: Uncommitted changes in working tree
    ANCESTRY_REWRITTEN = 4        # Pre-flight Guard 1: History rewritten / rebased
    DIVERGENCE_DETECTED = 5       # Pre-flight Guard 2: Concurrent commits on both remotes
    PATCH_APPLY_FAILED = 6        # Pre-flight Guard 3: Patch check failed
    COPYBARA_EXECUTION_ERROR = 7  # Copybara binary returned a non-zero exit code
    REPO_ACCESS_ERROR = 8         # Remote/local repo missing or inaccessible


COPYBARA_EXIT_CODES = {
    0: ("SUCCESS", "Everything went well and the migration was successful."),
    1: ("COMMAND_LINE_ERROR", "An error parsing the command line (wrong arguments/options)."),
    2: ("CONFIGURATION_ERROR", "An error in the configuration, flag values, or user input."),
    3: ("REPOSITORY_ERROR", "An error that happened during repository manipulation."),
    4: ("NO_OP", "Execution resulted in no-op (no changes were made in the destination)."),
    8: ("INTERRUPTED", "Execution was interrupted."),
    30: ("ENVIRONMENT_ERROR", "Error due to the environment (network access, filesystem, git remote)."),
    31: ("INTERNAL_ERROR", "Unexpected internal Copybara error."),
}


class SyncerError(Exception):
    """Base exception for hybrid-syncer errors."""

    def __init__(self, message: str, exit_code: ExitCode = ExitCode.GENERAL_ERROR, category: str = "ERROR"):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.category = category


class ManifestError(SyncerError):
    """Configuration error (manifest missing, invalid YAML format, target missing, path clash)."""

    def __init__(self, message: str):
        super().__init__(message, exit_code=ExitCode.CONFIG_ERROR, category="MANIFEST ERROR")


class RepoAccessError(SyncerError):
    """Repository access error (repository path/URL missing or inaccessible)."""

    def __init__(self, message: str):
        super().__init__(message, exit_code=ExitCode.REPO_ACCESS_ERROR, category="REPO ACCESS ERROR")


class CopybaraExecutionError(SyncerError):
    """Subprocess execution error when Copybara fails."""

    def __init__(self, workflow: str, returncode: int, stdout: str = "", stderr: str = "", suggested_command: str | None = None):
        code_info = COPYBARA_EXIT_CODES.get(returncode, ("UNKNOWN_ERROR", "Unknown Copybara exit code."))
        code_name, code_desc = code_info

        details = []
        details.append(f"Copybara Exit Code: {returncode} ({code_name}) - {code_desc}")

        combined_output = f"{stdout}\n{stderr}"
        suggestion = suggested_command

        if not suggestion:
            if "GitOrigin-RevId could not be found" in combined_output or "--init-history" in combined_output:
                import sys
                cmd_args = list(sys.argv)
                if "--init-history" not in cmd_args:
                    cmd_args.append("--init-history")
                suggestion = " ".join(cmd_args)

        if suggestion:
            details.append(f"\n💡 Suggested command:\n  {suggestion}")

        if stderr and stderr.strip():
            details.append(f"\nStderr:\n{stderr.strip()}")
        if stdout and stdout.strip():
            details.append(f"\nStdout:\n{stdout.strip()}")

        det_str = ("\n" + "\n".join(details)) if details else ""
        msg = f"Error executing Copybara workflow '{workflow}' (exit code {returncode}){det_str}"
        super().__init__(msg, exit_code=ExitCode.COPYBARA_EXECUTION_ERROR, category="COPYBARA EXECUTION ERROR")
        self.workflow = workflow
        self.returncode = returncode
        self.copybara_exit_code_name = code_name
        self.copybara_exit_code_desc = code_desc
        self.stdout = stdout
        self.stderr = stderr
        self.suggested_command = suggestion


# --- Circuit Breaker / Guard Exceptions ---

class CircuitBreakerError(SyncerError):
    """Base exception for pre-flight safety circuit breakers."""
    pass


class DirtyWorkspaceError(CircuitBreakerError):
    def __init__(self, target: str, direction: str, repo_label: str, repo_url: str, uncommitted_files: list[str]):
        summary = "\n".join(f"  {f}" for f in uncommitted_files[:10])
        if len(uncommitted_files) > 10:
            summary += f"\n  ... and {len(uncommitted_files) - 10} more files."
        msg = (
            f"Clean Workspace Guard Failed for '{target}' ({direction}):\n"
            f"{repo_label} repository at '{repo_url}' has uncommitted changes:\n"
            f"{summary}\n\n"
            f"Please commit or stash your changes before syncing."
        )
        super().__init__(msg, exit_code=ExitCode.DIRTY_WORKSPACE, category="SAFETY CIRCUIT BREAKER")


class AncestryRewrittenError(CircuitBreakerError):
    def __init__(self, target: str, direction: str, source_name: str, source_url: str, sync_sha: str):
        msg = (
            f"Ancestry & History Guard Failed for '{target}' ({direction}):\n"
            f"{source_name} commit history was rewritten (force-push or rebase detected).\n"
            f"Recorded last synced commit '{sync_sha[:8]}' is not in active history lineage of {source_name} ('{source_url}').\n"
            f"Run with --init-history to re-baseline."
        )
        super().__init__(msg, exit_code=ExitCode.ANCESTRY_REWRITTEN, category="SAFETY CIRCUIT BREAKER")


class DivergenceError(CircuitBreakerError):
    def __init__(self, target: str, direction: str, source_name: str, source_path: str, dest_name: str, dest_path: str, sync_sha: str):
        msg = (
            f"Concurrent Fork Guard Failed for '{target}' ({direction}):\n"
            f"Concurrent changes detected in both {source_name} and {dest_name} since last sync point ({sync_sha[:8]}).\n"
            f"  • {source_name} has new commits in '{source_path or '.'}'\n"
            f"  • {dest_name} has new commits in '{dest_path or '.'}'\n"
            f"Please pull/merge or resolve manually before syncing."
        )
        super().__init__(msg, exit_code=ExitCode.DIVERGENCE_DETECTED, category="SAFETY CIRCUIT BREAKER")


class PatchApplyError(CircuitBreakerError):
    def __init__(self, target: str, direction: str, source_name: str, dest_name: str, patch_err: str):
        msg = (
            f"Pre-Apply Patch Guard Failed (Structural / Content Conflict) for '{target}' ({direction}):\n"
            f"Incoming changes from {source_name} cannot be applied cleanly to {dest_name}.\n"
            f"Details: {patch_err}\n"
            f"Please resolve conflicts manually before syncing."
        )
        super().__init__(msg, exit_code=ExitCode.PATCH_APPLY_FAILED, category="SAFETY CIRCUIT BREAKER")
