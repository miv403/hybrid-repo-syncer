# hybrid-syncer

`hybrid-syncer` is a lightweight Python CLI wrapper around [Copybara](https://github.com/google/copybara). It simplifies multi-repository code synchronization by reading a declarative YAML manifest (`sync-manifest.yaml`), automatically generating Copybara Starlark (`copy.bara.sky`) configuration files, and executing `push`, `pull`, or `sync` operations.

---

## Features

- **YAML-driven Configuration**: Manage repository mapping targets in a clean `sync-manifest.yaml`.
- **Automatic Starlark Generation**: Dynamically renders `copy.bara.sky` files with `core.workflow()`, `core.move()` transformations, and path `glob()` matching.
- **Bi-Directional Synchronization**: Supports origin → hybrid (`push`), hybrid → origin (`pull`), and sequential bi-directional (`sync`).
- **Flexible Controls**: Target-specific filtering (`-t`), dry-run simulations (`-n`), initial history imports (`--init-history`), and custom working directory overrides (`-w`).

---

## Prerequisites & Installation

1. **Python 3.8+** with `PyYAML`:
   ```bash
   pip install pyyaml
   ```
2. **Copybara**: Ensure the `copybara` executable is in your system `PATH` (e.g. at `~/.local/bin/copybara` or `/usr/local/bin/copybara`).
3. **Git**: Installed and available in PATH.

Make `hybrid-syncer.py` executable:
```bash
chmod +x hybrid-syncer.py
```

---

## Configuration Manifest (`sync-manifest.yaml`)

`hybrid-syncer` uses `sync-manifest.yaml` to define how folders in origin repositories map to target directories in a central hybrid repository.

### Example Manifest

```yaml
# Top-level defaults
hybrid_repo: "./sample-repos/hybrid"
default_branch: "master"

authoring:
  default_email: "syncer@example.com"
  default_name: "Hybrid Syncer"

# Target mappings
targets:
  repo-1-a:
    origin:
      url: "./sample-repos/repo-1.git"
      path: "a"
    hybrid:
      path: "repo-1/a"

  repo-1-b:
    origin:
      url: "./sample-repos/repo-1.git"
      path: "b"
    hybrid:
      path: "repo-1/b"

  repo-2-a:
    origin:
      url: "./sample-repos/repo-2.git"
      path: "a"
    hybrid:
      path: "repo-2/a"
```

### Schema Description

- `hybrid_repo` *(string)*: Default URL or local path to the hybrid repository.
- `default_branch` *(string)*: Default Git ref for origin and hybrid repos (e.g., `main` or `master`).
- `authoring` *(object)*: Default Git commit author details (`default_email`, `default_name`).
- `targets` *(map)*: Named target mapping blocks.
  - `origin.url` *(string, required)*: Remote URL or path to the origin repository.
  - `origin.path` *(string, optional)*: Subdirectory in origin repository (defaults to root if empty).
  - `origin.branch` *(string, optional)*: Branch override for origin.
  - `hybrid.path` *(string, optional)*: Target directory in the hybrid repository.
  - `hybrid.url` *(string, optional)*: URL override for hybrid repository.
  - `hybrid.branch` *(string, optional)*: Branch override for hybrid.
  - `mode` *(string, optional)*: Copybara workflow mode (`ITERATIVE`, `SQUASH`, default: `ITERATIVE`).

---

## CLI Command Reference

### Global Options

```bash
hybrid-syncer [GLOBAL_OPTIONS] <COMMAND> [COMMAND_OPTIONS]
```

- `-c, --config PATH`: Path to sync manifest file (default: `./sync-manifest.yaml`).
- `-v, --verbose`: Enable detailed logging and stream Copybara stdout/stderr output.
- `-w, --workdir PATH`: Custom directory for storing temporary `copy.bara.sky` files.

---

### Subcommands

#### 1. `init`
Creates a starter `sync-manifest.yaml` configuration file.

```bash
./hybrid-syncer.py init [-f/--force]
```
- `-f, --force`: Overwrite existing `sync-manifest.yaml` if it already exists.

#### 2. `generate`
Generates and prints or exports the Copybara Starlark (`copy.bara.sky`) configuration file without executing migrations.

```bash
./hybrid-syncer.py generate [-o/--output PATH] [-t/--target NAME]
```
- `-o, --output PATH`: Write Starlark output to a specified file path instead of stdout.
- `-t, --target NAME`: Generate configuration only for a specific target mapping name.

#### 3. `push`
Executes origin → hybrid workflows (`<target>-push`).

```bash
./hybrid-syncer.py push [-t/--target NAME] [-n/--dry-run] [--init-history]
```
- `-t, --target NAME`: Run sync only for a specific target mapping.
- `-n, --dry-run`: Pass `--dry-run` to Copybara without modifying destination remotes.
- `--init-history`: Pass `--init-history` to Copybara (required during the first migration run for any workflow).

#### 4. `pull`
Executes hybrid → origin workflows (`<target>-pull`).

```bash
./hybrid-syncer.py pull [-t/--target NAME] [-n/--dry-run] [--init-history]
```
- `-t, --target NAME`: Run pull only for a specific target mapping.
- `-n, --dry-run`: Pass `--dry-run` to Copybara.
- `--init-history`: Pass `--init-history` to Copybara for first-time pull migration setups.

#### 5. `sync`
Performs sequential bi-directional sync (push and pull).

```bash
./hybrid-syncer.py sync [-t/--target NAME] [-n/--dry-run] [--init-history] [--strategy {push-first|pull-first}]
```
- `--strategy {push-first|pull-first}`: Execution order of sync operations (default: `push-first`).

---

## Test Cases & Verification Scenarios

### Test Case 1: Environment Setup and Starter Manifest Creation
**Goal**: Initialize a new project manifest and initialize sample test repositories.

```bash
# 1. Initialize sample git repositories
./sample-repos/init-repo.sh 1
./sample-repos/init-repo.sh 2
./sample-repos/init-hybrid.sh 1

# 2. Create starter manifest (force overwrite if existing)
./hybrid-syncer.py init -f
```
**Expected Outcome**: `sync-manifest.yaml` is created with standard target mappings for `repo-1-a`, `repo-1-b`, and `repo-2-a`.

---

### Test Case 2: Starlark Configuration Generation & Filtering
**Goal**: Verify generated Copybara Starlark syntax and target filtering options.

```bash
# Preview full Starlark config output
./hybrid-syncer.py generate

# Preview Starlark config for target 'repo-1-a' only
./hybrid-syncer.py generate -t repo-1-a

# Export generated config to a file
./hybrid-syncer.py generate -o /tmp/copy.bara.sky
```
**Expected Outcome**: Valid Starlark `core.workflow()` blocks with matching `origin_files`, `destination_files`, and `core.move()` transformations are displayed or written to file.

---

### Test Case 3: Dry-Run Push Simulation
**Goal**: Validate workflow execution without modifying git remotes.

```bash
./hybrid-syncer.py -v push -n --init-history
```
**Expected Outcome**: Copybara runs all push workflows in dry-run mode, executing transformations locally without pushing commits to the hybrid remote.

---

### Test Case 4: Initial Origin → Hybrid Migration (`push`)
**Goal**: Sync directory contents from origin repositories into the hybrid repository.

```bash
./hybrid-syncer.py -v push --init-history
```
**Expected Outcome**: Files from `sample-repos/repo-1` (folders `a` and `b`) and `sample-repos/repo-2` (folder `a`) are synced into `sample-repos/hybrid/repo-1/` and `sample-repos/hybrid/repo-2/`.

---

### Test Case 5: Target-Filtered Synchronization
**Goal**: Synchronize a single targeted mapping instead of all targets.

```bash
./hybrid-syncer.py -v push -t repo-1-a
```
**Expected Outcome**: Only the `repo-1-a-push` workflow executes.

---

### Test Case 6: Pulling Changes (Hybrid → Origin)
**Goal**: Propagate updates made in the hybrid repository back to the origin repository.

```bash
# 1. Make a change in the hybrid repository
echo "hybrid feature addition" >> sample-repos/hybrid/repo-1/a/file.a
git -C sample-repos/hybrid add .
git -C sample-repos/hybrid commit -m "feat: updated file.a in hybrid"

# 2. Pull changes back to origin repo-1-a
./hybrid-syncer.py -v pull -t repo-1-a --init-history

# 3. Verify changes in origin clone
git -C sample-repos/repo-1 pull origin master
cat sample-repos/repo-1/a/file.a
```
**Expected Outcome**: The content `"hybrid feature addition"` appears in `sample-repos/repo-1/a/file.a`.

---

### Test Case 7: Bi-Directional Synchronization with Custom Strategy
**Goal**: Run push followed by pull (or pull followed by push) in a single command.

```bash
# Push-first strategy (default)
./hybrid-syncer.py -v sync --strategy push-first -t repo-1-a

# Pull-first strategy
./hybrid-syncer.py -v sync --strategy pull-first -t repo-1-a
```
**Expected Outcome**: Workflows execute in the exact specified order (`push` then `pull`, or `pull` then `push`).

---

### Test Case 8: Custom Working Directory Execution
**Goal**: Specify a custom directory for temporary `copy.bara.sky` files.

```bash
./hybrid-syncer.py -w ./custom_workdir -v push -n
ls -la ./custom_workdir/copy.bara.sky
```
**Expected Outcome**: The generated `copy.bara.sky` file is saved and preserved in `./custom_workdir/`.

---

## Troubleshooting & Tips

- **First-Run Requirement (`--init-history`)**: Copybara requires `--init-history` on the first migration run of any new workflow to create the baseline commit mapping (`GitOrigin-RevId`).
- **Pushing to Local Non-Bare Repositories**: When pushing to local working directories (e.g. `./sample-repos/hybrid`), Git requires `receive.denyCurrentBranch` to be set:
  ```bash
  git config receive.denyCurrentBranch updateInstead
  ```
