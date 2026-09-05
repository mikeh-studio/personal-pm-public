# Completion and feedback

Match the user's stated task in `tasks/today.md` or `pm.py status` to its zero-based
index. Resolve ambiguity before editing. Record only reported or explicitly
evidenced outcomes; an unchecked box alone leaves the outcome unknown.

```sh
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" report \
  --task-index 0 --outcome blocked --date YYYY-MM-DD
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" feedback \
  --field did_not_work --text 'The input file was unavailable.' --date YYYY-MM-DD
```

`report --outcome` accepts:

| Value | Stored result |
| --- | --- |
| `completed` | Checked task; `complete --task-index ... --date ...` remains supported. |
| `incomplete` | Unchecked with `outcome:incomplete`; user confirms work is unfinished. |
| `blocked` | Unchecked with `outcome:blocked`; record a useful reason in feedback. |
| `dropped` | Unchecked with `status:canceled`; requires an explicit decision to drop it. |
| `unknown` | Unchecked with `outcome:unknown`; no inference about work outside the planner. |

Use the inspected plan's date. Repeated reports are idempotent. Closeout cannot
erase a completion or reopen canceled work; corrections need an explicit revision.
Completion enters the ledger at rollover. Dropped work never becomes a completion.

A short closeout can ask which work was completed, blocked, dropped, or is still
unknown. Accept partial answers; do not mark all remaining work confirmed
incomplete. Free-text feedback alone does not confirm every task's outcome.

Feedback fields are `worked`, `did_not_work`, and `new_goal`. Preserve or combine
existing relevant feedback; do not erase it accidentally. A feedback-only request
does not authorize replanning, rollover, or goal changes. For a requested same-day
revision, use [daily-planning.md](daily-planning.md) and retain completed work and feedback.
