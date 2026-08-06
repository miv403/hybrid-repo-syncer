#!/usr/bin/env python3
"""
Master Test Runner for Git-Syncer Test Suite
Runs all test scenarios sequentially and reports unified pass/fail results.
"""

import sys
import subprocess
from pathlib import Path

from common import (
    BOLD, FAIL, HEADER, OKBLUE, OKCYAN, OKGREEN, ENDC,
    print_banner
)

TEST_SCENARIOS = [
    ("test_01_unmapped_path_isolation.py", "Test Scenario 1: Unmapped Path Isolation"),
    ("test_02_structural_conflict_rename_vs_modify.py", "Test Scenario 2: Rename vs. Concurrent Modify"),
    ("test_03_asymmetric_destructive_modify_vs_delete.py", "Test Scenario 3: Modify vs. Delete"),
    ("test_04_same_name_independent_file_addition.py", "Test Scenario 4: Independent File Addition"),
    ("test_05_history_rewrite_rebase_desync.py", "Test Scenario 5: History Rewrite / Rebase Desync"),
    ("test_06_interleaved_commits_mapped_unmapped.py", "Test Scenario 6: Interleaved Commits"),
    ("test_07_status_command.py", "Test Scenario 7: Status Command Verification"),
    ("test_08_doctor_command.py", "Test Scenario 8: Doctor Command Verification"),
    ("test_09_unmapped_status_check.py", "Test Scenario 9: Unmapped Path & Orphan Analyzer"),
    ("test_10_exclusion_patterns.py", "Test Scenario 10: Target Exclusion Patterns"),
    ("test_11_trigger_server.py", "Test Scenario 11: Trigger Server Webhooks & Concurrency Mutex"),
    ("test_12_mandatory_target_and_no_sync.py", "Test Scenario 12: Mandatory Target & Sync Removal"),
    ("test_14_cross_platfrom_paths.py", "Test Scenario 13: Cross-Platform Paths & Normalization"),
    ("test_15_copybara_path_manifest_resolution.py", "Test Scenario 14: Manifest Copybara Path Resolution"),
]


def main():
    print_banner("GIT-SYNCER MASTER TEST SUITE RUNNER")

    tests_dir = Path(__file__).resolve().parent
    results = []

    for script_name, description in TEST_SCENARIOS:
        script_path = tests_dir / script_name
        print(f"{OKCYAN}▶ Executing {script_name}...{ENDC}")
        res = subprocess.run([sys.executable, str(script_path), "--auto"], text=True)

        passed = res.returncode == 0
        results.append((script_name, description, passed, res.returncode))
        print()

    print(f"\n{HEADER}{'=' * 75}{ENDC}")
    print(f"{HEADER}{'MASTER TEST SUITE RESULTS SUMMARY'.center(75)}{ENDC}")
    print(f"{HEADER}{'=' * 75}{ENDC}\n")

    all_passed = True
    for script_name, description, passed, code in results:
        status_str = f"{OKGREEN}[PASS]{ENDC}" if passed else f"{FAIL}[FAIL]{ENDC}"
        if not passed:
            all_passed = False
        print(f"  {status_str} {script_name:<50} (exit code {code})")
        print(f"         └─ {description}")

    print(f"\n{'-' * 75}")
    if all_passed:
        print(f"{OKGREEN}🎉 ALL TEST SCENARIOS PASSED SUCCESSFULLY!{ENDC}\n")
        sys.exit(0)
    else:
        print(f"{FAIL}❌ SOME TEST SCENARIOS FAILED! Check outputs above.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
