#!/usr/bin/env python3
"""
Test Scenario 6: Interleaved Commits Across Mapped and Unmapped Paths

Objective:
  Test how Copybara handles a series of iterative commits in origin that affect both mapped subdirectories (a/)
  and unmapped subdirectories (c/). Evaluate whether Copybara migrates mapped commits, skips unmapped-only commits,
  and strips out unmapped changes from multi-file commits.

Steps:
  1. Setup: Reset repos and run `push --init-history` to establish baseline state.
  2. Origin Action: Make 3 sequential commits in origin repo-1 and push to repo-1.git:
     - Commit 1: Modify mapped file `a/file.a`.
     - Commit 2: Modify unmapped file `c/other.txt`.
     - Commit 3: Modify both mapped `a/file.a` AND unmapped `c/other.txt` in a single commit.
  3. Execution: Run `hybrid-syncer.py push -t repo-1-a`.
  4. Verification & Assertions:
     - Check `a/file.a` in hybrid received all mapped updates.
     - Check `c/other.txt` did NOT leak into hybrid.
     - Verify Copybara skipped unmapped-only Commit 2 and stripped unmapped changes from Commit 3.
"""

import argparse
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


def print_git_log(repo_path, title, count=5):
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

    for folder in ["repo-1", "repo-1.git", "repo-2", "repo-2.git", "hybrid"]:
        p = sample_dir / folder
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()

    run_cmd("./init-repo.sh 1", cwd=sample_dir)
    run_cmd("./init-repo.sh 2", cwd=sample_dir)
    run_cmd("./init-hybrid.sh 1", cwd=sample_dir)
    print(f"{OKGREEN}✔ Sample repositories initialized cleanly.{ENDC}\n")


def main():
    parser = argparse.ArgumentParser(description="Test Scenario 6: Interleaved Commits Across Mapped and Unmapped Paths")
    parser.add_argument("--auto", "-y", action="store_true", help="Run automatically without interactive breakpoints")
    parser.add_argument("--skip-reset", action="store_true", help="Skip resetting sample repositories")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 6: Interleaved Commits Across Mapped and Unmapped Paths")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish clean baseline state."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline established. Ready for origin interleaved commits.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (INTERLEAVED COMMITS)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (3 Interleaved Commits)",
        "Make 3 sequential commits in origin repo-1 affecting mapped (a/) and unmapped (c/) paths."
    )

    origin_file_a = origin_dir / "a" / "file.a"
    origin_c_dir = origin_dir / "c"
    origin_c_dir.mkdir(parents=True, exist_ok=True)
    origin_file_c = origin_c_dir / "other.txt"

    # Commit 1: Modify mapped file a/file.a
    with open(origin_file_a, "a", encoding="utf-8") as f:
        f.write("Commit 1: mapped file update\n")
    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit -m "origin commit 1: update mapped file a/file.a"', cwd=origin_dir)

    # Commit 2: Modify unmapped file c/other.txt
    origin_file_c.write_text("Commit 2: unmapped file creation\n")
    run_cmd("git add c/other.txt", cwd=origin_dir)
    run_cmd('git commit -m "origin commit 2: update unmapped file c/other.txt"', cwd=origin_dir)

    # Commit 3: Modify both mapped a/file.a AND unmapped c/other.txt
    with open(origin_file_a, "a", encoding="utf-8") as f:
        f.write("Commit 3: mapped file update\n")
    with open(origin_file_c, "a", encoding="utf-8") as f:
        f.write("Commit 3: unmapped file update\n")
    run_cmd("git add a/file.a c/other.txt", cwd=origin_dir)
    run_cmd('git commit -m "origin commit 3: modify both mapped a/file.a and unmapped c/other.txt"', cwd=origin_dir)

    # Push all 3 commits to origin bare repo
    run_cmd("git push origin master", cwd=origin_dir)

    print_git_log(origin_dir, "Origin Repo (3 Interleaved Commits)")
    print_file_tree(origin_dir, "Origin Repo (after 3 commits)")

    breakpoint_prompt(args.auto, 2, "3 interleaved commits pushed to origin. Ready to execute iterative push.")

    # -------------------------------------------------------------------------
    # STEP 3: EXECUTION (ITERATIVE PUSH)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Execution",
        "Run `hybrid-syncer.py push -t repo-1-a` to execute Copybara migration in ITERATIVE mode."
    )

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push output", push_res.stdout)

    print_git_log(hybrid_dir, "Hybrid Repo (after iterative push)")
    print_file_tree(hybrid_dir, "Hybrid Repo (after iterative push)")

    breakpoint_prompt(args.auto, 3, "Iterative push executed. Ready for verification and assertions.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & ASSERTIONS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Assertions",
        "Verify mapped updates applied, unmapped file isolated, and commit filtering handled cleanly."
    )

    # Assertion 1: repo-1/a/file.a in hybrid should receive updates from Commit 1 and Commit 3
    hybrid_file_a = hybrid_dir / "repo-1" / "a" / "file.a"
    file_a_content = hybrid_file_a.read_text() if hybrid_file_a.exists() else ""
    check_1_pass = (
        "Commit 1: mapped file update" in file_a_content
        and "Commit 3: mapped file update" in file_a_content
    )

    # Assertion 2: unmapped file c/other.txt must NOT leak into hybrid
    hybrid_file_c_1 = hybrid_dir / "repo-1" / "c" / "other.txt"
    hybrid_file_c_2 = hybrid_dir / "c" / "other.txt"
    check_2_pass = not hybrid_file_c_1.exists() and not hybrid_file_c_2.exists()

    # Assertion 3: Copybara should process Commit 1, skip Commit 2 (no-op unmapped), and process Commit 3 (stripped unmapped)
    hybrid_log_res = run_cmd("git log -n 5 --oneline", cwd=hybrid_dir)
    hybrid_log = hybrid_log_res.stdout
    check_3_pass = (
        "origin commit 1" in hybrid_log
        and "origin commit 3" in hybrid_log
        and "origin commit 2" not in hybrid_log
    )

    print(f"{BOLD}Assertion Results Summary:{ENDC}")
    print(f"{'-' * 75}")

    def print_result(label, status, detail=""):
        status_str = f"{OKGREEN}[PASS]{ENDC}" if status else f"{FAIL}[FAIL]{ENDC}"
        print(f"  {status_str} {label}")
        if detail:
            print(f"         └─ {detail}")

    print_result(
        "1. repo-1/a/file.a in hybrid received all mapped updates (Commit 1 & Commit 3)",
        check_1_pass,
        f"Content:\n{file_a_content.strip()}"
    )

    print_result(
        "2. Unmapped file c/other.txt did NOT leak into hybrid",
        check_2_pass,
        f"Unmapped path exists: {hybrid_file_c_1.exists() or hybrid_file_c_2.exists()}"
    )

    print_result(
        "3. Copybara filtered commits cleanly (Commit 1 migrated, Commit 2 skipped, Commit 3 stripped)",
        check_3_pass,
        f"Hybrid Commit Log:\n{hybrid_log.strip()}"
    )
    print(f"{'-' * 75}\n")

    if check_1_pass and check_2_pass and check_3_pass:
        print(f"{OKGREEN}🎉 TEST SCENARIO 6 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")
    else:
        print(f"{FAIL}❌ TEST SCENARIO 6 FAILED! Check output above for details.{ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
