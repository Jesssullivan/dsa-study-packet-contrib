"""Copilot ``preToolUse`` hook: protect private practice state (see AGENTS.md).

Denies file-edit/write tool calls that target ``.challenges/**`` (the
candidate's workspace or generated study snapshots), shell commands that
directly reference that state, and clearly destructive shell patterns
(``rm -rf`` outside this workspace, ``git push --force``). Every deny carries a reason telling the
calling agent what to do instead. File-edit tools inspect only path-shaped
argument fields, so maintenance edits that merely mention the workspace in
file content receive the neutral continuation output. Schema and doc source:
``.github/hooks/README.md``.

Run as a hook (stdin -> stdout, exit 0 unless the payload itself is
unreadable, in which case exit 2 so the caller's own fail-closed default
applies):

    .venv/bin/python scripts/hooks/guard_pretooluse.py
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from typing import Any

_CANDIDATE_WORKSPACE = re.compile(r"(?<![\w-])\.challenges(?:[/\\]|$)")
_STUDY_SNAPSHOT = re.compile(r"(?<![\w-])\.challenges[/\\]study(?:[/\\]|$)")

# Tool-name substrings (case-insensitive) that mark a file-mutating tool
# across the runtimes that read this hook: Copilot CLI/cloud agent, and
# Claude Code's compatible "PreToolUse" plugin format.
EDIT_TOOL_NAME_HINTS = (
    "create",
    "delete",
    "edit",
    "write",
    "move",
    "remove",
    "rename",
    "unlink",
    "applypatch",
    "apply_patch",
    "str_replace",
    "replace_string",
)

# Argument-key substrings (case-insensitive) that mark a path-shaped value.
# Content fields like new_string/old_string/content must not trip the
# workspace marker, or edits to docs that mention .challenges/ get denied.
PATH_KEY_HINTS = (
    "path",
    "file",
    "filename",
    "target",
    "uri",
    "notebook",
)

# Tool-name substrings that mark a shell/terminal execution tool.
SHELL_TOOL_NAME_HINTS = (
    "bash",
    "shell",
    "terminal",
    "exec",
    "runcommand",
    "run_command",
)

_RM_WORD = re.compile(r"\brm\b")
_RM_COMBINED_FLAGS = re.compile(
    r"(?<![\w-])-[A-Za-z]*[rR][A-Za-z]*[fF][A-Za-z]*(?![\w-])"
    r"|(?<![\w-])-[A-Za-z]*[fF][A-Za-z]*[rR][A-Za-z]*(?![\w-])"
)
_RM_LONG_RECURSIVE = re.compile(r"--recursive\b")
_RM_LONG_FORCE = re.compile(r"--force\b")
# A target is "outside the workspace" when it is absolute, home-relative, or
# escapes via a parent-directory traversal; a bare relative path stays inside.
_UNSAFE_RM_TARGET = re.compile(r"(?:^|\s)(?:/|~|\$\{?HOME\}?|\.\.(?:/|\\|$))")
_GIT_PUSH = re.compile(r"\bgit\s+push\b")
_FORCE_FLAG = re.compile(r"--force(?:-with-lease)?\b|(?<![\w-])-f\b")


def _iter_strings(value: Any) -> Iterator[str]:
    """Yield every string leaf inside a JSON-shaped value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _parse_tool_args(tool_args: Any) -> Any:
    """``toolArgs`` is documented as an object in one place and a JSON-encoded
    string in another; accept either shape."""
    if isinstance(tool_args, str):
        try:
            return json.loads(tool_args)
        except json.JSONDecodeError:
            return tool_args
    return tool_args


def _matches_any_hint(name: str, hints: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in hints)


def _iter_path_strings(value: Any, key_hinted: bool = False) -> Iterator[str]:
    """Yield string leaves reachable only through path-shaped keys."""
    if isinstance(value, str):
        if key_hinted:
            yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            hinted = key_hinted or _matches_any_hint(str(key), PATH_KEY_HINTS)
            yield from _iter_path_strings(item, hinted)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_path_strings(item, key_hinted)


def _targets_candidate_workspace(tool_args: Any) -> bool:
    # A bare-string argument to an edit tool is itself path-shaped.
    if isinstance(tool_args, str):
        return bool(_CANDIDATE_WORKSPACE.search(tool_args))
    return any(
        _CANDIDATE_WORKSPACE.search(text) for text in _iter_path_strings(tool_args)
    )


def _targets_study_snapshot(tool_args: Any) -> bool:
    if isinstance(tool_args, str):
        return bool(_STUDY_SNAPSHOT.search(tool_args))
    return any(
        _STUDY_SNAPSHOT.search(text) for text in _iter_path_strings(tool_args)
    )


