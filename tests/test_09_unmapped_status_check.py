#!/usr/bin/env python3
"""
Test Scenario 9: Unmapped Path & Orphan File Analyzer Verification
Validates that `hybrid-syncer.py status --check-unmapped` accurately identifies:
1. Tracked orphan files in origin repositories outside defined target paths.
2. Uncommitted local orphan files outside defined target paths.
3. Does NOT flag mapped target paths as orphan files.
"""

import sys
from pathlib import Path

from common import (
    FAIL, OKGREEN, ENDC,
    breakpoint_prompt, get_test_arg_parser, print_banner,
    print_diagnostic, print_result_row, print_step_header, reset_sample_repos, run_cmd
)


def main():
    parser = get_test_arg_parser("Test Scenario 9: Unmapped Path & Orphan Analyzer")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    syncer_py = project_root / "hybrid-syncer.py"

    sample_dir = project_root / "sample-repos"
    origin_repo1_dir = sample_dir / "repo-1"

    print_banner("TEST SCENARIO 9: Unmapped Path & Orphan Analyzer")

    if not args.skip_reset:
        reset_sample_repos(project_root)

    # -------------------------------------------------------------------------
    # STEP 1: BASELINE UNMAPPED CHECK
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Baseline Unmapped Path Analysis",
        "Run `status --check-unmapped` on sample repos where repo-2 has unmapped b/file.b."
    )

    status_step1 = run_cmd(f"python3 {syncer_py} status --check-unmapped", cwd=project_root)
    out1 = status_step1.stdout + status_step1.stderr
    print_diagnostic("Status Output (Baseline Unmapped Check)", out1)

    breakpoint_prompt(args.auto, 1, "Baseline unmapped check complete.")

    # -------------------------------------------------------------------------
    # STEP 2: CREATE UNCOMMITTED ORPHAN FILE IN ORIGIN REPO-1
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Create Uncommitted Orphan File",
        "Create root-level unmapped file `root_script.sh` in repo-1."
    )

    orphan_script = origin_repo1_dir / "root_script.sh"
    orphan_script.write_text("#!/bin/bash\necho 'unmapped script'\n")

    mapped_file = origin_repo1_dir / "a" / "file.a"
    mapped_file.write_text("updated mapped file a\n")

    status_step2 = run_cmd(f"python3 {syncer_py} status --check-unmapped", cwd=project_root)
    out2 = status_step2.stdout + status_step2.stderr
    print_diagnostic("Status Output (With Uncommitted Orphan)", out2)

    breakpoint_prompt(args.auto, 2, "Uncommitted orphan check complete.")

    # -------------------------------------------------------------------------
    # STEP 3: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Verification & Assertions",
        "Validate detection of tracked orphan files, uncommitted orphan files, and path filtering."
    )

    # Assertion 1: Tracked orphan file b/file.b in repo-2 detected
    pass_tracked_orphan = "b/file.b" in out1 and "Tracked Orphan Files" in out1
    print_result_row("1. Tracked orphan file (b/file.b) detected in repo-2", pass_tracked_orphan, "Detected b/file.b outside target repo-2-a path")

    # Assertion 2: Uncommitted orphan file root_script.sh in repo-1 detected
    pass_uncommitted_orphan = "root_script.sh" in out2 and "Uncommitted Orphan Files" in out2
    print_result_row("2. Uncommitted orphan file (root_script.sh) detected in repo-1", pass_uncommitted_orphan, "Detected root_script.sh outside mapped target paths")

    # Assertion 3: Mapped file a/file.a is NOT flagged as orphan file
    pass_mapped_ignored = "a/file.a" not in out2.split("Unmapped & Orphan Path Analysis")[-1]
    print_result_row("3. Mapped target file (a/file.a) correctly excluded from orphan report", pass_mapped_ignored, "Mapped target files ignored by orphan analyzer")

    all_passed = pass_tracked_orphan and pass_uncommitted_orphan and pass_mapped_ignored

    if all_passed:
        print(f"\n{OKGREEN}🎉 TEST SCENARIO 9 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
        sys.exit(0)
    else:
        print(f"\n{FAIL}❌ TEST SCENARIO 9 FAILED! One or more assertions failed.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
