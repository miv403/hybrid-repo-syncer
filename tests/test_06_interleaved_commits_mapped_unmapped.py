#!/usr/bin/env python3
"""
Test Scenario 6: Interleaved Commits Across Mapped and Unmapped Paths

Objective:
  Test commit filtering and history preservation when sequential commits touch mapped and unmapped paths.
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
    parser = get_test_arg_parser("Test Scenario 6: Interleaved Commits Across Mapped and Unmapped Paths")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 6: Interleaved Commits Across Mapped and Unmapped Paths")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE SYNC
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish clean baseline state."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline established.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (3 INTERLEAVED COMMITS)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (3 Interleaved Commits)",
        "Make 3 sequential commits in origin repo-1 affecting mapped (a/) and unmapped (c/) paths."
    )

    # Commit 1: Update mapped file a/file.a
    origin_file_a = origin_dir / "a" / "file.a"
    with open(origin_file_a, "a") as f:
        f.write("Commit 1: mapped file update\n")
    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit -m "origin commit 1: update mapped file a/file.a"', cwd=origin_dir)

    # Commit 2: Create unmapped directory c/ and file c/other.txt
    origin_dir_c = origin_dir / "c"
    origin_dir_c.mkdir(parents=True, exist_ok=True)
    origin_other = origin_dir_c / "other.txt"
    origin_other.write_text("Commit 2: unmapped file content\n")
    run_cmd("git add c/other.txt", cwd=origin_dir)
    run_cmd('git commit -m "origin commit 2: update unmapped file c/other.txt"', cwd=origin_dir)

    # Commit 3: Modify BOTH mapped file a/file.a and unmapped file c/other.txt
    with open(origin_file_a, "a") as f:
        f.write("Commit 3: mapped file update\n")
    with open(origin_other, "a") as f:
        f.write("Commit 3: unmapped file update\n")
    run_cmd("git add a/file.a c/other.txt", cwd=origin_dir)
    run_cmd('git commit -m "origin commit 3: modify both mapped a/file.a and unmapped c/other.txt"', cwd=origin_dir)

    run_cmd("git push origin master", cwd=origin_dir)

    print_diagnostic("Recent Git Commits in Origin Repo (3 Interleaved Commits)", run_cmd("git log -n 5 --oneline", cwd=origin_dir).stdout)
    print_file_tree(origin_dir, "Origin Repo (after 3 commits)")

    breakpoint_prompt(args.auto, 2, "3 interleaved commits created and pushed in origin. Ready to execute push.")

    # -------------------------------------------------------------------------
    # STEP 3: EXECUTION (PUSH IN ITERATIVE MODE)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Execution",
        "Run `hybrid-syncer.py push -t repo-1-a` to execute Copybara migration in ITERATIVE mode."
    )

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push output", push_res.stdout)

    print_git_log(hybrid_dir, "Hybrid Repo (after iterative push)", count=5)
    print_file_tree(hybrid_dir, "Hybrid Repo (after iterative push)")

    breakpoint_prompt(args.auto, 3, "Iterative push complete. Ready to run verification assertions.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Assertions",
        "Verify mapped updates applied, unmapped file isolated, and commit filtering handled cleanly."
    )

    hybrid_file_a = hybrid_dir / "repo-1" / "a" / "file.a"
    file_a_content = hybrid_file_a.read_text() if hybrid_file_a.exists() else ""

    check_1_pass = (
        "Commit 1: mapped file update" in file_a_content
        and "Commit 3: mapped file update" in file_a_content
    )

    hybrid_c_dir = hybrid_dir / "repo-1" / "c"
    hybrid_other_file = hybrid_dir / "repo-1" / "c" / "other.txt"
    check_2_pass = not hybrid_c_dir.exists() and not hybrid_other_file.exists()

    hybrid_log_res = run_cmd("git log --oneline", cwd=hybrid_dir)
    hybrid_log = hybrid_log_res.stdout if hybrid_log_res.stdout else ""

    commit_1_migrated = "origin commit 1" in hybrid_log
    commit_2_skipped = "origin commit 2" not in hybrid_log
    commit_3_migrated = "origin commit 3" in hybrid_log

    check_3_pass = commit_1_migrated and commit_2_skipped and commit_3_migrated

    print(f"{BOLD}Assertion Results Summary:{ENDC}")
    print(f"{'-' * 75}")

    print_result_row(
        "1. repo-1/a/file.a in hybrid received all mapped updates (Commit 1 & Commit 3)",
        check_1_pass,
        f"Content:\n{file_a_content.strip()}"
    )

    print_result_row(
        "2. Unmapped file c/other.txt did NOT leak into hybrid",
        check_2_pass,
        f"Unmapped path exists: {hybrid_c_dir.exists()}"
    )

    print_result_row(
        "3. Copybara filtered commits cleanly (Commit 1 migrated, Commit 2 skipped, Commit 3 stripped)",
        check_3_pass,
        f"Hybrid Commit Log:\n{hybrid_log.strip()}"
    )
    print(f"{'-' * 75}\n")

    if check_1_pass and check_2_pass and check_3_pass:
        print(f"{OKGREEN}🎉 TEST SCENARIO 6 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
    else:
        print(f"{FAIL}❌ TEST SCENARIO 6 FAILED! Check output above for details.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