def _shell_references_candidate_workspace(command_text: str) -> bool:
    """Return whether a shell command directly names candidate-owned state.

    Unlike file-edit tools, a shell tool can mutate a path hidden anywhere in
    its command text (redirection, ``sed``, Python, and so on), so the full
    command is intentionally checked. Repo front-door commands such as
    ``just practice-test`` do not name the private path and stay neutral.
    """
    return bool(_CANDIDATE_WORKSPACE.search(command_text))


def _iter_shell_commands(value: Any, key_hinted: bool = False) -> Iterator[str]:
    """Yield only command-shaped shell input, never explanatory prose."""
    if isinstance(value, str):
        if key_hinted:
            yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            name = str(key).lower()
            hinted = (
                key_hinted
                or name in {"cmd", "script"}
                or name.endswith(("command", "commands"))
            )
            yield from _iter_shell_commands(item, hinted)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_shell_commands(item, key_hinted)


def _shell_command_text(tool_args: Any) -> str:
    if isinstance(tool_args, str):
        return tool_args
    return "\n".join(_iter_shell_commands(tool_args))


def _has_recursive_force_flags(command_text: str) -> bool:
    if _RM_COMBINED_FLAGS.search(command_text):
        return True
    return bool(
        _RM_LONG_RECURSIVE.search(command_text) and _RM_LONG_FORCE.search(command_text)
    )


def _is_destructive_rm(command_text: str) -> bool:
    if not _RM_WORD.search(command_text):
        return False
    if not _has_recursive_force_flags(command_text):
        return False
    return bool(_UNSAFE_RM_TARGET.search(command_text))


def _is_force_push(command_text: str) -> bool:
    for statement in re.split(r"&&|\|\||;|\n", command_text):
        if _GIT_PUSH.search(statement) and _FORCE_FLAG.search(statement):
            return True
    return False


def decide(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one preToolUse decision for a single hook invocation payload."""
    # Copilot CLI/cloud use camelCase. VS Code converts the same lower-camel
    # hook declaration to its Preview PascalCase event and sends snake_case.
    tool_name = str(payload.get("toolName", payload.get("tool_name", "")))
    raw_args = (
        payload["toolArgs"] if "toolArgs" in payload else payload.get("tool_input")
    )
    tool_args = _parse_tool_args(raw_args)

    if _matches_any_hint(
        tool_name, EDIT_TOOL_NAME_HINTS
    ) and _targets_candidate_workspace(tool_args):
        if _targets_study_snapshot(tool_args):
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "generated read-only study snapshot under .challenges/study/; "
                    "do not edit it; rerun the exact just practice-study front "
                    "door to regenerate it"
                ),
            }
        return {
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "candidate-owned file under .challenges/; relay the exact "
                "error and ask the candidate to make this edit themselves"
            ),
        }

    if _matches_any_hint(tool_name, SHELL_TOOL_NAME_HINTS):
        command_text = _shell_command_text(tool_args)
        if _shell_references_candidate_workspace(command_text):
            if _STUDY_SNAPSHOT.search(command_text):
                return {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "shell command directly references a generated read-only "
                        "study snapshot; use the file-read tool with the exact "
                        "STUDY_SOURCE or STUDY_TEST path emitted by "
                        "just practice-study"
                    ),
                }
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "shell command directly references candidate-owned "
                    ".challenges/ state; use the repo practice front doors or "
                    "ask the candidate to make the change themselves"
                ),
            }
        if _is_destructive_rm(command_text):
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "rm -rf targets a path outside this workspace; relay the "
                    "exact command and ask the candidate to run it themselves "
                    "if they intend it"
                ),
            }
        if _is_force_push(command_text):
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "git push --force rewrites shared history; relay the "
                    "exact command and ask the candidate to run it themselves "
                    "if they intend it"
                ),
            }

    return {"continue": True}


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"guard_pretooluse: invalid JSON payload: {exc}", file=sys.stderr)
        return 2
    decision = decide(payload)
    # This guard narrows authority; it never grants it. The documented common
    # output keeps hook processing active without making a PreToolUse
    # permission decision, so the runtime's normal approval policy still wins.
    if decision == {"continue": True}:
        print(json.dumps(decision))
        return 0
    if payload.get("hook_event_name") == "PreToolUse":
        hook_output = {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision["permissionDecision"],
        }
        reason = decision.get("permissionDecisionReason")
        if reason is not None:
            hook_output["permissionDecisionReason"] = reason
        print(json.dumps({"hookSpecificOutput": hook_output}))
    else:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
