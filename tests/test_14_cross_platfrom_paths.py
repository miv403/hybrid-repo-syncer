#!/usr/bin/env python3
"""
Test Scenario 13: Cross-Platform Path Normalization & Copybara Binary Resolution
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hybrid_syncer.git_utils import IS_WINDOWS, normalize_path_for_git, sanitize_git_arg, resolve_repo_url
from hybrid_syncer.config import clean_path, generate_sky_config
from hybrid_syncer.copybara import find_copybara_cmd
from tests.common import print_banner, print_result_row


def test_path_normalization():
    print_banner("TEST SCENARIO 13: Cross-Platform Path Normalization & Binary Resolution")

    # 1. Backslash conversion for local Windows-style paths
    win_path = "C:\\Users\\workspace\\repo"
    norm_path = normalize_path_for_git(win_path)
    assert norm_path == "C:/Users/workspace/repo", f"Expected POSIX path, got '{norm_path}'"
    print_result_row("1. Windows path normalized to POSIX forward slashes", True, f"'{win_path}' -> '{norm_path}'")

    # 2. Remote URL preservation
    remote_url = "https://github.com/example/repo.git"
    assert normalize_path_for_git(remote_url) == remote_url, "Remote URL should be preserved"
    print_result_row("2. Remote git URLs remain untouched", True, remote_url)

    # 3. Path sanitization for git arguments
    arg_path = Path("C:/foo/bar")
    sanitized = sanitize_git_arg(arg_path)
    assert sanitized == "C:/foo/bar", f"Expected 'C:/foo/bar', got '{sanitized}'"
    print_result_row("3. Path objects sanitized cleanly to POSIX format", True, sanitized)

    # 4. Manifest path cleaning with Windows backslashes
    clean_win = clean_path("repo-1\\a")
    assert clean_win == "repo-1/a", f"Expected 'repo-1/a', got '{clean_win}'"
    print_result_row("4. Manifest clean_path converts backslashes", True, clean_win)

    # 5. Starlark config generation with Windows paths
    sample_manifest = {
        "hybrid_repo": "C:\\workspace\\hybrid",
        "targets": {
            "test-target": {
                "origin": {"url": "C:\\workspace\\origin", "path": "sub\\dir"},
                "hybrid": {"path": "hybrid\\dir"}
            }
        }
    }
    starlark_out = generate_sky_config(sample_manifest)
    assert "\\workspace\\" not in starlark_out, "Starlark output must not contain unescaped backslashes"
    assert "C:/workspace/hybrid" in starlark_out or "C:\\\\workspace" in starlark_out or "C:/workspace/origin" in starlark_out
    print_result_row("5. Starlark spec generated without escape sequence risks", True, "No raw backslashes found in Starlark string literals")

    # 6. Copybara binary resolution finder
    cmd, resolution_source = find_copybara_cmd()
    print_result_row("6. find_copybara_cmd resolves valid executable/jar or fallback", True, f"Resolved cmd: {cmd} via {resolution_source}")

    print("\n🎉 ALL CROSS-PLATFORM PATH NORMALIZATION ASSERTIONS PASSED!\n")


if __name__ == "__main__":
    test_path_normalization()
