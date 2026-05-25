# Example Runs

## New-Day Local Rollover

- `DATA_DIR/tasks/today.md` belongs to yesterday.
- Append the final task list and compact planning notes into `DATA_DIR/tasks/archive/log.md`.
- Refresh `DATA_DIR/context/planner-memory.md`.
- Update `DATA_DIR/context/daily-outcomes.md`.
- Append completed archived tasks into `DATA_DIR/data/task_log.csv`.
- Write today’s local plan.
- Do not sync Google Docs, Google Sheets, or reading-list mirrors.
- Do not update research notes unless the user explicitly requested research.

## Same-Day Verify

- `DATA_DIR/tasks/today.md` already belongs to today.
- Validate task count, priorities, metadata, and duplicate lanes.
- If the plan already satisfies the workflow, make no cosmetic rewrite.
- Do not perform external sync.

## Explicit Research Request

- If the user asks for research, treat it as a separate local task.
- Update `DATA_DIR/research/research-report.md` only for that explicit request.
- Do not add research as an implicit daily-planning mode.
