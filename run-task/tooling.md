# Tooling check (Phase 0, every run)

What the run needs on this machine, checked before the scope check, and installed with the user's yes. Cheap: only
`command -v`, `claude plugin list` and file checks, no model calls.

## What is checked

| Need | When | Check | Install |
|---|---|---|---|
| helper skills `secperf-review`, `challenge`, `change-map`, `qa-notes` | always | `~/.claude/skills/<name>/SKILL.md` exists | symlink from the bundle (README "Install") |
| LSP plugin of each touched stack | always, whatever the profile's `plugins` lists | `claude plugin list` shows it enabled | `claude plugin install <plugin>@claude-plugins-official`; then added to the profile's `plugins` |
| its language server binary | always | `command -v <binary>` | the command in the table below |
| `security-guidance` plugin | always | `claude plugin list` | `claude plugin install security-guidance@claude-plugins-official` |
| `claude-security` plugin | profile `security_review: claude-security` | `claude plugin list` | `claude plugin install claude-security@claude-plugins-official` |
| tracker CLI | tracker input | `command -v twg` / `gh` / `glab` | `brew install gh` / `brew install glab`; `twg`: the user's own setup |
| gate tools from `stacks.md` | profile gates use them | `command -v` or the project-local path | the stack's own installer, global only (below) |
| `ffmpeg`, `mmdc` | visual review, change map `--svg` | `command -v` | `brew install ffmpeg`, `npm i -g @mermaid-js/mermaid-cli` |
| Playwright | QA walk or visual review with a web front end | resolvable from the front-end repo | not installed by the flow (see the rules) |

## LSP plugin and binary per stack

| Stack | Plugin | Binary | Install the binary |
|---|---|---|---|
| TypeScript / JavaScript | `typescript-lsp` | `typescript-language-server` | `npm i -g typescript-language-server typescript` |
| Python | `pyright-lsp` | `pyright-langserver` | `npm i -g pyright` |
| PHP | `php-lsp` | `intelephense` | `npm i -g intelephense` |
| Go | `gopls-lsp` | `gopls` | `go install golang.org/x/tools/gopls@latest` |
| Rust | `rust-analyzer-lsp` | `rust-analyzer` | `rustup component add rust-analyzer` |
| Ruby | `ruby-lsp` | `ruby-lsp` | `gem install ruby-lsp` |
| Java | `jdtls-lsp` | `jdtls` | `brew install jdtls` |
| Kotlin | `kotlin-lsp` | `kotlin-lsp` | `brew install JetBrains/utils/kotlin-lsp` |
| C# | `csharp-lsp` | `csharp-ls` | `dotnet tool install --global csharp-ls` |
| Swift | `swift-lsp` | `sourcekit-lsp` | ships with Xcode / the Swift toolchain |
| C / C++ | `clangd-lsp` | `clangd` | `brew install llvm` |

A binary whose own toolchain is missing is listed after its toolchain, which is installed first: `go` (`brew install
go`), `rustup` (`brew install rustup && rustup-init -y`), Ruby (`brew install ruby`), .NET (`brew install --cask
dotnet-sdk`), a JDK (`brew install openjdk`). The toolchain is listed once, also when gate tools need it.

Binaries installed by a toolchain land in its own bin directory: check `~/go/bin`, `~/.cargo/bin` and
`$(npm prefix -g)/bin` before calling one missing, and say when that directory is not on PATH (the language server then
does not start; the fix is a PATH line for the user's shell profile, which the user adds).

## Rules

1. Missing items go into the first message of the run (the scope-check message, or its own message when the scope
   check does not stop) as one numbered block `T1, T2, ...`: item, the gate or feature it unlocks, the exact install
   command. The answer line covers it: "T: yes" installs the whole block, "T2 no" strikes an item, and
   "recommendations" accepts the scope recommendations, the derived AC and the tooling block together. A bare "yes"
   or "ok" to a message that holds questions, derived AC and tooling gets the scope-check follow-up naming all three.
2. After the yes, run the commands one by one, then re-check each item and report installed / failed with the error.
   A failed install leaves its gate `not covered`; the run goes on.
3. Plugins install at user scope, or with `--scope local` when the user wants them for this project only. A plugin
   installed during the session works after `/reload-plugins` (the user types it, a `needs_me` item) or in the next
   session. `summary.md` lists the LSP state under Gates (`lsp: active | inactive until reload | missing`); it is not a
   verdict gate.
4. Only the official marketplace (`claude-plugins-official`) and the platform's package managers (brew, npm -g, gem,
   go install, rustup, dotnet tool). Anything else is named with its source and installed only on an explicit yes for
   that item.
5. Never install project dependencies (`npm i` in the repo, `composer require`, `pip install` into the project): they
   change the repo and would enter the task's diff. They are listed with the command for the user.
6. Never change the user's settings files to configure a plugin; name the setting and let the user set it.
7. A declined item is recorded in the profile (`tooling_declined: [<item> <date>]`) and not offered again until the
   user asks.
