#!/usr/bin/env python3
"""
Test Scenario 8: Doctor Command Manifest Health Check Verification
Validates that `hybrid-syncer.py doctor` (and alias `detector`) detects:
1. Valid manifests pass with 0 errors/warnings and exit code 0.
2. Exact path clashes between targets raise error and non-zero exit code.
3. Prefix path overlaps raise warnings.
4. Non-existent local origin repository paths raise error and non-zero exit code.
"""

import sys
import tempfile
from pathlib import Path

from common import (
    FAIL, OKGREEN, ENDC,
    breakpoint_prompt, get_test_arg_parser, print_banner,
    print_diagnostic, print_result_row, print_step_header, reset_sample_repos, run_cmd
)


def main():
    parser = get_test_arg_parser("Test Scenario 8: Doctor Command Verification")
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
    clean_out = clean_res.stdout + clean_res.stderr
    print_diagnostic("Doctor Output (Clean Manifest)", clean_out)

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
        clash_out = clash_res.stdout + clash_res.stderr
        print_diagnostic("Doctor Output (Exact Clash)", clash_out)

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
        overlap_out = overlap_res.stdout + overlap_res.stderr
        print_diagnostic("Doctor Output (Prefix Overlap)", overlap_out)

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
        missing_out = missing_res.stdout + missing_res.stderr
        print_diagnostic("Detector Output (Missing Repo)", missing_out)

        breakpoint_prompt(args.auto, 4, "Missing repo checked.")

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Assertions",
        "Validate clean pass, exact clash detection, prefix overlap detection, and missing repo detection."
    )

    pass_clean = clean_res.returncode == 0 and "passed health checks cleanly" in clean_out
    print_result_row("1. Doctor passes clean manifest with 0 errors and exit code 0", pass_clean, clean_out.strip().splitlines()[-1] if clean_out else "")

    pass_clash = clash_res.returncode != 0 and "clashes with" in clash_out and "❌ Error" in clash_out
    print_result_row("2. Doctor detects exact path clash and returns non-zero exit code", pass_clash, "Exact path clash error caught")

    pass_overlap = "overlaps with" in overlap_out and "⚠️ Warning" in overlap_out
    print_result_row("3. Doctor detects prefix overlap and reports warning", pass_overlap, "Prefix path overlap warning caught")

    pass_missing = missing_res.returncode != 0 and "does not exist on disk" in missing_out and "❌ Error" in missing_out
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
