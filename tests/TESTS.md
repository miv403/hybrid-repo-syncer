# Hybrid Syncer Test Suite

This directory contains interactive test scenario scripts designed to validate the correctness, boundary isolation, history preservation, and sync behavior of `hybrid-syncer.py` and Copybara workflows.

---

## 🚀 How to Run Tests

All test scripts are written in Python 3 and support both **interactive step-by-step mode** (with breakpoints and diagnostic prints) and **automated non-interactive mode**.

### Master Test Suite Runner
To execute the entire test suite sequentially and output a unified pass/fail summary table:

```bash
python3 tests/run_all.py
```

### Interactive Mode (Default)
Step-by-step execution with interactive breakpoints (`[BREAKPOINT]`), showing detailed diagnostic info (Git logs, file trees, diffs) at key mid-points.

```bash
python3 tests/test_01_unmapped_path_isolation.py
python3 tests/test_02_structural_conflict_rename_vs_modify.py
python3 tests/test_03_asymmetric_destructive_modify_vs_delete.py
python3 tests/test_04_same_name_independent_file_addition.py
python3 tests/test_05_history_rewrite_rebase_desync.py
python3 tests/test_06_interleaved_commits_mapped_unmapped.py
```

### Automated / Non-Interactive Mode
To run individual test scripts without interactive pause prompts:

```bash
python3 tests/test_01_unmapped_path_isolation.py --auto
python3 tests/test_02_structural_conflict_rename_vs_modify.py --auto
python3 tests/test_03_asymmetric_destructive_modify_vs_delete.py --auto
python3 tests/test_04_same_name_independent_file_addition.py --auto
python3 tests/test_05_history_rewrite_rebase_desync.py --auto
python3 tests/test_06_interleaved_commits_mapped_unmapped.py --auto
```

### Flags & Options
- `--auto` (`-y`): Skip breakpoints and run continuously to completion.
- `--skip-reset`: Skip sample repository clean reset step.

---

## 🛠️ Test Suite Architecture

The test suite uses a centralized architecture for DRY maintainability:

- **`tests/common.py`**: Shared helper module providing Git execution (`run_cmd`), sample repository resets (`reset_sample_repos`), diagnostic reporting (`print_file_tree`, `print_git_log`, `print_diagnostic`), interactive breakpoints (`breakpoint_prompt`), and CLI argument parsing.
- **`tests/run_all.py`**: Master test runner executing all scenario scripts sequentially and reporting unified pass/fail results.
- **Scenario Scripts (`test_01` through `test_06`)**: Individual scenario scripts focusing strictly on defining Git actions and verifying outcomes.

---

## Summary Overview Matrix

| Scenario | Primary Risk Area | Expected Copybara / Tool Behavior |
| --- | --- | --- |
| **1. Unmapped Path Isolation** | Scope boundary leakage | Unmapped paths strictly ignored during `pull`<br> |
| **2. Rename vs. Modify** | Directory transformation / `core.move`<br> | Sync error triggered; prevents silent duplication/deletion |
| **3. Modify vs. Delete** | Asymmetric state divergence | Migration fails cleanly without orphaned states |
| **4. Insertion Race** | Origin state tracking (`GitOrigin-RevId`) | Path collision error due to missing commit lineage |
| **5. History Rewrite** | Broken SHA bookmarks | RevId lookup failure; alerts necessity for history re-init |
| **6. Interleaved Commits** | `ITERATIVE` mode filtering | Filters non-matching origin path diffs dynamically |

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

```
Assertion Results Summary:
---------------------------------------------------------------------------
  [PASS] 1. a/file.a in origin (repo-1) received update
         └─ Content: 'file a updated inside hybrid repo'
  [PASS] 2. repo-1/c and unmapped.txt did NOT appear in origin (repo-1)
         └─ Origin path exists: False
  [PASS] 3. Copybara executed subsequent push/pull cleanly & repo-1/c remains intact in hybrid
         └─ Hybrid unmapped file exists: True
---------------------------------------------------------------------------
```

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

```
Risk Evaluation:
---------------------------------------------------------------------------
  [NOT DETECTED] Copybara Error / Conflict Raised
         └─ Copybara completed without raising a sync error (uncaught structural conflict leading to data loss).
  [NOT DETECTED] Silent Duplication Risk
         └─ No duplicate file creation detected.
  [DETECTED / RISK ACTIVE] Silent Deletion Risk
         └─ Hybrid modified content was lost during sync.
---------------------------------------------------------------------------
```

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

