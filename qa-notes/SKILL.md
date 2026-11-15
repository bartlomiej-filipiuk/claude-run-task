---
name: qa-notes
description: Generates QA testing notes (what was done + how to test) for pull requests and completed tasks. Use when a developer needs manual testing instructions.
allowed-tools:
  - Glob
  - Grep
  - Read
  - Bash
  - mcp__mcp-atlassian__jira_get_issue
  - mcp__mcp-atlassian__jira_search
argument-hint: "[JIRA-KEY or description of changes]"
---

# QA Notes Generator

Generate clear, concise QA notes from the task `$ARGUMENTS` and related PR/branch changes. Output must be **actionable**: for product/PR changes, understandable by non-technical testers; for developer, infra, or config tasks, include the **exact admin URLs and CLI commands** a developer runs to verify — concrete beats generic.

## Process

1. **Gather context**: If a JIRA key is provided, fetch the issue. Check `git log` and `git diff` for recent changes on the current branch vs main/master.
2. **Analyze changes**: Understand what user-visible behavior changed.
3. **Generate notes** in the format below.

## Output Structure

### What was done

- Summarize visible outcome or behavior change only; one bullet per change a tester can see
- NO code, function names, internal logic, or implementation details
- Write as if explaining to someone who has never seen the codebase

### How to test

- Numbered, step-by-step manual test instructions
- Each step must be concrete and actionable
- Use → arrow notation for expected results
- Cover the main happy path + at least one edge case
- For multi-page flows, organize steps by scenario with subheadings

### Checklist file (task folders only)

When the work has a task folder (`tasks/<KEY>/` in the workspace), also write `tasks/<KEY>/qa.json` with the same
steps as "How to test", so the Herdr task window can show them as a checklist. Same rules as the notes (no code
internals, concrete places); nothing that is not in the notes.

```json
{
  "version": 1,
  "envs": [{"name": "CMS dev", "url": "https://cms-dev.example"}, {"name": "Website dev", "url": "https://dev.example/eu-en"}],
  "setup": ["Use an administrator account.", "After the deploy: Configuration > Development > Performance > Clear all caches."],
  "test_text": "optional text the tester pastes, or empty",
  "steps": [
    {"where": "Homepage > Hero Carousel > first slide > Summary", "do": "Paste the test text in Source mode and save.",
     "expect": "The first slide shows \"QA test bold\"; no pop-up.", "url": "optional deep link, or empty"}
  ]
}
```

`envs` only when the notes name environments; `where` is the UI path or URL, `do` one action, `expect` what the
tester sees afterwards. Write the file even when the notes go to Jira; it stays local.

## Rules

- Don't repeat or paraphrase the task description; the reader has the ticket open
- Avoid code internals (functions, classes, logic) and source file paths. But DO include concrete admin URLs (e.g. `/admin/config/...`) and CLI commands (e.g. `drush ...`) for technical/infra tasks — they make the test reproducible.
- Keep it lean: `How to test` = the minimal steps that prove it. Drop anything a tester would not actually do.
- No vague steps like "check if it works": name where to go and what exactly to observe
- Be specific about WHERE to go and WHAT to do
- If changes are purely backend/invisible, state that and suggest indirect verification
- If context is insufficient, ask for clarification — do NOT guess
- No title line such as "QA notes, KEY." at the top; the note starts with the first section label (the Jira comment already sits on the ticket)
- No "Not covered here" section. If a limitation matters for the tester, fold it into the step it affects as an expected-result note; otherwise leave it out
- When paired with `writing-client-notes`, keep the first-person developer voice and its section-label style ("What was done." / "How to test."); the two skills are meant to be used together for client-facing QA notes
