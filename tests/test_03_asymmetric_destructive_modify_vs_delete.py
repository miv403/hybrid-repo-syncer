#!/usr/bin/env python3
"""
Test Scenario 3: Asymmetric Destructive Operation (Modify vs. Delete)

Objective:
  Test conflict detection when a file is modified in origin while deleted in hybrid.
"""

import sys
from pathlib import Path

from common import (
    BOLD, FAIL, OKGREEN, ENDC,
    run_cmd, print_banner, print_step_header, print_diagnostic,
    print_file_tree, print_git_log, breakpoint_prompt, reset_sample_repos,
    print_risk_row, get_test_arg_parser
)


def main():
    parser = get_test_arg_parser("Test Scenario 3: Asymmetric Destructive Operation (Modify vs. Delete)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 3: Asymmetric Destructive Operation (Modify vs. Delete)")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE SYNC
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish baseline state with file.a in both repos."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a -d main --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline established with file.a in both repos.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (CONTENT MODIFICATION)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (Content Modification)",
        "Append new lines to `a/file.a` in origin repo-1 and push to repo-1.git."
    )

    origin_file_a = origin_dir / "a" / "file.a"
    with open(origin_file_a, "a") as f:
        f.write("line 2: appended in origin repo\nline 3: another modification in origin repo\n")

    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit -m "origin: append new lines to a/file.a"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)
    print_diagnostic("Git Diff in Origin Repo", run_cmd("git diff HEAD~1", cwd=origin_dir).stdout)

    breakpoint_prompt(args.auto, 2, "Origin modification committed & pushed. Ready for hybrid action.")

    # -------------------------------------------------------------------------
    # STEP 3: HYBRID ACTION (FILE DELETION)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Hybrid Action (File Deletion)",
        "Delete `repo-1/a/file.a` in hybrid using `git rm` and commit."
    )

    run_cmd("git rm repo-1/a/file.a", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: delete repo-1/a/file.a"', cwd=hybrid_dir)

    print_diagnostic("Hybrid Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=hybrid_dir).stdout)
    print_file_tree(hybrid_dir, "Hybrid Repo (after file deletion)")

    breakpoint_prompt(args.auto, 3, "Hybrid file deletion committed. Ready to execute push.")

    # -------------------------------------------------------------------------
    # STEP 4: EXECUTION (PUSH)
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Execution",
        "Run `hybrid-syncer.py push -t repo-1-a -d main` to attempt syncing origin's modification into hybrid."
    )

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a -d main", cwd=project_root, check=False)

    stdout_msg = push_res.stdout if push_res.stdout else "(no stdout)"
    stderr_msg = push_res.stderr if push_res.stderr else "(no stderr)"

    print_diagnostic(f"hybrid-syncer.py push return code: {push_res.returncode}", f"Stdout:\n{stdout_msg}\nStderr:\n{stderr_msg}")

    print_file_tree(origin_dir, "Origin Repo (after push attempt)")
    print_file_tree(hybrid_dir, "Hybrid Repo (after push attempt)")

    breakpoint_prompt(args.auto, 4, "Push executed. Ready for behavior and outcome analysis.")

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & BEHAVIOR ANALYSIS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Behavior Analysis",
        "Evaluate whether Copybara failed explicitly or quietly recreated the deleted file in hybrid."
    )

    hybrid_file_a = hybrid_dir / "repo-1" / "a" / "file.a"
    hybrid_file_exists = hybrid_file_a.exists()
    hybrid_file_content = hybrid_file_a.read_text().strip() if hybrid_file_exists else "N/A"

    push_failed = push_res.returncode != 0

    print(f"{BOLD}State Analysis & Sync Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Push Return Code        : {push_res.returncode} ({'Error Raised' if push_failed else 'Clean Success'})")
    print(f"  • Hybrid File Exists      : {hybrid_file_exists}")
    print(f"  • Hybrid File Content     : '{hybrid_file_content}'")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Outcome Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    if push_failed:
        err_status = f"{OKGREEN}[YES]{ENDC}"
        err_desc = f"Copybara threw exit code {push_res.returncode} on conflict."
    else:
        err_status = f"{FAIL}[NO]{ENDC}"
        err_desc = "Copybara completed with code 0 without raising an explicit error."

    print_risk_row("Copybara Explicit Error Raised", err_status, err_desc)

    if not push_failed and hybrid_file_exists:
        recreate_status = f"{FAIL}[YES]{ENDC}"
        recreate_desc = "Copybara quietly recreated the deleted file in hybrid repo."
    else:
        recreate_status = f"{OKGREEN}[NO]{ENDC}"
        recreate_desc = "File was not recreated in hybrid."

    print_risk_row("File Quietly Recreated in Hybrid", recreate_status, recreate_desc)

    if not hybrid_file_exists:
        del_status = f"{OKGREEN}[YES]{ENDC}"
        del_desc = "repo-1/a/file.a remains deleted in hybrid repo."
    else:
        del_status = f"{FAIL}[NO]{ENDC}"
        del_desc = "Hybrid deletion was overridden by origin push."

    print_risk_row("Hybrid Deletion Preserved", del_status, del_desc)
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 3 COMPLETED. Diagnostics & outcome analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
