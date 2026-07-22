#!/usr/bin/env python3
"""
Test Scenario 2: Structural Conflict: File Rename vs. Concurrent Modification

Objective:
  Git tracks renames heuristically, but Copybara processes operations via transformed directory trees (core.move).
  If someone renames a file in origin while someone else modifies the original file in hybrid,
  evaluate whether Copybara raises a conflict/error or exhibits silent duplication / silent deletion risks.
"""

import sys
from pathlib import Path

from common import (
    BOLD, FAIL, OKGREEN, WARNING, ENDC,
    run_cmd, print_banner, print_step_header, print_diagnostic,
    print_file_tree, print_git_log, breakpoint_prompt, reset_sample_repos,
    print_risk_row, get_test_arg_parser
)


def main():
    parser = get_test_arg_parser("Test Scenario 2: Structural Conflict (Rename vs Concurrent Modify)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 2: File Rename vs. Concurrent Modification")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish baseline state with file.a."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline state established with file.a in both repos.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (RENAME)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (File Rename)",
        "In origin repo-1, rename `a/file.a` to `a/file_renamed.a` and push to repo-1.git."
    )

    run_cmd("git mv a/file.a a/file_renamed.a", cwd=origin_dir)
    run_cmd('git commit -m "origin: rename a/file.a to a/file_renamed.a"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)
    print_file_tree(origin_dir, "Origin Repo (after rename)")

    breakpoint_prompt(args.auto, 2, "Origin rename committed & pushed. Ready for hybrid action.")

    # -------------------------------------------------------------------------
    # STEP 3: HYBRID ACTION (CONCURRENT MODIFICATION)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Hybrid Action (Concurrent Content Modification)",
        "In hybrid repo, modify content of `repo-1/a/file.a` without renaming it and commit."
    )

    hybrid_file_a = hybrid_dir / "repo-1" / "a" / "file.a"
    hybrid_file_a.write_text("file a modified concurrently in hybrid repo\n")

    run_cmd("git add .", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: modify repo-1/a/file.a content"', cwd=hybrid_dir)

    print_diagnostic("Hybrid Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=hybrid_dir).stdout)
    print_diagnostic("Git Diff of HEAD~1 in Hybrid Repo", run_cmd("git diff HEAD~1", cwd=hybrid_dir).stdout)

    breakpoint_prompt(args.auto, 3, "Hybrid concurrent modification committed. Ready to execute sync.")

    # -------------------------------------------------------------------------
    # STEP 4: EXECUTION (SYNC)
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Execution",
        "Run `hybrid-syncer.py sync -t repo-1-a` to execute bi-directional sync under structural conflict."
    )

    sync_res = run_cmd(f"python3 {syncer_py} sync -t repo-1-a --init-history", cwd=project_root, check=False)

    stdout_msg = sync_res.stdout if sync_res.stdout else "(no stdout)"
    stderr_msg = sync_res.stderr if sync_res.stderr else "(no stderr)"

    print_diagnostic(f"hybrid-syncer.py sync return code: {sync_res.returncode}", f"Stdout:\n{stdout_msg}\nStderr:\n{stderr_msg}")

    run_cmd("git pull origin master", cwd=origin_dir, check=False)

    print_file_tree(origin_dir, "Origin Repo (after sync attempt)")
    print_file_tree(hybrid_dir, "Hybrid Repo (after sync attempt)")

    breakpoint_prompt(args.auto, 4, "Sync executed. Ready for risk and verification analysis.")

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & RISK ANALYSIS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Risk Analysis",
        "Analyze failure modes: Copybara conflict errors, Silent Duplication, or Silent Deletion."
    )

    origin_old_exists = (origin_dir / "a" / "file.a").exists()
    origin_renamed_exists = (origin_dir / "a" / "file_renamed.a").exists()

    hybrid_old_exists = (hybrid_dir / "repo-1" / "a" / "file.a").exists()
    hybrid_renamed_exists = (hybrid_dir / "repo-1" / "a" / "file_renamed.a").exists()

    origin_old_content = (origin_dir / "a" / "file.a").read_text().strip() if origin_old_exists else "N/A"
    origin_renamed_content = (origin_dir / "a" / "file_renamed.a").read_text().strip() if origin_renamed_exists else "N/A"
    hybrid_old_content = (hybrid_dir / "repo-1" / "a" / "file.a").read_text().strip() if hybrid_old_exists else "N/A"
    hybrid_renamed_content = (hybrid_dir / "repo-1" / "a" / "file_renamed.a").read_text().strip() if hybrid_renamed_exists else "N/A"

    sync_failed = sync_res.returncode != 0
    silent_duplication = (origin_old_exists and origin_renamed_exists) or (hybrid_old_exists and hybrid_renamed_exists)
    hybrid_mod_deleted = (
        "modified concurrently" not in origin_old_content
        and "modified concurrently" not in origin_renamed_content
        and "modified concurrently" not in hybrid_old_content
        and "modified concurrently" not in hybrid_renamed_content
    )

    print(f"{BOLD}State Analysis & Conflict Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Sync Exit Code          : {sync_res.returncode} ({'Error/Conflict Reported' if sync_failed else 'Success/Clean Exit'})")
    print(f"  • Origin Files Present   : file.a={origin_old_exists}, file_renamed.a={origin_renamed_exists}")
    print(f"  • Hybrid Files Present   : file.a={hybrid_old_exists}, file_renamed.a={hybrid_renamed_exists}")
    print(f"  • Origin file.a content  : '{origin_old_content}'")
    print(f"  • Origin renamed content : '{origin_renamed_content}'")
    print(f"  • Hybrid file.a content  : '{hybrid_old_content}'")
    print(f"  • Hybrid renamed content : '{hybrid_renamed_content}'")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Risk Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    if sync_failed:
        copybara_status = f"{OKGREEN}[DETECTED / ERROR RAISED]{ENDC}" if not (hybrid_mod_deleted or silent_duplication) else f"{FAIL}[DETECTED / ERROR RAISED]{ENDC}"
        copybara_desc = f"Copybara returned exit code {sync_res.returncode} due to structural divergence."
    elif hybrid_mod_deleted or silent_duplication:
        copybara_status = f"{WARNING}[NOT DETECTED]{ENDC}"
        copybara_desc = "Copybara completed without raising a sync error (uncaught structural conflict leading to data loss)."
    else:
        copybara_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        copybara_desc = "Copybara completed without raising a sync error."

    print_risk_row("Copybara Error / Conflict Raised", copybara_status, copybara_desc)

    if silent_duplication:
        dup_status = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}"
        dup_desc = "Both old file.a and new file_renamed.a co-exist in repo."
    else:
        dup_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        dup_desc = "No duplicate file creation detected."

    print_risk_row("Silent Duplication Risk", dup_status, dup_desc)

    if hybrid_mod_deleted:
        del_status = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}"
        del_desc = "Hybrid modified content was lost during sync."
    else:
        del_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        del_desc = "Hybrid modified content preserved in at least one repo location."

    print_risk_row("Silent Deletion Risk", del_status, del_desc)
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 2 COMPLETED. Diagnostics & risk analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
