# Personal PM

Personal PM is a local personal growth coach and lightweight PM system. It turns target goals into a daily task plan, keeps unfinished work visible, and uses completion history to make tomorrow's plan more realistic.

It is built for one practical loop:

```text
goals -> daily plan -> completion feedback -> better next plan
```

The system is local-first. Your real goals, tasks, archives, and logs live under `private/`. Reusable skill code, validators, templates, and demo data live outside `private/` so they can be shared safely.

## Product Promise

Personal PM helps you answer four daily questions:

1. What matters most today?
2. What is the smallest useful version of that work?
3. What can be skipped without breaking the day?
4. What pattern should tomorrow's plan learn from?

Good plans are not longer plans. A good plan has one clear `P1`, a few support tasks, optional lower-priority work, and a visible trail when something keeps slipping.

## Screenshots

These screenshots use the synthetic `demo/` dataset. They do not include private goals, archives, or task history.

### Daily Plan

![Demo daily plan](docs/screenshots/demo-today.png)

### 90-Day Analytics

![Demo analytics](docs/screenshots/demo-analytics.png)

### Recent Docs Cache

![Demo recent docs](docs/screenshots/demo-docs.png)

## How It Works

1. **Set target goals**
   Write long-term goals, near-term deadlines, skill lanes, and daily practice expectations in `goals/goal.md`.

2. **Track active projects**
   Keep project status and next actions in `goals/projects.md`.

3. **Run the PM skill**
   Ask the `personal-pm` skill to run normal planning or focus on one discipline.

4. **Get today's plan**
   The skill writes or verifies `tasks/today.md` with one `P1`, one or two `P2` tasks, and optional `P3` tasks.

5. **Use the plan**
   Complete tasks, leave feedback, and let unfinished work carry forward with visible `backlog:Nd` metadata.

6. **Review trends**
   Use the app's analytics view to see completion rate, discipline mix, and repeated misses.

## Quick Start

Run commands from the repo root.

Try the public-safe demo:

```bash
python3 -m pip install -r requirements.txt
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
PERSONAL_PM_DATA_DIR=demo PYTHONPATH=app \
  python3 -m flask --app server run --host 127.0.0.1 --port 5151
```

Use the default private workspace:

```bash
python3 -m pip install -r requirements.txt
./setup.sh
```

Then fill `private/goals/goal.md` and `private/goals/projects.md` with your target goals, active projects, deadlines, disciplines, and next actions.

Validate and start the app:

```bash
python3 scripts/validate_workspace.py --read-only
PYTHONPATH=app \
  python3 -m flask --app server run --host 127.0.0.1 --port 5151
```

Then open the local app URL printed by Flask.

If port `5151` is busy, choose another local port.

## Use The Skill

The skill contract lives at:

```text
public/skill/personal-pm/SKILL.md
```

In Codex, from this repo, use prompts like:

```text
Run the PM flow.
Run normal planning for today.
Run the PM flow focused on Data foundation.
```

Expected skill behavior:

1. Read `AGENTS.md` and `public/skill/personal-pm/SKILL.md`.
2. Resolve planner files through `PERSONAL_PM_DATA_DIR`, defaulting to `private/`.
3. Check whether `goals/goal.md` has enough goal context.
4. Ask for normal planning versus specific focus unless your prompt already provides it.
5. Roll forward stale daily state if needed.
6. Write or verify `tasks/today.md`.
7. Validate the result and report what changed.

To expose this repo's skill to a local Codex skills folder:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/public/skill/personal-pm" ~/.codex/skills/personal-pm
```

If the symlink already exists, inspect it before changing it.

## Daily Runner

The local runner wraps the skill with goal preflight, focus selection, and validation:

```bash
private/automation/scripts/personal_pm_runner.sh
```

Skip the focus prompt with an explicit focus:

```bash
PERSONAL_PM_FOCUS_OVERRIDE="Data foundation" \
  private/automation/scripts/personal_pm_runner.sh
```

Preview the prompt without changing files:

```bash
PERSONAL_PM_DRY_RUN=1 private/automation/scripts/personal_pm_runner.sh
```

## Repo Map

| Path | Role |
| --- | --- |
| `private/` | Local-only real goals, tasks, archives, logs, and automation. Ignored by git; do not publish. |
| `public/skill/personal-pm/` | Shareable skill instructions, references, validator, and ledger helper. |
| `demo/` | Synthetic public-safe data for screenshots, demos, and app testing. |
| `templates/` | Blank starter files for a new private data root. |
| `app/` | Local web interface that reads the active data root. |
| `scripts/` | Repo-level validators and cache builders. |
| `setup.sh` | Non-destructive bootstrap from `templates/` into `private/` or `PERSONAL_PM_DATA_DIR`. |
| `docs/screenshots/` | README screenshots generated from `demo/`. |
| `requirements.txt` | Python app dependencies for new users. |
| `pyproject.toml` | Project metadata plus Black and Ruff defaults. |
| `.github/workflows/validate.yml` | CI check that validates the public-safe demo workspace. |
| `LICENSE` | MIT License for public use and reuse. |

## Data Root Contract

Reusable code reads planner files from `PERSONAL_PM_DATA_DIR`.

When `PERSONAL_PM_DATA_DIR` is unset in this repo, app and script code use `private/`.

Expected data-root layout:

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

Optional docs cache:

```text
context/recent-drive-docs.json
```

## Documentation Map

- [USAGE.md](USAGE.md): day-to-day operating guide.
- [public/skill/personal-pm/SKILL.md](public/skill/personal-pm/SKILL.md): canonical skill behavior.
- [demo/README.md](demo/README.md): public-safe sample data notes.
- [templates/README.md](templates/README.md): starter workspace notes.

## Safety Rules

- Keep real personal goals, archives, logs, scheduler settings, and external-source cache data out of `public/`.
- Keep normal planning local-only. Google Drive, Docs, Sheets, email, and browser-derived context are opt-in.
- Test public process or interface changes against `demo/` before trusting them against `private/`.

## Useful Checks

```bash
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
python3 scripts/validate_workspace.py --read-only
python3 public/skill/personal-pm/scripts/validate_today.py --json
zsh -n private/automation/scripts/personal_pm_runner.sh
zsh -n private/automation/scripts/autonomous_daily_runner.sh
```
