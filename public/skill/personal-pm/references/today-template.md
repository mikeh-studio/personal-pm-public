# Today Template

Use this shape for `DATA_DIR/tasks/today.md`:

```md
# Today's Plan

## YYYY-MM-DD — Daily Plan

### Tasks
- [ ] [P1] [duration] Task — [project/discipline] | type:... | goal:... | sub:...
- [ ] [P2] [duration] Task — [project/discipline] | type:... | goal:... | sub:...
- [ ] [P3] [duration] Carried-forward task — [project/discipline] | type:... | goal:... | sub:... | backlog:Nd
- [ ] [P3] [duration] Task — [project/discipline] | type:... | goal:... | sub:...
- [ ] [P3] [duration] Task — [project/discipline] | type:... | goal:... | sub:...

### Carry-forward
- ...

### Heads-up
- ...

### Feedback For Tomorrow
- What worked:
- What did not work:
- New goal or constraint:
```

Rules:
- Write 5 tasks by default unless the user explicitly asks for fewer.
- Keep one task per project, interview lane, or concrete outcome.
- Use only eligible, non-paused, non-closed projects for project-work tasks. Do not create or carry forward daily tasks from projects whose `Status` is `Paused` or `Closed` unless the user explicitly selected that paused project.
- Use the lower `P3` slots for optionality instead of repeating the same lane.
- Keep metadata controlled and compact: `type`, `goal`, and `sub` should use stable enum-style values.
- For a task derived from a fresh recent-doc summary, mention the document title in the task text and add optional `doc:<id-or-url>` metadata after the required `type`, `goal`, and `sub` fields.
- Add `backlog:Nd` only when a task is carried forward from a prior run, archive entry, or backlog item. `N` is the number of calendar days it has remained available and unresolved.
- If a high-priority carried task has missed multiple runs, rewrite it as a smaller concrete next step before carrying it into the new plan.
- Allowed `type` values: `interview_prep`, `project_work`, `skill_practice`, `career`, `writing`, `design_exploration`
- Allowed `goal` values: `data_owner`, `experience_design`
- Allowed `sub` values: `decision_science`, `data_foundation`, `evaluation_discipline`, `service_platform_eng`, `website`, `writing`, `physical_ai`, `career_assets`
