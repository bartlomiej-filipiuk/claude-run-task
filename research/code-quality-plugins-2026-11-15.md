# Code-quality plugins for Claude Code: research (2026-11-15)

Goal: plugins that measurably raise the quality of code written through `run-task`, on any stack, at a sensible cost.
Sources: the local plugin directory cache (`~/.claude/plugins/plugin-directory-cache-v2.json`, 3731 listings, fetched
2026-11-15; filtered to dev-quality plugins reviewed by Anthropic or a partner: 61), the plugin READMEs in the local
official marketplace clone, the Claude Code docs, and web search for the partner plugins.

Already installed: code-review, pr-review-toolkit, code-simplifier, feature-dev, superpowers, php-lsp, laravel-boost,
context7, ponytail, architect-first.

## Recommended

### 1. LSP plugins, one per stack (Anthropic)

`typescript-lsp`, `pyright-lsp`, `gopls-lsp`, `rust-analyzer-lsp`, `ruby-lsp`, `jdtls-lsp`, `kotlin-lsp`,
`csharp-lsp`, `swift-lsp`, `clangd-lsp` (`php-lsp` is installed).

- Verified (docs, code-intelligence page): every time Claude edits or writes a file the server handles, Claude gets
  the server's errors and warnings automatically; no tool call needed. The `LSP` tool adds go-to-definition and
  references.
- The plugin does not install the language server binary (e.g. `go install golang.org/x/tools/gopls@latest`); without
  it the server does not start. No LSP in cloud sessions.
- Not documented: whether Agent-tool subagents (our implementers) get the diagnostics. Check on the first real run.
- Cost: no model calls; some context per diagnostic batch.
- Can be enabled per project with `enabledPlugins` in `.claude/settings.json` (shared) or `.claude/settings.local.json`
  (personal). Exact value format to confirm in the settings reference.

Why first: it turns type and compile errors into feedback inside the implementer's own loop, before any gate or
reviewer runs, on every stack, for free.

### 2. security-guidance (Anthropic)

Three layers: regex pattern warnings on Edit/Write (~25 dangerous patterns), an LLM diff review on Stop (newest Opus),
an agentic commit reviewer that traces data flow across files (IDOR, auth bypass, cross-file SSRF).

- Verified (README): kill switches per layer: `ENABLE_PATTERN_RULES=0`, `ENABLE_STOP_REVIEW=0`,
  `ENABLE_COMMIT_REVIEW=0`, `SECURITY_GUIDANCE_DISABLE=1`. The README itself recommends `ENABLE_STOP_REVIEW=0` for
  multi-agent or shared-worktree setups.
- Verified (docs): plugin hooks apply inside subagents, so implementers get the pattern warnings too.
- Cost: the Stop review is one model call per turn; with it off, pattern warnings are free and the commit review runs
  once per commit (`run-task` commits once per internal task).
- Overlap: complements `secperf-review` (which reviews the finished diff); it catches problems while the code is
  written and at commit.

Suggested setting for `run-task`: pattern warnings and commit review on, Stop review off.

## Useful on demand

- **claude-security (Anthropic)**: deep vulnerability scan of the codebase, a branch diff or a commit, at a chosen
  effort tier, every finding challenged before it is reported, optional patch files. Asks to confirm time and token
  cost. Candidate for the final security review of a `large` task on stacks where `secperf-review` has only its
  generic shard.
- **Semgrep Guardian (partner)**: deterministic SAST on agent-written code, many languages. Needs a Semgrep account
  and login; uses Semgrep's hosted server by default. Worth it where the organisation already uses Semgrep.
- **serena (partner, official marketplace)**: semantic code navigation through language servers, as an MCP server.
  Helps scouts and diggers in large codebases; overlaps the LSP tool. Try only if scouting is a bottleneck.
- **skill-creator (Anthropic)**: create skills and measure skill performance. Fits the `run-task` retro: a core change
  could be checked with a small eval set instead of a single dry run.
- **hookify (Anthropic)**: turns a repeated correction into a hook rule. Fits retro "user" rows that are mechanical
  (a command that must never run, a pattern that must never be written).

## Not recommended now

- **Axe Accessibility / axe MCP (Deque)**: the official server needs a paid axe DevTools subscription and a licence.
  Free alternative for the QA walk: `@axe-core/playwright` inside a step.
- **Codacy, Qodo, Greptile, Sonatype Guide, Opsera**: tied to a SaaS account; only where the team already uses it.
- **code-review, pr-review-toolkit, code-simplifier, feature-dev**: installed; they overlap the `run-task` reviewer,
  final review and approach check. Keep them for ad-hoc use outside the flow.

## Proposed changes to run-task (not applied)

1. `stacks.md`: an LSP plugin column per stack; bootstrap's Tooling line lists the missing plugin and binary with the
   install commands, and offers to enable the plugin for this project only (`enabledPlugins` in
   `.claude/settings.local.json`).
2. `profile.md`: `security_review` accepts `claude-security` for `large` tasks on stacks without a full secperf pack;
   a `plugins` key records what the project relies on.
3. README: recommend security-guidance with `ENABLE_STOP_REVIEW=0` when used with `run-task`.

## Sources

- Claude Code docs: https://code.claude.com/docs/en/plugins/code-intelligence.md,
  https://code.claude.com/docs/en/plugins/components.md, https://code.claude.com/docs/en/sub-agents.md,
  https://code.claude.com/docs/en/settings.md
- Semgrep Guardian: https://docs.semgrep.dev/semgrep-guardian/overview, https://claude.com/marketplace/plugins/semgrep-guardian
- Deque axe MCP server: https://hub.docker.com/r/dequesystems/axe-mcp-server,
  https://docs.deque.com/devtools-server/4.0.0/en/axe-mcp-server
- Roundups (used only as a cross-check): https://composio.dev/content/top-claude-code-plugins,
  https://designrevision.com/blog/best-claude-code-plugins
