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

Use Python 3.10+; no third-party packages are needed for the skill.

1. Bootstrap the private workspace if it does not exist yet:

```bash
./setup.sh
```

The script copies missing files from `templates/` and leaves existing files unchanged.

2. Ask your agent “Set up Personal PM with me”, or open `private/goals/goal.md`.
3. Fill in meaningful content for:
   - `Overall Goals`
   - `Current Near-Term Deadlines`
   - `Key Disciplines`
   - `Suggested Daily Practice`
4. Open `private/goals/projects.md`.
5. Add active projects, their status, and the next action for each.
6. After the first plan is written, run validation:

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

Expected flow:

1. Read the skill and open/reuse the UI as a visual companion, then read local goals, current state, and relevant conversation context.
2. Check freshness and reconcile work already done, obsolete priorities, and old carry-forward candidates.
3. Bundle missing mode, current priority, and capacity into one brief exchange. With unknown capacity, propose one small P1.
4. Record explicitly reported prior outcomes and roll over only when needed.
5. Save a short validated plan, or verify today's existing plan if it still fits.

A long gap prompts a small context refresh, not mandatory weekly setup. Age alone
does not make a task urgent or prove it was too large. Weekly focus is not silently
rewritten during normal daily planning.

## Headless Helpers

The agent supplies planning decisions; helpers validate and write local artifacts
without Flask or a nested agent CLI. Run from the checkout and set the data root:

```bash
export PERSONAL_PM_DATA_DIR="$(pwd)/private"
PM_HELPER=public/skill/personal-pm/scripts/pm.py
python3 "$PM_HELPER" status
```

`status` is read-only and reports missing goal context, current plan, project
eligibility, vocabulary, context freshness, outcome reporting coverage, and adaptive scope. During initial setup it is normal to
have missing weekly or daily artifacts. Once goals are complete, save the agent's
weekly JSON and daily Markdown drafts:

```bash
python3 "$PM_HELPER" save-weekly --week-of YYYY-MM-DD --file /path/to/weekly.json
python3 "$PM_HELPER" save-plan --file /path/to/today-draft.md
python3 "$PM_HELPER" complete --task-index 0 --date YYYY-MM-DD
python3 "$PM_HELPER" report --task-index 1 --outcome blocked --date YYYY-MM-DD
python3 "$PM_HELPER" feedback --field did_not_work --text 'The first step was too broad.' --date YYYY-MM-DD
python3 "$PM_HELPER" rollover --date YYYY-MM-DD
```

Use a Monday for `--week-of`, the inspected plan date for completion/feedback, and
the new planning date for rollover. Completion uses a zero-based index and is
idempotent. Repeated rollover does not duplicate archive or ledger entries; it
refreshes derived memory. It leaves the old daily file in place until a validated
new plan is saved. Conflicting history is reported without overwriting it.

`save-plan` checks goal context, task shape, configured metadata, known project
eligibility, and adaptive limits after recent, fully reported days with no completions. Add `--focus` only for
an explicitly selected paused project. Existing same-day plans and weekly focus
require `--replace` for an explicit revision; retain completion states and feedback.
Weekly JSON uses `{ "weekly": { "why": "...", "priorities": ["..."], "notes": "..." } }`.

For custom goals, copy `templates/config/planner.example.json` to
`DATA_DIR/config/planner.json` and edit the identifiers. See
[metadata](public/skill/personal-pm/references/metadata.md). Configuration is local;
historical ledger identifiers are preserved.

## Run The Local Wrapper

These optional scripts exist only in maintainer workspaces. They are not shipped
in a public clone; use the skill directly for the public workflow.

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

This optional launcher requires the maintainer-only autonomous runner and UI dependencies.

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
- Review old or repeatedly appearing work for relevance: keep, redefine, or leave it out. Narrow broad work after confirming it still matters.
- Keep the next action concrete: one checklist, one scorecard, one draft, one reviewable slice, or one 30-60 minute artifact.

## Adaptive Outcome Memory

The planner learns from archived outcomes through:

- `context/planning-insights.md`: reported and unknown outcomes, reporting coverage, observed task patterns, and applicable scope guidance.
- `context/weekly-outcomes.md`: compact weekly summaries that keep long-term history readable.

Regenerate them from the archive:

```bash
PERSONAL_PM_DATA_DIR=private \
  python3 public/skill/personal-pm/scripts/outcome_memory.py
```

Outcome rules:

- Completed tasks are checked tasks under `Final Tasks`.
- Deleted/canceled tasks must use `status:deleted`, `status:canceled`, `status:cancelled`, or the `Deleted / Canceled Tasks` archive section.
- Plain unchecked tasks remain open in history; their actual outcome is unknown.
- `report --outcome incomplete` or `blocked` records a confirmed unfinished outcome. `unknown` explicitly records uncertainty; `dropped` records intentional cancellation. Partial answers leave other outcomes unknown.
- Unknown outcomes do not trigger failure-based caps or enter learned outcome comparisons. Fully reported days with no completions can reduce scope only when recent (within seven days).
- Completion counts describe recorded work. Check reporting coverage before interpreting rates; reporting may be selective.

