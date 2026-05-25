# Archive Template

Append prior-day history to `DATA_DIR/tasks/archive/log.md` in this shape:

```md
## YYYY-MM-DD

### Final Tasks
- [x] ...
- [ ] ...

### Planning Notes
- Completed:
- Carry-forward:
- Constraint / feedback:
- Planning signal:
```

Rules:
- Preserve the final checkbox state exactly.
- Condense repeated carry-forward, heads-up, and feedback text into short planning notes instead of copying every section verbatim.
- Preserve user feedback and constraints when they materially affect the next plan.
- Add compact planning signals only when the evidence is visible in the archived day.
