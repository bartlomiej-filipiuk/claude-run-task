# Stack defaults (read only at bootstrap)

Default gate commands, test conventions and idioms per stack, for repos that do not declare their own. Rules:
1. A command the repo declares (manifest scripts, `Makefile`, `justfile`, CI steps) always wins over a row here.
2. A default is used only when its binary resolves (`command -v <tool>`, or the project-local binary such as
   `vendor/bin/phpstan`, `node_modules/.bin/eslint`); an optional tool (marked `opt`) only when it is installed or
   configured in the repo.
3. Run the fast defaults (format, lint, types, build) once on the base and write the result next to the value:
   `# default, green on base` or `# default, red on base` (a red base is a baseline, not the task's fault).
4. Every value taken from here is marked `# default` in the draft and confirmed by the user in the Profile block.
5. A stack with no row: leave the keys empty; the retro adds a row here as a core lesson.

| Stack (marker) | format | lint | types | unit | build | tests live in |
|---|---|---|---|---|---|---|
| Go (`go.mod`) | `test -z "$(gofmt -l .)"` | `go vet ./...`; opt `golangci-lint run` | (compiler) | `go test ./...` | `go build ./...` | `*_test.go` beside the code |
| Rust (`Cargo.toml`) | `cargo fmt --check` | `cargo clippy --all-targets -- -D warnings` | (compiler) | `cargo test` | `cargo build` | `tests/` for task tests (see trap) |
| Python (`pyproject.toml`, `requirements*.txt`) | opt `ruff format --check .` / `black --check .` | opt `ruff check .` / `flake8` | opt `mypy .` / `pyright` | `pytest` (Django without pytest: `python manage.py test`) | - | `tests/`, `test_*.py` |
| PHP (`composer.json`) | opt `vendor/bin/php-cs-fixer fix --dry-run` / `vendor/bin/pint --test` | opt `vendor/bin/phpcs` | opt `vendor/bin/phpstan analyse` / `vendor/bin/psalm` | `vendor/bin/phpunit` (Laravel: `php artisan test`; Pest: `vendor/bin/pest`) | - | `tests/`, `*Test.php` |
| JS/TS (`package.json`) | opt `npx prettier --check .` | opt `npx eslint .` | `npx tsc --noEmit` when `tsconfig.json` | the `test` script in CI mode (`CI=true`), else `npx vitest run` / `npx jest --ci` | the `build` script | `*.test.*`, `*.spec.*`, `__tests__/` |
| Ruby (`Gemfile`) | opt `bundle exec rubocop --format quiet` | (same) | opt `bundle exec srb tc` | `bundle exec rspec` / `bin/rails test` | - | `spec/`, `test/` |
| Java/Kotlin (`pom.xml`, `build.gradle*`) | opt `./gradlew spotlessCheck` / `mvn spotless:check` | opt `./gradlew check` | (compiler) | `./gradlew test` / `mvn -q test` | `./gradlew build -x test` / `mvn -q -DskipTests package` | `src/test/` |
| .NET (`*.csproj`, `*.sln`) | `dotnet format --verify-no-changes` | (analyzers in build) | (compiler) | `dotnet test` | `dotnet build` | `*.Tests` projects |

## Idioms and traps per stack

Copied into the profile's "Stack idioms" and "Trap checklist" as a start; the project's own docs win.

- **Go**: errors returned and wrapped with `%w`, never ignored; context passed as the first argument; table-driven
  tests. Trap: a goroutine without a cancel path leaks.
- **Rust**: `Result` and `?` over `unwrap`/`expect` on external input; no new `unsafe` without a comment saying why.
  Trap: inline `#[cfg(test)]` modules are reverted together with the code by `scripts/revert-check` (it classifies
  whole files), so the revert check reports a false fail; put the task's tests in `tests/`, or skip the check with
  that reason.
- **Python**: type hints on new public functions; no mutable default arguments; Django: `select_related` /
  `prefetch_related` for every relation read in a loop. Trap: settings and module-level state are cached by workers
  (Celery, gunicorn); restart them before a check.
- **PHP**: `declare(strict_types=1)`, typed properties, constructor promotion, readonly where possible; Laravel:
  authorisation through policies (`$this->authorize`, `Gate`), eager loading against N+1. Trap: config and route
  caches (`php artisan config:cache`) hide changes until cleared.
- **JS/TS**: strict mode, no `any` in new code, no unhandled promise. Trap: `npm test` may start watch mode; always
  run tests in CI mode.
- **Ruby/Rails**: strong parameters, `includes` against N+1, service objects over fat callbacks.
- **Java/Kotlin**: constructor injection, immutable DTOs, `Optional` over null for return values.
- **.NET**: async all the way (no `.Result`), nullable reference types on, `IOptions` for config.

## Compiled stacks and the negative control

For Go, Rust, Java and .NET the product must be rebuilt (and restarted when it runs as a server) after every revert
and restore, or the QA walk tests the old binary: put that command in the repo's `revert_pre`.

## LSP plugin per stack

Each stack's language server plugin and binary are in `tooling.md`; bootstrap records the ones this project uses in
the profile's `plugins`. With the plugin enabled, every Edit or Write returns the server's errors and warnings to the
model, so type and compile errors surface in the implementer's own loop, before any gate.

## Review skills per stack

Bootstrap fills `review_checklists` with the path of an installed review skill that matches the stack (for example
`~/.claude/skills/<stack>-code-review/SKILL.md`), when one exists; otherwise the reviewer works from the idioms above.
