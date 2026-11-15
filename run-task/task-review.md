# Task review (Phase 4, full tier)

Reviews one internal task's diff with four lenses in a fixed order: correctness and spec, stack standards, deletion,
architecture. The security review, challenge and the revert check run beside it.

Write the diff package first: `tasks/<ID>/review/T<N>.diff` = `git -C <repo> diff HEAD` plus
`git diff --no-index /dev/null <file>` for each new untracked file, one block per touched repo. One Agent call, strong
model, effort high, fresh context (or the project's own `reviewer` agent). Inputs: that file, the task brief and
`ac.md`; not the plan's reasoning, not the implementer's report, not the chat. Prompt verbatim (fill the slots from the
profile):

```text
You review one finished task of a change. You did not write it and you do not fix it. Workspace <WORKSPACE>, repos <REPOS with stacks>.

Inputs:
- Diff: tasks/<ID>/review/T<N>.diff, the whole change of this task.
- Task brief: <BRIEF>, what this task must do, its tests and its scope.
- Intent: tasks/<ID>/ac.md, the task description and acceptance criteria verbatim. "Decisions at intake" and "Decisions at the gate" override the task text where they disagree.

Read the diff, the files it touches and their direct callers and callees. Nothing else in the repositories. Do not modify any files.

Work through four lenses in this order. Finish one lens and write down its findings before you start the next.

1. Correctness and spec. A wrong result for a realistic input, a crash, state or race problems (concurrent requests, several instances, background jobs and users at the same time), access (who reaches this code and whether they should), an item of the brief or an AC this task owns that is not met, a guarantee the old code gave that the diff removes (a side effect, a guard, an access check, an assertion). Then walk the trap checklist: <profile "Trap checklist" path and section>. <ONLY WHEN the security review reported "not covered: perf, cache": Also check growth with data (queries in loops, unbounded lists, missing indexes or pagination) and caching (keys, invalidation, per-user data in shared caches) against the production topology.>
2. Stack standards. Apply <profile review_checklists for the touched stacks> to the changed lines. The target style is <profile "Stack idioms">, not the legacy style of the code around the diff.
3. Deletion. Code, abstraction, config, dependency or test that this task does not need. Each finding names what replaces it: nothing, a framework or platform feature, code the codebase already has, or a shorter form.
4. Architecture. Run this lens when the task adds a class, service, endpoint, table, hook or component, or changes a boundary. For any other task write "skipped: <reason>". Check dependency direction, reuse of what the codebase already has, and production topology: <profile "Topology">.

A finding has a file:line and its "what" quotes the line of code from that place. A finding without both is dropped. Severity: blocker = wrong behaviour, data loss, a security or access hole, an AC not met; major = breaks for a realistic input or under production topology; minor = worth fixing in this task; nit = style only. Report each problem once, under the first lens that catches it.

Return only JSON:
{"findings":[{"id":"R1","lens":"correctness|standards|deletion|architecture","severity":"blocker|major|minor|nit","file":"path:line","what":"one sentence","why":"one sentence","fix":"one sentence"}],"checked":{"correctness":"one line","standards":"one line","deletion":"one line","architecture":"one line or skipped: reason"}}
```

Save the JSON to `tasks/<ID>/review/T<N>.json`. Rule on every finding and write the ruling to the ledger:
- accepted: joins the task's fix round with the security, challenge and revert results, one brief to the implementer;
- rejected: the finding goes to the verifier as a claim, worded as the reviewer wrote it. REFUTED = the rejection
  stands. CONFIRMED = the finding is accepted. UNVERIFIABLE = disputed, it goes to the user in the final summary;
- nit: joins a fix round that runs for other findings; a nit alone starts no round.

After the fix round the verifier gets one claim per accepted finding ("R2 fixed at file:line"). Panel: gate `review`,
`fail` while a finding is accepted and unfixed. Light tier: the session applies the same four lenses inline,
`detail:"inline: N findings"`. Docs tier: `skip`.
