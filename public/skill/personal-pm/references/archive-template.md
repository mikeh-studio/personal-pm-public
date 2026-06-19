# Archive Template

Append prior-day history to `DATA_DIR/tasks/archive/log.md` in this shape:

```md
## YYYY-MM-DD

### Final Tasks
- [x] ...
- [ ] ...

### Deleted / Canceled Tasks
- [ ] ... | status:canceled
- [ ] ... | status:deleted

### Planning Notes
- Completed:
- Deleted / canceled:
- Incomplete / carry-forward:
- Completion rate:
- Carry-forward:
- Constraint / feedback:
- Planning signal:
```

Rules:
- Preserve the final checkbox state exactly.
- Treat unchecked tasks under `Final Tasks` as incomplete, not canceled.
- Use `status:canceled`, `status:cancelled`, `status:deleted`, or the `Deleted / Canceled Tasks` section only when a task was intentionally removed from the plan or marked skipped-but-not-carry in the UI.
- Keep completed tasks separate from deleted/canceled tasks in planning notes and generated memory.
- Condense repeated carry-forward, heads-up, and feedback text into short planning notes instead of copying every section verbatim.
- Preserve user feedback and constraints when they materially affect the next plan.
- Add compact planning signals only when the evidence is visible in the archived day.
