#!/usr/bin/env python3
"""
Test Scenario 7: Status Command Verification

Objective:
  Validate that `hybrid-syncer.py status` accurately reports repository status,
  commit ahead counts, uncommitted local changes, divergence warnings, and single-target filtering.
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
    parser = get_test_arg_parser("Test Scenario 7: Status Command Verification")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_repo1_dir = project_root / "sample-repos" / "repo-1"
    origin_repo2_dir = project_root / "sample-repos" / "repo-2"
    syncer_py = project_root / "hybrid-syncer.py"

    print_banner("TEST SCENARIO 7: Status Command Verification")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE SYNC
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish baseline state."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)

    status_step1 = run_cmd(f"python3 {syncer_py} status", cwd=project_root)
    print_diagnostic("Status Output (Baseline)", status_step1.stdout)

    breakpoint_prompt(args.auto, 1, "Baseline status checked.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN AHEAD & HYBRID AHEAD & DIRTY WORKSPACE
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin & Hybrid Modifications",
        "Make commits in origin repo-1 (repo-1-a ahead) and hybrid (repo-1-b ahead, repo-1-a diverged)."
    )

    # 1. Commit in origin repo-1 for path a (repo-1-a ahead by 1)
    file_a = origin_repo1_dir / "a" / "file.a"
    file_a.write_text("origin update 1 for file.a\n")
    run_cmd("git add a/file.a", cwd=origin_repo1_dir)
    run_cmd('git commit -m "origin: update file.a"', cwd=origin_repo1_dir)
    run_cmd("git push origin master", cwd=origin_repo1_dir)

    # 2. Commit in hybrid repo for path b (repo-1-b ahead by 1)
    file_b_hybrid = hybrid_dir / "repo-1" / "b" / "file.b"
    file_b_hybrid.write_text("hybrid update for file.b\n")
    run_cmd("git add repo-1/b/file.b", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: update file.b"', cwd=hybrid_dir)

    # 3. Commit in hybrid repo for path a (repo-1-a diverged!)
    file_a_hybrid = hybrid_dir / "repo-1" / "a" / "file.a"
    file_a_hybrid.write_text("hybrid divergent update for file.a\n")
    run_cmd("git add repo-1/a/file.a", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: divergent update file.a"', cwd=hybrid_dir)

    # 4. Dirty file in origin repo-2
    dirty_file = origin_repo2_dir / "a" / "dirty.txt"
    dirty_file.write_text("uncommitted change in repo-2\n")

    status_step2 = run_cmd(f"python3 {syncer_py} status", cwd=project_root)
    print_diagnostic("Status Output (After Changes)", status_step2.stdout)

    breakpoint_prompt(args.auto, 2, "Status after modifications checked.")

    # -------------------------------------------------------------------------
    # STEP 3: TARGET FILTERING
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Target Filtering Verification",
        "Run `status -t repo-1-a` to ensure single target output filtering."
    )

    status_target = run_cmd(f"python3 {syncer_py} status -t repo-1-a", cwd=project_root)
    print_diagnostic("Status Output (-t repo-1-a)", status_target.stdout)

    breakpoint_prompt(args.auto, 3, "Target filtering checked.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Assertions",
        "Validate table contents, ahead counts, divergence flags, dirty flags, and filter behavior."
    )

    out_s1 = status_step1.stdout
    out_s2 = status_step2.stdout
    out_t = status_target.stdout

    # Assertions for Step 1 (Baseline)
    pass_in_sync = "repo-1-a" in out_s1 and "In Sync" in out_s1
    print_result_row("1. Baseline status shows 'In Sync' for targets", pass_in_sync, out_s1.strip().splitlines()[0] if out_s1 else "")

    # Assertions for Step 2
    pass_diverged = "⚠️ DIVERGED (Conflict)" in out_s2 or "DIVERGED" in out_s2
    print_result_row("2. Target repo-1-a correctly flagged as DIVERGED", pass_diverged, "Detected conflict divergence between origin and hybrid")

    pass_hybrid_ahead = "repo-1-b" in out_s2 and ("Ahead (1)" in out_s2 or "Ready to Pull" in out_s2)
    print_result_row("3. Target repo-1-b shows Hybrid Ahead and 'Ready to Pull'", pass_hybrid_ahead, "Detected hybrid commit ahead")

    pass_dirty = "repo-2-a" in out_s2 and ("Dirty" in out_s2 or "[Dirty]" in out_s2)
    print_result_row("4. Target repo-2-a detects uncommitted local changes", pass_dirty, "Detected uncommitted local changes in origin repo-2")

    # Assertions for Step 3 (Target Filter)
    pass_filter = "repo-1-a" in out_t and "repo-1-b" not in out_t and "repo-2-a" not in out_t
    print_result_row("5. Target filter `-t repo-1-a` isolates requested target", pass_filter, out_t.strip())

    all_passed = pass_in_sync and pass_diverged and pass_hybrid_ahead and pass_dirty and pass_filter

    if all_passed:
        print(f"\n{OKGREEN}🎉 TEST SCENARIO 7 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
        sys.exit(0)
    else:
        print(f"\n{FAIL}❌ TEST SCENARIO 7 FAILED! One or more assertions failed.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
