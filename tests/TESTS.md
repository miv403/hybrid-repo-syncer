# Hybrid Syncer Test Suite

This directory contains interactive test scenario scripts designed to validate the correctness, boundary isolation, history preservation, and sync behavior of `hybrid-syncer.py` and Copybara workflows.

---

## 🚀 How to Run Tests

All test scripts are written in Python 3 and support both **interactive step-by-step mode** (with breakpoints and diagnostic prints) and **automated non-interactive mode**.

### Interactive Mode (Default)
Step-by-step execution with interactive breakpoints (`[BREAKPOINT]`), showing detailed diagnostic info (Git logs, file trees, diffs) at key mid-points.

```bash
python3 tests/test_01_unmapped_path_isolation.py
python3 tests/test_02_structural_conflict_rename_vs_modify.py
python3 tests/test_03_asymmetric_destructive_modify_vs_delete.py
```

### Automated / Non-Interactive Mode
To run without interactive pause prompts (ideal for CI/CD or rapid validation):

```bash
python3 tests/test_01_unmapped_path_isolation.py --auto
python3 tests/test_02_structural_conflict_rename_vs_modify.py --auto
python3 tests/test_03_asymmetric_destructive_modify_vs_delete.py --auto
```

### Flags & Options
- `--auto` (`-y`): Skip breakpoints and run continuously to completion.
- `--skip-reset`: Skip sample repository clean reset step.

---

## 📜 Test Scenarios Catalog

