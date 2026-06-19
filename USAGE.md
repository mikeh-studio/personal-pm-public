# Personal PM Usage Guide

Use this guide when you want to run the planner, verify a workspace, or understand what the `personal-pm` skill should do.

For the product overview and screenshots, start with [README.md](README.md).

## Operating Model

Personal PM is a daily planning loop:

```text
goal context -> current state -> daily plan -> feedback -> archive memory
```

Project work follows the same lightweight operating loop:

```text
goal -> project -> artifact -> daily task -> evidence -> review
```

Use `goals/projects.md` as the source of truth. Keep each project tagged as `Now`, `Next`, or `Later`; set its status to `Active`, `Idea`, `Paused`, or `Closed`; and keep the `Next Action` small enough to become a single daily task. The Project tab can add, edit, delete, and close these rows, then joins in current daily tasks and recent-docs evidence when those local caches are available.

Paused projects are intentionally out of the daily flow unless explicitly selected, and closed projects are portfolio history. The daily planner should derive project-work tasks only from projects whose status is neither `Paused` nor `Closed`, and it should not carry forward unresolved tasks from paused or closed projects unless they are reframed under an active goal or eligible project.

The planner reads Markdown and CSV files from one data root. In this repo, the default data root is `private/`. You can point the same code at another workspace with `PERSONAL_PM_DATA_DIR`.

Expected data root:

```text
goals/goal.md
goals/projects.md
context/weekly-focus.md
context/planner-memory.md
context/daily-outcomes.md
context/planning-insights.md
context/weekly-outcomes.md
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
6. Refresh `context/planning-insights.md` and `context/weekly-outcomes.md` from the archive when rollover happened.
7. Write or verify `tasks/today.md` using the adaptive task/time cap.
8. Run validation.
9. Report what changed and what was verified.

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

## Run The Morning Launcher

Use the morning launcher when you want the least manual daily entrypoint:

```bash
scripts/pm_morning.sh
```

It checks whether `tasks/today.md` is current and whether the latest autonomous run failed today. If the plan needs work, it runs `private/automation/scripts/autonomous_daily_runner.sh`, then starts or reuses the local app and opens the Today view. If the current plan is already ready, it skips the planner and opens the app directly.

The launcher prefers `python3.11` when available because this project requires Python 3.10+. Set `PERSONAL_PM_PYTHON_BIN` if you want a specific interpreter.

Preview without changing planner files, starting Flask, or opening a browser:

```bash
PERSONAL_PM_DRY_RUN=1 scripts/pm_morning.sh
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

## Adaptive Outcome Memory

The planner learns from archived outcomes through:

- `context/planning-insights.md`: latest archived day, zero-completion streak, learned task-type patterns, and the next active-task or planned-minute cap.
- `context/weekly-outcomes.md`: compact weekly summaries that keep long-term history readable.

Regenerate them from the archive:

```bash
PERSONAL_PM_DATA_DIR=private \
  python3 public/skill/personal-pm/scripts/outcome_memory.py
```

Outcome rules:

- Completed tasks are checked tasks under `Final Tasks`.
- Deleted/canceled tasks must use `status:deleted`, `status:canceled`, `status:cancelled`, or the `Deleted / Canceled Tasks` archive section.
- Plain unchecked tasks are incomplete/carry-forward, not deleted or canceled.
- If the latest archived day completed no active tasks, the next plan should reduce either active task count or total planned minutes before adding more lanes.

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

The app has four main views:

- `Today`: morning run status, task list, carry-forward, heads-up, and feedback fields.
- `Projects`: editable project portfolio, next actions, recent-doc evidence, and the daily-pull candidate.
- `Analytics`: completion trends from archive and ledger data.
- `Docs`: optional recent-docs cache from `context/recent-drive-docs.json`.

If port `5151` is busy, rerun the command with another local port.

## Guided Weekly Setup

The app helps you set a weekly focus on first launch. When the Today view loads and there is no weekly focus for the current week (or `goals/goal.md` has no overall goals), it shows a short guided setup that drafts the weekly focus with an agent CLI.

How it works:

1. Pick a runner — Codex, Claude Code, or Gemini CLI (the same runners as "Run Today's Flow"; Codex is the default).
2. The app asks that CLI for 3-5 questions tailored to your goals and active projects.
3. You answer them once.
4. The app asks the CLI to synthesize a weekly focus (and overall goals only when none exist), then writes it to `context/weekly-focus.md` (and `goals/goal.md` when needed).
5. You land on the Today view; edit the result anytime on the Weekly tab.

The CLI receives your current goal/project/week context and your answers. It is run read-only and asked to return JSON only, so it never edits files directly; the server validates the JSON before writing.

Configuration:

