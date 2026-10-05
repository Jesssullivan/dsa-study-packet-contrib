"""Semantic checks for the native Codespaces/Copilot practice surface."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARADIGMS = ("reacto", "clarp", "umpire", "comments")
PROMPTS = (*PARADIGMS, "continue")
AGENT_TOOLS = {
    "read",
    "execute",
}


def _json(relative: str) -> object:
    return json.loads((ROOT / relative).read_text())


def _frontmatter(path: Path) -> list[str]:
    text = path.read_text()
    assert text.startswith("---\n")
    return text.split("---\n", 2)[1].splitlines()


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def _fake_tool(path: Path, name: str, version: str) -> None:
    _write_executable(path, f"#!/bin/sh\nprintf '%s\\n' '{name} {version}'\n")


def _fake_release_commands(path: Path) -> None:
    _write_executable(
        path / "uname",
        """#!/bin/sh
case "${1:-}" in
  -s) printf '%s\n' "${FAKE_UNAME_S:-Linux}" ;;
  -m) printf '%s\n' "${FAKE_UNAME_M:-x86_64}" ;;
  *) exit 2 ;;
esac
""",
    )
    _write_executable(
        path / "curl",
        """#!/bin/sh
output=
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$output" ] || exit 2
mkdir -p "$(dirname "$output")"
: > "$output"
touch "$HOME/curl-called"
""",
    )
    _write_executable(
        path / "sha256sum",
        """#!/bin/sh
cat > "$HOME/checksum-input"
exit "${FAKE_CHECKSUM_EXIT:-0}"
""",
    )
    _write_executable(
        path / "tar",
        """#!/bin/sh
archive=
destination=
while [ "$#" -gt 0 ]; do
  case "$1" in
    -C) destination="$2"; shift 2 ;;
    -*) shift ;;
    *) archive="$1"; shift ;;
  esac
done
[ -n "$archive" ] && [ -n "$destination" ] || exit 2
name="$(basename "$archive")"
write_tool() {
  target="$1"
  label="$2"
  version="$3"
  mkdir -p "$(dirname "$target")"
  printf '#!/bin/sh\nprintf "%%s\\n" "%s %s"\n' "$label" "$version" > "$target"
  chmod +x "$target"
}
case "$name" in
  uv-*.tar.gz)
    directory="${name%.tar.gz}"
    write_tool "$destination/$directory/uv" uv \
      "${FAKE_UV_INSTALL_VERSION:-0.11.27}"
    ;;
  just-*.tar.gz)
    write_tool "$destination/just" just \
      "${FAKE_JUST_INSTALL_VERSION:-1.40.0}"
    ;;
  watchexec-*.tar.xz)
    directory="${name%.tar.xz}"
    write_tool "$destination/$directory/watchexec" watchexec \
      "${FAKE_WATCHEXEC_INSTALL_VERSION:-2.3.2}"
    ;;
  *) exit 2 ;;