### Scenario 1: Unmapped Path Isolation (Boundary Leakage Test)
- **Script**: [`tests/test_01_unmapped_path_isolation.py`](file:///home/miv/workspace/staj2026/git-syncer/tests/test_01_unmapped_path_isolation.py)
- **Objective**: Verify that changes occurring outside manifest-defined mapped folders (`origin.path`, `hybrid.path`) are strictly isolated and ignored during `pull` / `push` operations.

#### Test Workflow:
1. **Step 1: Setup & Initial Sync (`--init-history`)**
   - Reset sample repos (`repo-1`, `repo-2`, `hybrid`) to a clean initial state.
   - Run `python3 hybrid-syncer.py push --init-history` to establish Copybara history.
   - *Diagnostic Output*: Print baseline file trees and Git commit logs for `origin` and `hybrid`.
   - *Breakpoint 1*: User inspects clean baseline.

2. **Step 2: Hybrid Action (Unmapped & Mapped Changes)**
   - In `hybrid`, create an unmapped directory `repo-1/c/` and file `unmapped.txt`.
   - In `hybrid`, modify mapped file `repo-1/a/file.a`.
   - Commit both changes together in `hybrid`.
   - *Diagnostic Output*: Print recent Git commit with `--stat`, diff against `HEAD~1`, and updated file tree.
   - *Breakpoint 2*: User inspects committed unmapped and mapped changes.

3. **Step 3: Execution (Pull Target `repo-1-a`)**
   - Run `python3 hybrid-syncer.py pull -t repo-1-a --init-history`.
   - *Diagnostic Output*: Print Copybara execution logs, origin Git commit log, and origin file tree.
   - *Breakpoint 3*: User inspects pull output before assertion check.

4. **Step 4: Verification & Assertions**
   - **Assertion 1**: Mapped file `a/file.a` in `repo-1` receives the update from `hybrid`.
   - **Assertion 2**: Unmapped path `repo-1/c` and `unmapped.txt` do **NOT** leak into origin `repo-1`.
   - **Assertion 3**: Copybara executes subsequent push/pull operations without errors, and `repo-1/c/unmapped.txt` remains intact inside `hybrid`.

---

### Scenario 2: Structural Conflict (File Rename vs. Concurrent Modification)
- **Script**: [`tests/test_02_structural_conflict_rename_vs_modify.py`](file:///home/miv/workspace/staj2026/git-syncer/tests/test_02_structural_conflict_rename_vs_modify.py)
- **Objective**: Git tracks renames heuristically, but Copybara processes operations via transformed directory trees (`core.move`). Evaluate whether Copybara raises a conflict error or exhibits silent duplication / silent deletion risks when a file is renamed in origin while concurrently modified in hybrid.

#### Test Workflow:
1. **Step 1: Setup & Baseline Sync**
   - Reset sample repos to clean initial state.
   - Run `python3 hybrid-syncer.py push --init-history` to establish baseline with `file.a`.
   - *Breakpoint 1*: User inspects clean baseline with `file.a` present in both repos.

2. **Step 2: Origin Action (File Rename)**
   - In origin `repo-1`, rename `a/file.a` to `a/file_renamed.a` (`git mv`) and push to `repo-1.git`.
   - *Diagnostic Output*: Print origin commit log and updated origin file tree.
   - *Breakpoint 2*: User inspects origin rename commit.

3. **Step 3: Hybrid Action (Concurrent Modification)**
   - In hybrid repo, modify content of `repo-1/a/file.a` without renaming it, and commit.
   - *Diagnostic Output*: Print hybrid commit log, commit diff, and updated hybrid file tree.
   - *Breakpoint 3*: User inspects hybrid content modification.

4. **Step 4: Execution (`hybrid-syncer.py sync`)**
   - Run `python3 hybrid-syncer.py sync -t repo-1-a --init-history` to execute bi-directional sync under structural divergence.
   - *Diagnostic Output*: Print stdout, stderr, and exit code from Copybara execution.
   - *Breakpoint 4*: User inspects sync execution outcome.

5. **Step 5: Verification & Risk Analysis**
   - **Error / Conflict Raised Check**: Evaluate if Copybara detected structural divergence and raised an error.
   - **Silent Duplication Risk Check**: Check if both `file.a` AND `file_renamed.a` persist in either repository.
   - **Silent Deletion Risk Check**: Check if hybrid's modified content was overwritten or deleted without trace.

---

### Scenario 3: Asymmetric Destructive Operation (Modify vs. Delete)
- **Script**: [`tests/test_03_asymmetric_destructive_modify_vs_delete.py`](file:///home/miv/workspace/staj2026/git-syncer/tests/test_03_asymmetric_destructive_modify_vs_delete.py)
- **Objective**: Test what happens when origin updates a file's contents while hybrid completely deletes the file. Evaluate if Copybara detects destination/origin state mismatch or quietly recreates the file in hybrid.

#### Test Workflow:
1. **Step 1: Setup & Baseline Sync**
   - Reset sample repos to clean initial state.
   - Run `python3 hybrid-syncer.py push --init-history` to establish baseline with `file.a` in both repos.
   - *Breakpoint 1*: User inspects baseline.

2. **Step 2: Origin Action (Content Modification)**
   - Append new lines to `a/file.a` in origin `repo-1` and push to `repo-1.git`.
   - *Diagnostic Output*: Print origin commit log and diff.
   - *Breakpoint 2*: User inspects origin modification.

3. **Step 3: Hybrid Action (File Deletion)**
   - Delete `repo-1/a/file.a` in hybrid using `git rm` and commit.
   - *Diagnostic Output*: Print hybrid commit log and updated hybrid file tree.
   - *Breakpoint 3*: User inspects file deletion in hybrid.

4. **Step 4: Execution (`hybrid-syncer.py push`)**
   - Run `python3 hybrid-syncer.py push -t repo-1-a` to attempt syncing origin's modification into hybrid.
   - *Diagnostic Output*: Print stdout, stderr, exit code, and updated file trees.
   - *Breakpoint 4*: User inspects push execution outcome.

5. **Step 5: Verification & Behavior Analysis**
   - Check if Copybara raised an explicit error/conflict.
   - Check if `repo-1/a/file.a` was quietly recreated in hybrid with origin's modified content.
   - Check if hybrid's file deletion was preserved or overridden.

---
