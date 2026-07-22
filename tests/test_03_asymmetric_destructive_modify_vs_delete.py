#!/usr/bin/env python3
"""
Test Scenario 3: Asymmetric Destructive Operation (Modify vs. Delete)

Objective:
  Test what happens when origin modifies a file's content while hybrid completely deletes the file.
  Evaluate if Copybara detects that origin is trying to update a file that was deleted in hybrid,
  or if it quietly recreates/overwrites the file in hybrid.

Steps:
  1. Setup: Baseline clean state with file.a present in both repos (origin a/file.a and hybrid repo-1/a/file.a).
  2. Origin Action: Append new lines to a/file.a in origin repo-1 and push to repo-1.git.
  3. Hybrid Action: Delete repo-1/a/file.a in hybrid (git rm) and commit.
  4. Execution: Run `hybrid-syncer.py push -t repo-1-a`.
  5. Verification & Analysis:
     - Evaluate if Copybara fails explicitly or quietly recreates the file in hybrid.
     - Inspect final file states and content preservation in origin and hybrid.
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
    parser = argparse.ArgumentParser(description="Test Scenario 3: Asymmetric Destructive Operation (Modify vs Delete)")
    parser.add_argument("--auto", "-y", action="store_true", help="Run automatically without interactive breakpoints")
    parser.add_argument("--skip-reset", action="store_true", help="Skip resetting sample repositories")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 3: Asymmetric Destructive Operation (Modify vs. Delete)")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish baseline state with file.a in both repos."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline established. Ready to perform origin modify and hybrid delete.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (MODIFY CONTENT)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (Content Modification)",
        "Append new lines to `a/file.a` in origin repo-1 and push to repo-1.git."
    )

    origin_file_a = origin_dir / "a" / "file.a"
    with open(origin_file_a, "a", encoding="utf-8") as f:
        f.write("line 2: appended in origin repo\nline 3: another modification in origin repo\n")

    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit -m "origin: append new lines to a/file.a"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)
    print_diagnostic("Git Diff in Origin Repo", run_cmd("git diff HEAD~1", cwd=origin_dir).stdout)

    breakpoint_prompt(args.auto, 2, "Origin content modification pushed. Ready for hybrid deletion.")

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
        "Run `hybrid-syncer.py push -t repo-1-a` to attempt syncing origin's modification into hybrid."
    )

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root, check=False)

    stdout_msg = push_res.stdout if push_res.stdout else "(no stdout)"
    stderr_msg = push_res.stderr if push_res.stderr else "(no stderr)"

    print_diagnostic(f"hybrid-syncer.py push return code: {push_res.returncode}", f"Stdout:\n{stdout_msg}\nStderr:\n{stderr_msg}")

    print_file_tree(origin_dir, "Origin Repo (after push attempt)")
    print_file_tree(hybrid_dir, "Hybrid Repo (after push attempt)")

    breakpoint_prompt(args.auto, 4, "Push executed. Ready for verification and behavior analysis.")

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
    file_recreated = hybrid_file_exists and "appended in origin" in hybrid_file_content

    print(f"{BOLD}State Analysis & Sync Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Push Return Code        : {push_res.returncode} ({'Error Raised' if push_failed else 'Clean Success (0)'})")
    print(f"  • Hybrid File Exists      : {hybrid_file_exists}")
    print(f"  • Hybrid File Content     : '{hybrid_file_content}'")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Outcome Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    def print_outcome(label, detected, description):
        status_str = f"{OKGREEN}[YES]{ENDC}" if detected else f"{WARNING}[NO]{ENDC}"
        print(f"  {status_str} {label}")
        print(f"         └─ {description}")

    print_outcome(
        "Copybara Explicit Error Raised",
        push_failed,
        f"Copybara threw exit code {push_res.returncode} on conflict." if push_failed else "Copybara executed with exit code 0 without raising an error."
    )

    print_outcome(
        "File Quietly Recreated in Hybrid",
        file_recreated,
        "Copybara recreated repo-1/a/file.a in hybrid with origin's modified content, overriding hybrid's deletion." if file_recreated else "File was not recreated in hybrid."
    )

    print_outcome(
        "Hybrid Deletion Preserved",
        not hybrid_file_exists,
        "repo-1/a/file.a remains deleted in hybrid repo." if not hybrid_file_exists else "Hybrid's deletion was undone by the push migration."
    )
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 3 COMPLETED. Diagnostics & outcome analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
