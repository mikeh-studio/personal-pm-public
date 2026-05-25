---
name: personal-pm
description: Run the local-only daily-planning workflow for this repo. Use when the user asks to run the flow, refresh today’s plan, or do a daily PM pass grounded in this repo’s goals, projects, and carry-forward state.
---

# Personal PM

Keep personal goals, tasks, archives, logs, scheduler config, external-source caches, and app settings outside the public skill package.

Planner data is resolved from the configured data root. In this local repo, the default data root is `private/`; reusable scripts and app code should honor `PERSONAL_PM_DATA_DIR` when it is set. Public demos should use `demo/`; blank starter data should use `templates/`.

## When to Use
- The user asks to run the daily planning flow, refresh today’s plan, or perform a personal PM pass.
- You need the repo’s default local planning behavior with verify-first handling and compact carry-forward logic.

## Do Not Use
- Do not use for midday syncs, backlog triage-only sessions, planner-maintenance work, external sync, or research work that is not a daily planning run.

## Inputs
- Goal preflight:
  - `Goal incomplete`
  - `Normal planning`
  - `Specific focus`
- Focus area:
  - `Default`
  - `Judgement`
  - one built-in discipline
  - `Other...`

Input handling:
- Inspect `DATA_DIR/goals/goal.md` before normal planning.
- Treat goals as incomplete when any required section is missing or placeholder-only: `Overall Goals`, `Current Near-Term Deadlines`, `Key Disciplines`, or `Suggested Daily Practice`.
- If goals are incomplete, collect the missing context and update `DATA_DIR/goals/goal.md` before planning.
- If goals are complete, ask whether to run normal planning or bias today toward a specific focus.
- For direct chat invocations, asking is mandatory unless the user's message already supplied the mode/focus or the launcher/autonomous runner supplied it. Do not silently default to normal planning for requests like "run the PM flow", "refresh today's plan", or "run it for today".
- Daily-start questions:
  1. "Run normal planning, or bias today toward a specific focus?"
  2. If specific focus: "What focus area should I use: Default, Judgement, Data foundation, Decision science, Evaluation discipline, Service / platform engineering, Physical AI, Experience Design, or another focus?"
- Preferred prompt method:
  - Use the host's interactive question tool when one is available, following the gstack `AskUserQuestion` pattern.
  - In Codex Plan mode, use `request_user_input`.
  - In Claude/gstack-compatible hosts, use `AskUserQuestion`.
  - In plain chat or any host without an interactive question tool, fall back to a concise text list and wait for the user's reply.
- Interactive chooser shape:
  - If the tool supports many visible options, show `Normal planning`, `Specific focus: Default`, `Specific focus: Judgement`, each built-in discipline, and a free-text/custom option.
  - If the tool only supports 2-3 visible options, show `Normal planning`, `Specific focus: Default`, and `Specific focus: Judgement`; rely on the tool's free-form `Other` input for built-in disciplines and custom focus areas.
  - If the user chooses or enters a built-in discipline or any custom focus, treat it as `Specific focus`.
- `Default` means randomly choose one built-in discipline before planning.
- `Judgement` means do not force a discipline bias.
- `Other...` means accept a free-text focus area.
- Skip the daily-start questions only when an explicit input is present, such as "run normal planning", "focus on Data foundation", `PERSONAL_PM_FOCUS_OVERRIDE`, or an unattended/autonomous runner prompt that already includes the selected mode/focus.

## Source Precedence
1. `DATA_DIR/goals/goal.md`
2. `DATA_DIR/goals/projects.md`
3. `DATA_DIR/context/weekly-focus.md`
4. `DATA_DIR/tasks/today.md` and `DATA_DIR/tasks/backlog.md`
5. `DATA_DIR/tasks/archive/log.md`, `DATA_DIR/context/planner-memory.md`, and `DATA_DIR/context/daily-outcomes.md`
6. `DATA_DIR/data/task_log.csv` when task-tracking state matters

Reference-only files:
- `DATA_DIR/goals/reading-list.md` and `DATA_DIR/research/research-report.md` are not part of the default daily flow. Read or edit them only when the user explicitly asks for research or reading-list work.

Local-only boundary:
- Do not call Google Drive, Google Docs, Google Sheets, or external mirror syncs.
- `DATA_DIR/tasks/today.md` is the daily source of truth.
- `DATA_DIR/data/task_log.csv` is the local completed-task ledger.

## Planning Quality Bar

Daily planning should maximize useful action, not maximize assignment count. The plan should help the user know what to do first, how to do it well, and what can safely be skipped.

Before writing or rewriting `DATA_DIR/tasks/today.md`, review the candidate plan through three PM lenses:
- Execution PM: Is the plan finishable today? Is the `P1` task small enough to complete, with a clear done state, a cutoff rule, and lower-priority tasks that can be skipped without breaking the day?
- Interview / product-sense PM: If interview or case practice is present, does the task force a reusable structure: problem framing, success metric, guardrail, assumptions, recommendation, pushback handling, and a short scorecard?
- Data / platform PM: If the day touches data-owner growth, does at least one task turn practice into a reusable artifact, such as a data model, data contract, metric tree, evaluation checklist, or failure-check template?

