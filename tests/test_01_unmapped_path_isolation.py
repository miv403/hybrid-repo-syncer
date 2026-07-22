#!/usr/bin/env python3
"""
Test Scenario 1: Unmapped Path Isolation (Boundary Leakage Test)

Objective:
  Manifest defines strict mappings (origin.path, hybrid.path).
  Ensure changes occurring outside target folders in either repos are ignored,
  preventing dirty states, unwanted deletions, or cross-contamination during pull/push operations.

Steps:
  1. Setup: Reset sample repos and run `push --init-history` so both origin and hybrid are clean.
  2. Hybrid Action:
     - In hybrid, create an unmapped folder `repo-1/c/` with `unmapped.txt`.
     - In hybrid, create a valid update inside mapped folder `repo-1/a/file.a`.
     - Commit both changes in hybrid.
  3. Execution: Run `hybrid-syncer.py pull -t repo-1-a`.
  4. Verification:
     - Check `repo-1` in origin: `a/file.a` receives update.
     - `repo-1/c` and `unmapped.txt` must NOT appear in origin (`repo-1`).
     - Copybara should not delete `repo-1/c` from hybrid during subsequent operations.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ANSI Terminal Colors
HEADER = "\033[95m\033[1m"
OKBLUE = "\033[94m"
OKCYAN = "\033[96m"
OKGREEN = "\033[92m\033[1m"
WARNING = "\033[93m"
FAIL = "\033[91m\033[1m"
ENDC = "\033[0m"
BOLD = "\033[1m"


def run_cmd(cmd, cwd=None, check=True, capture=True):
    """Executes a shell command and returns output."""
    res = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and res.returncode != 0:
        err = res.stderr if capture else f"exit code {res.returncode}"
        print(f"{FAIL}[ERROR] Command failed: {cmd}{ENDC}")
        if capture and res.stderr:
            print(f"{FAIL}{res.stderr.strip()}{ENDC}")
        sys.exit(res.returncode)
    return res


def print_banner(title):
    print(f"\n{HEADER}{'=' * 75}{ENDC}")
    print(f"{HEADER}{title.center(75)}{ENDC}")
    print(f"{HEADER}{'=' * 75}{ENDC}\n")


def print_step_header(step_num, title, description=""):
    print(f"{OKCYAN}{'━' * 75}{ENDC}")
    print(f"{BOLD}{OKCYAN}STEP {step_num}: {title}{ENDC}")
    if description:
        print(f"{OKCYAN}{description}{ENDC}")
    print(f"{OKCYAN}{'━' * 75}{ENDC}\n")


def print_diagnostic(title, content):
    print(f"{WARNING}🔍 [DIAGNOSTIC] {title}:{ENDC}")
    if content:
        print(f"{content.strip()}")
    else:
        print("  (empty)")
    print()


def print_file_tree(repo_path, title):
    repo_path = Path(repo_path)
    if not repo_path.exists():
        print_diagnostic(f"File tree for {title}", "Path does not exist")
        return
    res = run_cmd("git ls-files", cwd=repo_path, check=False)
    files = res.stdout.strip() if res.stdout else "No tracked files"
    print_diagnostic(f"Tracked Files in {title} ({repo_path})", files)


def print_git_log(repo_path, title, count=3):
    repo_path = Path(repo_path)
    if not repo_path.exists():
        return
    res = run_cmd(f"git log -n {count} --oneline --graph --stat", cwd=repo_path, check=False)
    print_diagnostic(f"Recent Git Commits in {title}", res.stdout)


def breakpoint_prompt(auto_mode, step_num, title):
    if auto_mode:
        print(f"{OKBLUE}⏩ [AUTO] Skipping breakpoint for Step {step_num}...{ENDC}\n")
        return
    print(f"{BOLD}{WARNING}⏸️  [BREAKPOINT {step_num}] {title}{ENDC}")
    print("Inspect the output above. Press [ENTER] to execute the next step, or [Ctrl+C] to abort...")
    try:
        input()
    except KeyboardInterrupt:
        print(f"\n{FAIL}Test aborted by user.{ENDC}")
        sys.exit(130)


def reset_sample_repos(project_root):
    print(f"{OKBLUE}🔄 Resetting sample repositories...{ENDC}")
    sample_dir = project_root / "sample-repos"
    
    # Remove existing repo directories
    for folder in ["repo-1", "repo-1.git", "repo-2", "repo-2.git", "hybrid"]:
        p = sample_dir / folder
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()

    # Re-initialize repos using init scripts
    run_cmd("./init-repo.sh 1", cwd=sample_dir)
    run_cmd("./init-repo.sh 2", cwd=sample_dir)
    run_cmd("./init-hybrid.sh 1", cwd=sample_dir)
    print(f"{OKGREEN}✔ Sample repositories initialized cleanly.{ENDC}\n")


def main():
    parser = argparse.ArgumentParser(description="Test Scenario 1: Unmapped Path Isolation")
    parser.add_argument("--auto", "-y", action="store_true", help="Run automatically without interactive breakpoints")
    parser.add_argument("--skip-reset", action="store_true", help="Skip resetting sample repositories")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 1: Unmapped Path Isolation (Boundary Leakage)")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & INIT-HISTORY
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Initial Sync",
        "Reset repos and run `hybrid-syncer.py push --init-history` to establish baseline history."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")
    print_git_log(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline established. Ready to perform hybrid actions.")

    # -------------------------------------------------------------------------
    # STEP 2: HYBRID ACTION
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Hybrid Action",
        "Create unmapped file `repo-1/c/unmapped.txt` AND update mapped file `repo-1/a/file.a` in hybrid."
    )

    # 1. Create unmapped folder and file
    unmapped_dir = hybrid_dir / "repo-1" / "c"
    unmapped_dir.mkdir(parents=True, exist_ok=True)
    unmapped_file = unmapped_dir / "unmapped.txt"
    unmapped_file.write_text("This file is in unmapped folder repo-1/c and should NOT leak to origin.\n")

    # 2. Update valid mapped file
    mapped_file = hybrid_dir / "repo-1" / "a" / "file.a"
    mapped_file.write_text("file a updated inside hybrid repo\n")

    # 3. Commit both in hybrid
    run_cmd("git add .", cwd=hybrid_dir)
    run_cmd('git commit -m "hybrid: add repo-1/c/unmapped.txt and update repo-1/a/file.a"', cwd=hybrid_dir)

    print_diagnostic("Latest commit in Hybrid Repo", run_cmd("git log -n 1 --stat", cwd=hybrid_dir).stdout)
    print_diagnostic("Git Diff of HEAD~1 in Hybrid Repo", run_cmd("git diff HEAD~1", cwd=hybrid_dir).stdout)
    print_file_tree(hybrid_dir, "Hybrid Repo (after commit)")

    breakpoint_prompt(args.auto, 2, "Hybrid commit created. Ready to execute pull command.")

    # -------------------------------------------------------------------------
    # STEP 3: EXECUTION (PULL)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Execution",
        "Run `hybrid-syncer.py pull -t repo-1-a` to sync target `repo-1-a` from hybrid to origin."
    )

    pull_res = run_cmd(f"python3 {syncer_py} pull -t repo-1-a --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py pull -t repo-1-a --init-history output", pull_res.stdout)

    # Make origin worktree fetch/pull latest changes from bare origin repo-1.git if needed
    run_cmd("git pull origin master", cwd=origin_dir, check=False)

    print_file_tree(origin_dir, "Origin Repo (repo-1 after pull)")
    print_git_log(origin_dir, "Origin Repo (repo-1 after pull)")

    breakpoint_prompt(args.auto, 3, "Pull executed. Ready to run verification assertions.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & EXPECTED RESULTS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Assertions",
        "Checking expected results: mapped file updated, unmapped file isolated, copybara clean state."
    )

    # Assertion 1: repo-1/a/file.a in origin should receive the update
    origin_file_a = origin_dir / "a" / "file.a"
    file_a_content = origin_file_a.read_text() if origin_file_a.exists() else ""
    check_1_pass = "file a updated inside hybrid repo" in file_a_content

    # Assertion 2: repo-1/c and unmapped.txt MUST NOT appear in origin repo-1
    origin_c_dir = origin_dir / "c"
    origin_unmapped_file = origin_dir / "c" / "unmapped.txt"
    check_2_pass = not origin_c_dir.exists() and not origin_unmapped_file.exists()

    # Assertion 3: Copybara should not throw errors (0=success, 4=NO_OP) or delete repo-1/c from hybrid on subsequent push/pull
    subsequent_push = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root, check=False)
    subsequent_pull = run_cmd(f"python3 {syncer_py} pull -t repo-1-a", cwd=project_root, check=False)
    hybrid_unmapped_exists = unmapped_file.exists()
    check_3_pass = (
        subsequent_push.returncode in (0, 4)
        and subsequent_pull.returncode in (0, 4)
        and hybrid_unmapped_exists
    )

    # Print Assertion Results Table
    print(f"{BOLD}Assertion Results Summary:{ENDC}")
    print(f"{'-' * 75}")

    def print_result(label, status, detail=""):
        status_str = f"{OKGREEN}[PASS]{ENDC}" if status else f"{FAIL}[FAIL]{ENDC}"
        print(f"  {status_str} {label}")
        if detail:
            print(f"         └─ {detail}")

    print_result(
        "1. a/file.a in origin (repo-1) received update",
        check_1_pass,
        f"Content: '{file_a_content.strip()}'"
    )

    print_result(
        "2. repo-1/c and unmapped.txt did NOT appear in origin (repo-1)",
        check_2_pass,
        f"Origin path exists: {origin_c_dir.exists()}"
    )

    print_result(
        "3. Copybara executed subsequent push/pull cleanly & repo-1/c remains intact in hybrid",
        check_3_pass,
        f"Hybrid unmapped file exists: {hybrid_unmapped_exists}"
    )
    print(f"{'-' * 75}\n")

    if check_1_pass and check_2_pass and check_3_pass:
        print(f"{OKGREEN}🎉 TEST SCENARIO 1 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
    else:
        print(f"{FAIL}❌ TEST SCENARIO 1 FAILED! Check output above for details.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
