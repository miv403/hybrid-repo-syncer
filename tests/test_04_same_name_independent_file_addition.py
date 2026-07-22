#!/usr/bin/env python3
"""
Test Scenario 4: Same-Name Independent File Addition (Insertion Race Condition)

Objective:
  Test what happens when two developers independently create a file at the exact same relative path
  (origin `a/feature.py` vs hybrid `repo-1/a/feature.py`) before any sync occurs.
  Evaluate whether Copybara halts execution with a path collision conflict error or silently overwrites hybrid's file.

Steps:
  1. Setup: Baseline clean state. Run `push --init-history` to establish baseline state.
  2. Origin Action: Create `a/feature.py` with text "Origin version" in origin repo-1 and push to repo-1.git.
  3. Hybrid Action: Create `repo-1/a/feature.py` with text "Hybrid version" in hybrid repo and commit.
  4. Execution: Run `hybrid-syncer.py push -t repo-1-a`.
  5. Verification & Risk Analysis:
     - Check if Copybara raises a collision / revision conflict error.
     - Inspect whether hybrid's "Hybrid version" file was overwritten by "Origin version".
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
    parser = argparse.ArgumentParser(description="Test Scenario 4: Same-Name Independent File Addition")
    parser.add_argument("--auto", "-y", action="store_true", help="Run automatically without interactive breakpoints")
    parser.add_argument("--skip-reset", action="store_true", help="Skip resetting sample repositories")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 4: Same-Name Independent File Addition (Insertion Race)")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos and run `push --init-history` to establish baseline history state."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    init_push_res = run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push --init-history output", init_push_res.stdout)

    print_file_tree(origin_dir, "Origin Repo (repo-1)")
    print_file_tree(hybrid_dir, "Hybrid Repo")

    breakpoint_prompt(args.auto, 1, "Baseline state established. Ready to create independent files.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (CREATE feature.py)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (Create a/feature.py)",
        "In origin repo-1, create `a/feature.py` with content 'Origin version' and push to repo-1.git."
    )

    origin_feature_file = origin_dir / "a" / "feature.py"
    origin_feature_file.write_text("Origin version\n")

    run_cmd("git add a/feature.py", cwd=origin_dir)
    run_cmd('git commit -m "origin: add feature.py"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)
    print_file_tree(origin_dir, "Origin Repo (after adding feature.py)")

    breakpoint_prompt(args.auto, 2, "Origin feature.py created & pushed. Ready for hybrid independent creation.")

    # -------------------------------------------------------------------------
    # STEP 3: HYBRID ACTION (INDEPENDENTLY CREATE repo-1/a/feature.py)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Hybrid Action (Independently Create repo-1/a/feature.py)",
        "In hybrid repo, independently create `repo-1/a/feature.py` with content 'Hybrid version' and commit."
    )

    hybrid_feature_file = hybrid_dir / "repo-1" / "a" / "feature.py"
    hybrid_feature_file.write_text("Hybrid version\n")

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

    breakpoint_prompt(args.auto, 4, "Push executed. Ready for verification and risk analysis.")

    # -------------------------------------------------------------------------
    # STEP 5: VERIFICATION & RISK ANALYSIS
    # -------------------------------------------------------------------------
    print_step_header(
        5,
        "Verification & Risk Analysis",
        "Evaluate whether Copybara raised a collision conflict error or silently overwrote hybrid's file."
    )

    hybrid_feature_exists = hybrid_feature_file.exists()
    hybrid_feature_content = hybrid_feature_file.read_text().strip() if hybrid_feature_exists else "N/A"

    push_failed = push_res.returncode != 0
    silent_overwrite = hybrid_feature_content == "Origin version"
    hybrid_version_preserved = "Hybrid version" in hybrid_feature_content

    print(f"{BOLD}State Analysis & Collision Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Push Return Code         : {push_res.returncode} ({'Collision Error Raised' if push_failed else 'Success (0)'})")
    print(f"  • Hybrid feature.py Exists : {hybrid_feature_exists}")
    print(f"  • Hybrid feature.py Content: '{hybrid_feature_content}'")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Risk Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    def print_risk(label, detected, description):
        status_str = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}" if detected else f"{OKGREEN}[NOT DETECTED / SAFE]{ENDC}"
        print(f"  {status_str} {label}")
        print(f"         └─ {description}")

    print_risk(
        "Copybara Collision Error Raised",
        push_failed,
        f"Copybara halted with exit code {push_res.returncode} due to path collision." if push_failed else "Copybara completed without raising a path collision error."
    )

    print_risk(
        "Silent Overwrite Risk",
        silent_overwrite,
        "Hybrid's independently created file was silently overwritten by Origin's version." if silent_overwrite else "Hybrid's independent version was not silently overwritten."
    )

    print_risk(
        "Hybrid Independent Content Preserved",
        hybrid_version_preserved,
        "Hybrid's independent content was preserved." if hybrid_version_preserved else "Hybrid's independent content was lost."
    )
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 4 COMPLETED. Diagnostics & risk analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