The [feedback reference](public/skill/personal-pm/references/feedback.md) defines the
closeout contract. Existing archives remain unchanged; regenerate derived memory
to apply the new interpretation of unreported outcomes.

## Run The App

To open the visual companion without running a planner or requiring private adapters:

```bash
./scripts/pm_morning.sh --ui-only
```

Add `--no-open` when the host will open the printed URL with its own browser tools.
The launcher verifies the server's data root before reuse and skips occupied ports.


The UI opens by default for interactive skill planning and review when available.
The skill owns planning; opening the UI does not start another planning run.
Headless requests and unattended runs skip automatic opening. Install its dependencies first:

```bash
python3 -m pip install -r requirements-ui.txt
```

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

The app has five main views:

- `Today`: task rows beside feedback for tomorrow, with expandable planning context and run status. Feedback saves when you leave a field; archived plans are read-only.
- `Projects`: project rows with next actions, expandable details, and editing.
- `Weekly`: the latest focus, outcome progress, and expandable previous weeks.
- `Analytics`: completion trends from archive and ledger data.
- `Setting`: [API connections](public/skill/personal-pm/references/api-connections.md) and optional recent documents.

If port `5151` is busy, rerun the command with another local port.

## Guided Weekly Setup

The app provides an optional interface to the [shared weekly planning contract](public/skill/personal-pm/references/weekly-planning.md). The skill can perform this workflow directly in conversation. The app helps you manage goals and set a weekly focus on first launch. When the Today view loads and there is no weekly focus for the current week, no overall goals, or required goal context is missing, it shows a two-stage guided setup.

How it works:

1. Review, add, edit, or remove overall goals. Fill any missing deadlines, relevant disciplines, and daily practice preferences; an explicit "No fixed deadlines" is valid. The server validates these fields together before saving to `goals/goal.md` and preserves existing context and other sections.
2. The app frames the decision as "What do you want to work on this week?" and provides guidance to choose 2-4 outcomes, account for commitments and capacity, name blockers and trade-offs, and define what done looks like.
3. Pick a local CLI or a configured API from the same provider menu as "Run Today's Flow". Codex is the default.
4. The app asks that provider for 6-8 questions grounded in the saved goals and active projects. Every question includes answer guidance and a concrete example.
5. Answer at least four questions.
6. The app asks the provider to synthesize only the weekly focus, then writes it to `context/weekly-focus.md`. The assistant does not rewrite goals.
7. You land on the Today view; edit the result anytime on the Weekly tab.

The selected provider receives your current goal/project/week context and your answers. API calls use the saved model and server-side credential; CLI calls use the installed runner. The CLI runs read-only, while APIs receive no tools. Both return JSON for validation before writing.

Configuration:

- Requires the chosen runner's CLI on your `PATH`, or set `PERSONAL_PM_CODEX_BIN`, `PERSONAL_PM_CLAUDE_BIN`, or `PERSONAL_PM_GEMINI_BIN`.
- `PERSONAL_PM_ONBOARDING_MODEL` selects a specific model for this step (applied as the runner's model flag).
- Skip it for the session, or choose "set it up manually" to use the Weekly tab form instead.

Endpoints (`POST`, JSON body, default `provider` is `codex`; APIs use `api:openai`, `api:xai`, `api:openrouter`, or `api:sakana`):

The browser bootstraps `/api/session`, then sends its session cookie and `X-PM-CSRF` token on mutations. Cookie names are scoped to the workspace and server address, allowing multiple local workspaces in the same browser. `/api/health` is the read-only launcher probe.

```text
/api/onboarding/goals       { "goals": ["...", "..."], "context": { "deadlines": "...", "disciplines": "...", "daily_practice": "..." } }
/api/onboarding/questions   { "provider": "codex|claude|gemini" }
/api/onboarding/generate    { "provider": "...", "answers": [ { "label": "...", "answer": "..." } ] }
```

`goals` returns `{ ok, goals }`, including `goals.setup_fields` for missing context. The UI submits only missing context fields; saved sections are preserved. Legacy goal-only requests may omit `context`, but daily planning still requires complete goal context. `questions` returns `{ ok, provider, questions: [...] }`. `generate` requires four non-empty answers, validates and persists the focus, then returns `{ ok, provider, weekly, goals }`. Weekly endpoints return `409` until at least one goal has been saved. An unsupported provider returns `400`; a CLI/parse/timeout failure returns `502` with a readable `error`.

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

The app's `Setting → Documents` section reads only `context/recent-drive-docs.json` from the active data root.

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

By default, `--task-count` is the maximum valid count and `--min-task-count` defaults to `1`, so short plans can pass when capacity or reported outcomes warrant them. Use `--min-task-count 5 --task-count 5` only when you intentionally want an exact five-task check.

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
