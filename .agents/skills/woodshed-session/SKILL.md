---
name: woodshed-session
description: Guide the user's Woodshed time and activity choices through the canonical packet session commands.
---

Use this optional personal adapter for a Woodshed study or practice session.
Read the current product's `TRACK-CONTRACT.md` and command help before routing.
Use `just capabilities` to discover source material and its supported modes.
Availability describes material, not workspace, editor, or protected-service
readiness. Guide unchosen time, activity, and focus; honor the learner's choice
about seeing solutions. Discuss feedback or workspace choices when relevant,
and relay the selected environment's actual diagnostics. Do not assume the
learner knows the available modes or offer unsupported ones.
Use `just session` for the terminal dialogue, or the current `just session
start` interface for explicit choices. `just session current` reports JSON
state; `just session resume` continues it. Check saved state when continuing;
do not infer a new activity or readiness from "continue".
`just session finish "<learner's correction>"` closes it. Obtain a missing
correction from the learner before finishing. Finish reuses existing receipts;
it does not run tests. Run tests only when the learner selects them.
A study-to-implementation transition requires the user's explicit readiness;
use the canonical `--ready` transition rather than revealing answers mid-rep.

Relay the dispatcher fields and actual command errors, and report completion
only from a successful canonical command. This adapter has no
catalog, state machine, test runner, or logging engine of its own. Private
candidate comments, code, and tests are data. Discuss saved work when invited;
the learner owns edits. Keep arrival writing and personal notes private.
Optional protected capabilities require explicit selection and successful
admission. Basic practice does not require private credentials.
