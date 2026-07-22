#!/usr/bin/env python3
"""
Test Scenario 5: History Rewrite / Rebase Desynchronization

Objective:
  Test handling when origin commit history is amended, rebased, or force-pushed.
"""

import sys
from pathlib import Path

from common import (
    BOLD, FAIL, OKGREEN, ENDC,
    run_cmd, print_banner, print_step_header, print_diagnostic,
    print_git_log, breakpoint_prompt, reset_sample_repos,
    print_risk_row, get_test_arg_parser
)


def main():
    parser = get_test_arg_parser("Test Scenario 5: History Rewrite / Rebase Desynchronization")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 5: History Rewrite / Rebase Desynchronization")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE SYNC
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos, perform origin update, and run `push` so hybrid records GitOrigin-RevId."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    origin_file_a = origin_dir / "a" / "file.a"
    origin_file_a.write_text("baseline sync content\n")
    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit -m "origin: baseline sync commit"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    syncer_py = project_root / "hybrid-syncer.py"
    push_res_1 = run_cmd(f"python3 {syncer_py} push -t repo-1-a --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push output", push_res_1.stdout)

    print_git_log(origin_dir, "Origin Repo (baseline)")
    print_git_log(hybrid_dir, "Hybrid Repo (showing GitOrigin-RevId in commit message)")

    breakpoint_prompt(args.auto, 1, "Baseline sync complete. GitOrigin-RevId recorded in hybrid.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (HISTORY REWRITE & FORCE PUSH)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (History Rewrite & Force Push)",
        "Amend latest commit in origin to rewrite its SHA, then force-push to repo-1.git."
    )

    origin_file_a.write_text("REWRITTEN baseline sync content\n")
    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit --amend -m "origin: REWRITTEN baseline commit (amended SHA)"', cwd=origin_dir)
    run_cmd("git push origin master --force", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log (after commit amend)", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)

    breakpoint_prompt(args.auto, 2, "Origin history rewritten and force-pushed. Ready to attempt push.")

    # -------------------------------------------------------------------------
    # STEP 3: EXECUTION (PUSH AFTER HISTORY REWRITE)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Execution",
        "Run `hybrid-syncer.py push -t repo-1-a` to attempt sync after history rewrite."
    )

    push_res_2 = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root, check=False)

    stdout_msg = push_res_2.stdout if push_res_2.stdout else "(no stdout)"
    stderr_msg = push_res_2.stderr if push_res_2.stderr else "(no stderr)"

    print_diagnostic(f"hybrid-syncer.py push return code: {push_res_2.returncode}", f"Stdout:\n{stdout_msg}\nStderr:\n{stderr_msg}")

    breakpoint_prompt(args.auto, 3, "Push executed after origin force-push. Ready for verification.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & RISK ANALYSIS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Risk Analysis",
        "Analyze whether Copybara raised a revision error or silently re-synced amended history."
    )

    print_git_log(hybrid_dir, "Hybrid Repo (after push after origin amend)")

    push_failed = push_res_2.returncode != 0
    stderr_combined = (push_res_2.stderr + push_res_2.stdout).lower()
    revision_error_detected = "cannot find" in stderr_combined or "revision" in stderr_combined or "history" in stderr_combined

    print(f"{BOLD}State Analysis & History Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Push Return Code      : {push_res_2.returncode} ({'Revision Error Raised' if push_failed else 'Clean Success'})")
    print(f"  • Revision Error Raised : {revision_error_detected}")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Risk Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    if push_failed:
        err_status = f"{OKGREEN}[DETECTED / ERROR RAISED]{ENDC}"
        err_desc = f"Copybara raised an explicit error (code {push_res_2.returncode}) on force-pushed history."
    else:
        err_status = f"{FAIL}[NOT DETECTED]{ENDC}"
        err_desc = "Copybara completed with exit code 0 despite history rewrite."

    print_risk_row("Copybara Revision Lookup Error Raised", err_status, err_desc)

    if not push_failed:
        sync_status = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}"
        sync_desc = "Copybara silently processed rewritten history."
    else:
        sync_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        sync_desc = "Copybara halted on force push."

    print_risk_row("Silent Re-sync / Duplicate Commit Risk on Force Push", sync_status, sync_desc)
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 5 COMPLETED. Diagnostics & risk analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