- Requires the chosen runner's CLI on your `PATH`, or set `PERSONAL_PM_CODEX_BIN`, `PERSONAL_PM_CLAUDE_BIN`, or `PERSONAL_PM_GEMINI_BIN`.
- `PERSONAL_PM_ONBOARDING_MODEL` selects a specific model for this step (applied as the runner's model flag).
- Skip it for the session, or choose "set it up manually" to use the Weekly tab form instead.

Endpoints (both `POST`, JSON body, default `provider` is `codex`):

```text
/api/onboarding/questions   { "provider": "codex|claude|gemini", "need_goals": false }
/api/onboarding/generate    { "provider": "...", "need_goals": false, "answers": [ { "label": "...", "answer": "..." } ] }
```

`questions` returns `{ ok, provider, questions: [...] }`. `generate` validates and persists, then returns `{ ok, provider, weekly, goals }`. An unsupported provider returns `400`; a CLI/parse/timeout failure returns `502` with a readable `error`.

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

## Token Usage Logging

Codex-backed flow runs log model-call token usage under the active data root:

```text
data/agent_token_usage.jsonl
```

Each JSONL row includes:

- `run_id`: shared id for the flow run.
- `step`: flow surface that produced the call, such as `personal_pm_runner` or `browser_run_today`.
- `model`: model name from the Codex event stream when available, or from a configured hint.
- `sequence`: model-call order within that step.
- `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, and `total_tokens`.
- `cumulative_*` fields from Codex when available.

Autonomous records in `data/agent_runs.jsonl` include the same `run_id`, `token_usage_log_path`, and a summed `token_usage` object with model names when usage rows were captured. Shell-launched Codex runs also keep the raw structured event stream in `data/codex_events/<run_id>.jsonl`.

Overrides:

```bash
PERSONAL_PM_RUN_ID=my-run-id
PERSONAL_PM_MODEL_HINT=gpt-5.5
PERSONAL_PM_CODEX_MODEL_HINT=gpt-5.5
PERSONAL_PM_TOKEN_USAGE_LOG=/path/to/agent_token_usage.jsonl
PERSONAL_PM_CODEX_EVENT_LOG=/path/to/raw-codex-events.jsonl
```

Providers that do not expose structured token counts continue to run, but their token usage is reported as unavailable instead of estimated.

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
  --lookback-days 3 \
  --activity-timezone Asia/Taipei
```

The app's `Docs` tab reads only `context/recent-drive-docs.json` from the active data root.

When `context/recent-drive-docs.json` has a fresh approved scan with a doc tied to a planner goal, the daily planning flow should include one task that references one selected doc and turns it into a concrete artifact. The planner still stays local-only; it reads the local cache and does not call Google during daily planning.

Low-cost daily ingest should use metadata-first triage, local dedupe, and local summary reuse before reading any Google Doc body. The private ingest runner maintains:

- `private/data/google_docs_ingest_keys.json`: `doc_id_or_url|activity_date` keys already written.
- `private/data/google_docs_summary_cache.json`: compact summaries keyed by `doc_id_or_url|activity_date|modified_at`.

These files must not contain raw document bodies.

## GitHub Issues And Projects Sync

The GitHub sync is explicit and opt-in. It is not part of the normal daily planning flow.

Use it when you want a private GitHub issue repo and private GitHub Project v2 to mirror durable Personal PM work while keeping local Markdown authoritative.

For the implementation checklist and completion criteria, see [docs/github-sync.md](docs/github-sync.md).

Security defaults:

- Uses `gh` authentication only; no GitHub token is read from or written to repo files.
- Refuses to sync to a public issue repo.
- Refuses to sync to a public Project v2.
- Writes sync IDs and GitHub item IDs to `DATA_DIR/data/github_sync_map.json`; keep that file private.
- Does not sync archives, feedback sections, token logs, Google cache files, or raw external-source content.

One-time GitHub setup:

1. Create or choose a private GitHub repo for the Personal PM issues.
2. Create a private GitHub Project v2 for the board.
3. Add these optional Project fields if you want field sync: `PM Status`, `Project Priority`, `Day Priority`, `Goal`, `Sub`, `Type`, `Planned Date`, `Timebox`, `Local Source`, and `Sync ID`.
4. Authenticate the GitHub CLI:

```bash
gh auth login --web
gh auth refresh -s repo -s project
```

Optional private config:

```bash
mkdir -p private/config
cp templates/config/github_sync.example.json private/config/github_sync.json
```

Then edit `private/config/github_sync.json` with your private issue repo and optional Project v2 target. Command-line flags override this file for supported private-target settings.

You can also create the private config from flags:

```bash
python3 scripts/github_sync.py \
  --data-dir private \
  --repo OWNER/PRIVATE_REPO \
  --project-owner OWNER \
  --project-number 1 \
  --init-config
```

Preview the local records without calling GitHub:

```bash
python3 scripts/github_sync.py --data-dir private --json
```

Check `gh` auth, target privacy, and optional Project field coverage before writing:

```bash
python3 scripts/github_sync.py \
  --data-dir private \
  --repo OWNER/PRIVATE_REPO \
  --project-owner OWNER \
  --project-number 1 \
  --preflight
```

Apply issue-only sync:

```bash
python3 scripts/github_sync.py \
  --data-dir private \
  --repo OWNER/PRIVATE_REPO \
  --apply
```

Apply issue plus Project v2 sync:

```bash
python3 scripts/github_sync.py \
  --data-dir private \
  --repo OWNER/PRIVATE_REPO \
  --project-owner OWNER \
  --project-number 1 \
  --apply
```

Use `--project-owner-type org` when the project belongs to an organization.

By default, the sync creates issues for all rows in `goals/projects.md` and durable daily tasks from `tasks/today.md`: `P1`, `type:project_work`, `backlog:Nd`, or tasks explicitly marked with `sync:github`. Use `--tasks all` only when you intentionally want every visible daily checkbox to become an issue.

## Validation Commands

Workspace validation:

```bash
python3 scripts/validate_workspace.py --read-only
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
python3 -m unittest discover -s tests
```

Validate today's plan:

```bash
python3 public/skill/personal-pm/scripts/validate_today.py --json
```

By default, `--task-count` is the maximum valid count and `--min-task-count` defaults to `1`, so adaptive three-task plans can pass after no-completion days. Use `--min-task-count 5 --task-count 5` only when you intentionally want an exact five-task check.

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
| Weekly setup says a runner "CLI not found" | Install that runner or set its bin var (`PERSONAL_PM_CODEX_BIN` / `PERSONAL_PM_CLAUDE_BIN` / `PERSONAL_PM_GEMINI_BIN`), or pick a different runner in the setup dialog. |
| Weekly setup "did not return usable JSON" | Retry, switch runners, or choose "set it up manually" to use the Weekly tab form. |
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
