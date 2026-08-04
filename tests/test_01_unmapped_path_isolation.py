#!/usr/bin/env python3
"""
Test Scenario 1: Unmapped Path Isolation (Boundary Leakage Test)

Objective:
  Manifest defines strict mappings (origin.path, hybrid.path).
  Ensure changes occurring outside target folders in either repos are ignored,
  preventing dirty states, unwanted deletions, or cross-contamination during pull/push operations.
"""

import sys
from pathlib import Path

from common import (
    BOLD, FAIL, OKGREEN, ENDC,
    run_cmd, print_banner, print_step_header, print_diagnostic,
    print_file_tree, print_git_log, breakpoint_prompt, reset_sample_repos,
    print_result_row, get_test_arg_parser
)


def main():
    parser = get_test_arg_parser("Test Scenario 1: Unmapped Path Isolation")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 1: Unmapped Path Isolation (Boundary Leakage)")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & INIT-HISTORY
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Initial Sync",
        "Reset repos and run `hybrid-syncer.py push --init-history` to establish baseline history."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")
    print_git_log(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline established. Ready to perform hybrid actions.")

    # -------------------------------------------------------------------------
    # STEP 2: HYBRID ACTION
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Hybrid Action",
        "Create unmapped file `repo-1/c/unmapped.txt` AND update mapped file `repo-1/a/file.a` in hybrid."
    )

    # 1. Create unmapped folder and file
    unmapped_dir = hybrid_dir / "repo-1" / "c"
    unmapped_dir.mkdir(parents=True, exist_ok=True)
    unmapped_file = unmapped_dir / "unmapped.txt"
    unmapped_file.write_text("This file is in unmapped folder repo-1/c and should NOT leak to origin.\n")

    # 2. Update valid mapped file
    mapped_file = hybrid_dir / "repo-1" / "a" / "file.a"
    mapped_file.write_text("file a updated inside hybrid repo\n")

    # 3. Commit both in hybrid
    run_cmd("git add .", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: add repo-1/c/unmapped.txt and update repo-1/a/file.a"', cwd=hybrid_dir)

    print_diagnostic("Latest commit in Hybrid Repo", run_cmd("git log -n 1 --stat", cwd=hybrid_dir).stdout)
    print_diagnostic("Git Diff of HEAD~1 in Hybrid Repo", run_cmd("git diff HEAD~1", cwd=hybrid_dir).stdout)
    print_file_tree(hybrid_dir, "Hybrid Repo (after commit)")

    breakpoint_prompt(args.auto, 2, "Hybrid commit created. Ready to execute pull command.")

    # -------------------------------------------------------------------------
    # STEP 3: EXECUTION (PULL)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Execution",
        "Run `hybrid-syncer.py pull -t repo-1-a` to sync target `repo-1-a` from hybrid to origin."
    )

    pull_res = run_cmd(f"python3 {syncer_py} pull -t repo-1-a --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py pull -t repo-1-a --init-history output", pull_res.stdout)

    # Make origin worktree fetch/pull latest changes from bare origin repo-1.git if needed
    run_cmd("git pull origin master", cwd=origin_dir, check=False)

    print_file_tree(origin_dir, "Origin Repo (repo-1 after pull)")
    print_git_log(origin_dir, "Origin Repo (repo-1 after pull)")

    breakpoint_prompt(args.auto, 3, "Pull executed. Ready to run verification assertions.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & EXPECTED RESULTS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Assertions",
        "Checking expected results: mapped file updated, unmapped file isolated, copybara clean state."
    )

    origin_file_a = origin_dir / "a" / "file.a"
    file_a_content = origin_file_a.read_text() if origin_file_a.exists() else ""
    check_1_pass = "file a updated inside hybrid repo" in file_a_content

    origin_c_dir = origin_dir / "c"
    origin_unmapped_file = origin_dir / "c" / "unmapped.txt"
    check_2_pass = not origin_c_dir.exists() and not origin_unmapped_file.exists()

    subsequent_push = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root, check=False)
    subsequent_pull = run_cmd(f"python3 {syncer_py} pull -t repo-1-a", cwd=project_root, check=False)
    hybrid_unmapped_exists = unmapped_file.exists()
    check_3_pass = (
        subsequent_push.returncode in (0, 4)
        and subsequent_pull.returncode in (0, 4)
        and hybrid_unmapped_exists
    )

    print(f"{BOLD}Assertion Results Summary:{ENDC}")
    print(f"{'-' * 75}")

    print_result_row(
        "1. a/file.a in origin (repo-1) received update",
        check_1_pass,
        f"Content: '{file_a_content.strip()}'"
    )

    print_result_row(
        "2. repo-1/c and unmapped.txt did NOT appear in origin (repo-1)",
        check_2_pass,
        f"Origin path exists: {origin_c_dir.exists()}"
    )

    print_result_row(
        "3. Copybara executed subsequent push/pull cleanly & repo-1/c remains intact in hybrid",
        check_3_pass,
        f"Hybrid unmapped file exists: {hybrid_unmapped_exists}"
    )
    print(f"{'-' * 75}\n")

    if check_1_pass and check_2_pass and check_3_pass:
        print(f"{OKGREEN}🎉 TEST SCENARIO 1 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
    else:
        print(f"{FAIL}❌ TEST SCENARIO 1 FAILED! Check output above for details.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
