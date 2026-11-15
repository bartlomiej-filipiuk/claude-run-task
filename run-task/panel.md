# Progress panel (optional)

When a `task_progress` tool is listed, also as a deferred tool (load its schema first), report the moments below, one call each, no prose.
When it is not available, skip every call silently; the ledger and the task files carry the same information.

- Phase change: `{kind:"phase", phase:"intake"|"analysis"|"gate"|"plan"|"loop"|"final"|"wrapup"}`.
- Internal task: `{kind:"task", task:"T2", status:"start"|"review"|"fix"|"done", round?}`.
- Gates that are not a plain exit code, also when skipped or not covered:
  `{kind:"gate", task:"T2"|null, gate:"<name>", result:"pass"|"fail"|"skip"|"baseline", detail:"<counts or reason>"}`.
  Names: `scope`, `approach`, `review`, `revert`, `secperf`, `challenge`, `verifier`, `intent`, `visual`, `smoke`,
  `qa-walk`, `change-map`. Per task always report `review`, `revert`, `secperf`, `challenge`, `verifier`. A
  `not covered` gate is `result:"skip"` with `detail:"not covered: <what>"`.
- The verdict: `{kind:"note", text:"verdict: GO with conditions (2)"}`.
- Every manual step for the user (a decision, a click on an environment, a post or a merge):
  `{kind:"needs_me", id:"<ID>-<slug>", text:"<what to do, what they should see>", key:"<ID>", ref:"<file or URL>"}`,
  and `{kind:"needs_me", id, done:true}` once done or no longer needed.
- A change outside scope (a pre-existing fix, environment drift, a follow-up):
  `{kind:"ruling", scope:"pre-existing"|"env"|"follow-up", files:[...], text:"..."}`.

`needs_me` reaches the user's dashboard from the transcript, also when the panel shows no card for this task; the
other kinds show only while a card is open, and a call nothing shows costs nothing.
