"""
Manifest loading, validation, and Copybara Starlark sky generation.
"""

import sys
from pathlib import Path
import yaml

from hybrid_syncer.errors import ManifestError
from hybrid_syncer.git_utils import check_repo_exists, resolve_repo_url

STARTER_MANIFEST = """# hybrid-syncer configuration manifest
default_branch: "master"

# Optional custom Copybara binary, .jar, .bat, or .ps1 executable path
# copybara_path: "./bin/copybara_deploy.jar"

authoring:
  default_email: "syncer@example.com"
  default_name: "Hybrid Syncer"

# Top-level repository alias registry
repositories:
  repo1: "./sample-repos/repo-1.git"
  repo2: "./sample-repos/repo-2.git"
  hybrid: "./sample-repos/hybrid"

targets:
  repo-1-a:
    origin:
      repo: repo1
      path: "a"
    destinations:
      - name: main
        repo: hybrid
        path: "repo-1/a"

  repo-1-b:
    origin:
      repo: repo1
      path: "b"
    destinations:
      - name: main
        repo: hybrid
        path: "repo-1/b"

  repo-2-a:
    origin:
      repo: repo2
      path: "a"
    destinations:
      - name: main
        repo: hybrid
        path: "repo-2/a"
"""


def clean_path(p) -> str:
    if not p or p == ".":
        return ""
    return str(p).replace("\\", "/").strip("/")


def normalize_manifest(data: dict, base_dir: Path = Path(".")) -> dict:
    normalized = {
        "default_branch": data.get("default_branch", "main"),
        "authoring": data.get("authoring", {}),
        "repositories": {},
        "targets": {}
    }

    if "copybara_path" in data:
        normalized["copybara_path"] = str(data["copybara_path"])
    elif "copybara" in data and isinstance(data["copybara"], str):
        normalized["copybara_path"] = str(data["copybara"])

    # 1. Register top-level repository aliases
    raw_repos = data.get("repositories", {})
    if isinstance(raw_repos, dict):
        for alias, url in raw_repos.items():
            normalized["repositories"][str(alias)] = str(url)

    # Legacy hybrid_repo fallback
    if "hybrid_repo" in data:
        h_url = str(data["hybrid_repo"])
        if "hybrid_repo" not in normalized["repositories"]:
            normalized["repositories"]["hybrid_repo"] = h_url
        if "hybrid" not in normalized["repositories"]:
            normalized["repositories"]["hybrid"] = h_url

    # 2. Normalize targets
    raw_targets = data.get("targets", {})
    if not isinstance(raw_targets, dict):
        return normalized

    for t_name, t_cfg in raw_targets.items():
        if not isinstance(t_cfg, dict):
            continue

        norm_t = {
            "mode": t_cfg.get("mode", "ITERATIVE"),
            "exclude": t_cfg.get("exclude", []),
            "origin": {},
            "destinations": []
        }

        # Normalize origin
        origin_cfg = t_cfg.get("origin", {})
        o_repo_key = origin_cfg.get("repo") or origin_cfg.get("url")
        o_url = ""
        if o_repo_key and str(o_repo_key) in normalized["repositories"]:
            o_url = normalized["repositories"][str(o_repo_key)]
            o_repo_alias = str(o_repo_key)
        elif origin_cfg.get("url"):
            o_url = str(origin_cfg["url"])
            o_repo_alias = "origin"
            if "origin" not in normalized["repositories"]:
                normalized["repositories"]["origin"] = o_url
        else:
            o_repo_alias = str(o_repo_key or "origin")
            o_url = str(o_repo_key or "")

        norm_t["origin"] = {
            "repo": o_repo_alias,
            "url": o_url,
            "path": clean_path(origin_cfg.get("path", "")),
            "branch": origin_cfg.get("branch", normalized["default_branch"]),
            "exclude": origin_cfg.get("exclude", [])
        }

        # Normalize destinations
        if "destinations" in t_cfg and isinstance(t_cfg["destinations"], list):
            for idx, d_item in enumerate(t_cfg["destinations"]):
                if not isinstance(d_item, dict):
                    continue
                d_repo_alias = d_item.get("repo") or "hybrid"
                d_url = d_item.get("url") or normalized["repositories"].get(str(d_repo_alias)) or ""
                d_name = d_item.get("name") or (str(d_repo_alias) if str(d_repo_alias) != "hybrid" else f"dest-{idx}")

                norm_t["destinations"].append({
                    "name": str(d_name),
                    "repo": str(d_repo_alias),
                    "url": str(d_url),
                    "path": clean_path(d_item.get("path", "")),
                    "branch": d_item.get("branch", normalized["default_branch"]),
                    "exclude": d_item.get("exclude", [])
                })
        else:
            # Legacy hybrid fallback
            hybrid_cfg = t_cfg.get("hybrid", {})
            h_repo_alias = hybrid_cfg.get("repo") or ("hybrid_repo" if "hybrid_repo" in normalized["repositories"] else "hybrid")
            h_url = hybrid_cfg.get("url") or normalized["repositories"].get(str(h_repo_alias)) or data.get("hybrid_repo", "./hybrid")

            norm_t["destinations"].append({
                "name": "main",
                "repo": str(h_repo_alias),
                "url": str(h_url),
                "path": clean_path(hybrid_cfg.get("path", "")),
                "branch": hybrid_cfg.get("branch", normalized["default_branch"]),
                "exclude": hybrid_cfg.get("exclude", [])
            })

        normalized["targets"][t_name] = norm_t

    return normalized


