# Approach check (Phase 1, conditional)

Runs after the decider, before the plan gate, when the size is large or the decider's plan:
- adds a module, service, plugin, entity, table, endpoint, package or a shared UI component used in several places;
- needs a manual step on a remote environment (a secret or variable, a file on shared storage, a one-off command, a
  reindex, a cache flush, an admin click on production).

Otherwise `skip` with the reason ("one-line fix", "copy change").

Write `tasks/<ID>/approach-brief.md` first: `ac.md`, the decider's `recommended_fix`, `architecture_ruling`,
`implementation_steps`, `internal_task_breakdown` and `rollout`, and the scout's file anchors. Not the decider's
reasoning, not the diggers' output, not the chat. One Agent call, strong model, effort high, fresh context. Prompt
verbatim (fill `<ID>`, `<WORKSPACE>`, `<REPOS>`, `<CONVENTIONS>`, `<TOPOLOGY>`, `<STACKS>`):

```text
You are an independent reviewer of a proposed solution, before any code is written. You did not design it. Your job is to find the strongest better alternative, or to say plainly that there is none. You do not review code quality.

Read the brief: <WORKSPACE>/tasks/<ID>/approach-brief.md (repos: <REPOS>, stacks: <STACKS>). Read the code it names. Project conventions: <CONVENTIONS>. Recorded decisions (ADRs), when the project has them: an alternative that reverses one needs a strong reason. Production topology: <TOPOLOGY>.

Walk these questions in order and stop digging on a question once it is answered:
1. Does it need code at all? Config, content, an admin setting or a change of process that meets the AC.
2. Does this codebase already have it? Grep the repos for an existing module, service, component, helper or pattern that does the job or most of it.
3. Platform and ready-made: the framework's built-ins, packages already in the lockfiles, well-maintained packages of the ecosystem (name, version, maintenance status).
4. Operational cost: manual steps per environment, secrets and variables, deploy hooks, reindexing, cache flushes, ordering between repos or services.
5. Maintenance risk: depending on another package's internals or UI texts, the next framework upgrade, how hard it is to roll back.
6. Scale: what grows (rows, records, requests, users) and when the proposal starts to hurt.

For each alternative you propose: what it is, evidence (file:line, package name and version, a link), what it saves, what it costs or risks, and which AC it would not meet, if any. At most 2 alternatives. An alternative without evidence is not an alternative.
Also list the proposal's weak points that are not alternatives (a hidden manual step, an upgrade risk), at most 3.
Do not modify any files.

Return only JSON:
{"verdict": "keep" | "switch" | "user decides", "alternatives": [{"option": "...", "evidence": ["..."], "saves": "...", "costs": "...", "misses_ac": "none | ..."}], "weak_points": ["..."], "questions_checked": {"1": "one line", "2": "...", "3": "...", "4": "...", "5": "...", "6": "..."}}
```

Rule on it (keep, switch, or put the choice to the user as an open question at the plan gate) and write the ruling to
the ledger. The plan gate always shows the agent's alternatives with the ruling, also on `keep`. Panel: gate
`approach`, detail e.g. `"keep, 1 alternative rejected"`.
