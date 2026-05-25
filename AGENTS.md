# AGENTS.md

This is the public-safe root instruction file for coding agents working in this repository.

The shareable skill package lives at [public/skill/personal-pm/SKILL.md](public/skill/personal-pm/SKILL.md). Use that file as the canonical public workflow contract for planner behavior, task formats, archive handling, and local ledger helpers.

Keep real goals, tasks, archives, logs, external-source caches, local scheduler settings, app settings, and machine-specific instructions out of version control. The `private/` directory is a local-only data root and is ignored by git.

Reusable app, script, validator, and interface code should resolve planner data through `PERSONAL_PM_DATA_DIR` when it is set, defaulting to `private/` for this local workspace. Use `demo/` for public-safe examples and `templates/` for blank starter data.

If you are working in a maintainer's private checkout with local-only agent instructions, read those before changing private planner behavior or automation. Those files are not part of the public repository contract.
