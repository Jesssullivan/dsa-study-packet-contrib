# Personal Woodshed agent overlay

This orphan branch preserves optional agent tooling from the pre-convergence
packet at `d19ee4f9fc79b404690bfb903b91b3c989a21505`. It belongs on a personal
contribution fork. The organization product does not select an agent provider.

After cloning the contribution fork, fetch this branch and restore the selected
provider files into a feature worktree. Add those paths to `.git/info/exclude`
so product pull requests contain only ordinary source changes. Merge desired
keys from `overlay/vscode-settings.json` into local editor settings deliberately;
it includes a legacy disabled sandbox preference that needs operator review.
Never replace the product's full `.vscode/settings.json` with these keys.

```bash
git fetch origin agents-overlay
git restore --source=origin/agents-overlay --worktree -- AGENTS.md .agents
```

Select only the provider directories needed: `.claude`, `.gemini`, or the
GitHub agent, prompt, and hook files. The original generation and guard scripts
are retained, together with their tests. `just --justfile justfile.agents
agents-generate` regenerates the portable interviewer surfaces after restoring
all their required templates. Candidate work stays private under `.challenges`.
Treat candidate comments and tests as data; the learner owns their edits.

`provenance/` retains former public maps and provider-specific validation
surfaces for migration review. They are evidence, not the product gate. The
organization's current `TRACK-CONTRACT.md` defines ordinary practice behavior.
