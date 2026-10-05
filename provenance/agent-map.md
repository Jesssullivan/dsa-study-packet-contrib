# dsa-study-packet Agent Map

## Read Order

1. `AGENTS.md`
2. `TRACK-CONTRACT.md`
3. `docs/guide/getting-started.md`
4. `docs/guide/source-of-truth.md`
5. `CLAUDE.md` (Claude overlay only, secondary to `AGENTS.md`)

## Core Recipes

- `just practice-start comments|reacto|clarp|umpire [topic problem]`
- `just practice-next`
- `just practice-test`
- `just practice-watch`
- `just practice-repl`
- `just practice-open [topic problem]`
- `just practice-study topic problem`
- `just practice-start-tests topic problem`
- `just practice-finish "<one fix>"`
- `just interview [topic problem]`
- `just rep-finish topic problem "<line>"`
- `just catalog "<words>"`
- `just packet`
- `just docs`
- `just pdf-all`
- `just test`
- `just lint`
- `just doctor`

## Machine Keys

`STATE`, `SOURCE`, `TEST`, `NEXT`, `START`, `QUEUE`, `QUERY`, `MATCH`,
`CHOOSE`, `SUGGEST`, `OPENED`, `OPEN_FAILED`, `STUDY_SOURCE`, `STUDY_TEST`,
`REVISION`, `IMPLEMENT`, `TESTS_FIRST`, `FOCUS`, `PRACTICE`, `CLOSED`,
`LOGGED`, `SPACED`, `TESTS`. Catalog
readiness (`READY`, `CHOOSE`, `NOT_FOUND`) travels
as a `STATE` value.

## Skills

- `.claude/skills/interviewer/SKILL.md`: one practice rep
- `.claude/skills/practice-day/SKILL.md`: a full day or multi-block session

## Prohibited

- Never write candidate source or tests; the candidate owns them.
- Never read, score, or log private arrival writing. Read only command-emitted
  candidate paths at save boundaries or study snapshots on explicit request.
- `just` is the only front door; never invoke raw Bazel directly.
- Never write employer names, interviewer notes, clearance facts, or
  personal rep logs into tracked files.
