# Starter Templates

Copy these files into a private data root when creating a new workspace. Goal and project files intentionally use placeholders; replace them with your real outcomes and next actions before validating the workspace.

`setup.sh` replaces `{{YYYY-MM-DD}}` in `tasks/today.md` with the current local date when it bootstraps a new data root.

Use `templates/` when you want a blank workspace. Use `demo/` when you want public-safe example content.

## Setup Flow

1. Run `./setup.sh`, or copy the template files into a new private data root.
2. Fill `goals/goal.md` with real target goals, deadlines, disciplines, and daily practice expectations.
3. Fill `goals/projects.md` with active projects and next actions.
4. Run workspace validation.
5. Run the daily planner.

Expected data-root layout:

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

Optional local-only GitHub sync config:

```text
config/github_sync.example.json
```

Copy it to `config/github_sync.json` inside your private data root and edit the private GitHub issue repo or Project v2 target there. The real `github_sync.json` file should stay local-only.

Validation command from the repo root:

```bash
PERSONAL_PM_DATA_DIR=/path/to/new-private-root \
  python3 scripts/validate_workspace.py --read-only
```

Bootstrap command from the repo root:

```bash
PERSONAL_PM_DATA_DIR=/path/to/new-private-root ./setup.sh
```
