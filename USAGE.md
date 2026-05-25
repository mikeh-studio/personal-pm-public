# Personal PM Usage Guide

Use this guide when you want to run the planner, verify a workspace, or understand what the `personal-pm` skill should do.

For the product overview and screenshots, start with [README.md](README.md).

## Operating Model

Personal PM is a daily planning loop:

```text
goal context -> current state -> daily plan -> feedback -> archive memory
```

The planner reads Markdown and CSV files from one data root. In this repo, the default data root is `private/`. You can point the same code at another workspace with `PERSONAL_PM_DATA_DIR`.

Expected data root:

```text
goals/goal.md
goals/projects.md
context/weekly-focus.md
context/planner-memory.md
context/daily-outcomes.md
tasks/today.md
tasks/backlog.md
tasks/archive/log.md
data/task_log.csv
```

## First-Time Setup

1. Install app dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Bootstrap the private workspace if it does not exist yet:

```bash
./setup.sh
```

The script copies missing files from `templates/` and leaves existing files unchanged.

3. Open `private/goals/goal.md`.
4. Fill in meaningful content for:
   - `Overall Goals`
   - `Current Near-Term Deadlines`
   - `Key Disciplines`
   - `Suggested Daily Practice`
5. Open `private/goals/projects.md`.
6. Add active projects, their status, and the next action for each.
7. Run validation:

```bash
python3 scripts/validate_workspace.py --read-only
```

If goal context is missing, the daily runner should ask for it before writing a daily plan.

## Run The Planner From Codex

From this repo, ask Codex:

```text
Run the PM flow.
```

Or be explicit:

```text
Run normal planning for today.
Run the PM flow focused on Decision science.
```

Expected Codex flow:

1. Read `AGENTS.md` and `public/skill/personal-pm/SKILL.md`.
2. Check `goals/goal.md` before reading the rest of the planning state.
3. Ask whether to run normal planning or a specific focus unless your prompt already supplies that choice.
4. Read the active data root in source-precedence order.
5. Archive stale `tasks/today.md` only when rollover is needed.
6. Write or verify `tasks/today.md`.
7. Run validation.
8. Report what changed and what was verified.

## Run The Local Wrapper

The wrapper handles goal preflight, focus selection, and Codex invocation:

```bash
private/automation/scripts/personal_pm_runner.sh
```

Use a focus override when you want an unattended or one-command run:

```bash
PERSONAL_PM_FOCUS_OVERRIDE="Data foundation" \
  private/automation/scripts/personal_pm_runner.sh
```

Preview the prompt without changing files:

```bash
PERSONAL_PM_DRY_RUN=1 private/automation/scripts/personal_pm_runner.sh
```

Preview with a focus:

```bash
PERSONAL_PM_DRY_RUN=1 PERSONAL_PM_FOCUS_OVERRIDE="Decision science" \
  private/automation/scripts/personal_pm_runner.sh
```

## Focus Choices

Built-in focus values:

- `Default`: randomly pick one built-in discipline and bias one support task.
- `Judgement`: use normal prioritization with no forced discipline.
- `Data foundation`
- `Decision science`
- `Evaluation discipline`
- `Service / platform engineering`
- `Physical AI`
- `Experience Design`

Any other non-empty value is treated as a custom focus.

## Read The Daily Plan

`tasks/today.md` is the source of truth for the day.

A good plan should have:

- One `P1` success condition.
- One or two `P2` support tasks.
- Optional `P3` tasks that can be skipped safely.
- Compact metadata on every task: `type`, `goal`, and `sub`.
- A clear `Carry-forward` section.
- A `Heads-up` section for risks, deadlines, and cut rules.
- A `Feedback For Tomorrow` section.

Example task shape:

```md
- [ ] [P1] [50m] Complete one scored case rep and write a 3-gap scorecard — Decision science / Interview prep | type:interview_prep | goal:data_owner | sub:decision_science
```

## Carry-Forward And Backlog Age

Unfinished work should stay visible without letting broad tasks repeat forever.

When a task carries forward from a prior run, add `backlog:Nd` metadata:

```md
- [ ] [P2] [30m] Draft one reviewable agent-template section — Analytics agents | type:project_work | goal:data_owner | sub:service_platform_eng | backlog:4d
```

Rules:

- Use `backlog:Nd` only for unresolved work that stayed available from prior runs.
- Count calendar days from the earliest reliable unresolved appearance.
- If a `P1` or `P2` backlog task has missed multiple runs and is still broad, shrink it into a smaller next action.
- Keep the next action concrete: one checklist, one scorecard, one draft, one reviewable slice, or one 30-60 minute artifact.

