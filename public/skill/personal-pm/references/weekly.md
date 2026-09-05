# Weekly focus and review

Read [weekly-planning.md](weekly-planning.md) for the shared coaching contract.
Read saved goals, eligible projects, weekly focus, and compact outcome memory.
For incomplete goal context, use [setup.md](setup.md) before drafting commitments.

For weekly setup, collect only missing outcome/capacity/trade-off information.
State the proposed priorities and the capacity assumptions supporting them. If the
user asks to draft only, return the proposal without saving. When saving is within
the request, persist a grounded weekly JSON draft through the shared writer:

```sh
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" save-weekly \
  --week-of YYYY-MM-DD --file /path/to/weekly-draft.json
```

The date is the Monday starting the intended week. Use the user's requested week;
do not assume a weekly review means replacing the current week. Add `--replace`
only for an explicitly requested revision of an existing week. The helper validates
the draft and preserves unchanged priorities' completion states. It never edits goals.

For review, report completed results, incomplete priorities, and canceled work
separately. Cite local dates/tasks supporting one practical lesson about scope or
task shape. Save a requested review to `context/weekly-reviews.md` under `## Week of
YYYY-MM-DD`, preserving other weeks. Do not regenerate daily archives just to write
a weekly review. If the user also requests next week's plan, use the review as
evidence, ask for any missing upcoming constraints, then save that week's focus.

Report the selected week, concrete priorities, and any unresolved assumptions.
