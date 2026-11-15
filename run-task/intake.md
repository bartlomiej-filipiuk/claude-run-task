# Intake: from input to `source.md`, `ac.md` and a task id

## Input adapters

Pick the first row that matches the input. Every adapter writes `tasks/<ID>/source.md` with: title, description,
acceptance criteria (as written, or "none stated"), every comment with author and date, labels, links, parent or
epic, and a list of attachments with where each was saved or why it was not.

| Input | Fetch | `<ID>` |
|---|---|---|
| Jira key (`[A-Z][A-Z0-9]+-\d+`) or an Atlassian URL | `twg jira workitem get <KEY> --full` when the `twg-jira` skill is installed (attachments: `twg jira workitem attachment download`); otherwise the Atlassian MCP (`jira_get_issue` with comments, `jira_download_attachments`) | the key |
| GitHub issue URL or `owner/repo#N` | `gh issue view N -R owner/repo --json title,body,comments,labels,milestone,url` (sub-issues and links through `gh api` when the body points at them); images and files linked in the body: `gh api` for private repos, `curl -L` for public ones | `<repo>-<N>` |
| GitLab issue URL | `glab issue view N -R group/repo --comments`; attachments via `glab api` | `<repo>-<N>` |
| Any other URL (Linear, Asana, Slack, Notion, a doc) | an MCP connector for it when one is connected and authenticated; otherwise ask the user to paste the text and continue as plain text | as for plain text |
| Plain text | the text itself, verbatim | `YYYYMMDD-<slug>`, shown to the user with the scope questions; they can rename it before anything but `source.md` and `ac.md` exists (rename the directory, close and reopen the panel item) |

**Instructions to the session are not the task.** Words in the input that tell the session how to work ("don't ask",
"quickly", "I have little time", "use X model") go to `source.md` under `## Instructions to the session`, never into
`ac.md`. They change how the flow talks, never which gates run. Requests for a deliverable ("also record a demo
video", "write docs") are part of the task and stay.

A fetch that fails (no CLI, no auth, 403) is said to the user with the exact command that failed; the run continues
only on pasted text, never on a guessed description.

The profile's `tracker.key_pattern` overrides the Jira pattern when the project's keys look different. A new tracker
type is added as a row here by the retro (`improve.md`) the first time a project needs it.

## `ac.md`

The description and the acceptance criteria verbatim from `source.md`, nothing else. When the source states no AC,
write "No acceptance criteria stated" and let the scope check derive them: derived AC are confirmed by the user at
gate 0 before anything is built on them.

Later sections, appended by the flow and never rewritten: `## Decisions at intake`, `## Decisions at the gate`, dated
mid-loop decisions.

## Names that use the id

- `<slug>`: three to five English words in kebab case, from the title, or from the scope check's goal when the input
  has no title. Branch: the profile's `branch_pattern` (default `feature/<ID>-<slug>`; for a generated id the
  slug is already in it: `feature/<ID>`).
- Commit message: the profile's `commit_format`, set at bootstrap from the repo's own style (default `<ID>: <what>` for a Jira key, `<what> (#<N>)` for a GitHub or GitLab issue, `<what>` for plain text).
- Panel ids: `<ID>-<what>` (e.g. `<ID>-scope`, `<ID>-retro`).
- Tracker writes (a comment draft, follow-up items) exist only for tracker inputs, always as drafts first.
