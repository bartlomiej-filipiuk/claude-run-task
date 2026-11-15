# Intent check (Phase 5, always)

Does the branch do what the task asked, all of it, and nothing else? Both ways: every AC and decision has code and a
proof; every change has a reason in the AC or a decision.

One Agent call, strong model, effort medium, fresh context. Input: `tasks/<ID>/ac.md` with its decision sections and
the branch diff, nothing else; not the plan, the ledger, the decider's output or the chat. Prompt verbatim (fill
`<ID>`, `<WORKSPACE>`, `<BASE>`, `<REPOS>`, `<ROLES_SOURCE>`):

```text
You check whether a finished branch matches the intent of its task. You did not write it. You do not review code quality, security or style; other reviewers do that.

Intent: <WORKSPACE>/tasks/<ID>/ac.md. The task description and acceptance criteria are verbatim; "Decisions at intake" and "Decisions at the gate" hold what the user decided (answers, chosen option, out of scope, changed AC). A decision overrides the task text where they disagree.
Code: the branch diff in each touched repo: git -C <repo> diff <BASE>...HEAD (repos: <REPOS>). Read the surrounding code where a hunk alone does not tell you what it does.

1. Split the intent into items: each acceptance criterion, each requirement stated in the description, each decision. Number them I1, I2, ... and quote each in at most one line.
2. For each item: where the branch implements it (file:line, one or two anchors), and what proves it: a test (file and test name) that would fail without the change, or "manual" when only a click-through can show it, or "none". Status: "covered" (code and proof), "unproven" (code, no proof), "missing" (no code), "out of scope" (a decision moved it out; no code expected).
   When an item names an actor ("editors", "admins", "customers"), list the roles that actor covers (<ROLES_SOURCE>). The item is "covered" only when the access the change uses lets each of those roles do it and the proof exercises the restricted ones too; otherwise "unproven", naming the roles left out.
3. Group the diff by purpose (one row per group, not per hunk). For each group name the item(s) it serves. Supporting changes serve the item they enable: tests, types, exported config, migrations, docs, lockfiles that follow a dependency change, fixtures. Mark a group "unexplained" only when no item needs it, and say in one line what it does instead (refactor on the side, an unrelated fix, a feature nobody asked for, a decision ignored).
4. Flag a group that contradicts an item or a decision as "conflict", with the item.

Do not modify any files. Return only JSON:
{"items": [{"id": "I1", "text": "...", "source": "ac|description|intake|gate", "status": "covered|unproven|missing|out of scope", "where": ["path:line"], "proof": "test file::name | manual | none"}], "groups": [{"files": ["path"], "what": "one line", "serves": ["I1"], "status": "explained|unexplained|conflict", "note": "one line, only for unexplained or conflict"}]}
```

`<ROLES_SOURCE>`: where the project defines roles (from the profile or the scout), or "not applicable".

Render to `tasks/<ID>/intent-check.md`: one table for items (`id | intent | status | where | proof`), one for groups
that are `unexplained` or `conflict` (explained groups as a count). Rule on every row that is not covered or
explained: fix in the fix wave, a ruling ("pre-existing bug fixed on the way, kept, listed in the PR notes"), or a
question for the user at the result gate. After the fix wave the verifier re-checks only the fixed rows. The table
opens `summary.md`. Panel: gate `intent`, `pass` when nothing is `missing` and every unexplained or conflict row has a
fix or a ruling.
