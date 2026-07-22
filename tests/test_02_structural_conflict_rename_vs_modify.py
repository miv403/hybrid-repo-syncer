#!/usr/bin/env python3
"""
Test Scenario 2: Structural Conflict: File Rename vs. Concurrent Modification

Objective:
  Git tracks renames heuristically, but Copybara processes operations via transformed directory trees (core.move).
  If someone renames a file in origin while someone else modifies the original file in hybrid,
  evaluate whether Copybara raises a conflict/error or exhibits silent duplication / silent deletion risks.

Steps:
  1. Setup: Baseline clean state with file.a existing in both origin (a/file.a) and hybrid (repo-1/a/file.a).
  2. Origin Action: Rename a/file.a to a/file_renamed.a in origin repo-1 and push to repo-1.git.
  3. Hybrid Action: Modify the content of repo-1/a/file.a in hybrid without renaming it, and commit.
  4. Execution: Run `hybrid-syncer.py sync -t repo-1-a`.
  5. Verification & Risk Analysis:
     - Check if Copybara raises an error/conflict.
     - Inspect for silent duplication (both file.a and file_renamed.a exist).
     - Inspect for silent deletion (hybrid modification lost without trace).
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
    parser = argparse.ArgumentParser(description="Test Scenario 2: Structural Conflict (Rename vs Concurrent Modify)")
    parser.add_argument("--auto", "-y", action="store_true", help="Run automatically without interactive breakpoints")
    parser.add_argument("--skip-reset", action="store_true", help="Skip resetting sample repositories")
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

    # Fetch latest in origin to inspect state
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

    # Inspect file existence in origin
    origin_old_exists = (origin_dir / "a" / "file.a").exists()
    origin_renamed_exists = (origin_dir / "a" / "file_renamed.a").exists()

    # Inspect file existence in hybrid
    hybrid_old_exists = (hybrid_dir / "repo-1" / "a" / "file.a").exists()
    hybrid_renamed_exists = (hybrid_dir / "repo-1" / "a" / "file_renamed.a").exists()

    # Read contents if existing
    origin_old_content = (origin_dir / "a" / "file.a").read_text().strip() if origin_old_exists else "N/A"
    origin_renamed_content = (origin_dir / "a" / "file_renamed.a").read_text().strip() if origin_renamed_exists else "N/A"
    hybrid_old_content = (hybrid_dir / "repo-1" / "a" / "file.a").read_text().strip() if hybrid_old_exists else "N/A"
    hybrid_renamed_content = (hybrid_dir / "repo-1" / "a" / "file_renamed.a").read_text().strip() if hybrid_renamed_exists else "N/A"

    # Evaluate specific risks
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

    def print_risk(label, is_detected, description):
        status_str = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}" if is_detected else f"{OKGREEN}[NOT DETECTED]{ENDC}"
        print(f"  {status_str} {label}")
        print(f"         └─ {description}")

    print_risk(
        "Copybara Error / Conflict Raised",
        sync_failed,
        f"Copybara returned exit code {sync_res.returncode} due to structural divergence." if sync_failed else "Copybara completed without raising a sync error."
    )

    print_risk(
        "Silent Duplication Risk",
        silent_duplication,
        "Both old file.a and new file_renamed.a co-exist in repo." if silent_duplication else "No duplicate file creation detected."
    )

    print_risk(
        "Silent Deletion Risk",
        hybrid_mod_deleted,
        "Hybrid modified content was lost during sync." if hybrid_mod_deleted else "Hybrid modified content preserved in at least one repo location."
    )
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 2 COMPLETED. Diagnostics & risk analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
