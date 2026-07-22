#!/usr/bin/env python3
"""
Test Scenario 5: History Rewrite / Rebase Desynchronization

Objective:
  Copybara relies on commit metadata (GitOrigin-RevId) recorded in destination commit logs to calculate revision state.
  If an origin developer rewrites history (git commit --amend / rebase) and force-pushes,
  the origin SHA changes. Evaluate whether Copybara detects the missing SHA and throws an explicit revision error.

Steps:
  1. Setup: Reset repos and run `push --init-history` followed by a initial sync so hybrid has GitOrigin-RevId recorded.
  2. Origin Action: Amend the latest commit in origin (`git commit --amend`) to rewrite its SHA, then force-push (`git push --force`).
  3. Execution: Run `hybrid-syncer.py push -t repo-1-a`.
  4. Verification & Assertions:
     - Check if Copybara fails explicitly with a revision lookup error (e.g., Cannot find last migrated revision).
     - Verify that `--init-history` or state recovery is required to re-establish sync.
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
WARNING = "\033[93m\033[1m"
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
    parser = argparse.ArgumentParser(description="Test Scenario 5: History Rewrite / Rebase Desynchronization")
    parser.add_argument("--auto", "-y", action="store_true", help="Run automatically without interactive breakpoints")
    parser.add_argument("--skip-reset", action="store_true", help="Skip resetting sample repositories")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    hybrid_dir = project_root / "sample-repos" / "hybrid"
    origin_dir = project_root / "sample-repos" / "repo-1"

    print_banner("TEST SCENARIO 5: History Rewrite / Rebase Desynchronization")

    # -------------------------------------------------------------------------
    # STEP 1: SETUP & BASELINE SYNC
    # -------------------------------------------------------------------------
    print_step_header(
        1,
        "Setup & Baseline Sync",
        "Reset repos, perform origin update, and run `push` so hybrid records GitOrigin-RevId."
    )

    if not args.skip_reset:
        reset_sample_repos(project_root)

    syncer_py = project_root / "hybrid-syncer.py"
    run_cmd(f"python3 {syncer_py} push --init-history", cwd=project_root)

    # Make a baseline change in origin and push it to hybrid to record GitOrigin-RevId
    origin_file = origin_dir / "a" / "file.a"
    origin_file.write_text("baseline change in origin for revision tracking\n")
    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit -m "origin: baseline sync commit"', cwd=origin_dir)
    run_cmd("git push origin master", cwd=origin_dir)

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root)
    print_diagnostic("hybrid-syncer.py push output", push_res.stdout)

    print_git_log(origin_dir, "Origin Repo (baseline)")
    print_git_log(hybrid_dir, "Hybrid Repo (showing GitOrigin-RevId in commit message)")

    breakpoint_prompt(args.auto, 1, "Baseline sync complete. GitOrigin-RevId recorded in hybrid.")

    # -------------------------------------------------------------------------
    # STEP 2: ORIGIN ACTION (AMEND COMMIT & FORCE PUSH)
    # -------------------------------------------------------------------------
    print_step_header(
        2,
        "Origin Action (History Rewrite & Force Push)",
        "Amend latest commit in origin to rewrite its SHA, then force-push to repo-1.git."
    )

    # Amend origin commit to rewrite SHA
    origin_file.write_text("amended content during origin history rewrite\n")
    run_cmd("git add a/file.a", cwd=origin_dir)
    run_cmd('git commit --amend -m "origin: REWRITTEN baseline commit (amended SHA)"', cwd=origin_dir)
    run_cmd("git push --force origin master", cwd=origin_dir)

    print_diagnostic("Origin Repo Commit Log (after commit amend)", run_cmd("git log -n 1 --stat", cwd=origin_dir).stdout)

    breakpoint_prompt(args.auto, 2, "Origin history rewritten & force-pushed. Ready to execute push.")

    # -------------------------------------------------------------------------
    # STEP 3: EXECUTION (PUSH)
    # -------------------------------------------------------------------------
    print_step_header(
        3,
        "Execution",
        "Run `hybrid-syncer.py push -t repo-1-a` to attempt sync after history rewrite."
    )

    push_res = run_cmd(f"python3 {syncer_py} push -t repo-1-a", cwd=project_root, check=False)

    stdout_msg = push_res.stdout if push_res.stdout else "(no stdout)"
    stderr_msg = push_res.stderr if push_res.stderr else "(no stderr)"

    print_diagnostic(f"hybrid-syncer.py push return code: {push_res.returncode}", f"Stdout:\n{stdout_msg}\nStderr:\n{stderr_msg}")

    breakpoint_prompt(args.auto, 3, "Push executed. Ready for failure mode verification.")

    # -------------------------------------------------------------------------
    # STEP 4: VERIFICATION & RISK ANALYSIS
    # -------------------------------------------------------------------------
    print_step_header(
        4,
        "Verification & Risk Analysis",
        "Analyze whether Copybara raised a revision error or silently re-synced amended history."
    )

    push_failed = push_res.returncode != 0
    stderr_combined = (push_res.stderr + push_res.stdout).lower()
    revision_error_detected = (
        "cannot find" in stderr_combined
        and "revision" in stderr_combined
    ) or (
        "gitorigin-revid" in stderr_combined
        or "cannot resolve reference" in stderr_combined
        or "could not be found" in stderr_combined
    )

    print_git_log(hybrid_dir, "Hybrid Repo (after push after origin amend)")

    print(f"{BOLD}State Analysis & History Inspection:{ENDC}")
    print(f"{'-' * 75}")
    print(f"  • Push Return Code      : {push_res.returncode} ({'Revision Error Raised' if push_failed else 'Success (0)'})")
    print(f"  • Revision Error Raised : {revision_error_detected}")
    print(f"{'-' * 75}\n")

    print(f"{BOLD}Risk Evaluation:{ENDC}")
    print(f"{'-' * 75}")

    def print_risk(label, status_str, description):
        print(f"  {status_str} {label}")
        print(f"         └─ {description}")

    if push_failed or revision_error_detected:
        copybara_status = f"{FAIL}[DETECTED / ERROR RAISED]{ENDC}"
        copybara_desc = f"Copybara raised an explicit error (code {push_res.returncode}) on force-pushed history."
    elif not push_failed:
        copybara_status = f"{WARNING}[NOT DETECTED]{ENDC}"
        copybara_desc = "Copybara completed without raising a revision error (silently processed force-pushed history without halting)."
    else:
        copybara_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        copybara_desc = "Copybara completed without raising a revision error."

    print_risk("Copybara Revision Lookup Error Raised", copybara_status, copybara_desc)

    if not push_failed:
        resync_status = f"{FAIL}[DETECTED / RISK ACTIVE]{ENDC}"
        resync_desc = "Copybara silently processed the force-pushed commit instead of halting for history verification."
    else:
        resync_status = f"{OKGREEN}[NOT DETECTED]{ENDC}"
        resync_desc = "Copybara halted on force push."

    print_risk("Silent Re-sync / Duplicate Commit Risk on Force Push", resync_status, resync_desc)
    print(f"{'-' * 75}\n")

    print(f"{OKGREEN}🎉 TEST SCENARIO 5 COMPLETED. Diagnostics & risk analysis reported above.{ENDC}\n")


if __name__ == "__main__":
    main()