esac
""",
    )


def _setup_env(
    tmp_path: Path,
    *,
    uv_version: str = "0.11.27",
    just_version: str = "1.40.0",
    watchexec_version: str = "2.3.2",
) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    system_bin = tmp_path / "system-bin"
    home.mkdir()
    system_bin.mkdir()
    _fake_tool(system_bin / "uv", "uv", uv_version)
    _fake_tool(system_bin / "just", "just", just_version)
    _fake_tool(system_bin / "watchexec", "watchexec", watchexec_version)
    _fake_release_commands(system_bin)
    env = os.environ | {
        "HOME": str(home),
        "PATH": f"{system_bin}{os.pathsep}{os.environ['PATH']}",
    }
    return env, home


def test_devcontainer_runs_each_lifecycle_phase_once() -> None:
    config = _json(".devcontainer/devcontainer.json")
    assert isinstance(config, dict)
    assert config["onCreateCommand"].endswith("setup.sh --tools")
    assert config["updateContentCommand"].endswith("setup.sh --sync")
    assert config["postCreateCommand"].endswith("setup.sh --seed")
    assert config["waitFor"] == "updateContentCommand"
    lifecycle = (
        config["onCreateCommand"],
        config["updateContentCommand"],
        config["postCreateCommand"],
    )
    assert len(set(lifecycle)) == 3
    assert "@sha256:" in config["image"]
    assert config["remoteEnv"]["PATH"].startswith("/home/vscode/.local/bin:")


def test_devcontainer_uses_copilot_chat_without_deprecated_extension() -> None:
    config = _json(".devcontainer/devcontainer.json")
    assert isinstance(config, dict)
    customizations = config["customizations"]
    assert isinstance(customizations, dict)
    vscode = customizations["vscode"]
    assert isinstance(vscode, dict)
    extensions = set(vscode["extensions"])
    assert "GitHub.copilot-chat" in extensions
    assert "GitHub.copilot" not in extensions
    assert not any("anthropic" in extension.lower() for extension in extensions)
    features = config.get("features", {})
    assert isinstance(features, dict)
    # Infrastructure features only: sshd enables headless verification over
    # `gh codespace ssh`. No feature may provision an AI CLI.
    assert set(features) <= {"ghcr.io/devcontainers/features/sshd:1"}
    assert not any(
        term in feature.lower()
        for feature in features
        for term in ("copilot", "anthropic", "openai", "claude")
    )
    assert "secrets" not in config
    assert "postAttachCommand" not in config


def test_devcontainer_provides_sshd_for_headless_verification() -> None:
    """The sshd feature lets gh codespace ssh drive acceptance checks headlessly."""
    config = _json(".devcontainer/devcontainer.json")
    assert isinstance(config, dict)
    features = config["features"]
    assert isinstance(features, dict)
    assert "ghcr.io/devcontainers/features/sshd:1" in features


def test_devcontainer_does_not_inject_a_container_wide_node_preload() -> None:
    # Exact-head Codespaces evidence proved that VS Code removes NODE_OPTIONS
    # before it starts the remote extension host. A repository preload cannot
    # reach that process, but can still alter or break every ordinary Node
    # process in the container.
    config = _json(".devcontainer/devcontainer.json")
    assert isinstance(config, dict)
    container_env = config["containerEnv"]
    assert isinstance(container_env, dict)
    assert container_env["UV_PYTHON_PREFERENCE"] == "only-managed"
    serialized = json.dumps(config)
    assert "NODE_OPTIONS" not in serialized
    assert "--require" not in serialized
    assert "kill-navigator.cjs" not in serialized
    assert not (ROOT / ".devcontainer/kill-navigator.cjs").exists()


def test_setup_verifies_declared_tool_versions() -> None:
    setup = (ROOT / ".devcontainer/setup.sh").read_text()
    for tool, variable in (
        ("uv", "UV_VERSION"),
        ("just", "JUST_VERSION"),
        ("watchexec", "WATCHEXEC_VERSION"),
    ):
        assert f'has_version {tool} "${variable}"' in setup
    assert 'require_version uv "$UV_VERSION"' in setup
    assert 'require_version just "$JUST_VERSION"' in setup
    assert "install.sh" not in setup
    assert "sha256sum --check --status" in setup
    assert setup.count("_SHA256_X86_64=") == 3
    assert setup.count("_SHA256_AARCH64=") == 3


def test_setup_accepts_matching_tools_without_downloading(tmp_path: Path) -> None:
    env, home = _setup_env(tmp_path, uv_version="0.11.27")
    system_bin = Path(env["PATH"].split(os.pathsep, 1)[0])
    _write_executable(system_bin / "curl", "#!/bin/sh\nexit 97\n")

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert not (home / "curl-called").exists()


def test_setup_forgets_hashed_old_tool_after_install(tmp_path: Path) -> None:
    env, home = _setup_env(tmp_path, uv_version="0.0.0")

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert (home / "curl-called").is_file()
    assert (home / "checksum-input").read_text().split()[0] == (
        "5d5594af1530c7c31e46a8cc0a35ceb4d28f3890049efe2149ac53c9ad121493"
    )
    installed = subprocess.run(
        [str(home / ".local/bin/uv"), "--version"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert installed.stdout.strip() == "uv 0.11.27"


def test_setup_fails_when_installer_leaves_wrong_version(tmp_path: Path) -> None:
    env, _ = _setup_env(tmp_path, uv_version="0.0.0")
    env["FAKE_UV_INSTALL_VERSION"] = "0.0.1"

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "uv install did not provide declared version 0.11.27" in proc.stderr


def test_setup_forgets_hashed_old_just_after_install(tmp_path: Path) -> None:
    env, _ = _setup_env(tmp_path, just_version="0.0.0")

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_setup_rejects_an_archive_with_wrong_digest(tmp_path: Path) -> None:
    env, home = _setup_env(tmp_path, uv_version="0.0.0")
    env["FAKE_CHECKSUM_EXIT"] = "1"

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "uv install did not provide declared version 0.11.27" in proc.stderr
    assert not (home / ".local/bin/uv").exists()


def test_setup_selects_arm64_release_digest(tmp_path: Path) -> None:
    env, home = _setup_env(tmp_path, uv_version="0.0.0")
    env["FAKE_UNAME_M"] = "aarch64"

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert (home / "checksum-input").read_text().split()[0] == (
        "b0b1909a7e5caf2ec0cbe2649f5171050c26d85efb65d9d4de2cfe754dc14ea3"
    )


def test_setup_rejects_unknown_release_architecture(tmp_path: Path) -> None:
    env, _ = _setup_env(tmp_path, uv_version="0.0.0")
    env["FAKE_UNAME_M"] = "riscv64"

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "unsupported Codespaces architecture: riscv64" in proc.stderr


def test_setup_keeps_watchexec_optional_when_install_fails(tmp_path: Path) -> None:
    env, _ = _setup_env(tmp_path, watchexec_version="0.0.0")
    system_bin = Path(env["PATH"].split(os.pathsep, 1)[0])
    _write_executable(system_bin / "curl", "#!/bin/sh\nexit 97\n")

    proc = subprocess.run(
        ["bash", ".devcontainer/setup.sh", "--tools"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "watch mode unavailable" in proc.stderr


def test_setup_does_not_install_unused_agent_sandbox_packages() -> None:
    setup = (ROOT / ".devcontainer/setup.sh").read_text()

    assert "apt-get" not in setup
    assert "sudo " not in setup
    assert "bubblewrap" not in setup
    assert "socat" not in setup


def test_devcontainer_workflow_uses_pinned_actions_and_login_free_path() -> None:
    workflow = (ROOT / ".github/workflows/devcontainer.yml").read_text()
    assert "export PATH=" not in workflow
    assert "bash --noprofile --norc" in workflow
    assert "# RESTATE:" not in workflow
    assert "ordinary comments or a docstring" in workflow
    assert "THINKING GATE" not in workflow
    assert "grep -q '^STATE: THINK$'" in workflow
    assert "grep -q '^STATE: REFLECT$'" in workflow
    assert "grep -q '^STATE: CLOSE$'" in workflow
    assert workflow.count("just practice-test") >= 3
    action_refs = [
        line.strip().removeprefix("- uses: ").split(" #", 1)[0]
        for line in workflow.splitlines()
        if line.strip().startswith("- uses: ")
    ]
    assert action_refs
    for action_ref in action_refs:
        revision = action_ref.rsplit("@", 1)[1]
        assert len(revision) == 40
        assert all(character in "0123456789abcdef" for character in revision)


def test_workspace_recommends_prompts_but_disables_inline_completion() -> None:
    settings = _json(".vscode/settings.json")
    assert isinstance(settings, dict)
    assert settings["chat.useAgentsMdFile"] is True
    assert settings["github.copilot.chat.codeGeneration.useInstructionFiles"] is False
    assert settings["chat.promptFilesRecommendations"] == dict.fromkeys(PROMPTS, True)
    assert settings["github.copilot.enable"] == {"*": False}
    assert settings["github.copilot.nextEditSuggestions.enabled"] is False
    assert "chat.disableAIFeatures" not in settings


def test_workspace_uses_the_managed_uv_environment_without_preview_prompts() -> None:
    settings = _json(".vscode/settings.json")
    assert isinstance(settings, dict)
    assert settings["python.defaultInterpreterPath"] == (
        "${workspaceFolder}/.venv/bin/python"
    )
    assert settings["python.useEnvironmentsExtension"] is False


def test_workspace_autoapprove_allowlist_is_narrow() -> None:
    settings = _json(".vscode/settings.json")
    assert isinstance(settings, dict)
    auto_approve = settings["chat.tools.terminal.autoApprove"]
    assert auto_approve == {
        (
            r"/^just practice-start (reacto|clarp|umpire|comments)"
            r"( [a-z][a-z0-9_]* [a-z][a-z0-9_]*)?$/"
        ): True,
        r"/^just practice-start-tests [a-z][a-z0-9_]* [a-z][a-z0-9_]*$/": True,
        r"/^just practice-next$/": True,
        r"/^just practice-test$/": True,
        r"/^just practice-watch$/": True,
        r"/^just practice-repl$/": True,
        r"/^just practice-open( [a-z][a-z0-9_]* [a-z][a-z0-9_]*)?$/": True,
        r"/^just practice-study [a-z][a-z0-9_]* [a-z][a-z0-9_]*$/": True,
        r"""/^just practice-finish "[A-Za-z0-9 .,;:!?()'_-]{1,500}"$/""": True,
        r"/^just interview( [a-z][a-z0-9_]* [a-z][a-z0-9_]*)?$/": True,
        r"""/^just catalog "[A-Za-z0-9 ,.?!'_-]{1,120}"$/""": True,
    }
    assert all(value is True for value in auto_approve.values())
    assert "*" not in auto_approve
    # VS Code's preview Bubblewrap sandbox cannot nest inside Codespaces.
    # Keep it off without broadening container privileges; the Codespace
    # boundary, narrow allowlist, and pre-tool guard remain in force.
    assert settings["chat.agent.sandbox.enabled"] == "off"
    assert not any(
        key.startswith("chat.agent.sandbox") and key != "chat.agent.sandbox.enabled"
        for key in settings
    )


def test_catalog_autoapprove_accepts_documented_lists_but_not_shell_syntax() -> None:
    settings = _json(".vscode/settings.json")
    assert isinstance(settings, dict)
    auto_approve = settings["chat.tools.terminal.autoApprove"]
    encoded = next(key for key in auto_approve if key.startswith("/^just catalog "))
    pattern = re.compile(encoded[1:-1])

    assert pattern.fullmatch('just catalog "anagram, 2 sum and prime"')
    assert pattern.fullmatch(
        'just catalog "Hey there! lets focus on untimed iteration and practice on LRU cache"'
    )
    assert not pattern.fullmatch('just catalog "$(touch /tmp/pwned)"')
    assert not pattern.fullmatch('just catalog "`touch /tmp/pwned`"')
    assert not pattern.fullmatch('just catalog "lru\'; touch /tmp/pwned"')
    assert not pattern.fullmatch('just catalog "two sum"; touch /tmp/pwned')


def test_welcome_does_not_require_nested_sandbox_repair() -> None:
    welcome = (ROOT / "WELCOME.md").read_text().casefold()
    assert "terminal sandboxing is off" in welcome
    assert "repair bubblewrap" not in welcome


def test_workspace_tasks_are_explicit_and_never_run_on_folder_open() -> None:
    tasks = _json(".vscode/tasks.json")
    assert isinstance(tasks, dict)
    serialized = json.dumps(tasks)
    assert "folderOpen" not in serialized
    assert ".devcontainer/launch-agent.sh" not in serialized
    commands = {task.get("command") for task in tasks["tasks"]}
    assert {
        "just practice-start ${input:practiceParadigm}",
        "just practice-next",
        "just practice-test",
        "just practice-watch",
        "just practice-open",
        "just practice-repl",
    } <= commands
    finish = next(
        task
        for task in tasks["tasks"]
        if task["label"] == "practice: finish current rep"
    )
    assert finish["type"] == "process"
    assert finish["command"] == "just"
    assert finish["args"] == ["practice-finish", "${input:practiceFinishNote}"]


@pytest.mark.parametrize(
    ("topic", "problem"),
    [("lru_cache", ""), ("", "lru_cache")],
)
def test_practice_open_recipe_forwards_exact_pairs_and_guides_partial_names(
    topic: str,
    problem: str,
) -> None:
    exact = subprocess.run(
        ["just", "--dry-run", "practice-open", "linked_lists", "lru_cache"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert exact.returncode == 0, exact.stderr
    exact_output = exact.stdout + exact.stderr
    assert "topic='linked_lists'" in exact_output
    assert "problem='lru_cache'" in exact_output
    assert 'practice_workspace.py open "$topic" "$problem"' in exact_output

    partial = subprocess.run(
        ["just", "practice-open", topic, problem],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert partial.returncode == 2
    assert 'NEXT: just catalog "lru_cache"' in partial.stdout


def test_practice_study_requires_and_forwards_one_exact_pair() -> None:
    exact = subprocess.run(
        ["just", "--dry-run", "practice-study", "linked_lists", "lru_cache"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert exact.returncode == 0, exact.stderr
    output = exact.stdout + exact.stderr
    assert "topic='linked_lists'" in output
    assert "problem='lru_cache'" in output
    assert 'practice_workspace.py study "$topic" "$problem"' in output

    missing = subprocess.run(
        ["just", "practice-study"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "requires one exact topic/problem pair" in missing.stdout
    assert "NEXT: just catalog" in missing.stdout

    partial = subprocess.run(
        ["just", "practice-study", "lru_cache"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert partial.returncode == 2
    assert "requires one exact topic/problem pair" in partial.stdout
    assert "omit both for a draw" not in partial.stdout
    assert 'NEXT: just catalog "lru_cache"' in partial.stdout


def test_practice_start_tests_activates_exact_pair_with_test_focus() -> None:
    exact = subprocess.run(
        ["just", "--dry-run", "practice-start-tests", "linked_lists", "lru_cache"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert exact.returncode == 0, exact.stderr
    output = exact.stdout + exact.stderr
    assert "practice_workspace.py start comments" in output
    assert "linked_lists" in output
    assert "lru_cache" in output
    assert "--focus test" in output


def test_all_interviewer_surfaces_prioritize_safe_file_open_intent() -> None:
    for relative in (
        "AGENTS.md",
        ".claude/skills/interviewer/SKILL.md",
        ".github/agents/interviewer.agent.md",
        ".github/copilot-instructions.md",
    ):
        text = " ".join((ROOT / relative).read_text().split())
        folded = text.casefold()
        assert "just interview topic problem" in text
        assert "practice-open" in text
        assert "just practice-study topic problem" in text
        assert "just practice-start-tests topic problem" in text
        assert '"untimed iteration"' in text
        assert "STUDY_SOURCE" in text
        assert "STUDY_TEST" in text
        assert "STATE: STUDY" in text
        assert "REVISION" in text
        assert "IMPLEMENT" in text
        assert "TESTS_FIRST" in text
        assert "work review/check" in folded
        assert "just practice-next" in text
        assert "FOCUS" in text
        assert "OPENED" in text
        assert "OPEN_FAILED" in text
        assert "QUEUE" in text
        assert any(
            phrase in folded
            for phrase in (
                "hold `queue`",
                "never request `queue`",
                "never `queue`",
                "request no `queue`",
            )
        )
        assert "reopen" in text
        assert "never open tracked" in folded
        assert any(
            phrase in folded
            for phrase in (
                "never auto-test",
                "never open tracked source/tests or auto-test",
                "do not run tests yet",
            )
        )
        assert "candidate-authored comment/docstring idea" in folded
        assert "candidate-written terms" in folded
        assert (
            "no pattern, data-structure, or pass-count term absent from their comments"
            in folded
        )


def test_all_interviewer_surfaces_relay_structured_test_preflight() -> None:
    for relative in (
        "AGENTS.md",
        ".agents/skills/interviewer/SKILL.md",
        ".claude/skills/interviewer/SKILL.md",
        ".github/agents/interviewer.agent.md",
        ".github/copilot-instructions.md",
    ):
        text = " ".join((ROOT / relative).read_text().split())
        assert "missing harness" in text.casefold()
        assert "relay present" in text
        assert "otherwise relay exact error" in text or "else exact error" in text
        for field in ("`STATE`", "`TEST`", "`NEXT`"):
            assert field in text


def test_all_interviewer_surfaces_require_explicit_test_intent() -> None:
    for relative in (
        "AGENTS.md",
        ".agents/skills/interviewer/SKILL.md",
        ".claude/skills/interviewer/SKILL.md",
        ".github/agents/interviewer.agent.md",
        ".github/copilot-instructions.md",
        ".github/prompts/continue.prompt.md",
    ):
        text = " ".join((ROOT / relative).read_text().split())
        assert "Only explicit test intent runs `just practice-test`" in text


def test_slash_prompts_route_to_the_interviewer_and_portable_recipe() -> None:
    prompt_dir = ROOT / ".github/prompts"
    assert {
        path.stem.removesuffix(".prompt") for path in prompt_dir.glob("*.prompt.md")
    } == set(PROMPTS)
    for paradigm in PARADIGMS:
        path = prompt_dir / f"{paradigm}.prompt.md"
        frontmatter = _frontmatter(path)
        assert f"name: {paradigm}" in frontmatter
        assert "agent: 'Interviewer'" in frontmatter
        assert not any(line.startswith("tools:") for line in frontmatter)
        prompt = path.read_text()
        assert f"just practice-start {paradigm}" in prompt
        assert "never start directly" in prompt
        assert prompt.index('just catalog "<arguments>"') < prompt.index(
            f"just practice-start {paradigm} topic problem"
        )

    continuation = prompt_dir / "continue.prompt.md"
    continuation_frontmatter = _frontmatter(continuation)
    assert "name: continue" in continuation_frontmatter
    assert "agent: 'Interviewer'" in continuation_frontmatter
    assert not any(line.startswith("tools:") for line in continuation_frontmatter)
    continuation_text = continuation.read_text()
    assert "just practice-next" in continuation_text
    assert "practice-status" not in continuation_text
    assert "practice-current" not in continuation_text
    for field in ("SOURCE:", "TEST:", "NEXT:"):
        assert field in continuation_text
    assert "edit candidate files" in continuation_text
    assert "automatic save detection" in continuation_text
    assert "candidate-authored comment/docstring idea" in continuation_text
    assert "candidate-written terms" in continuation_text
    assert (
        "no pattern, data-structure, or pass-count term absent from their comments"
        in continuation_text.casefold()
    )


def test_interviewer_agent_has_no_direct_edit_tool() -> None:
    path = ROOT / ".github/agents/interviewer.agent.md"
    frontmatter = _frontmatter(path)
    assert "target: vscode" in frontmatter
    tools_index = frontmatter.index("tools:")
    tools = {
        line.removeprefix("  - ")
        for line in frontmatter[tools_index + 1 :]
        if line.startswith("  - ")
    }
    assert tools == AGENT_TOOLS
    assert "AGENTS.md" in path.read_text()
    assert "not a security boundary" in path.read_text()


def test_copilot_hooks_reference_an_existing_guard_script() -> None:
    hooks_dir = ROOT / ".github/hooks"
    hook_paths = sorted(hooks_dir.glob("*.json"))
    assert hook_paths
    for hook_path in hook_paths:
        config = json.loads(hook_path.read_text())
        assert config["version"] == 1
        pre_tool_use = config["hooks"]["preToolUse"]
        assert pre_tool_use
        for entry in pre_tool_use:
            assert entry["type"] == "command"
            assert entry["cwd"] == "."
            command = entry["bash"]
            assert command.startswith(".venv/bin/python ")
            script_relative = command.removeprefix(".venv/bin/python ").split()[0]
            script_path = ROOT / script_relative
            assert script_path.is_file(), f"{hook_path}: missing {script_relative}"
            assert "powershell" not in entry
    assert (ROOT / ".github/hooks/README.md").is_file()


def test_copilot_hook_launcher_uses_synced_python_with_empty_path(
    tmp_path: Path,
) -> None:
    hook_path = ROOT / ".github/hooks/candidate-workspace-guard.json"
    config = json.loads(hook_path.read_text())
    command = config["hooks"]["preToolUse"][0]["bash"]

    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "runTerminalCommand",
        "tool_input": {"command": "just practice-open arrays two_sum"},
    }
    proc = subprocess.run(
        command,
        shell=True,
        executable="/bin/sh",
        cwd=ROOT,
        env=os.environ | {"PATH": str(empty_bin)},
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == '{"continue": true}\n'