def load_manifest(config_path: Path) -> dict:
    if not config_path.exists():
        raise ManifestError(f"Configuration file '{config_path}' not found.\nRun 'hybrid-syncer init' to create a starter sync-manifest.yaml.")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as e:
        raise ManifestError(f"Error reading configuration file '{config_path}': {e}")

    if "targets" not in data or not isinstance(data.get("targets"), dict):
        raise ManifestError(f"Invalid manifest format in '{config_path}'. 'targets' section missing or invalid.")

    base_dir = config_path.parent.resolve()
    return normalize_manifest(data, base_dir=base_dir)


def format_exclude_pattern(pattern: str, base_path: str) -> list[str]:
    pattern = pattern.strip()
    if not base_path:
        return [pattern]
    if pattern.startswith(base_path + "/"):
        return [pattern]
    if pattern.startswith("**/"):
        suffix = pattern[3:]
        return [f"{base_path}/{suffix}", f"{base_path}/**/{suffix}"]
    return [f"{base_path}/{pattern}"]


def build_glob_expr(base_path: str, exclude_patterns: list[str] | None = None) -> str:
    include_pattern = f"{base_path}/**" if base_path else "**"

    if not exclude_patterns:
        return f'glob(["{include_pattern}"])'

    formatted_excludes = []
    for p in exclude_patterns:
        if isinstance(p, str) and p.strip():
            formatted_excludes.extend(format_exclude_pattern(p, base_path))

    if not formatted_excludes:
        return f'glob(["{include_pattern}"])'

    excludes_str = ", ".join(f'"{p}"' for p in formatted_excludes)
    return f'glob(["{include_pattern}"], exclude = [{excludes_str}])'