```
Outcome Evaluation:
---------------------------------------------------------------------------
  [NO] Copybara Explicit Error Raised
         └─ Copybara executed with exit code 0 without raising an error.
  [YES] File Quietly Recreated in Hybrid
         └─ Copybara recreated repo-1/a/file.a in hybrid with origin's modified content, overriding hybrid's deletion.
  [NO] Hybrid Deletion Preserved
         └─ Hybrid's deletion was undone by the push migration.
---------------------------------------------------------------------------
```

---

### Scenario 4: Same-Name Independent File Addition (Insertion Race Condition)
- **Script**: [`tests/test_04_same_name_independent_file_addition.py`](file:///home/miv/workspace/staj2026/git-syncer/tests/test_04_same_name_independent_file_addition.py)
- **Objective**: Test what happens when two developers independently create a file at the exact same relative path (`a/feature.py` in origin vs `repo-1/a/feature.py` in hybrid) before any sync occurs. Evaluate whether Copybara halts execution with a path collision error or silently overwrites hybrid's file.

#### Test Workflow:
1. **Step 1: Setup & Baseline Sync**
   - Reset sample repos to clean initial state.
   - Run `python3 hybrid-syncer.py push --init-history` to establish baseline history state.
   - *Breakpoint 1*: User inspects clean baseline.

2. **Step 2: Origin Action (Create `a/feature.py`)**
   - Create `a/feature.py` with content `"Origin version"` in origin `repo-1` and push to `repo-1.git`.
   - *Diagnostic Output*: Print origin commit log and file tree.
   - *Breakpoint 2*: User inspects origin file creation.

3. **Step 3: Hybrid Action (Independently Create `repo-1/a/feature.py`)**
   - Independently create `repo-1/a/feature.py` with content `"Hybrid version"` in hybrid repo and commit.
   - *Diagnostic Output*: Print hybrid commit log and file tree.
   - *Breakpoint 3*: User inspects hybrid independent file creation.

4. **Step 4: Execution (`hybrid-syncer.py push`)**
   - Run `python3 hybrid-syncer.py push -t repo-1-a` to attempt syncing origin's `feature.py` into hybrid.
   - *Diagnostic Output*: Print stdout, stderr, exit code, and updated file trees.
   - *Breakpoint 4*: User inspects push execution outcome.

5. **Step 5: Verification & Risk Analysis**
   - **Collision Error Raised Check**: Check if Copybara halts with exit code error due to path collision.
   - **Silent Overwrite Risk Check**: Check if hybrid's `"Hybrid version"` content was silently overwritten by origin's `"Origin version"`.
   - **Hybrid Content Preservation Check**: Check if hybrid's independent content was preserved or lost.

```
Risk Evaluation:
---------------------------------------------------------------------------
  [NOT DETECTED] Copybara Collision Error Raised
         └─ Copybara completed without raising a path collision error (uncaught path collision leading to data loss).
  [DETECTED / RISK ACTIVE] Silent Overwrite Risk
         └─ Hybrid's independently created file was silently overwritten by Origin's version.
  [DETECTED / RISK ACTIVE] Hybrid Independent Content Loss Risk
         └─ Hybrid's independent content was lost during sync.
---------------------------------------------------------------------------
```

---

### Scenario 5: History Rewrite / Rebase Desynchronization
- **Script**: [`tests/test_05_history_rewrite_rebase_desync.py`](file:///home/miv/workspace/staj2026/git-syncer/tests/test_05_history_rewrite_rebase_desync.py)
- **Objective**: Copybara relies heavily on commit metadata (`GitOrigin-RevId`) recorded in destination commit logs to calculate revision state. If an origin developer rewrites history (`git commit --amend` or rebase) and force-pushes, the origin SHA changes. Evaluate whether Copybara detects the missing SHA and throws an explicit revision error.

#### Test Workflow:
1. **Step 1: Setup & Baseline Sync**
   - Reset sample repos to clean initial state.
   - Perform initial push so hybrid records `GitOrigin-RevId` pointing to origin's latest commit SHA.
   - *Diagnostic Output*: Print origin commit log and hybrid commit log showing `GitOrigin-RevId`.
   - *Breakpoint 1*: User inspects baseline history recording.

2. **Step 2: Origin Action (History Rewrite & Force Push)**
   - Amend the latest commit in origin (`git commit --amend`) to rewrite its SHA.
   - Force-push to origin (`git push --force origin master`).
   - *Diagnostic Output*: Print origin's amended commit log.
   - *Breakpoint 2*: User inspects amended commit and force push.

3. **Step 3: Execution (`hybrid-syncer.py push`)**
   - Run `python3 hybrid-syncer.py push -t repo-1-a` to attempt sync after history rewrite.
   - *Diagnostic Output*: Print Copybara error output and exit code.
   - *Breakpoint 3*: User inspects push failure.

4. **Step 4: Verification & Failure Mode Assertions**
   - **Explicit Error Raised Check**: Verify `push` fails with a non-zero exit code.
   - **Revision Lookup Desynchronization Check**: Verify Copybara error output matches revision lookup / `GitOrigin-RevId` failure.

```
Risk Evaluation:
---------------------------------------------------------------------------
  [NOT DETECTED] Copybara Revision Lookup Error Raised
         └─ Copybara completed without raising a revision error (silently processed force-pushed history without halting).
  [DETECTED / RISK ACTIVE] Silent Re-sync / Duplicate Commit Risk on Force Push
         └─ Copybara silently processed the force-pushed commit instead of halting for history verification.
---------------------------------------------------------------------------
```

---

### Scenario 6: Interleaved Commits Across Mapped and Unmapped Paths
- **Script**: [`tests/test_06_interleaved_commits_mapped_unmapped.py`](file:///home/miv/workspace/staj2026/git-syncer/tests/test_06_interleaved_commits_mapped_unmapped.py)
- **Objective**: Test how Copybara handles a series of iterative commits in origin that affect both mapped subdirectories (`a/`) and unmapped subdirectories (`c/`). Evaluate whether Copybara migrates mapped commits, skips unmapped-only commits, and strips out unmapped changes from multi-file commits.

#### Test Workflow:
1. **Step 1: Setup & Baseline Sync**
   - Reset sample repos to clean initial state.
   - Run `python3 hybrid-syncer.py push --init-history` to establish clean baseline.
   - *Breakpoint 1*: User inspects baseline.

2. **Step 2: Origin Action (3 Interleaved Commits)**
   - Commit 1: Modify mapped file `a/file.a`.
   - Commit 2: Modify unmapped file `c/other.txt`.
   - Commit 3: Modify both mapped `a/file.a` AND unmapped `c/other.txt` in a single commit.
   - Push all 3 commits to `repo-1.git`.
   - *Diagnostic Output*: Print origin commit log showing all 3 commits.
   - *Breakpoint 2*: User inspects 3 origin commits.

3. **Step 3: Execution (`hybrid-syncer.py push`)**
   - Run `python3 hybrid-syncer.py push -t repo-1-a` in `ITERATIVE` mode.
   - *Diagnostic Output*: Print stdout, stderr, and hybrid commit log.
   - *Breakpoint 3*: User inspects iterative push migration.

4. **Step 4: Verification & Assertions**
   - **Assertion 1**: `repo-1/a/file.a` in hybrid received all mapped updates from Commit 1 and Commit 3.
   - **Assertion 2**: Unmapped file `c/other.txt` did **NOT** leak into hybrid.
   - **Assertion 3**: Copybara filtered commits cleanly: Commit 1 migrated, Commit 2 skipped (no-op), Commit 3 stripped unmapped changes and migrated mapped diff.

```
Assertion Results Summary:
---------------------------------------------------------------------------
  [PASS] 1. repo-1/a/file.a in hybrid received all mapped updates (Commit 1 & Commit 3)
         └─ Content:
file a
Commit 1: mapped file update
Commit 3: mapped file update
  [PASS] 2. Unmapped file c/other.txt did NOT leak into hybrid
         └─ Unmapped path exists: False
  [PASS] 3. Copybara filtered commits cleanly (Commit 1 migrated, Commit 2 skipped, Commit 3 stripped)
         └─ Hybrid Commit Log:
170a6d6 origin commit 3: modify both mapped a/file.a and unmapped c/other.txt
d553d5d origin commit 1: update mapped file a/file.a
ee2fe26 added a/file.a
147ad38 added b/file.b
d13598d added a/file.a
---------------------------------------------------------------------------
```

---
