#!/usr/bin/env python3
"""
Test Scenario 4: Same-Name Independent File Addition (Insertion Race)

Objective:
  Test conflict detection when a file with the exact same relative path is independently created
  in both origin and hybrid repositories before syncing.
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
    parser = get_test_arg_parser("Test Scenario 4: Same-Name Independent File Addition (Insertion Race)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 4: Same-Name Independent File Addition (Insertion Race)")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE SYNC
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish baseline history state."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline state established.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (CREATE a/feature.py)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (Create a/feature.py)",
        "In origin repo-1, create `a/feature.py` with content 'Origin version' and push to repo-1.git."
    )

    origin_feature = origin_dir / "a" / "feature.py"
    origin_feature.write_text("Origin version of feature.py\n")

    run_cmd("git add a/feature.py", cwd=origin_dir)
    run_cmd('git commit -m "origin: add feature.py"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)
    print_file_tree(origin_dir, "Origin Repo (after adding feature.py)")

    breakpoint_prompt(args.auto, 2, "Origin feature.py created and pushed. Ready for hybrid action.")

    # -------------------------------------------------------------------------
    # STEP 3: HYBRID ACTION (INDEPENDENTLY CREATE repo-1/a/feature.py)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Hybrid Action (Independently Create repo-1/a/feature.py)",
        "In hybrid repo, independently create `repo-1/a/feature.py` with content 'Hybrid version' and commit."
    )

    hybrid_feature = hybrid_dir / "repo-1" / "a" / "feature.py"
    hybrid_feature.write_text("Hybrid version of feature.py\n")

    run_cmd("git add repo-1/a/feature.py", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: add repo-1/a/feature.py"', cwd=hybrid_dir)

    print_diagnostic("Hybrid Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=hybrid_dir).stdout)
    print_file_tree(hybrid_dir, "Hybrid Repo (after independent feature.py creation)")

    breakpoint_prompt(args.auto, 3, "Hybrid independent feature.py created. Ready to execute push.")

    # -------------------------------------------------------------------------
    # STEP 4: EXECUTION (PUSH)
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Execution",
        "Run `hybrid-syncer.py push -t repo-1-a` to attempt syncing origin's feature.py into hybrid."
    )

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root, check=False)

    stdout_msg = push_res.stdout if push_res.stdout else "(no stdout)"
    stderr_msg = push_res.stderr if push_res.stderr else "(no stderr)"

    print_diagnostic(f"hybrid-syncer.py push return code: {push_res.returncode}", f"Stdout:\n{stdout_msg}\nStderr:\n{stderr_msg}")

    print_file_tree(origin_dir, "Origin Repo (after push attempt)")
    print_file_tree(hybrid_dir, "Hybrid Repo (after push attempt)")

    breakpoint_prompt(args.auto, 4, "Push executed. Ready for risk and collision analysis.")

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & RISK ANALYSIS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Risk Analysis",
        "Evaluate whether Copybara raised a collision conflict error or silently overwrote hybrid's file."
    )

    hybrid_feature_exists = hybrid_feature.exists()
    hybrid_feature_content = hybrid_feature.read_text().strip() if hybrid_feature_exists else "N/A"

    push_failed = push_res.returncode != 0
    overwritten = hybrid_feature_content == "Origin version of feature.py"

    print(f"{BOLD}State Analysis & Collision Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Push Return Code         : {push_res.returncode} ({'Collision Error Raised' if push_failed else 'Clean Success'})")
    print(f"  • Hybrid feature.py Exists : {hybrid_feature_exists}")
    print(f"  • Hybrid feature.py Content: '{hybrid_feature_content}'")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Risk Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    if push_failed:
        err_status = f"{OKGREEN}[DETECTED / ERROR RAISED]{ENDC}"
        err_desc = f"Copybara halted with exit code {push_res.returncode} due to path collision."
    else:
        err_status = f"{FAIL}[NOT DETECTED]{ENDC}"
        err_desc = "Copybara completed without raising a path collision error."

    print_risk_row("Copybara Collision Error Raised", err_status, err_desc)

    if overwritten:
        ow_status = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}"
        ow_desc = "Hybrid's independent feature.py was silently overwritten by origin's version."
    else:
        ow_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        ow_desc = "Hybrid's independent version was not silently overwritten."

    print_risk_row("Silent Overwrite Risk", ow_status, ow_desc)

    if not overwritten and hybrid_feature_content == "Hybrid version of feature.py":
        loss_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        loss_desc = "Hybrid's independent content was preserved."
    else:
        loss_status = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}"
        loss_desc = "Hybrid's independent content was lost or modified."

    print_risk_row("Hybrid Independent Content Loss Risk", loss_status, loss_desc)
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 4 COMPLETED. Diagnostics & risk analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
