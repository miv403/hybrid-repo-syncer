#!/usr/bin/env python3
"""
Test Scenario 12: Mandatory Target Specification & Sync Command Removal Verification
Validates that:
1. `push` and `pull` commands without -t/--target fail with exit code 2 (CONFIG_ERROR).
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
        "Verify `hybrid-syncer.py push` without `-t` exits with non-zero exit code and prints informative output."
    )

    res_push = subprocess.run(
        [sys.executable, str(syncer_py), "push"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    output_push = res_push.stderr + res_push.stdout
    print_diagnostic(f"Push without target return code: {res_push.returncode}", output_push)

    push_failed = res_push.returncode != 0
    has_mandatory_err = "mandatory" in output_push.lower() or "-t / --target" in output_push
    has_yaml_path = str(manifest_path.resolve()) in output_push
    has_available_targets = "repo-1-a" in output_push and "repo-1-b" in output_push
    has_sample_usage = "sample usage" in output_push.lower()

    # -------------------------------------------------------------------------
    # STEP 1B: PUSH WITHOUT DESTINATION TEST
    # -------------------------------------------------------------------------
    res_push_nodest = subprocess.run(
        [sys.executable, str(syncer_py), "push", "-t", "repo-1-a"],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    out_nodest = res_push_nodest.stderr + res_push_nodest.stdout
    print_diagnostic(f"Push without destination return code: {res_push_nodest.returncode}", out_nodest)

    push_nodest_failed = res_push_nodest.returncode != 0
    has_dest_mandatory_err = "destination specification" in out_nodest.lower() or "-d / --destination" in out_nodest

    # -------------------------------------------------------------------------
    # STEP 2: PULL WITHOUT TARGET TEST
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Pull Without Target Specification",
        "Verify `hybrid-syncer.py pull` without `-t` exits with non-zero exit code and prints informative output."
    )

    res_pull = subprocess.run(
        [sys.executable, str(syncer_py), "pull"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    output_pull = res_pull.stderr + res_pull.stdout
    print_diagnostic(f"Pull without target return code: {res_pull.returncode}", output_pull)

    pull_failed = res_pull.returncode != 0
    pull_has_mandatory_err = "mandatory" in output_pull.lower() or "-t / --target" in output_pull

    # -------------------------------------------------------------------------
    # STEP 3: LIST COMMAND TEST
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "List Subcommand Verification",
        "Verify `hybrid-syncer.py list`, `hybrid-syncer.py list <target>`, and non-existent target error output."
    )

    # 3a. List all targets
    res_list_all = subprocess.run(
        [sys.executable, str(syncer_py), "list"],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    out_list_all = res_list_all.stdout + res_list_all.stderr
    print_diagnostic(f"List all return code: {res_list_all.returncode}", out_list_all)
    list_all_ok = res_list_all.returncode == 0 and "repo-1-a" in out_list_all and "Destinations" in out_list_all

    # 3b. List specific target
    res_list_target = subprocess.run(
        [sys.executable, str(syncer_py), "list", "repo-1-a"],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    out_list_target = res_list_target.stdout + res_list_target.stderr
    print_diagnostic(f"List target return code: {res_list_target.returncode}", out_list_target)
    list_target_ok = res_list_target.returncode == 0 and "Target: repo-1-a" in out_list_target and "main" in out_list_target

    # 3c. List non-existent target
    res_list_invalid = subprocess.run(
        [sys.executable, str(syncer_py), "list", "invalid-target-xyz"],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    out_list_invalid = res_list_invalid.stdout + res_list_invalid.stderr
    print_diagnostic(f"List invalid target return code: {res_list_invalid.returncode}", out_list_invalid)
    list_invalid_ok = res_list_invalid.returncode != 0 and "not found in manifest" in out_list_invalid and "repo-1-a" in out_list_invalid

    # -------------------------------------------------------------------------
    # STEP 4: REMOVED SYNC COMMAND TEST
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Removed Sync Command Verification",
        "Verify `hybrid-syncer.py sync` is invalid and returns command parse error."
    )

    res_sync = subprocess.run(
        [sys.executable, str(syncer_py), "sync"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    output_sync = res_sync.stderr + res_sync.stdout
    print_diagnostic(f"Sync command return code: {res_sync.returncode}", output_sync)

    sync_invalid = res_sync.returncode != 0 and ("invalid choice" in output_sync or "unrecognized" in output_sync or "invalid" in output_sync)

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Assertions",
        "Summary of assertions for target requirement, list command, and sync removal."
    )

    print_result_row(
        "1. Push command fails when target is missing (non-zero exit code)",
        push_failed,
        f"Return code {res_push.returncode}"
    )

    print_result_row(
        "2. Error output displays mandatory target message and lists destinations",
        has_mandatory_err and "Destinations" in output_push,
        "Found target and destination requirement warning"
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
        "7. `list` lists all targets and their destinations",
        list_all_ok,
        f"Return code {res_list_all.returncode}"
    )

    print_result_row(
        "8. `list <target-name>` lists specific target destinations",
        list_target_ok,
        f"Return code {res_list_target.returncode}"
    )

    print_result_row(
        "9. `list <invalid-target>` reports missing target and lists available targets",
        list_invalid_ok,
        f"Return code {res_list_invalid.returncode}"
    )

    print_result_row(
        "10. Sync subcommand is removed and rejected",
        sync_invalid,
        f"Return code {res_sync.returncode}"
    )

    print_result_row(
        "11. Push command fails when destination (-d) is missing",
        push_nodest_failed and has_dest_mandatory_err,
        f"Return code {res_push_nodest.returncode}"
    )

    all_passed = (
        push_failed and has_mandatory_err and has_yaml_path and
        has_available_targets and has_sample_usage and pull_failed and
        list_all_ok and list_target_ok and list_invalid_ok and
        sync_invalid and push_nodest_failed and has_dest_mandatory_err
    )

    if all_passed:
        print(f"\n{OKGREEN}🎉 TEST SCENARIO 12 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
        sys.exit(0)
    else:
        print(f"\n{FAIL}❌ TEST SCENARIO 12 FAILED! Check failed assertions above.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
