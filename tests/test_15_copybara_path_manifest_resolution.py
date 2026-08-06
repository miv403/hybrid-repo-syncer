#!/usr/bin/env python3
"""
Test Scenario 15: Manifest copybara_path resolution & fallback handling.
Validates that:
1. `copybara_path` defined in manifest YAML is parsed correctly.
2. Valid `.jar`, `.ps1`, `.bat`, and binary paths are formatted correctly for execution.
3. Relative `copybara_path` resolves relative to the manifest directory.
4. Non-existent `copybara_path` falls back gracefully to default resolution.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hybrid_syncer.config import normalize_manifest
from hybrid_syncer.copybara import find_copybara_cmd
from tests.common import print_banner, print_result_row


def main():
    print_banner("TEST SCENARIO 15: Manifest Copybara Path Resolution & Fallbacks")

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. Manifest normalization with copybara_path
        manifest_data = {
            "copybara_path": "./custom_tools/copybara_deploy.jar",
            "targets": {}
        }
        norm = normalize_manifest(manifest_data, base_dir=tmp_dir)
        assert norm.get("copybara_path") == "./custom_tools/copybara_deploy.jar"
        print_result_row("1. copybara_path extracted during manifest normalization", True, norm.get("copybara_path"))

        # 2. Valid Jar file resolution
        custom_jar = tmp_dir / "my_copybara.jar"
        custom_jar.write_text("dummy jar content")
        cmd_jar, res_jar = find_copybara_cmd(config_copybara_path="my_copybara.jar", base_dir=tmp_dir)
        assert cmd_jar == ["java", "-jar", str(custom_jar.resolve())]
        assert "Manifest Configuration" in res_jar
        print_result_row("2. Configured .jar file resolves to java -jar command", True, f"{cmd_jar} via {res_jar}")

        # 3. Valid PS1 script resolution
        custom_ps1 = tmp_dir / "run_copybara.ps1"
        custom_ps1.write_text("Write-Host 'test'")
        cmd_ps1, res_ps1 = find_copybara_cmd(config_copybara_path="run_copybara.ps1", base_dir=tmp_dir)
        assert "Manifest Configuration" in res_ps1
        assert str(custom_ps1.resolve()) in cmd_ps1[-1]
        print_result_row("3. Configured .ps1 script resolves cleanly", True, f"{cmd_ps1} via {res_ps1}")

        # 4. Valid executable binary resolution
        custom_bin = tmp_dir / "copybara_bin"
        custom_bin.write_text("#!/bin/sh\necho test")
        cmd_bin, res_bin = find_copybara_cmd(config_copybara_path="copybara_bin", base_dir=tmp_dir)
        assert cmd_bin == [str(custom_bin.resolve())]
        assert "Manifest Configuration" in res_bin
        print_result_row("4. Configured custom binary resolves cleanly", True, f"{cmd_bin} via {res_bin}")

        # 5. Non-existent path fallback behavior
        cmd_fb, res_fb = find_copybara_cmd(config_copybara_path="non_existent_copybara.jar", base_dir=tmp_dir)
        assert "Manifest Configuration" not in res_fb
        print_result_row("5. Non-existent copybara_path falls back to standard resolution", True, f"Fallback mode: {res_fb}")

    print("\n🎉 TEST SCENARIO 15 COMPLETED SUCCESSFULLY!\n")


if __name__ == "__main__":
    main()
