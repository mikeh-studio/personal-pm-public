# Evaluating the planning skill

The release gate is a complete headless file loop from a fresh template workspace:
goal setup → weekly focus → daily plan → completion/feedback → rollover → next plan.
`tests/test_skill_workflow.py` runs this with Python site packages disabled and
isolated synthetic data. It never invokes an agent, browser, or external service.

The regression cases check missing goals, custom vocabulary, canceled versus
incomplete tasks, paused/closed projects, freshness and carry-forward review signals, reported versus unknown outcomes,
recent confirmed scope reduction, duplicate-free history, and rejected malformed weekly JSON.

Use real agent forward-testing when changing coaching guidance. Give the agent
only the skill, a synthetic data root, and one of these requests. Keep generated
artifacts in an isolated temporary workspace; do not use private planner data.

| Scenario | Request | Evidence to inspect |
| --- | --- | --- |
| Fresh setup | “Help me set up a language-learning plan. I have 60 minutes this week.” | Missing questions are relevant; no invented goals or commitments; no UI dependency. |
| Weekly review | “Review the week, then plan next week around two busy evenings.” | Recorded outcomes support the lesson; cancellations are separate; next week uses the constraint. |
| Return after a gap | “Run normal planning today.” with a month-old plan and stale weekly priorities | One brief relevance/capacity exchange; no automatic old P1; no forced weekly setup. |
| Unknown outcomes | “I did not keep the planner updated.” with unchecked historical tasks | No inference of failure or inactivity; reporting coverage is explicit. |
| Reported blockers | “Both days were blocked by missing input.” with explicit blocked outcomes | Blocker and relevance considered; smaller scope without diagnosing inability. |
| Work already done | “Plan the rest of today.” after evidenced work on a project marked Closed | Acknowledge progress, resolve status conflict, ask remaining capacity; do not assign completed work again. |
| No capacity answer | “Normal planning; that old interview is no longer active.” | Retire that lane prospectively; one small proposed P1, no invented time commitment. |
| Partial closeout | “First task done, second blocked; I don't remember the rest.” | Exact reports persisted; remaining tasks unknown; no silent cancellation. |
| Scope creep | “I finished the first task; the second needed too much setup.” | Completion and feedback recorded without unrequested replanning. |
| Existing plan | “Run normal planning today.” with a current valid plan | Verify-only outcome preserves checkboxes and feedback. |

Review whether the P1 has a concrete done state, the total scope fits stated
capacity, priorities are tied to current goals, and explanations distinguish
evidence from assumptions. Record the prompt, artifacts, observed behavior, and
remaining uncertainty. A green format check or mocked model response does not
prove that an agent made good planning decisions.

The optional UI must read the resulting files through the same shared store.
API regression checks cover this contract; rendered UI checks are separate.

## Product evaluation

For a small set of real sessions, record these observations with the user's feedback;
do not infer acceptance, starting work, or completion from silence:

| Signal | Record |
| --- | --- |
| P1 relevance | Accepted, revised, rejected, or unknown; reason if supplied. |
| Correction burden | Number of substantive priority/context corrections before the plan was useful. |
| Planning effort | Time from request to a usable plan, when timestamps are available. |
| Help starting | User-reported started, did not start, or unknown; elapsed time only if known. |
| Outcome evidence | Completed, blocked/incomplete, dropped, and unknown counts; reporting coverage alongside any completion rate. |

Keep observations in the local data root. Do not add required forms or automatic
telemetry to ordinary planning. Compare the observed correction burden and relevance
across sessions before claiming that planning quality improved.