def generate_sky_config(manifest: dict, target_filter: str = "", dest_filter: str = "", config_path: str = "sync-manifest.yaml") -> str:
    manifest = normalize_manifest(manifest, Path(config_path).parent.resolve())
    targets = manifest.get("targets", {})
    base_dir = Path(config_path).parent.resolve()

    if target_filter:
        if target_filter not in targets:
            available = ", ".join(targets.keys()) or "none"
            raise ManifestError(f"Target '{target_filter}' not found in manifest. Available targets: {available}")
        targets_to_gen = {target_filter: targets[target_filter]}
    else:
        targets_to_gen = targets

    default_branch = manifest.get("default_branch", "main")
    authoring_cfg = manifest.get("authoring", {})
    author_email = authoring_cfg.get("default_email", "syncer@example.com")
    author_name = authoring_cfg.get("default_name", "Hybrid Syncer")
    author_str = f"{author_name} <{author_email}>"

    lines = [
        f"# Generated by hybrid-syncer from {config_path}",
        "# Do not edit manually.",
        ""
    ]

    for t_name, t_cfg in targets_to_gen.items():
        origin_cfg = t_cfg.get("origin", {})
        raw_origin_url = origin_cfg.get("url")
        if not raw_origin_url:
            raise ManifestError(f"Target '{t_name}' origin repository URL is empty or unresolved")

        origin_url = resolve_repo_url(raw_origin_url, base_dir)
        origin_branch = origin_cfg.get("branch", default_branch)
        origin_path = clean_path(origin_cfg.get("path", ""))

        destinations = t_cfg.get("destinations", [])
        if dest_filter:
            matching_dests = [d for d in destinations if d["name"] == dest_filter]
            if not matching_dests:
                available_d = ", ".join(d["name"] for d in destinations) or "none"
                raise ManifestError(f"Destination '{dest_filter}' not found for target '{t_name}'. Available destinations: {available_d}")
            dests_to_gen = matching_dests
        else:
            dests_to_gen = destinations

        for d in dests_to_gen:
            d_name = d["name"]
            raw_dest_url = d.get("url")
            if not raw_dest_url:
                raise ManifestError(f"Target '{t_name}' destination '{d_name}' repository URL is empty or unresolved")

            dest_url = resolve_repo_url(raw_dest_url, base_dir)
            dest_branch = d.get("branch", default_branch)
            dest_path = clean_path(d.get("path", ""))

            mode = t_cfg.get("mode", "ITERATIVE")

            # Exclude patterns
            target_exclude = t_cfg.get("exclude", [])
            if isinstance(target_exclude, str):
                target_exclude = [target_exclude]
            elif not isinstance(target_exclude, list):
                target_exclude = []

            origin_exclude_raw = origin_cfg.get("exclude", [])
            if isinstance(origin_exclude_raw, str):
                origin_exclude_raw = [origin_exclude_raw]
            elif not isinstance(origin_exclude_raw, list):
                origin_exclude_raw = []

            dest_exclude_raw = d.get("exclude", [])
            if isinstance(dest_exclude_raw, str):
                dest_exclude_raw = [dest_exclude_raw]
            elif not isinstance(dest_exclude_raw, list):
                dest_exclude_raw = []

            origin_exclude = origin_exclude_raw + target_exclude
            dest_exclude = dest_exclude_raw + target_exclude

            origin_files_push = build_glob_expr(origin_path, origin_exclude)
            dest_files_push = build_glob_expr(dest_path, dest_exclude)

            wf_push_suffix = "push" if (len(destinations) == 1 and d_name == "main") else f"{d_name}-push"
            wf_pull_suffix = "pull" if (len(destinations) == 1 and d_name == "main") else f"{d_name}-pull"

            # Transformations for push
            push_trans = ""
            if origin_path != dest_path:
                push_trans = f'\n    transformations = [\n        core.move("{origin_path}", "{dest_path}"),\n    ],'

            # Workflow: push
            lines.append(f"# Target: {t_name} [{d_name}] (push)")
            lines.append("core.workflow(")
            lines.append(f'    name = "{t_name}-{wf_push_suffix}",')
            lines.append("    origin = git.origin(")
            lines.append(f'        url = "{origin_url}",')
            lines.append(f'        ref = "{origin_branch}",')
            lines.append("    ),")
            lines.append("    destination = git.destination(")
            lines.append(f'        url = "{dest_url}",')
            lines.append(f'        fetch = "{dest_branch}",')
            lines.append(f'        push = "{dest_branch}",')
            lines.append("    ),")
            lines.append(f"    origin_files = {origin_files_push},")
            lines.append(f"    destination_files = {dest_files_push},")
            lines.append(f'    authoring = authoring.pass_thru(default = "{author_str}"),')
            lines.append(f'    mode = "{mode}",{push_trans}')
            lines.append(")")
            lines.append("")

            # Transformations for pull
            pull_trans = ""
            if dest_path != origin_path:
                pull_trans = f'\n    transformations = [\n        core.move("{dest_path}", "{origin_path}"),\n    ],'

            # Workflow: pull
            lines.append(f"# Target: {t_name} [{d_name}] (pull)")
            lines.append("core.workflow(")
            lines.append(f'    name = "{t_name}-{wf_pull_suffix}",')
            lines.append("    origin = git.origin(")
            lines.append(f'        url = "{dest_url}",')
            lines.append(f'        ref = "{dest_branch}",')
            lines.append("    ),")
            lines.append("    destination = git.destination(")
            lines.append(f'        url = "{origin_url}",')
            lines.append(f'        fetch = "{origin_branch}",')
            lines.append(f'        push = "{origin_branch}",')
            lines.append("    ),")
            lines.append(f"    origin_files = {dest_files_push},")
            lines.append(f"    destination_files = {origin_files_push},")
            lines.append(f'    authoring = authoring.pass_thru(default = "{author_str}"),')
            lines.append(f'    mode = "{mode}",{pull_trans}')
            lines.append(")")
            lines.append("")

    return "\n".join(lines)


