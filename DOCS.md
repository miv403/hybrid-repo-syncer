# hybrid-syncer

`hybrid-syncer` is a lightweight Python CLI wrapper around [Copybara](https://github.com/google/copybara). It simplifies multi-repository code synchronization by reading a declarative YAML manifest (`sync-manifest.yaml`), automatically generating Copybara Starlark (`copy.bara.sky`) configuration files, executing `push`, `pull`, `sync`, `status`, and `doctor` operations.

---

## Features

- **YAML-driven Configuration**: Manage repository mapping targets in a clean `sync-manifest.yaml`.
- **Automatic Starlark Generation**: Dynamically renders `copy.bara.sky` files with `core.workflow()`, `core.move()` transformations, and path `glob()` matching.
- **Bi-Directional Synchronization**: Supports origin → hybrid (`push`), hybrid → origin (`pull`), and sequential bi-directional (`sync`).
- **Detailed Repository Status (`status`)**: Multi-column tabular status reporting commit ahead/behind counts, uncommitted local changes (`Dirty`), divergence warnings (`⚠️ DIVERGED`), and unmapped path analysis (`--check-unmapped`).
- **Manifest Doctor & Detector (`doctor` / `detector`)**: Manifest health detector scanning for exact target path clashes, nested prefix overlaps, and missing repository paths on disk.
- **Target Path Exclusion (`exclude`)**: Exclude specific file globs (e.g. `**/*.tmp`, `.github/**`) per origin, hybrid, or target mapping.
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
      exclude:
        - "**/*.tmp"
        - ".github/**"
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
  - `origin.exclude` *(list of strings, optional)*: Glob patterns to exclude from origin repository sync.
  - `hybrid.path` *(string, optional)*: Target directory in the hybrid repository.
  - `hybrid.url` *(string, optional)*: URL override for hybrid repository.
  - `hybrid.branch` *(string, optional)*: Branch override for hybrid.
  - `hybrid.exclude` *(list of strings, optional)*: Glob patterns to exclude from hybrid repository sync.
  - `exclude` *(list of strings, optional)*: Target-level glob patterns to exclude from both origin and hybrid sync.
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
./hybrid-syncer.py push [-t/--target NAME] [-n/--dry-run] [--init-history] [--skip-guards]
```
- `-t, --target NAME`: Run sync only for a specific target mapping.
- `-n, --dry-run`: Pass `--dry-run` to Copybara without modifying destination remotes.
- `--init-history`: Pass `--init-history` to Copybara (required during the first migration run for any workflow).
- `--skip-guards`: Skip pre-flight safety circuit breaker guard checks.

#### 4. `pull`
Executes hybrid → origin workflows (`<target>-pull`).

```bash
./hybrid-syncer.py pull [-t/--target NAME] [-n/--dry-run] [--init-history] [--skip-guards]
```
- `-t, --target NAME`: Run pull only for a specific target mapping.
- `-n, --dry-run`: Pass `--dry-run` to Copybara.
- `--init-history`: Pass `--init-history` to Copybara for first-time pull migration setups.
- `--skip-guards`: Skip pre-flight safety circuit breaker guard checks.

#### 5. `sync`
Performs sequential bi-directional sync (push and pull).

```bash
./hybrid-syncer.py sync [-t/--target NAME] [-n/--dry-run] [--init-history] [--strategy {push-first|pull-first}] [--skip-guards]
```
- `--strategy {push-first|pull-first}`: Execution order of sync operations (default: `push-first`).
- `--skip-guards`: Skip pre-flight safety circuit breaker guard checks.

#### 6. `status`
Displays synchronization status, commit ahead counts, local uncommitted workspace changes, divergence warnings, and unmapped path reports.

```bash
./hybrid-syncer.py status [-t/--target NAME] [--check-unmapped]
```
- `-t, --target NAME`: Filter status report to a specific target.
- `--check-unmapped`: Analyze origin repositories for tracked or uncommitted orphan files living outside defined target paths.

#### 7. `doctor` (or `detector`)
Runs a manifest health check to detect exact target path clashes, nested prefix path overlaps, and missing repository paths on disk.

```bash
./hybrid-syncer.py doctor
# or
./hybrid-syncer.py detector
```

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

### Test Case 5: Multi-Column Repository Status (`status`)
**Goal**: View comprehensive sync status, commit ahead counts, local changes, and unmapped path reports across targets.

```bash
# Display basic status table
./hybrid-syncer.py status

# Display status with unmapped path & orphan file analysis
./hybrid-syncer.py status --check-unmapped
```
**Expected Outcome**: Multi-column table output detailing `Target`, `Origin Path`, `Hybrid Path`, `Origin Status`, `Hybrid Status`, and `Sync Status`, along with orphan file listings.

---

### Test Case 6: Manifest Doctor Health Detector (`doctor` / `detector`)
**Goal**: Detect manifest configuration mistakes, path clashes, nested prefix overlaps, and missing repositories on disk.

```bash
./hybrid-syncer.py doctor
```
**Expected Outcome**: Manifest health check outputs `✔ All 3 manifest target(s) passed health checks cleanly` or lists detailed error/warning diagnostics.

---

### Test Case 7: Target Exclusion Sync (`exclude`)
**Goal**: Exclude specific files and directories (e.g. `**/*.tmp`, `.github/**`) from sync migrations.

```bash
./hybrid-syncer.py generate -t repo-1-a
```
**Expected Outcome**: Generated Starlark `origin_files` expression includes `glob(["a/**"], exclude = ["a/*.tmp", "a/**/*.tmp", "a/.github/**"])`.

---

## Troubleshooting & Tips

- **First-Run Requirement (`--init-history`)**: Copybara requires `--init-history` on the first migration run of any new workflow to create the baseline commit mapping (`GitOrigin-RevId`).
- **Pushing to Local Non-Bare Repositories**: When pushing to local working directories (e.g. `./sample-repos/hybrid`), Git requires `receive.denyCurrentBranch` to be set:
  ```bash
  git config receive.denyCurrentBranch updateInstead
  ```

