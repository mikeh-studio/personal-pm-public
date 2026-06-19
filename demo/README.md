# Demo Data

This folder is a synthetic Personal PM workspace for public demos, screenshots, validation, and interface testing. It is not based on a real person's goals, tasks, archive, or task ledger.

The demo includes:

- A current daily plan for 2026-05-25 with specific, artifact-oriented tasks.
- 90 archived days from 2026-02-24 through 2026-05-24.
- A matching completed-task ledger in `data/task_log.csv`.
- Daily outcome notes with realistic variability: strong days, partial days, no-completion days, and weekend shrinkage.
- Generated planning insights and weekly outcome rollups in `context/planning-insights.md` and `context/weekly-outcomes.md`.
- A synthetic recent Google Docs cache in `context/recent-drive-docs.json` for the app's `Docs` tab.

Use this data when you need to demonstrate the product without exposing private planning content.

## Validate

```bash
PERSONAL_PM_DATA_DIR=demo python3 scripts/validate_workspace.py --read-only
```

## Preview

```bash
PERSONAL_PM_DATA_DIR=demo PYTHONPATH=app \
  python3 -m flask --app server run --host 127.0.0.1 --port 5151
```

## Screenshot Source

README screenshots should be captured from this data root, not from `private/`.
