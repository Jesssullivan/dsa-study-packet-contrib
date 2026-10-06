# Personal Woodshed agent overlay

This orphan branch preserves optional personal tooling and migration evidence
from packet `d19ee4f9fc79b404690bfb903b91b3c989a21505`. Push it only to the
personal contribution fork, never merge it into the organization product.

The active adapter is `.agents/skills/woodshed-session/SKILL.md`. It discovers
the current product through `just capabilities` and routes all activity through
`just session`. It does not maintain a second catalog or state machine.

After fetching the contribution fork's overlay branch, restore the active
adapter into a product feature worktree and exclude it locally. Restore only
the chosen adapter, leaving optional operator tools and provenance separate:

```bash
git fetch origin agents-overlay
git restore --source=origin/agents-overlay --worktree -- AGENTS.md .agents/skills/woodshed-session
printf 'AGENTS.md\n.agents/\n' >> "$(git rev-parse --git-path info/exclude)"
```

Install the skill in the tool you choose, or read its small adapter directly.
Provider-specific setup and authentication remain deliberate local choices.
`just capabilities` lists material and its supported modes. Workspace, editor,
and protected-service readiness come from the chosen environment's diagnostics.
Candidate work stays private under `.challenges`; the learner owns source and
test edits and supplies the correction used to finish a session.

`.agents/tools/gh-codespace-file/` preserves optional operator tooling for an
existing file-only GitHub credential provider. Its pinned public-source
bootstrap builds a narrow upstream Codespaces SSH/logs/rebuild adapter and runs
synthetic/race checks. The tool never participates in the practice dispatcher
and is not needed for public practice. Read its README and qualification before
an explicitly selected owned-resource action; credentials stay outside git.

`provenance/legacy/` preserves the retired provider templates, generated
personas, hook guard, generators, and their tests byte-for-byte. Other
`provenance/` files retain prior maps and validation contracts. These files
are evidence, not active commands or product authority. Do not restore the
old generated routing as a second engine. `overlay/vscode-settings.json`
records former editor preferences for review; it includes a retired disabled
sandbox preference. Apply any approved provider keys to user or profile editor
settings outside the tracked product, never to product `.vscode/settings.json`.
