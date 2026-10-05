"""Unit tests for the Copilot preToolUse guard (scripts/hooks/guard_pretooluse.py).

Exercises the persona invariant directly: the agent never edits
candidate-owned files under .challenges/, never directly accesses them through
a shell tool, and never runs an unbounded rm -rf or a forced git push.
Maintenance edits to src/ and tests/ must receive neutral continuation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_HOOKS_SCRIPTS = ROOT / "scripts" / "hooks"
sys.path.insert(0, str(_HOOKS_SCRIPTS))

from guard_pretooluse import decide  # type: ignore[import-not-found]  # noqa: E402

GUARD_SCRIPT = _HOOKS_SCRIPTS / "guard_pretooluse.py"


def test_denies_edit_targeting_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "Edit",
            "toolArgs": {"file_path": ".challenges/workspace/two_sum.py"},
        }
    )
    assert decision["permissionDecision"] == "deny"
    assert "candidate" in decision["permissionDecisionReason"]
    assert "themselves" in decision["permissionDecisionReason"]


def test_denies_write_targeting_candidate_workspace_via_nested_args() -> None:
    decision = decide(
        {
            "toolName": "create_file",
            "toolArgs": {"params": {"path": "./.challenges/workspace/notes.md"}},
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_copilot_create_targeting_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "create",
            "toolArgs": json.dumps(
                {"path": ".challenges/workspace/test_two_sum_candidate.py"}
            ),
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_edit_targeting_candidate_workspace_with_backslashes() -> None:
    decision = decide(
        {
            "toolName": "create_file",
            "toolArgs": {"path": r".challenges\workspace\notes.md"},
        }
    )
    assert decision["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    "tool_name",
    [
        "deleteFile",
        "remove_file",
        "moveFile",
        "rename_path",
        "unlink",
    ],
)
def test_denies_other_mutation_tools_targeting_candidate_workspace(
    tool_name: str,
) -> None:
    decision = decide(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {
                "path": ".challenges/workspace/two_sum.py",
                "targetPath": ".challenges/history/two_sum.py",
            },
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_continues_edit_targeting_maintained_source() -> None:
    decision = decide(
        {
            "toolName": "Edit",
            "toolArgs": {"file_path": "src/algo/arrays/two_sum.py"},
        }
    )
    assert decision == {"continue": True}


def test_continues_edit_targeting_tests_tree() -> None:
    decision = decide(
        {
            "toolName": "str_replace_editor",
            "toolArgs": {"path": "tests/test_hooks_guard.py"},
        }
    )
    assert decision == {"continue": True}


def test_continues_maintenance_edit_whose_content_mentions_workspace() -> None:
    decision = decide(
        {
            "toolName": "Edit",
            "toolArgs": {
                "file_path": "docs/guide/local-practice.md",
                "new_string": "Personal state belongs under .challenges/ only.",
            },
        }
    )
    assert decision == {"continue": True}


def test_read_only_tool_never_denies_even_over_candidate_path() -> None:
    decision = decide(
        {
            "toolName": "readFile",
            "toolArgs": {"file_path": ".challenges/workspace/two_sum.py"},
        }
    )
    assert decision == {"continue": True}


def test_toolargs_as_json_encoded_string_is_parsed() -> None:
    decision = decide(
        {
            "toolName": "Write",
            "toolArgs": json.dumps({"file_path": ".challenges/workspace/x.py"}),
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_vscode_snake_case_edit_payload_is_denied() -> None:
    decision = decide(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": ".challenges/workspace/x.py"},
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_vscode_snake_case_shell_payload_is_denied() -> None:
    decision = decide(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git push --force origin main"},
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_shell_redirection_into_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "execute",
            "toolArgs": {
                "command": "printf '%s\\n' answer > .challenges/arrays/two_sum.py"
            },
        }
    )
    assert decision["permissionDecision"] == "deny"
    assert ".challenges/" in decision["permissionDecisionReason"]


def test_denies_shell_read_from_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "terminal",
            "toolArgs": {"command": r"type .challenges\arrays\two_sum.py"},
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_python_shell_write_to_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "run_command",
            "toolArgs": {
                "command": (
                    'python -c "from pathlib import Path; '
                    "Path('.challenges/x.py').write_text('answer')\""
                )
            },
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_shell_variable_assigned_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "bash",
            "toolArgs": {
                "command": 'target=.challenges/x.py; printf answer > "$target"'
            },
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_continues_repo_practice_front_door_without_private_path() -> None:
    decision = decide(
        {
            "toolName": "execute",
            "toolArgs": {"command": "just practice-test"},
        }
    )
    assert decision == {"continue": True}


def test_continues_study_front_door_without_private_path() -> None:
    decision = decide(
        {
            "toolName": "execute",
            "toolArgs": {"command": "just practice-study linked_lists lru_cache"},
        }
    )
    assert decision == {"continue": True}


def test_denies_edit_targeting_generated_study_snapshot() -> None:
    decision = decide(
        {
            "toolName": "Edit",
            "toolArgs": {
                "file_path": (
                    ".challenges/study/linked_lists/lru_cache/revision/lru_cache.py"
                )
            },
        }
    )
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert "generated read-only study snapshot" in reason
    assert "just practice-study" in reason
    assert "regenerate" in reason
    assert "ask the candidate to make this edit" not in reason


def test_denies_shell_access_to_study_snapshot_without_outsourcing_the_edit() -> None:
    decision = decide(
        {
            "toolName": "execute",
            "toolArgs": {
                "command": (
                    "sed -n '1,20p' "
                    ".challenges/study/linked_lists/lru_cache/revision/lru_cache.py"
                )
            },
        }
    )

    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert "generated read-only study snapshot" in reason
    assert "file-read tool" in reason
    assert "STUDY_SOURCE or STUDY_TEST" in reason
    assert "just practice-study" in reason
    assert "regenerate" not in reason
    assert "ask the candidate" not in reason


def test_shell_explanation_can_mention_candidate_workspace() -> None:
    decision = decide(
        {
            "toolName": "execute",
            "toolArgs": {
                "command": "just practice-test",
                "description": "Test the candidate files under .challenges/.",
            },
        }
    )
    assert decision == {"continue": True}


def test_denies_rm_rf_outside_workspace_absolute_path() -> None:
    decision = decide(
        {
            "toolName": "runInTerminal",
            "toolArgs": {"command": "rm -rf /var/tmp/scratch"},
        }
    )
    assert decision["permissionDecision"] == "deny"
    assert "rm -rf" in decision["permissionDecisionReason"]


def test_denies_rm_fr_short_flags_targeting_home() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "rm -fr ~/Downloads"}}
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_rm_rf_targeting_braced_home_variable() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "rm -rf ${HOME}/scratch"}}
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_rm_long_flags_targeting_parent_traversal() -> None:
    decision = decide(
        {
            "toolName": "shell",
            "toolArgs": {"command": "rm --recursive --force ../sibling-repo"},
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_rm_rf_inside_candidate_workspace() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "rm -rf .challenges/tmp"}}
    )
    assert decision["permissionDecision"] == "deny"


def test_continues_plain_rm_without_force_recursive_flags() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "rm /var/tmp/one-file.txt"}}
    )
    assert decision == {"continue": True}


def test_denies_git_push_force_long_flag() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "git push --force origin main"}}
    )
    assert decision["permissionDecision"] == "deny"
    assert "force" in decision["permissionDecisionReason"]


def test_denies_git_push_force_short_flag() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "git push -f origin main"}}
    )
    assert decision["permissionDecision"] == "deny"


def test_denies_git_push_force_with_lease() -> None:
    decision = decide(
        {
            "toolName": "terminal",
            "toolArgs": {"command": "git push --force-with-lease"},
        }
    )
    assert decision["permissionDecision"] == "deny"


def test_continues_plain_git_push() -> None:
    decision = decide(
        {"toolName": "bash", "toolArgs": {"command": "git push origin main"}}
    )
    assert decision == {"continue": True}


def test_continues_unrelated_shell_command() -> None:
    decision = decide({"toolName": "bash", "toolArgs": {"command": "uv run pytest -q"}})
    assert decision == {"continue": True}


def test_missing_tool_name_and_args_default_to_continue() -> None:
    assert decide({}) == {"continue": True}


def test_main_copilot_payload_prints_top_level_decision() -> None:
    payload = json.dumps(
        {"toolName": "Edit", "toolArgs": {"file_path": ".challenges/x.py"}}
    )
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    decision = json.loads(proc.stdout)
    assert decision["permissionDecision"] == "deny"
    assert "hookSpecificOutput" not in decision


def test_main_vscode_payload_prints_nested_hook_specific_output() -> None:
    payload = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": ".challenges/x.py"},
        }
    )
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    output = json.loads(proc.stdout)
    assert set(output) == {"hookSpecificOutput"}
    decision = output["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "candidate" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "toolName": "bash",
            "toolArgs": {"command": "printf '%s\\n' safe"},
        },
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "runTerminalCommand",
            "tool_input": {"command": "printf '%s\\n' safe"},
        },
    ],
)
def test_main_safe_payload_emits_documented_neutral_common_output(
    payload: dict[str, object],
) -> None:
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == '{"continue": true}\n'


def test_main_denies_via_nonzero_exit_on_unparseable_payload() -> None:
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        input="not json",
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
