# Private/Public Split Report

Date: 2026-05-20

## Decision Rule

- `private/` contains personal context, local operating state, local app adapters, machine-specific automation, and historical artifacts.
- `public/` contains the reusable skill package: instructions, templates, validators, and ledger helpers that can be shared without personal planning content.
- `demo/` contains synthetic public-safe data for demos and compatibility tests.
- `templates/` contains blank starter data files; `setup.sh` stamps date placeholders when bootstrapping a new data root.
- Reusable code resolves planner data through `PERSONAL_PM_DATA_DIR`, defaulting to `private/` in this local workspace.
- Root keeps only discovery and repository-maintenance shims so agents can still find the right contract quickly.

## Inventory

| Element | Destination | Rationale |
| --- | --- | --- |
| `AGENTS.md` | Root shim | Agent discovery entrypoint; points to private contract and public skill. |
| `CLAUDE.md` | Root shim | Claude discovery entrypoint; points to private Claude notes. |
| `README.md` | Root product entry point | Explains purpose, screenshots, quick start, skill usage, repo map, and safety boundaries without exposing private content. |
| `.gitignore` | Root shim | Repo-maintenance rule file for ignored local artifacts. |
| `app/` | Root reusable interface | Reads from `PERSONAL_PM_DATA_DIR`; default target is `private/`, demo target is `demo/`. |
| `demo/` | Public-safe demo data | Synthetic data-owner/chips/robotics/Japanese workspace for public demos and tests. |
| `templates/` | Public-safe starter data | Blank placeholders for new private data roots; avoids fixed stale dates. |
| `scripts/validate_workspace.py` | Root reusable validator | Read-only compatibility check for any data root. |
| `goals/` | `private/goals/` | Long-term goals, active projects, and reading list are personal context. |
| `context/` | `private/context/` | Weekly focus, planner memory, outcomes, reports, retros, and proposals are personal context. |
| `tasks/` | `private/tasks/` | Today, backlog, and archive are the private operating ledger. |
| `research/` | `private/research/` | Research notes are tied to personal goals and interview/project context. |
| external priority scans | `private/context/external-priority-signals.md` | External Google/email signals are private evidence and should not be copied into the public skill. |
| external source config | `private/config/priority_sources.example.yml` | Example-only config for opt-in Google Doc, Sheet, or email sources. |
| `_system/data/` | `private/data/` | Run logs and task ledger are local/private state. |
| `_system/agent/` | `private/agent/` | Canonical repo instructions describe private source-of-truth files and local autonomy boundaries. |
| `_system/scripts/personal_pm_runner.sh` | `private/automation/scripts/` | Local launcher depends on local Codex install, macOS dialogs, and private repo paths. |
| `_system/scripts/autonomous_daily_runner.sh` | `private/automation/scripts/` | Local unattended wrapper writes private logs and invokes the private workspace. |
| `_system/cron/` | `private/automation/cron/` | Scheduler setup includes machine/user paths and local run windows. |
| `_system/launchd/` | `private/automation/launchd/` | Legacy macOS LaunchAgent setup includes machine/user paths. |
| `.claude/` | `private/claude/` | Local Claude command adapters and settings are private app-specific workspace setup. |
| `.obsidian/` | `private/obsidian/` | Obsidian settings are local workspace configuration. |
| `Untitled.base` | `private/Untitled.base` | Local workspace artifact with no public skill purpose. |
| `_system/history/` | `private/history/` | Historical workflow comparisons and older skill versions are private development context. |
| `_system/test-runs/` | `private/test-runs/` | Throwaway local validation artifacts should not be public package content. |
| `_system/skills/personal-pm/SKILL.md` | `public/skill/personal-pm/SKILL.md` | Shareable skill contract for the planning workflow. |
| `_system/skills/personal-pm/references/` | `public/skill/personal-pm/references/` | Shareable templates and example run shapes. |
| `_system/scripts/validate_today.py` | `public/skill/personal-pm/scripts/validate_today.py` | Reusable validation helper with configurable file input. |
| `_system/scripts/task_ledger.py` | `public/skill/personal-pm/scripts/task_ledger.py` | Reusable archive-to-ledger helper with configurable paths. |

## Updates Made

- Moved private planning docs, local context, archives, logs, and local automation under `private/`.
- Moved reusable skill instructions, references, and helper scripts under `public/skill/personal-pm/`.
- Updated root shims, README, usage guide, private agent instructions, public skill docs, runner scripts, validator defaults, ledger defaults, cron docs, launchd docs, and Claude command adapters to use the new paths.
- Updated ignores so local/private app settings, history, test runs, and machine-specific LaunchAgent config stay out of public packaging.

## Boundary Notes

- Do not copy `private/` into a public repo.
- The public package should remain free of personal goals, task archives, run logs, local scheduler config, and machine-specific settings.
- Public scripts keep default paths for this repo layout but still accept explicit path flags for reuse.
- `README.md` and `USAGE.md` may describe the private workflow, but should avoid copying real private goals, task text, archive entries, or run logs.

## Pre-Existing Absences

- `scripts/sync_today_to_google_doc.sh` and `skills/personal-pm/references/research-template.md` were already absent from the working tree before this split and were not restored.
- That matches the current local-only boundary: external sync and research-specific flows are not part of the default shareable skill package.
