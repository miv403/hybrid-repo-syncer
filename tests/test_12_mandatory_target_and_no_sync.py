#!/usr/bin/env python3
"""
Test Scenario 12: Mandatory Target Specification & Sync Command Removal Verification
Validates that:
1. `push` and `pull` commands without -t/--target fail with exit code 1.
2. Informative output lists mandatory target requirement, manifest file path, available targets, and sample usage.
3. `sync` subcommand has been completely removed and returns command parsing error.
"""

import sys
import subprocess
from pathlib import Path

from common import (
    BOLD, FAIL, OKBLUE, OKGREEN, ENDC,
    get_test_arg_parser, print_banner, print_step_header,
    print_diagnostic, print_result_row
)


def main():
    parser = get_test_arg_parser("Test Scenario 12: Mandatory Target & Sync Removal")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    syncer_py = project_root / "hybrid-syncer.py"
    manifest_path = project_root / "sync-manifest.yaml"

    print_banner("TEST SCENARIO 12: Mandatory Target Specification & Sync Removal")

    # -------------------------------------------------------------------------
    # STEP 1: PUSH WITHOUT TARGET TEST
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Push Without Target Specification",
        "Verify `hybrid-syncer.py push` without `-t` exits with code 1 and prints informative output."
    )

    res_push = subprocess.run(
        [sys.executable, str(syncer_py), "push"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    stderr_push = res_push.stderr
    print_diagnostic(f"Push without target return code: {res_push.returncode}", stderr_push)

    push_failed = res_push.returncode == 1
    has_mandatory_err = "mandatory" in stderr_push.lower() or "-t / --target" in stderr_push
    has_yaml_path = str(manifest_path.resolve()) in stderr_push
    has_available_targets = "repo-1-a" in stderr_push and "repo-1-b" in stderr_push
    has_sample_usage = "sample usage" in stderr_push.lower()

    # -------------------------------------------------------------------------
    # STEP 2: PULL WITHOUT TARGET TEST
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Pull Without Target Specification",
        "Verify `hybrid-syncer.py pull` without `-t` exits with code 1 and prints informative output."
    )

    res_pull = subprocess.run(
        [sys.executable, str(syncer_py), "pull"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    stderr_pull = res_pull.stderr
    print_diagnostic(f"Pull without target return code: {res_pull.returncode}", stderr_pull)

    pull_failed = res_pull.returncode == 1
    pull_has_mandatory_err = "mandatory" in stderr_pull.lower() or "-t / --target" in stderr_pull

    # -------------------------------------------------------------------------
    # STEP 3: REMOVED SYNC COMMAND TEST
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Removed Sync Command Verification",
        "Verify `hybrid-syncer.py sync` is invalid and returns command parse error."
    )

    res_sync = subprocess.run(
        [sys.executable, str(syncer_py), "sync"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    stderr_sync = res_sync.stderr
    print_diagnostic(f"Sync command return code: {res_sync.returncode}", stderr_sync)

    sync_invalid = res_sync.returncode != 0 and ("invalid choice" in stderr_sync or "unrecognized" in stderr_sync or "invalid" in stderr_sync)

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Assertions",
        "Summary of assertions for target requirement and sync removal."
    )

    print_result_row(
        "1. Push command fails when target is missing (exit code 1)",
        push_failed,
        f"Return code {res_push.returncode}"
    )

    print_result_row(
        "2. Error output displays mandatory target message",
        has_mandatory_err,
        "Found target requirement warning"
    )

    print_result_row(
        "3. Error output displays manifest file path",
        has_yaml_path,
        f"Path: {manifest_path.resolve()}"
    )

    print_result_row(
        "4. Error output lists available targets",
        has_available_targets,
        "Found repo-1-a and repo-1-b in output"
    )

    print_result_row(
        "5. Error output includes sample usage instructions",
        has_sample_usage,
        "Found sample usage demonstration"
    )

    print_result_row(
        "6. Pull command fails when target is missing",
        pull_failed and pull_has_mandatory_err,
        f"Return code {res_pull.returncode}"
    )

    print_result_row(
        "7. Sync subcommand is removed and rejected",
        sync_invalid,
        f"Return code {res_sync.returncode}"
    )

    all_passed = (
        push_failed and has_mandatory_err and has_yaml_path and
        has_available_targets and has_sample_usage and pull_failed and
        sync_invalid
    )

    if all_passed:
        print(f"\n{OKGREEN}🎉 TEST SCENARIO 12 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
        sys.exit(0)
    else:
        print(f"\n{FAIL}❌ TEST SCENARIO 12 FAILED! Check failed assertions above.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
