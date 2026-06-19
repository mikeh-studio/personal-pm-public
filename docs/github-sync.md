# GitHub Issues And Projects Sync

This is the implementation plan and operator checklist for mirroring Personal PM projects and durable tasks into private GitHub Issues and an optional private GitHub Project v2.

The local Markdown workspace remains authoritative. GitHub is a visibility and execution layer, not the source of truth.

## Scope

Sync source:

- `goals/projects.md` project rows
- durable `tasks/today.md` tasks

Not synced:

- archive history
- feedback sections
- token usage logs
- Google Docs caches
- raw external-source content
- private automation settings

## Privacy Model

The sync is private by default:

- Uses `gh` authentication only.
- Does not store GitHub tokens in repo files.
- Refuses public issue repos.
- Refuses public Project v2 boards.
- Stores real target config in `DATA_DIR/config/github_sync.json`.
- Stores sync IDs and GitHub object IDs in `DATA_DIR/data/github_sync_map.json`.
- Rejects unknown config keys and token-like config keys.
- Requires custom sync-map paths to stay under the active data root.
- Keeps real config and sync-map files out of git through `.gitignore`.

## GitHub Setup

Create or choose:

1. A private GitHub repo with Issues enabled.
2. Optional private GitHub Project v2 board.

Recommended Project v2 fields:

- `PM Status`
- `Project Priority`
- `Day Priority`
- `Goal`
- `Sub`
- `Type`
- `Planned Date`
- `Timebox`
- `Local Source`
- `Sync ID`

Project field sync is best-effort. Missing fields are reported by preflight and skipped during apply.

## Local Setup

Authenticate with GitHub CLI:

```bash
gh auth login --web
```

For Project v2 mutation support, refresh project scope:

```bash
gh auth refresh -s project
```

Create private sync config from flags:

```bash
python3 scripts/github_sync.py \
  --data-dir private \
  --repo OWNER/PRIVATE_REPO \
  --project-owner OWNER \
  --project-owner-type user \
  --project-number 1 \
  --tasks durable \
  --projects all \
  --init-config
```

For issue-only sync, omit the Project flags.

## Run Order

Preview local export without GitHub writes:

```bash
python3 scripts/github_sync.py --data-dir private --json
```

Preflight GitHub auth and target privacy:

```bash
python3 scripts/github_sync.py --data-dir private --preflight
```

Apply issue-only sync:

```bash
python3 scripts/github_sync.py --data-dir private --apply
```

Apply Issues plus Project v2 sync:

```bash
python3 scripts/github_sync.py --data-dir private --apply
```

When `config/github_sync.json` is present, the apply commands read the private repo and optional Project v2 target from that file.

Supported config keys are `repo`, `project_owner`, `project_owner_type`, `project_number`, `tasks`, `projects`, and `map_path`.

## Task Policy

Default task policy is `durable`.

Durable tasks include:

- `P1` tasks
- `type:project_work`
- tasks with `backlog:Nd`
- tasks explicitly marked `sync:github`

Tasks can opt out with `sync:false`.

Use `--tasks all` only when every visible daily checkbox should become a GitHub issue.

## Validation

Run the local gate before publishing changes to the public repo:

```bash
python3 -m ruff check .
python3 -m unittest discover -s tests
python3 -m compileall app public/skill/personal-pm/scripts scripts tests
python3 scripts/validate_workspace.py --data-dir demo --read-only
python3 scripts/validate_workspace.py --data-dir templates --read-only --template
python3 scripts/validate_workspace.py --read-only
PYTHONPATH=app python3 -m flask --app server routes
```

`validate_workspace.py` rejects token-like keys in `config/github_sync.json`. Keep all authentication in `gh`.

## Completion Criteria

The integration is complete for a private workspace when:

- `gh auth status` succeeds in the environment running the sync.
- `DATA_DIR/config/github_sync.json` points to a private issue repo.
- Optional Project v2 target is private, or Project sync is omitted.
- `python3 scripts/github_sync.py --data-dir DATA_DIR --preflight` passes.
- `python3 scripts/github_sync.py --data-dir DATA_DIR --apply` creates or updates the expected issues.
- `DATA_DIR/data/github_sync_map.json` exists only under the private data root.
- No real task, goal, repo target, token, or sync-map data is committed.
