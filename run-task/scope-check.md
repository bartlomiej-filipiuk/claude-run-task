# Scope check (Phase 0, always)

Runs on every task before any analysis agent, also when a prior analysis exists and with `--analysis-only`. It finds
every place where what we would build can drift from what the task's authors (client, PM, reporter) mean, and closes
the ones that matter with the user before any plan is made.

Write `tasks/<ID>/scope-brief.md` first: the scout's file anchors, the prior analysis paths when one exists, and the
repos with their stacks from the profile. Then one Agent call, strong model, effort high, fresh context; it gets
files, never the chat. Prompt verbatim (fill `<ID>`, `<WORKSPACE>`):

```text
You check a task BEFORE anyone plans it. Your job is to find every point where the delivered change could differ from what the task's authors mean, and to separate the points that need a human decision from the ones the code or the task text already answers. You do not design the solution.

Read: <WORKSPACE>/tasks/<ID>/source.md (the task with its comments), tasks/<ID>/ac.md, the attachments in tasks/<ID>/, and the anchors, prior analysis and repos listed in tasks/<ID>/scope-brief.md. Read the code the anchors name, and more if a point needs it. Do not modify any files.

Walk every lens. For each, look for a concrete point in THIS task; skip a lens with no point.
1. Words with two readings: which pages, screens, endpoints, content types, records, users; "all", "every", "like X".
2. Missing AC: behaviour the description, comments or attachments imply that no AC states; an AC no single observable step could prove. When no AC is stated, derive them and mark each as derived.
3. Conflicts: description vs AC vs comments vs attachments vs parent item vs prior estimate. A later comment that widens or narrows scope, and who wrote it (client, PM, developer). Requests marked "nice to have", "maybe", "to be confirmed".
4. Who and where: anonymous vs signed-in users, roles and permissions, admin vs end user, languages and locales, which parts of the product, which environments.
5. Data and states: empty or missing data, many items, legacy and existing records, what happens to what exists today, migration.
6. Code reality: an AC the code already meets, an AC that contradicts the current data model, architecture or a recorded decision (ADR), an AC that depends on data the system does not have. Give file:line.
7. Non-functional, only where the task touches it: caching, performance, SEO, accessibility, tracking and analytics, security, emails, notifications, forms.
8. Boundaries and dependencies: what is out of scope, follow-ups, content or config someone else must deliver, third parties, other tasks, a manual step on an environment.
9. Done: for each AC, what the requester will look at to say "this works", and whether that matches the AC text.

Classify every point:
- "blocking": the answer changes what is built, an AC, the scope or the proof of an AC, and neither the task text nor the code answers it. Write the question as one decision in plain words a non-developer can answer, 2-3 options, the option you recommend and why, and what goes wrong if we guess wrong.
- "answered": the task text or the code answers it; give the evidence (quote or file:line).
- "assumption": low impact and a safe default exists; state the default.
Prefer "answered" over asking: never ask the user what the code can tell. Never mark a point blocking only to be safe; never hide a blocking point as an assumption.

Return only JSON:
{"understanding": {"goal": "one sentence", "ac": [{"id": "AC1", "text": "...", "source": "task | derived from <where>", "done_looks_like": "what the requester sees"}], "out_of_scope": ["..."]},
 "points": [{"id": "S1", "lens": 1, "what": "...", "evidence": ["quote or file:line"], "class": "blocking | answered | assumption", "question": "blocking only", "options": ["..."], "recommended": "option + why", "if_wrong": "...", "answer_or_default": "answered/assumption only"}]}
```

Save the JSON as `tasks/<ID>/scope-check.json`. Open the file:line of every `answered` point the plan will rest on; a
wrong one becomes `blocking`. Panel: gate `scope`, `fail` while blocking points are open, detail
`"9 points: 3 blocking, 5 answered, 1 assumption"`.

## Asking the user

Blocking points exist: one message in the chat language, then stop. No analysis agent starts before the answers.
1. **How I understand the task**: the goal in one sentence, the numbered AC (derived ones marked as derived), out of
   scope, and the task id when it was generated from plain text.
2. **Questions I must close before the plan**: every blocking point, ordered by `if_wrong`, each as the question,
   the options, and "I recommend: ..." with the reason in one line.
3. **Assumptions**: every assumption in one line, so the user can overrule one.
4. **Profile**, only when it was bootstrapped in this run: the block `profile.md` "Bootstrap" step 3 describes.
5. **Size**: the proposed size (`SKILL.md`, Phase 0) and one line why; the user can change it.
6. Last line: how to answer, e.g. "S1 b, S2 a", or "recommendations" to accept every recommended option and every
   derived AC. That reply records them as "default accepted" with no follow-up.
Panel: `needs_me` `<ID>-scope`, "answer N scope questions", ref `tasks/<ID>/scope-check.json`.

The user asked for speed or "no questions" (`source.md`, `## Instructions to the session`): the message keeps the
goal, the questions, the derived AC, the size and the answer line, drops the rest, and says in one line that the
questions stay because they change what gets built.

A reply that leaves some questions or derived AC unconfirmed ("ok", "go") gets one follow-up naming them: "I take the
recommendations for S2 and S4 and the derived AC3?". Any reply to that follow-up that does not reject or change an
item accepts the named items. A question the user says needs the client or PM stays open: offer a tracker comment
draft with the questions (posted only on approval) and continue only with what the open answer cannot change, or stop.

No blocking points and no derived AC: post the blocks with "no blocking questions" and go on to Phase 1 without
waiting. Derived AC always wait for the user, because nothing is built on an AC nobody asked for.

After the answers append to `tasks/<ID>/ac.md`:

```markdown
## Decisions at intake
- S1 <question in a few words>: <answer> (user | default accepted | client, <date>)
- AC3 (derived): <text> (confirmed by user)
- Assumed: <assumption> (S5)
- Out of scope: <item>
- Deferred: S2 <question in a few words> (to <who>; condition of the verdict)
```

What, never how: no files, steps or design. Every `--intent` reader judges the branch against this section, so a
question answered here is not asked again later.
