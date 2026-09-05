# Conversational setup

Establish enough context for a useful plan, entirely in the current conversation.
Do not start the UI or call another agent to interview the user.

1. Read `pm.py status`. For a fresh repository workspace, run `./setup.sh` from
   the checkout with `PERSONAL_PM_DATA_DIR` set. It copies missing starter files
   without replacing existing content. For a separately copied skill, create the
   same goal/project/context/task files under the explicit data root as needed.
2. Ask for missing long-term outcomes, near-term deadlines, relevant disciplines,
   and practice expectations. Use the user's existing answers. Record an explicit
   absence of deadlines in plain language; do not invent dates or priorities.
3. Write the supplied context into these `goals/goal.md` sections, preserving other
   sections: `Overall Goals`, `Current Near-Term Deadlines`, `Key Disciplines`, and
   `Suggested Daily Practice`. Goals/deadlines/practice use `*` bullets; disciplines
   use a `Discipline Area | Why It Matters` Markdown table.
4. Read or establish `goals/projects.md` with columns `Project | Priority | Status |
   Discipline | Next Action | Notes`. Priorities are `Now`, `Next`, `Later`; statuses
   are `Active`, `Idea`, `Paused`, `Closed`. An empty project table is valid; do not
   invent a project just to fill it.
5. Set meaningful goal and subcategory identifiers in `config/planner.json` when
   the default vocabulary does not fit. See [metadata.md](metadata.md). Never
   reassign historical task identifiers to fit a new vocabulary.
6. Run `pm.py status` again and resolve `goal_errors` before daily planning.
   Missing weekly focus or a first daily plan is expected during setup.
7. If the user requested initial planning, continue with [weekly.md](weekly.md),
   then [daily-planning.md](daily-planning.md). Otherwise report setup readiness.

For any helper example above, `pm.py` means
`python3 "$SKILL_DIR/scripts/pm.py" --data-dir "$DATA_DIR"`.
