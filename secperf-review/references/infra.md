# CI, container and edge configuration

Pipelines (Azure, GitHub, GitLab, Bitbucket), Dockerfiles, web server and edge cache config (nginx, .htaccess, VCL, CDN). Area: security or cache as listed per item.

Each item: severity is the default; `severity.md` rules apply. Report a pattern only when "Not a finding when" does not hold for the file you read.

### INF-01 · Secret baked into an image or printed in a log

**Severity:** high · **Area:** security · **Taxonomy:** A02:2025, CWE-532, CWE-538 · **Applies to:** Dockerfile, pipeline YAML and scripts

**Signals:** `ARG`/`ENV` holding a token, key, DSN or password in a final image stage; `echo $SECRET`, `set -x` or `env`/`printenv` in a step that has secrets; secrets written to a file that ends up in an artifact or image layer; `.env` copied into the image.

**Why:** Image layers and pipeline logs are readable by more people than the secret store; layers keep values even when a later step deletes the file.

**Fix:** Pass secrets at runtime (task definition, secret mount) or use a build secret mount; mask variables; never print the environment.

**Not a finding when:** The value is public by design (e.g. a browser DSN or a public site key) or comes from a secret mount that is not persisted.

### INF-02 · Pipeline secrets reachable from untrusted triggers

**Severity:** high · **Area:** security · **Taxonomy:** A03:2025, CWE-829 · **Applies to:** PR/MR builds, fork builds, manual parameters

**Signals:** secret variable groups or service connections available to PR validation builds from forks; user-controlled parameters or branch names interpolated into shell; deploy stages without an environment approval or branch condition.

**Why:** Anyone who can open a PR or set a parameter can run code with production credentials.

**Fix:** Restrict secrets to protected branches/environments; pass parameters as env vars, not inline script text; keep manual approvals on prod stages.

**Not a finding when:** The project has no external contributors and the trigger is limited to protected branches.

### INF-03 · Unpinned or unverified build inputs

**Severity:** medium · **Area:** security · **Taxonomy:** A03:2025, CWE-494 · **Applies to:** Dockerfile, pipeline install steps

**Signals:** base image `:latest` or a floating tag in a production image; `curl … | sh`; `npm install` instead of `npm ci` (or composer without the lock) in a build; tools downloaded without checksum.

**Why:** The build changes without a code change, and a compromised upstream lands in production.

**Fix:** Pin by version or digest; install from lockfiles; verify checksums.

**Not a finding when:** The floating tag is a deliberate, documented security-patch channel and the image is rebuilt and tested on each change.

### INF-04 · Missing variable silently disables a control

**Severity:** medium · **Area:** security · **Taxonomy:** A09:2025, CWE-1188 · **Applies to:** build args, env defaults, feature flags in pipelines and entrypoints

**Signals:** `${VAR:-}` or an empty default for a secret, monitoring key, webhook secret or auth setting; code or entrypoint that turns the integration off when the value is empty without logging; a new variable added in code but not in the pipeline that passes build args.

**Why:** A missing variable in one environment turns off monitoring, webhook verification or auth without anyone noticing.

**Fix:** Fail the build or startup for required values per environment, or log a warning that monitoring sees.

**Not a finding when:** The integration is optional by design in that environment and the absence is logged.

### INF-05 · Edge cache stores private or varied responses under one key

**Severity:** high · **Area:** cache · **Taxonomy:** CWE-524, CWE-525 · **Applies to:** VCL, nginx proxy_cache, CDN behaviours, cache headers set in server config

**Signals:** caching responses with `Set-Cookie`, `Authorization` or `Cache-Control: private`; stripping cookies or headers before the backend for routes that personalize; cache key without host, language, query or a header the backend varies on; overriding backend `Cache-Control` with a long TTL globally.

**Why:** One user's response or one language's page is served to others, or editors' changes never show.

**Fix:** Pass private responses through; include every varying input in the key; respect backend cache headers except for documented static assets.

**Not a finding when:** The route is static and identical for everyone (assets, public files) and the key covers host and path.

### INF-06 · Purge or admin endpoint open at the edge

**Severity:** high · **Area:** security · **Taxonomy:** A01:2025, CWE-284 · **Applies to:** VCL BAN/PURGE handling, nginx locations, CDN rules

**Signals:** PURGE/BAN accepted without an ACL; admin or status paths (`/server-status`, `/varnish`, `/admin` on the frontend host) reachable publicly; a new location block without the allow/deny rules the others have.

**Why:** Anyone can empty the cache (load spike on the origin) or read internal status.

**Fix:** ACL on internal addresses or a secret header; mirror the restrictions of sibling blocks.

**Not a finding when:** The endpoint is only reachable inside a private network (security group, internal listener).

### INF-07 · Web server rules expose files or drop headers

**Severity:** medium · **Area:** security · **Taxonomy:** A02:2025, CWE-538 · **Applies to:** .htaccess, nginx, Next/Vercel headers config

**Signals:** removed deny rules for dotfiles, backups, `.git`, `.env`, `composer.*`, private files; directory listing on; removed or weakened security headers (CSP, HSTS, X-Content-Type-Options, frame-ancestors).

**Why:** Source, configuration or private files become downloadable; browser protections drop silently.

**Fix:** Restore the deny rules and headers; add tests or curl checks for them.

**Not a finding when:** The headers are set at another layer (CDN response headers policy) that the project context documents.

### INF-08 · Deploy order incompatible with rolling instances

**Severity:** medium · **Area:** cache · **Taxonomy:** n/a · **Applies to:** pipelines that run migrations, config import or cache clears while old instances still serve

**Signals:** schema or config change applied before or after a rollout where old and new code run together; cache clear before new instances are healthy (old code re-fills cache); a removed field or route still used by the old version during drain.

**Why:** For the duration of the rollout, requests hit code that does not match the schema or cache, and wrong pages get cached.

**Fix:** Make changes backward compatible across one release; clear caches after the rollout finishes.

**Not a finding when:** The deploy stops all old instances before the migration, or the change is additive.