Planning rules from those lenses:
- Use one `P1` anchor that produces a concrete artifact or scored practice rep, not just generic practice.
- Use one or two `P2` support tasks that deepen the anchor or advance an active project.
- Use `P3` tasks for diversified optionality: writing, website, design exploration, career assets, or lightweight skill practice.
- Avoid over-assigning after recent no-completion days; keep the total planned load realistic and make the first 60-90 minutes sufficient for a successful day.
- When focus is `Default`, randomly choose one built-in discipline, document that chosen discipline in the plan, and use it to bias one support task without collapsing the whole day into one lane.
- When a task combines practice and artifact creation, define the minimum acceptable output and stop before expanding into a broad study session.
- When a high-priority task has remained unresolved for multiple runs, treat that as evidence the task is too broad. Rewrite it into a smaller next action, such as one checklist, one scorecard, one first draft, one reviewable slice, or one 30-60 minute artifact.

## Workflow

### 1. Run Goal Preflight
- Inspect `DATA_DIR/goals/goal.md` for the required goal sections.
- If the goal file is incomplete, ask for the missing goal details and update `DATA_DIR/goals/goal.md` first.
- If the goal file is complete and no selected normal/focus mode was provided, stop and ask the daily-start questions with the preferred interactive prompt method before reading the remaining planning files or editing any workflow state.
- If the goal file is complete and the selected normal/focus mode was provided by the user, launcher, or autonomous runner, use that supplied mode and continue.

### 2. Ground In Current State
- Read the files in source-precedence order.
- Check whether `DATA_DIR/tasks/today.md` is already for the current date before planning anything else.
- Read `DATA_DIR/context/daily-report.md` only if recent execution context matters.

### 3. Handle Rollover Only When Needed
- If `DATA_DIR/tasks/today.md` belongs to a prior date, append its final state to `DATA_DIR/tasks/archive/log.md`.
- Preserve the final checkbox states in full, then condense the carry-forward, heads-up, and feedback evidence into short planning notes.
- If an archive entry is written, refresh `DATA_DIR/context/planner-memory.md` with compact reusable signals.
- If an archive entry is written, update `DATA_DIR/context/daily-outcomes.md` with the completed tasks, specific feedback/constraints, and one planning takeaway from that archived day.
- If an archive entry is written, append the completed tasks from that archived day into `DATA_DIR/data/task_log.csv`.
- If `DATA_DIR/tasks/today.md` is already current, do not archive or rewrite history.

Reference shapes:
- [today-template.md](references/today-template.md)
- [archive-template.md](references/archive-template.md)

### 4. Build Or Verify Today’s Plan
- Produce 5 tasks by default unless the user explicitly asks for fewer.
- Keep one all-day task list in `DATA_DIR/tasks/today.md`; do not split by time of day.
- Mark every task with `P1`, `P2`, or `P3`.
- Add compact `| type:... | goal:... | sub:...` metadata to every task line.
- For any task carried forward from a prior run, archive entry, or backlog item, add `| backlog:Nd` after the core metadata, where `N` is the number of calendar days the task has remained available and unresolved.
- Omit `backlog` for genuinely fresh tasks. If the earliest unresolved appearance is ambiguous, use the latest reliable prior run and explain the uncertainty in `Carry-forward`.
- Keep one task per project, interview lane, or concrete outcome.
- Preserve one consolidated task for urgent deadlines or unresolved `P1` work that still matters.
- Make the `P1` task the day's success condition and include a concrete artifact, scorecard, or completed rep.
- Keep support tasks connected to the anchor when useful, but preserve diversified optional `P3` work so the day is not one-note.
- Use `P3` tasks for optionality instead of duplicating the same lane.
- If the weekly focus is stale or placeholder-like, flag that as a risk without auto-rewriting it.
- If the backlog is empty, derive tasks from goals, projects, carry-forward signals, and daily-practice expectations.
- If `DATA_DIR/tasks/today.md` is already current and already satisfies the workflow, prefer verify-only over a cosmetic rewrite.

### 5. Respond
- Keep the user-facing response concise and operational.
- Report what changed and what was verified.
- Do not mention skipped Google or research steps unless the user asks.

## Done Checklist
- Goal preflight was completed before planning.
- The daily-start questions were asked using the preferred interactive prompt method when available, or explicit mode/focus input from the user, launcher, or autonomous runner was documented.
- If required goal context was missing, `DATA_DIR/goals/goal.md` was updated before `DATA_DIR/tasks/today.md`.
- `DATA_DIR/tasks/today.md` is current for today, or explicitly verified as already current.
- The final task list passed the three-lens planning quality review: finishable execution, useful guidance, and at least one reusable artifact or scored rep.
- Prior-day archive was appended only if rollover was actually needed.
- `DATA_DIR/context/planner-memory.md` was refreshed only if archive state changed.
- `DATA_DIR/context/daily-outcomes.md` was updated only if archive state changed.
- `DATA_DIR/data/task_log.csv` was updated only if rollover created a new archive day.
- No Google Drive, Google Docs, Google Sheets, external mirror, research-note, or reading-list work was performed by default.
- Any stale weekly focus, empty backlog, or unresolved `P1` risk was surfaced in the plan or final response.
- Any carried-forward task from prior runs has a visible `backlog:Nd` metadata indicator.
- Any repeated high-priority backlog task was narrowed into an actionable next step rather than repeated as a broad block.

## Edge Cases / No-op
- If `DATA_DIR/tasks/today.md` already matches today and the rest of the local outputs are current, treat the run as verify-only and avoid a needless rewrite.
- If `DATA_DIR/tasks/today.md` is current and no rollover happened, do not append duplicate rows into `DATA_DIR/data/task_log.csv`.
- If the weekly focus is stale, call that out but continue using goals, projects, planner memory, and current deadlines.
- If backlog is empty, do not invent backlog items; derive tasks from the active planning sources.
- If the user explicitly asks for research, treat that as a separate local task and do not make it part of the default daily flow.

## References
- [example-run.md](references/example-run.md)