## Run The App

Use private data:

```bash
PYTHONPATH=app \
  python3 -m flask --app server run --host 127.0.0.1 --port 5151
```

Use demo data:

```bash
PERSONAL_PM_DATA_DIR=demo PYTHONPATH=app \
  python3 -m flask --app server run --host 127.0.0.1 --port 5151
```

The app has three main views:

- `Today`: task list, carry-forward, heads-up, and feedback fields.
- `Analytics`: completion trends from archive and ledger data.
- `Docs`: optional recent-docs cache from `context/recent-drive-docs.json`.

If port `5151` is busy, rerun the command with another local port.

## Run The Demo

The `demo/` folder is synthetic and public-safe.

```bash
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
PERSONAL_PM_DATA_DIR=demo PYTHONPATH=app \
  python3 -m flask --app server run --host 127.0.0.1 --port 5151
```

The demo uses fixed example dates. Use workspace validation for the demo. Use `validate_today.py` when you intentionally want a current-date check.

## Initialize Another Data Root

Use `PERSONAL_PM_DATA_DIR` with `setup.sh` to bootstrap a separate private workspace:

```bash
PERSONAL_PM_DATA_DIR=/path/to/new-private-root ./setup.sh
PERSONAL_PM_DATA_DIR=/path/to/new-private-root \
  python3 scripts/validate_workspace.py --read-only
```

## Autonomous Runs

The autonomous wrapper is intended for cron or unattended local runs:

```bash
private/automation/scripts/autonomous_daily_runner.sh
```

It should:

- Run the same goal preflight.
- Stop if required goal context is missing.
- Validate `private/tasks/today.md` after Codex runs.
- Write run records to `private/data/agent_runs.jsonl`.
- Keep the normal workflow local-only.

Force an autonomous run when a same-day run record already exists:

```bash
PERSONAL_PM_FORCE_RUN=1 private/automation/scripts/autonomous_daily_runner.sh
```

## External Context

External context is opt-in only.

Normal planning does not call Google Drive, Google Docs, Google Sheets, email, or browser-derived sources. When you explicitly want outside signals, summarize them into private local files first.

Recommended flow:

```text
external source -> private/context/external-priority-signals.md -> daily planner
```

Rules:

- Store compact evidence, not raw email bodies or long document excerpts.
- Keep external scan output under `private/`.
- Treat external signals as evidence, not authority over local goals.

Recent-docs cache:

```bash
PERSONAL_PM_DATA_DIR=private \
  python3 scripts/build_recent_drive_docs_cache.py \
  --input /path/to/recent-drive-docs.json \
  --lookback-days 3
```

The app's `Docs` tab reads only `context/recent-drive-docs.json` from the active data root.

## Validation Commands

Workspace validation:

```bash
python3 scripts/validate_workspace.py --read-only
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
```

Validate today's plan:

```bash
python3 public/skill/personal-pm/scripts/validate_today.py --json
```

Validate a fixed-date or demo plan:

```bash
PERSONAL_PM_TODAY_DATE=YYYY-MM-DD \
  python3 public/skill/personal-pm/scripts/validate_today.py --json

PERSONAL_PM_DATA_DIR=demo \
  python3 public/skill/personal-pm/scripts/validate_today.py --skip-date-check --json
```

Shell syntax:

```bash
zsh -n private/automation/scripts/personal_pm_runner.sh
zsh -n private/automation/scripts/autonomous_daily_runner.sh
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Goal template incomplete` | Fill missing sections in `goals/goal.md`, or let the runner collect the missing context. |
| `Codex CLI not found` | Set `PERSONAL_PM_CODEX_BIN` to the Codex executable path. |
| `Plan date is ... expected ...` | Run the planner to roll stale `tasks/today.md` forward. |
| `Autonomous run skipped` | Use `PERSONAL_PM_FORCE_RUN=1` only when you intentionally want another same-day run. |
| Demo date looks stale | Use `scripts/validate_workspace.py --read-only`; demo dates are fixed examples. |

## Safe Update Workflow

When changing process, app behavior, validators, or skill instructions:

1. Test against `demo/`.
2. Run read-only validation against `private/`.
3. Run the private planner in dry-run mode.
4. Only then allow writes against real private planning state.

Example:

```bash
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
python3 scripts/validate_workspace.py --read-only
PERSONAL_PM_DRY_RUN=1 private/automation/scripts/personal_pm_runner.sh
```
