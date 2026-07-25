#!/usr/bin/env python3
"""
Test Scenario 8: Doctor (Detector) Command Verification

Objective:
  Validate that `hybrid-syncer.py doctor` (and alias `detector`) detects:
  - Clean baseline manifests (0 errors, 0 warnings)
  - Exact path clashes (duplicate hybrid/origin paths)
  - Prefix overlaps (nested directory target paths)
  - Missing local repository paths on disk
"""

import sys
import tempfile
from pathlib import Path

from common import (
    BOLD, FAIL, OKGREEN, ENDC,
    run_cmd, print_banner, print_step_header, print_diagnostic,
    print_file_tree, print_git_log, breakpoint_prompt, reset_sample_repos,
    print_result_row, get_test_arg_parser
)


def main():
    parser = get_test_arg_parser("Test Scenario 8: Doctor (Detector) Command Verification")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    syncer_py = project_root / "hybrid-syncer.py"

    print_banner("TEST SCENARIO 8: Doctor Command Verification")

    if not args.skip_reset:
        reset_sample_repos(project_root)

    # -------------------------------------------------------------------------
    # STEP 1: CLEAN MANIFEST CHECK
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Clean Baseline Manifest Check",
        "Run `hybrid-syncer.py doctor` on valid default sync-manifest.yaml."
    )

    clean_res = run_cmd(f"python3 {syncer_py} doctor", cwd=project_root)
    print_diagnostic("Doctor Output (Clean Manifest)", clean_res.stdout)

    breakpoint_prompt(args.auto, 1, "Clean manifest checked.")

    # Create temporary directory for invalid test manifests
    with tempfile.TemporaryDirectory(prefix="doctor_test_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # -------------------------------------------------------------------------
        # STEP 2: EXACT PATH CLASH CHECK
        # -------------------------------------------------------------------------
        print_step_header(
            2,
            "Exact Path Clash Check",
            "Create manifest with two targets mapping to the exact same hybrid path."
        )

        clash_manifest = tmp_path / "clash_manifest.yaml"
        clash_manifest.write_text("""
hybrid_repo: "./sample-repos/hybrid"
targets:
  target-a:
    origin:
      url: "./sample-repos/repo-1.git"
      path: "a"
    hybrid:
      path: "shared/path"
  target-b:
    origin:
      url: "./sample-repos/repo-2.git"
      path: "a"
    hybrid:
      path: "shared/path"
""")

        clash_res = run_cmd(f"python3 {syncer_py} -c {clash_manifest} doctor", cwd=project_root, check=False)
        print_diagnostic("Doctor Output (Exact Clash)", clash_res.stdout)

        breakpoint_prompt(args.auto, 2, "Exact path clash checked.")

        # -------------------------------------------------------------------------
        # STEP 3: PREFIX OVERLAP CHECK
        # -------------------------------------------------------------------------
        print_step_header(
            3,
            "Prefix Overlap Check",
            "Create manifest with nested target paths (e.g. `repo-1/a` and `repo-1/a/sub`)."
        )

        overlap_manifest = tmp_path / "overlap_manifest.yaml"
        overlap_manifest.write_text("""
hybrid_repo: "./sample-repos/hybrid"
targets:
  parent-target:
    origin:
      url: "./sample-repos/repo-1.git"
      path: "a"
    hybrid:
      path: "repo-1/a"
  nested-target:
    origin:
      url: "./sample-repos/repo-2.git"
      path: "a"
    hybrid:
      path: "repo-1/a/sub"
""")

        overlap_res = run_cmd(f"python3 {syncer_py} -c {overlap_manifest} doctor", cwd=project_root, check=False)
        print_diagnostic("Doctor Output (Prefix Overlap)", overlap_res.stdout)

        breakpoint_prompt(args.auto, 3, "Prefix overlap checked.")

        # -------------------------------------------------------------------------
        # STEP 4: MISSING REPO CHECK
        # -------------------------------------------------------------------------
        print_step_header(
            4,
            "Missing Repository Check",
            "Create manifest referencing non-existent origin repository URL."
        )

        missing_manifest = tmp_path / "missing_manifest.yaml"
        missing_manifest.write_text("""
hybrid_repo: "./sample-repos/hybrid"
targets:
  bad-target:
    origin:
      url: "./sample-repos/non_existent_repo_dir.git"
      path: "a"
    hybrid:
      path: "repo-1/a"
""")

        missing_res = run_cmd(f"python3 {syncer_py} -c {missing_manifest} detector", cwd=project_root, check=False)
        print_diagnostic("Detector Output (Missing Repo)", missing_res.stdout)

        breakpoint_prompt(args.auto, 4, "Missing repo checked.")

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Assertions",
        "Validate clean pass, exact clash detection, prefix overlap detection, and missing repo detection."
    )

    pass_clean = clean_res.returncode == 0 and "passed health checks cleanly" in clean_res.stdout
    print_result_row("1. Doctor passes clean manifest with 0 errors and exit code 0", pass_clean, clean_res.stdout.strip().splitlines()[-1] if clean_res.stdout else "")

    pass_clash = clash_res.returncode == 1 and "clashes with" in clash_res.stdout and "❌ Error" in clash_res.stdout
    print_result_row("2. Doctor detects exact path clash and returns exit code 1", pass_clash, "Exact path clash error caught")

    pass_overlap = "overlaps with" in overlap_res.stdout and "⚠️ Warning" in overlap_res.stdout
    print_result_row("3. Doctor detects prefix overlap and reports warning", pass_overlap, "Prefix path overlap warning caught")

    pass_missing = missing_res.returncode == 1 and "does not exist on disk" in missing_res.stdout and "❌ Error" in missing_res.stdout
    print_result_row("4. Detector alias catches missing local repository path", pass_missing, "Missing repository path error caught")

    all_passed = pass_clean and pass_clash and pass_overlap and pass_missing

    if all_passed:
        print(f"\n{OKGREEN}🎉 TEST SCENARIO 8 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
        sys.exit(0)
    else:
        print(f"\n{FAIL}❌ TEST SCENARIO 8 FAILED! One or more assertions failed.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
