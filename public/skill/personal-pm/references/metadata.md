# Workspace vocabulary

Every daily task carries `type`, `goal`, and `sub`. Define stable snake_case goal
and subcategory identifiers in `DATA_DIR/config/planner.json`:

```json
{
  "goals": ["learn_language", "healthy_routine"],
  "sub_categories": ["speaking", "reading", "exercise"]
}
```

The optional keys replace the corresponding default list. Omitted keys retain the
existing defaults. `pm.py status` reports the effective vocabulary. The format
rejects unknown keys, empty lists, duplicate identifiers, and malformed identifiers.

Without this file, goals remain `data_owner` and `experience_design`; subcategories
remain `decision_science`, `data_foundation`, `evaluation_discipline`,
`service_platform_eng`, `website`, `writing`, `physical_ai`, and `career_assets`.

Task types remain `interview_prep`, `project_work`, `skill_practice`, `career`,
`writing`, and `design_exploration`. Use the goal file's discipline names for human
guidance. Goal identifiers should correspond to the user's recorded outcomes.

Add `project:Exact project name` for project-linked tasks. Carry-forward tasks use
`backlog:Nd`, based on their earliest reliable unresolved appearance. Optional
`status:canceled` or `status:deleted` preserves intentional removals.
Unchecked tasks have unknown outcomes unless `outcome:incomplete` or
`outcome:blocked` records an explicit report. `outcome:unknown` can make that
uncertainty explicit. Completion is represented by the checkbox. See
[feedback.md](feedback.md) for closeout commands.

New plan validation uses the current vocabulary. Ledger ingestion preserves
explicit custom identifiers from historical tasks, even after configuration changes;
legacy metadata-free tasks retain the original inference rules.
