# Daily planning

Use [SKILL.md](../SKILL.md) for paths and shared boundaries. Planning should help
the user choose useful work and start with little effort.

## Ground the decision

Read `pm.py status`, then the necessary local sources:

1. Current conversation: explicit corrections, chosen focus, available time, and work already evidenced.
2. `goals/goal.md` and `goals/projects.md`.
3. `context/weekly-focus.md`, `tasks/today.md`, and `tasks/backlog.md`.
4. Generated `context/planning-insights.md` and `context/weekly-outcomes.md`.
5. Archive, daily outcomes, planner memory, and completed-task ledger when needed to resolve history.

Current explicit user information overrides stale files. Reconcile discrepancies
before choosing work. A project marked Closed alongside current session work is a
status question, not permission to reopen it or ignore the work. Acknowledge
completed session work; do not assign it again, infer remaining capacity, or add it
to the completion ledger without a clear task match and reported/evidenced completion.

`goal_errors` checks structure only. Collect missing required goal sections before
saving a plan; do not invent goals. A structurally complete file may still contain
obsolete deadlines or priorities. Persist explicit corrections in the relevant
source file, preserving unrelated content and history.

`planning_context` reports recording gaps, stale weekly focus, and old carry-forward
candidates. A gap of at least 7 days or weekly focus at least 14 days old prompts a
brief refresh of assumptions that affect today's choice. Missing weekly focus does
not force weekly setup. These dates describe records, not activity outside the planner.

Before reusing a task that is at least two weeks old, or has repeatedly appeared
without a confirmed outcome, resolve whether it is still worth doing: keep,
redefine, or leave it out. Age alone establishes neither priority nor a sizing
failure. Leaving work out of today's plan does not cancel its historical record.

## Ask only what changes the plan

Reuse answers already supplied by the user or launcher. Bundle missing mode,
priority, capacity, and consequential stale assumptions into one short exchange.
Use the host's question tool when appropriate, otherwise plain chat.

- No selected mode: ask normal planning or a specific focus alongside time available.
- After a long gap: acknowledge known progress and ask what is worth moving now,
  plus available time. Mention only stale assumptions that affect that decision.
- If a specific focus is chosen, use that discipline or custom focus. `Judgement`
  means no forced discipline; `Default` randomly chooses one goal discipline.
- If capacity remains unknown, propose one small P1, usually 15–25 minutes. State
  that its duration is an estimate. Additional ideas stay unscheduled and optional;
  do not turn silence into a 55- or 90-minute commitment.
- If priority relevance remains unresolved, propose a candidate for confirmation;
  do not silently promote old backlog. An unattended run should surface missing
  context and leave a valid existing plan intact when it cannot choose grounded work.

The user can confirm a current priority without refreshing the entire weekly plan.
No weekly rewrite, research, or external sync is added to a daily request.

## Choose useful, finishable work

- Make one P1 the success condition: action, finish condition, and estimated time.
  Already completed work may mean there is no need for another task today.
- Add support tasks only when they have current value and fit stated remaining
  capacity. Five is an upper limit, not a target. Diversification is optional.
- Keep one task per project, interview lane, or concrete outcome. Prefer reusable
  artifacts or scored practice when they serve the user's goal; do not force them
  into unrelated work.
- Only eligible projects may generate tasks. Paused projects require explicit
  selection; Closed projects require an explicit status correction before new work.
- For carry-forward, establish relevance first, then narrow work if actual blockers
  or task scope warrant it. Use `backlog:Nd` for calendar age from the earliest
  reliable unresolved appearance; do not describe this as missed workdays.
- Unknown outcomes do not establish failure or justify automatic scope penalties.
  Prefer explicit reports about time, blockers, relevance, and what helped.
- The helper applies reduced scope after recent, fully reported days with no
  completions. Review blockers without diagnosing why completion was difficult.
  Do not use stale generated advice that labels missing records as failure.
- If external context is requested, use fresh approved local handoffs only, after
  local priorities. A doc-based task must be useful now and yield a concrete result.
  Do not call external services or read research/reading lists by default.

## Persist and verify

If an old plan needs closeout, record only outcomes the user actually supplies;
see [feedback.md](feedback.md). No answer means unknown. Then run:

```sh
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" rollover --date YYYY-MM-DD
```

Rollover preserves final task lines and checkboxes, separates cancellations,
archives once, and refreshes the completed ledger and derived memory. It does not
invent intervening days. Retry repairs derived outputs; conflicting archived state
requires reconciliation before any new save. Do not overwrite a future plan.

Draft UTF-8 Markdown using [today-template.md](today-template.md), then run:

```sh
python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR" save-plan --file /path/to/draft.md
```

The helper validates structure, vocabulary, date, one P1, project eligibility, and
applicable scope limits. `--focus "Project name"` allows an explicitly selected
paused project. `--replace` is for a requested same-day revision; preserve completed
work, canceled status, and feedback. Never infer that format validation proves relevance.

When today's plan is current and fits the user's current priorities, verify it
instead of rewriting. A changed deadline or explicit correction is substantive;
a current date alone does not establish relevance. Use `validate_today.py` for
read-only format checks. If a deadline requires exceeding a helper scope cap,
explain the trade-off and use the user's chosen scope in an explicit manual revision.

## Keep the result short

Present the P1 and its done signal first. Add optional work only if useful, and at
most a couple of notes about consequential assumptions or carry-forward choices.
Leave archive counts, validation mechanics, and writer coordination out of the
visible plan. Keep a necessary detailed rationale in a Markdown comment in the
plan; it is supporting evidence, not a competing task list.

Closeout should be light: completed, blocked, incomplete, dropped, or status
unknown. Ask for one useful reason only when it changes the next planning decision.
