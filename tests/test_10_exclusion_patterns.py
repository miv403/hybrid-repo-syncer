#!/usr/bin/env python3
"""
Test Scenario 10: Target Exclusion Patterns Verification

Objective:
  Validate that `hybrid-syncer.py` properly parses `exclude` pattern rules from
  the YAML manifest, converts them into Copybara Starlark `glob(..., exclude = [...])`
  specifications, and prevents matching excluded files from syncing.
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
    parser = get_test_arg_parser("Test Scenario 10: Target Exclusion Patterns")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    origin_repo1_dir = project_root / "sample-repos" / "repo-1"
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    syncer_py = project_root / "hybrid-syncer.py"

    print_banner("TEST SCENARIO 10: Target Exclusion Patterns")

    if not args.skip_reset:
        reset_sample_repos(project_root)

    with tempfile.TemporaryDirectory(prefix="exclude_test_") as tmp_dir:
        manifest_path = Path(tmp_dir) / "exclude-manifest.yaml"
        manifest_path.write_text(f"""# Manifest with exclude rules
hybrid_repo: "{project_root}/sample-repos/hybrid"
default_branch: "master"

targets:
  repo-1-a:
    origin:
      url: "{project_root}/sample-repos/repo-1.git"
      path: "a"
      exclude:
        - "**/*.tmp"
        - ".github/**"
    hybrid:
      path: "repo-1/a"
""")

        # -------------------------------------------------------------------------
        # STEP 1: STARLARK CONFIG GENERATION
        # -------------------------------------------------------------------------
        print_step_header(
            1,
            "Starlark Spec Generation Verification",
            "Generate Starlark config and verify `glob(..., exclude = [...])` expressions."
        )

        gen_res = run_cmd(f"python3 {syncer_py} -c {manifest_path} generate", cwd=project_root)
        print_diagnostic("Generated Starlark Specification", gen_res.stdout)

        pass_starlark = 'exclude = [' in gen_res.stdout and '"a/**/*.tmp"' in gen_res.stdout and '"a/.github/**"' in gen_res.stdout
        print_result_row("1. Starlark spec contains formatted exclusion glob expression", pass_starlark, 'Found exclude clause with "a/**/*.tmp" and "a/.github/**"')

        breakpoint_prompt(args.auto, 1, "Starlark generation checked.")

        # -------------------------------------------------------------------------
        # STEP 2: CREATE EXCLUDED & VALID FILES IN ORIGIN
        # -------------------------------------------------------------------------
        print_step_header(
            2,
            "Create Excluded & Valid Files in Origin",
            "Create `a/valid_file.a`, `a/cache.tmp`, and `a/.github/ci.yml` in origin repo-1."
        )

        valid_file = origin_repo1_dir / "a" / "valid_file.a"
        valid_file.write_text("This file should sync to hybrid.\n")

        tmp_file = origin_repo1_dir / "a" / "cache.tmp"
        tmp_file.write_text("Temporary file that should NOT sync.\n")

        github_dir = origin_repo1_dir / "a" / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        ci_file = github_dir / "ci.yml"
        ci_file.write_text("name: CI Workflow\n")

        run_cmd("git add .", cwd=origin_repo1_dir)
        run_cmd('git commit -m "origin: add valid file and excluded .tmp / .github files"', cwd=origin_repo1_dir)
        run_cmd("git push origin master", cwd=origin_repo1_dir)

        print_file_tree(origin_repo1_dir, "Origin Repo (repo-1 with excluded files)")

        breakpoint_prompt(args.auto, 2, "Excluded files created in origin.")

        # -------------------------------------------------------------------------
        # STEP 3: EXECUTE PUSH WITH EXCLUSION RULES
        # -------------------------------------------------------------------------
        print_step_header(
            3,
            "Execute Push Migration",
            "Run `push` with exclusion manifest to sync target `repo-1-a`."
        )

        push_res = run_cmd(f"python3 {syncer_py} -c {manifest_path} push --init-history --skip-guards", cwd=project_root)
        print_diagnostic("Push Migration Output", push_res.stdout)

        print_file_tree(hybrid_dir, "Hybrid Repo (after push with exclusions)")

        breakpoint_prompt(args.auto, 3, "Push migration executed.")

        # -------------------------------------------------------------------------
        # STEP 4: VERIFICATION & ASSERTIONS
        # -------------------------------------------------------------------------
        print_step_header(
            4,
            "Verification & Assertions",
            "Validate valid_file.a synced while cache.tmp and .github/ci.yml were excluded."
        )

        hybrid_valid = hybrid_dir / "repo-1" / "a" / "valid_file.a"
        hybrid_tmp = hybrid_dir / "repo-1" / "a" / "cache.tmp"
        hybrid_ci = hybrid_dir / "repo-1" / "a" / ".github" / "ci.yml"

        pass_synced = hybrid_valid.exists() and hybrid_valid.read_text() == "This file should sync to hybrid.\n"
        print_result_row("1. Valid file `repo-1/a/valid_file.a` successfully synced to hybrid", pass_synced, f"Exists: {hybrid_valid.exists()}")

        pass_tmp_excluded = not hybrid_tmp.exists()
        print_result_row("2. Excluded pattern `**/*.tmp` prevented `cache.tmp` from syncing", pass_tmp_excluded, f"Excluded file exists: {hybrid_tmp.exists()}")

        pass_github_excluded = not hybrid_ci.exists()
        print_result_row("3. Excluded pattern `.github/**` prevented `.github/ci.yml` from syncing", pass_github_excluded, f"Excluded file exists: {hybrid_ci.exists()}")

        all_passed = pass_starlark and pass_synced and pass_tmp_excluded and pass_github_excluded

        if all_passed:
            print(f"\n{OKGREEN}🎉 TEST SCENARIO 10 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
            sys.exit(0)
        else:
            print(f"\n{FAIL}❌ TEST SCENARIO 10 FAILED! One or more assertions failed.{ENDC}\n")
            sys.exit(1)


if __name__ == "__main__":
    main()
