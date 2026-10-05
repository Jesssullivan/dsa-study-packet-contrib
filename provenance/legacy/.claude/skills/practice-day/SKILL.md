---
name: practice-day
description: Conduct an explicitly requested full 4 to 5 hour interview-practice day, multi-block practice session, or short 90-minute block. Default to editor-first coding reps with real tests, breaks, targeted review, and an optional board or observed mock. Do not trigger on a generic request to practice one problem.
---

# Practice day conductor

Read the persona block in repo-root `AGENTS.md`; it is authoritative. Use this
skill only when the candidate explicitly requests a full practice day,
multi-block session, or 90-minute block. Route a generic single-rep request to
the `interviewer` skill.

Ask whether they want the full 4 to 5 hour ceiling or the short 90-minute
block. Offer the arrival reset once. Never treat regulation as a gate or score.

## Full day or numbered day

If the candidate supplied a day number, run `just practice-day <day>`. For an
unnumbered full day, ask which sheet-11 day (1 through 14) they are running,
then run the same command. The command is the schedule authority.

Relay its focus, breaks, and exact editor commands. If it prints `## Rest day`,
relay the rest plan and stop. Otherwise run only its printed commands, one at a
time, following the `AGENTS.md` editor state loop. Do not invent another block,
draw, or schedule.

## Short block

1. Run `just study-spaced 3` and let the candidate choose one printed command,
   or use the first.
2. Run that exact `just practice-start` command. Default to CLARP unless the
   candidate requested REACTO, UMPIRE, or plain comments.
3. Follow the `AGENTS.md` editor state loop. The candidate owns the source,
   tests, and comments.
4. Close with one win, one fix, and `just practice-finish "one specific fix"`.
   Stop at 90 minutes even if work remains.

For an optional board or observed mock printed by the conductor, follow the
persona cadence and close once with `just rep-finish <topic> <problem> "<rep
line>"`. Never close it with separate log and review commands.

## Standing rules

- Editor-first is the default. Whiteboard is an optional requested variant.
- Prefer retrieval and coding over passive review.
- Never exceed 90 minutes without a real break.
- Never edit candidate-owned files or solve the problem.
- Keep employer details and personal logs outside tracked public files.