def check_manifest_health(manifest: dict, config_path: Path = Path("sync-manifest.yaml")) -> tuple[int, int]:
    targets = manifest.get("targets", {})
    repositories = manifest.get("repositories", {})
    base_dir = config_path.parent.resolve()

    errors = []
    warnings = []

    print(f"\n🩺 Running Hybrid Syncer Health Check on '{config_path}'...\n", file=sys.stderr)

    # 1. Repository Accessibility Checks
    checked_repos = set()
    for alias, repo_url_raw in repositories.items():
        repo_url = resolve_repo_url(repo_url_raw, base_dir)
        if repo_url and repo_url not in checked_repos:
            checked_repos.add(repo_url)
            exists, err_msg = check_repo_exists(repo_url)
            if not exists:
                errors.append(f"Repository Alias '{alias}' ('{repo_url}'): {err_msg}")

    for t_name, t_cfg in targets.items():
        origin_url = resolve_repo_url(t_cfg.get("origin", {}).get("url", ""), base_dir)
        if origin_url and origin_url not in checked_repos:
            checked_repos.add(origin_url)
            exists, err_msg = check_repo_exists(origin_url)
            if not exists:
                errors.append(f"Target '{t_name}': Origin repository URL '{origin_url}' {err_msg}")

        for d in t_cfg.get("destinations", []):
            dest_url = resolve_repo_url(d.get("url", ""), base_dir)
            if dest_url and dest_url not in checked_repos:
                checked_repos.add(dest_url)
                exists, err_msg = check_repo_exists(dest_url)
                if not exists:
                    errors.append(f"Target '{t_name}' [{d.get('name')}]: Destination repository URL '{dest_url}' {err_msg}")

    # 2. Destination Path Clashes & Prefix Overlaps (Within the Same Destination Repo)
    dest_paths = {}  # dest_url -> dict((target_name, dest_name) -> path)
    for t_name, t_cfg in targets.items():
        for d in t_cfg.get("destinations", []):
            d_name = d.get("name", "main")
            d_url = resolve_repo_url(d.get("url", ""), base_dir)
            d_path = clean_path(d.get("path", ""))

            if not d_url:
                continue

            if d_url not in dest_paths:
                dest_paths[d_url] = {}

            for (existing_target, existing_d_name), existing_path in dest_paths[d_url].items():
                label = f"Target '{t_name}' [{d_name}]"
                existing_label = f"'{existing_target}' [{existing_d_name}]"

                if d_path == existing_path:
                    errors.append(f"{label} clashes with {existing_label} at path '{d_path or '.'}' in repo '{d_url}'")
                elif d_path and existing_path:
                    if d_path.startswith(existing_path + "/") or existing_path.startswith(d_path + "/"):
                        warnings.append(f"{label} path ({d_path}) overlaps with {existing_label} ({existing_path}) in repo '{d_url}'")
                elif not d_path or not existing_path:
                    warnings.append(f"{label} ({d_path or '.'}) overlaps with root path of {existing_label} ({existing_path or '.'}) in repo '{d_url}'")

            dest_paths[d_url][(t_name, d_name)] = d_path

    # 3. Origin Path Clashes & Prefix Overlaps (Within the Same Origin Repo)
    origin_paths = {}  # repo_url -> dict(target_name -> o_path)
    for t_name, t_cfg in targets.items():
        o_url = resolve_repo_url(t_cfg.get("origin", {}).get("url", ""), base_dir)
        o_path = clean_path(t_cfg.get("origin", {}).get("path", ""))
        if not o_url:
            continue
        if o_url not in origin_paths:
            origin_paths[o_url] = {}
        for existing_target, existing_path in origin_paths[o_url].items():
            if o_path == existing_path:
                errors.append(f"Target '{t_name}' clashes with '{existing_target}' at origin path '{o_path or '.'}' in '{o_url}'")
            elif o_path and existing_path:
                if o_path.startswith(existing_path + "/") or existing_path.startswith(o_path + "/"):
                    warnings.append(f"Target '{t_name}' origin path ({o_path}) overlaps with '{existing_target}' ({existing_path}) in '{o_url}'")
        origin_paths[o_url][t_name] = o_path

    # Output findings to stderr
    if errors:
        for err in errors:
            print(f"❌ Error: {err}", file=sys.stderr)
    if warnings:
        for warn in warnings:
            print(f"⚠️ Warning: {warn}", file=sys.stderr)

    if not errors and not warnings:
        print(f"✔ All {len(targets)} manifest target(s) passed health checks cleanly with 0 errors and 0 warnings.", file=sys.stderr)
    else:
        print(f"\nManifest Health Summary: {len(errors)} error(s), {len(warnings)} warning(s) detected across {len(targets)} target(s).", file=sys.stderr)

    return len(errors), len(warnings)
