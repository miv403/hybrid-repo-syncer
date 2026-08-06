"""
Test Scenario 16: Copybara Exit Codes Mapping & Actionable Command Suggestions
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hybrid_syncer.errors import COPYBARA_EXIT_CODES, CopybaraExecutionError


def test_copybara_exit_codes_mapping():
    print("===========================================================================")
    print("      TEST SCENARIO 16: Copybara Exit Codes & Command Suggestions")
    print("===========================================================================")

    expected_codes = {
        1: "COMMAND_LINE_ERROR",
        2: "CONFIGURATION_ERROR",
        3: "REPOSITORY_ERROR",
        4: "NO_OP",
        8: "INTERRUPTED",
        30: "ENVIRONMENT_ERROR",
        31: "INTERNAL_ERROR",
    }

    for code, expected_name in expected_codes.items():
        assert code in COPYBARA_EXIT_CODES, f"Code {code} missing from COPYBARA_EXIT_CODES"
        name, desc = COPYBARA_EXIT_CODES[code]
        assert name == expected_name, f"Expected name {expected_name}, got {name}"

        err = CopybaraExecutionError("test-workflow", code, stdout="", stderr="Some error")
        assert f"Copybara Exit Code: {code} ({expected_name})" in str(err)
        assert err.copybara_exit_code_name == expected_name

    print("  [PASS] 1. All Copybara exit codes (1, 2, 3, 4, 8, 30, 31) mapped correctly.")


def test_init_history_command_suggestion():
    copybara_stderr = (
        "Task: Git Destination: Fetching: http://admin:6161@localhost:3001/admin/hybrid.git refs/heads/main\n"
        "ERROR: Previous revision label GitOrigin-RevId could not be found in GitDestination{repoUrl=...} and --last-rev or --init-history flags were not passed"
    )

    err = CopybaraExecutionError("config-3-repo-1-gitea-pull", 2, stdout="", stderr=copybara_stderr)

    err_msg = str(err)
    assert "Copybara Exit Code: 2 (CONFIGURATION_ERROR)" in err_msg
    assert "💡 Suggested command:" in err_msg
    assert "--init-history" in err_msg
    assert err.suggested_command is not None

    print("  [PASS] 2. Missing revision label automatically generates --init-history command suggestion.")


def test_explicit_suggested_command():
    custom_cmd = "./hybrid-syncer.py pull -t target1 -d dest1 --init-history"
    err = CopybaraExecutionError("workflow-a", 2, stdout="", stderr="Error", suggested_command=custom_cmd)

    assert custom_cmd in str(err)
    assert err.suggested_command == custom_cmd
    print("  [PASS] 3. Explicitly provided suggested_command rendered in exception output.")


if __name__ == "__main__":
    try:
        test_copybara_exit_codes_mapping()
        test_init_history_command_suggestion()
        test_explicit_suggested_command()
        print("\n🎉 TEST SCENARIO 16 COMPLETED SUCCESSFULLY!\n")
    except AssertionError as e:
        print(f"\n❌ TEST SCENARIO 16 FAILED: {e}\n")
        sys.exit(1)
