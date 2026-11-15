#!/usr/bin/env python3
"""Select the few diff hunks worth challenging and write the challenger brief.

A hunk is a candidate only when it REMOVES something that carried a guarantee: a side effect,
a guard, an access/sanitise check, error handling, or a test assertion. Pure additions, moved
code, formatting and comment-only edits score zero. Scope (base, --pair, wrong-base guard,
exclusions) comes from secperf-review's prepare.collect() so both tools see the same diff.

Drupal, Next.js and infra files (and PHP/JS tests) are scored with the LEGACY row. Other stacks
(prepare's `generic` group and their tests) get a per-language row keyed by file extension, in a
separate pass, so the Drupal/Next.js selection does not change when other code sits in the diff.
"""
import argparse
import json
import os
import re
import subprocess
import sys

# prepare.py lives in the sibling skill: ../secperf-review/scripts next to this skill, wherever both are
# installed (~/.claude/skills or a checkout); the fixed install path is the fallback.
_SIBLING = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        'secperf-review', 'scripts')
sys.path.insert(0, _SIBLING if os.path.isfile(os.path.join(_SIBLING, 'prepare.py'))
                else os.path.expanduser('~/.claude/skills/secperf-review/scripts'))
import prepare  # noqa: E402

CAP = 5
MIN_SCORE = 3
HUNK_LINES = 80

# Diffed as text when they hold no NUL byte (small fixtures, `git add -N`); never worth a question.
BINARY = re.compile(r'\.(png|jpe?g|gif|webp|avif|ico|pdf|mp4|webm|woff2?|zip|gz)$', re.I)
# A composer-patches entry: "description": "path or URL".
PATCH_ENTRY = re.compile(r'"\s*:\s*"')
TEST_FILE = re.compile(r'(^|/)(tests?|__tests__|e2e)/|\.(test|spec)\.[jt]sx?$|Test\.php$')
COMMENT = re.compile(r'^\s*(//|#(?!\[)|\*|/\*)')  # PHP 8 `#[...]` attributes are code
# (weight, label, pattern, blocker) checked against each removed, non-moved code line.
SIGNALS = [
    (4, 'access/permission/sanitise check', re.compile(
        r'->access\(|hasPermission\(|AccessResult::|_permission\s*:|_access\s*:|_csrf|#access|checkAccess|'
        r'isAuthenticated|Xss::filter|Html::escape|sanitize|isSafeUrl|escapeHtml|DOMPurify|->isAllowed\(|'
        r'requirePermission|roles?\s*:|permissions?\s*:', re.I), True),
    (3, 'side effect', re.compile(
        r'->delete\(|->save\(|\bunset\(|->dispatch\(|invalidateTags|->invalidate|->purge|->createItem\(|'
        r'->send\(|->mail\(|->register\(|->setRedirect|->set\(|->commit\(|->rollBack\(|startTransaction|'
        r'->lock\(|->acquire\(|->release\(|res\.setHeader|setHeader\(|revalidate\(|\.delete\(|\.destroy\('), True),
    (3, 'throw', re.compile(r'\bthrow\b'), True),
    # A PHP 8 attribute with arguments registers behaviour (Drupal #[Hook], plugin attributes, Symfony #[Route]).
    (3, 'registration attribute removed', re.compile(r'^\s*#\[[A-Z]\w*\('), True),
    (2, 'guard condition', re.compile(r'^\s*(}\s*)?(if|elseif|else if|while)\s*\(|\?\?|&&|\|\|'), False),
    (2, 'error handling', re.compile(r'\bcatch\s*\(|\btry\s*\{|->error\(|->critical\(|console\.error'), False),
    (1, 'return', re.compile(r'^\s*return\b'), False),
    (1, 'limit/default', re.compile(r'\b(MAX|MIN|LIMIT|TIMEOUT|TTL|max_age|maxAge|limit|timeout)\b'), False),
]
# Behaviour switched off by ADDING code; scored on added lines.
ADDED_SIGNALS = [
    (4, 'test skipped', re.compile(r'\.skip\(|markTestSkipped|@group\s+skip|xit\(|xdescribe\('), True),
    (4, 'TLS verification off', re.compile(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|'verify'\s*=>\s*(FALSE|false)"), True),
    (3, 'disabled by addition', re.compile(
        r'NormalModuleReplacementPlugin|IgnorePlugin|enabled\s*:\s*false|status\s*:\s*false|'
        r'if\s*\(\s*(false|FALSE|0)\s*\)|@ts-ignore|@ts-expect-error|eslint-disable|phpcs:ignore|@phpstan-ignore'), False),
]
# Removed registrations in YAML config/services/routing: the feature they wire up stops running.
YAML_SIGNALS = [
    (3, 'config registration removed', re.compile(
        r'plugin_id\s*:|^\s*class\s*:|_controller\s*:|_form\s*:|event_subscriber|^\s*-?\s*id\s*:|'
        r'status\s*:\s*true|enabled\s*:\s*true|^\s*path\s*:'), True),
]
# YAML lines are judged by their key path in the base file (permissions, required_roles > local_hr, ...).
GRANT_KEY = re.compile(r'role|permission|access|required|allowed|allow|deny|auth|trusted', re.I)
SWITCH_KEY = re.compile(r'enabled|status|verify|secure|https|csrf|sanitize|encrypt', re.I)
LIMIT_KEY = re.compile(r'skip|limit|max|min|threshold|window|flood|timeout|ttl|lifetime|expire|length|size', re.I)
YAML_KEY = re.compile(r'^\s*(?:-\s*)?[\'"]?([\w.\- ]+?)[\'"]?\s*:(?:\s|$)')
TEST_SIGNALS = [
    (5, 'test method removed', re.compile(r'function\s+test\w*\s*\(|\b(it|test)\s*\(\s*[\'"`]'), True),
    (4, 'assertion removed', re.compile(r'->assert\w*\(|\bassert\w*\(|\bexpect\s*\(|\.toBe|\.toEqual|\.toHave'), True),
]
GUARD_STRIP = re.compile(r'^\s*(}\s*)?(if|elseif|else if|while)\s*\(|\)\s*\{?\s*$')
FUNC = re.compile(r'\bfunction\s+(\w+)\s*\(|^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(|'
                  r'^\s*(?:public|protected|private|static|async|\s)*(\w+)\s*\([^)]*\)\s*(?::\s*[\w<>\[\]|?]+\s*)?\{\s*$')
# The original PHP/JS row. Drupal, Next.js and infra files use it unchanged.
LEGACY = {'name': 'drupal/nextjs', 'comment': COMMENT, 'signals': SIGNALS, 'tests': TEST_SIGNALS,
          'added': ADDED_SIGNALS, 'strip': GUARD_STRIP, 'negation': None, 'func': FUNC, 'test_file': None}

# ---- Per-language rows for every other stack, keyed by file extension. ----
NEVER = re.compile(r'(?!)')
RETURN = re.compile(r'^\s*return\b')
LIMIT = re.compile(r'\b(MAX|MIN|LIMIT|TIMEOUT|TTL|max_age|maxAge|limit|timeout|page_size|per_page|max_length|'
                   r'max_retries|retries|throttle\w*|rate_limit\w*)\b')
GENERIC_STRIP = re.compile(r'^\s*(?:\{%-?|<%-?)?\s*(}\s*)?(else\s+)?(if|elif|elsif|elseif|unless|while|until|guard)\b'
                           r'\s*(let\s+)?\(?|\)?\s*(\{|:|do|then|-?%\}|-?%>)?\s*$')
NEGATION = re.compile(r'^\s*(not\s+|!\s*)+')
GENERIC_ATOMS = {'strip': GENERIC_STRIP, 'negation': NEGATION}  # shared by every language row
LEGACY_ACCESS = SIGNALS[0][2].pattern
LEGACY_EFFECT = SIGNALS[1][2].pattern


def lang_row(name, ext, comment, access, effect, throw, guard, error, define, assertion, skip, tls, disabled,
             opened, func, test_file=None, generic_only=False, flags=0, code_extra=()):
    c = lambda p: re.compile(p, flags) if isinstance(p, str) else p
    return {
        'name': name, 'ext': re.compile(ext), 'comment': c(comment), 'generic_only': generic_only,
        'test_file': re.compile(test_file) if test_file else None, 'func': re.compile(func),
        'strip': GENERIC_STRIP, 'negation': NEGATION,
        'signals': [
            (4, 'access/permission/sanitise check', c(access), True),
            (3, 'side effect', c(effect), True),
            (3, 'throw', c(throw), True),
            (2, 'guard condition', c(guard), False),
            (2, 'error handling', c(error), False),
            (1, 'return', RETURN, False),
            (1, 'limit/default', LIMIT, False),
            *code_extra,
        ],
        'tests': [(5, 'test method removed', c(define), True), (4, 'assertion removed', c(assertion), True)],
        'added': [
            (4, 'test skipped', c(skip), True),
            (4, 'TLS verification off', c(tls), True),
            (4, 'access check switched off by addition', c(opened), True),
            (3, 'disabled by addition', c(disabled), False),
        ],
    }


C_COMMENT = r'^\s*(//|/\*|\*)'  # `#[...]`, `@Annotation` and C# `#pragma` are code
ROWS = [
    # Laravel, Symfony and plain PHP outside Drupal: the legacy patterns plus framework guards. PHP 8
    # attributes (`#[IsGranted]`) are code, so `#[` is not a comment here.
    lang_row(
        'php', r'\.php$', r'^\s*(//|#(?!\[)|\*|/\*)', flags=re.I, generic_only=True, func=FUNC.pattern,
        access=LEGACY_ACCESS + r'|->authorize\w*\(|\bauthorize\(|Gate::|\bcan(not)?\(|->middleware\(|::middleware\('
        r'|#\[IsGranted|\bisGranted\(|denyAccessUnlessGranted\(|isCsrfTokenValid\(|->(allows|denies)\(|Auth::(check|user|id)\('
        r'|\bauth\(\)->(check|user|id)\(|@(can|cannot|auth|guest|csrf)\b|->validated?\(|Validator::make\(|htmlspecialchars\(',
        effect=LEGACY_EFFECT + r'|\bdispatch\(|\bevent\(|Cache::(forget|put|forever|flush|tags)|->forget\(|::(create|destroy|'
        r'updateOrCreate|insert)\(|->(update|forceDelete|sync|attach|detach|notify|persist|remove|flush)\(|Mail::|Notification::'
        r'|DB::(transaction|beginTransaction|commit|rollBack)\(|Storage::(delete|put)',
        throw=r'\bthrow\b|\babort(_if|_unless)?\(|\bthrow_(if|unless)\(',
        guard=r'^\s*(}\s*)?(if|elseif|else if|while)\s*\(|\?\?|\?:|&&|\|\||^\s*@(if|unless|isset|empty)\b',
        error=r'\bcatch\s*\(|\btry\s*\{|->error\(|->critical\(|\breport\(|Log::(error|critical|alert|emergency)\(',
        define=TEST_SIGNALS[0][2].pattern, assertion=TEST_SIGNALS[1][2].pattern, skip=ADDED_SIGNALS[0][2].pattern,
        tls=ADDED_SIGNALS[1][2].pattern + r'|->withoutVerifying\(|CURLOPT_SSL_VERIFY(PEER|HOST)\s*,\s*(false|0)',
        disabled=ADDED_SIGNALS[2][2].pattern + r'|\{!!',
        opened=r'withoutMiddleware\(|validateCsrfTokens\(\s*except|\$except\s*=|csrf_protection\s*:\s*false|PUBLIC_ACCESS'),
    lang_row(
        'python', r'\.pyi?$', r'^\s*#', test_file=r'(^|/)(test_[^/]*|[^/]*_tests?|tests|conftest)\.py$',
        func=r'^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)',
        access=r'@(\w+\.)*\w*_required\b|@user_passes_test\b|@csrf_protect\b|@require_(GET|POST|safe|http_methods)\b'
        r'|\b(permission|authentication|throttle)_classes\b|\b(LoginRequired|PermissionRequired|UserPassesTest)Mixin\b'
        r'|\bhas_(object_)?perms?\(|\bhas_(object_)?permission\(|\bis_(authenticated|staff|superuser|active)\b'
        r'|\bDepends\(\s*\w*(auth|user|current|token|verify|permission|admin|scope)\w*|\bSecurity\(|\bcheck_password\('
        r'|\bverify_\w+\(|compare_digest\(|\bescape\(|\bbleach\.|\bsanitiz\w*\(|\bcurrent_user\b'
        r'|\b(owner|user|tenant|org|account|created_by)(_id)?\s*=\s*(request\.user|current_user)\b|\.before_request\b',
        effect=r'\.(delete|save|bulk_create|bulk_update|update|update_or_create|get_or_create|create|commit|rollback|flush|'
        r'send|publish|dispatch|invalidate\w*|purge|acquire|release|delay|apply_async|enqueue|add_task)\(|\bsend_(mass_)?mail\('
        r'|^\s*del\s|\bos\.(remove|unlink|rmdir)\(|\bshutil\.rmtree\(|\btransaction\.atomic\b|select_for_update\('
        r'|@receiver\(|\bcache\.(set|delete\w*|clear)\(',
        throw=r'\braise\b|\babort\(|HttpResponse(Forbidden|NotAllowed|BadRequest)\b|status\.HTTP_40[13]_',
        guard=r'^\s*(el)?if\b|^\s*while\b|^\s*assert\b',
        error=r'^\s*except\b|^\s*try\s*:|^\s*finally\s*:|\blog(ger|ging)?\.(error|exception|critical|warning)\(',
        define=r'^\s*(async\s+)?def\s+test\w*\s*\(|^\s*class\s+Test\w*',
        assertion=r'^\s*assert\b|\bassert\w*\(|\bpytest\.raises\(|\bself\.fail\(',
        skip=r'@pytest\.mark\.(skip|skipif|xfail)\b|@(unittest\.)?(skip|skipIf|skipUnless|expectedFailure)\b'
        r'|\bpytest\.(skip|xfail)\(|\bself\.skipTest\(',
        tls=r'\bverify\s*=\s*False\b|_create_unverified_context|\bCERT_NONE\b|check_hostname\s*=\s*False',
        disabled=r'#\s*(noqa|type:\s*ignore|nosec|pragma:\s*no\s*cover)\b|^\s*if\s+(False|0)\s*:|\bDEBUG\s*=\s*True\b',
        opened=r'@csrf_exempt\b|\bAllowAny\b|\blogin_not_required\b|(permission|authentication)_classes\s*=\s*(\[\s*\]|\(\s*\))'
        r'|ALLOWED_HOSTS\s*=\s*\[\s*[\'"]\*'),
    lang_row(
        'go', r'\.go$', C_COMMENT, test_file=r'_test\.go$', func=r'^\s*func\s+(?:\([^)]*\)\s*)?(\w+)',
        access=r'\b\w*(Authori[sz]e|Authenticat|RequireAuth|RequireUser|RequireRole|RequireAdmin|Permission|IsAdmin|HasRole'
        r'|HasScope|CurrentUser|UserFrom\w*|Claims)\w*\(|\bStatus(Unauthorized|Forbidden)\b|\bErr(Unauthorized|Forbidden'
        r'|Unauthenticated|PermissionDenied)\b|codes\.(Unauthenticated|PermissionDenied)|\.Use\(|\bjwt\.\w+\(|\.Verify\w*\('
        r'|ConstantTimeCompare\(|hmac\.Equal\(|CompareHashAndPassword\(|html\.EscapeString\(|bluemonday|filepath\.IsLocal\('
        r'|MaxBytesReader\(|\bcsrf\.\w+\(',
        effect=r'\.(Delete\w*|Save|Create\w*|Update\w*|Insert\w*|Exec(Context)?|Commit|Rollback|Publish|Send\w*|Dispatch'
        r'|Enqueue|Invalidate\w*|Purge|Lock|Unlock|RLock|RUnlock|Flush|Remove\w*|Del|Set|SetEx|Expire|Evict)\('
        r'|^\s*defer\s|\bos\.Remove(All)?\(|\bdelete\(\w+|\bcancel\(\)',
        throw=r'\bpanic\(|\bhttp\.Error\(|\.AbortWith\w*\(|\berrors\.New\(|\bfmt\.Errorf\(|\blog\.(Fatal|Panic)\w*\('
        r'|\bstatus\.Errorf?\(',
        guard=r'^\s*(}\s*else\s+)?if\s|&&|\|\|',
        error=r'\berr\s*!=\s*nil\b|\breturn\b.*\berr\b|\brecover\(\)|\b(log|slog|logger)\.(Error|Warn)\w*\(',
        define=r'^\s*func\s+(Test|Fuzz|Example|Benchmark)\w*\s*\(|\bt\.Run\(|\b(It|Describe|Context)\(\s*"',
        assertion=r'\b(assert|require)\.\w+\(|\bt\.(Error|Errorf|Fatal|Fatalf|Fail|FailNow)\(|\bcmp\.Diff\(|\bExpect\('
        r'|reflect\.DeepEqual\(',
        skip=r'\b[tb]\.Skip(f|Now)?\(|\b[XP]It\(',
        tls=r'InsecureSkipVerify\s*:\s*true',
        disabled=r'//\s*nolint\b|#nosec\b|^\s*if\s+false\s*\{',
        opened=r'AllowAllOrigins\s*:\s*true|AllowedOrigins\s*:\s*\[\]string\{\s*"\*"'),
    lang_row(
        'rust', r'\.rs$', C_COMMENT, func=r'\bfn\s+(\w+)',
        access=r'\b(authori[sz]e\w*|authenticat\w*|require_\w+|check_\w*(perm|auth|access|role|owner)\w*|has_(perm|role|scope)'
        r'\w*|is_admin|verify_\w+|ensure_\w*(auth|perm|admin|owner)\w*)\s*\(|\b(AuthUser|Identity|Claims|CurrentUser'
        r'|BearerAuth|RequireAuth\w*|Authenticated\w*)\b|\.(wrap|layer|route_layer)\(|\bfrom_fn(_with_state)?\('
        r'|StatusCode::(UNAUTHORIZED|FORBIDDEN)|HttpResponse::(Unauthorized|Forbidden)|Error(Unauthorized|Forbidden)\b'
        r'|constant_time_eq|\bct_eq\(|\bammonia\b|html_escape|encode_(text|safe)\(',
        effect=r'\.(delete|save|insert|update|execute|commit|rollback|send|publish|dispatch|invalidate\w*|purge|remove|flush'
        r'|lock|write|set|expire|del)\(|\bdrop\(|\bfs::remove_\w+\(|\b(tokio::)?spawn\(',
        throw=r'\bpanic!|\bunreachable!|\bbail!|\bensure!|\bErr\(|\.ok_or(_else)?\(',
        guard=r'^\s*(}\s*else\s+)?if\s|^\s*while\s|^\s*let\s.*\belse\s*\{|&&|\|\|',
        error=r'\?\s*;?\s*$|\?\)|\.map_err\(|\.or_else\(|\b(log|tracing)::(error|warn)!|^\s*(error|warn)!\(',
        # Unit tests live in the same file (#[cfg(test)] mod tests), so test signals count in code too.
        code_extra=((5, 'test method removed', re.compile(r'#\[(\w+::)*test\b'), True),
                    (4, 'assertion removed', re.compile(r'\b(debug_)?assert(_eq|_ne)?!|\bassert_matches!'), True)),
        define=r'#\[(\w+::)*test\b', assertion=r'\b(debug_)?assert(_eq|_ne)?!|\bassert_matches!',
        skip=r'#\[ignore\b', tls=r'danger_accept_invalid_(certs|hostnames)\(\s*true',
        disabled=r'#!?\[allow\((?!dead_code|unused)|^\s*if\s+false\s*\{|\bunsafe\s*(\{|fn\b|impl\b)',
        opened=r'CorsLayer::(very_)?permissive\(|Cors::permissive\(|\.allow_any_origin\('),
    lang_row(
        'ruby', r'\.(rb|erb|rake)$', r'^\s*#', test_file=r'(_spec|_test)\.rb$|(^|/)spec/.*\.rb$',
        func=r'^\s*def\s+(?:self\.)?(\w+[?!]?)',
        # Removing a skip_* line re-enables a guard, so it is not a removed check.
        access=r'^(?!.*\bskip_).*?(\b(prepend_)?before_action\b|\bauthenticate\w*|\bauthoriz\w*|\bpolicy_scope\b|\bcan(not)?\?'
        r'|\bcurrent_user\b|\bprotect_from_forgery\b|\bverify_authenticity_token\b|\bsanitize\(|\bh\(|\bhtml_escape\('
        r'|\.permit\(|\brequire_\w+|\bensure_\w+|\bhas_role\?|\badmin\?)',
        effect=r'\.(destroy|delete|save|update|create|update_all|delete_all|destroy_all|insert_all|upsert_all|touch|with_lock'
        r'|deliver_later|deliver_now|perform_later|perform_async|perform_in|publish|broadcast\w*|enqueue|expire|purge'
        r'|invalidate\w*|increment|decrement|lock)\b!?|\bRails\.cache\.(delete|write|clear|delete_matched)\b'
        r'|\b(after|before|around)_(commit|save|create|update|destroy)\b|\bdependent:\s*:(destroy|delete_all|nullify)'
        r'|\btransaction\b|\bFile\.(delete|unlink)\b|\bFileUtils\.rm',
        throw=r'\braise\b|\bthrow\b|\bhead\s+:(forbidden|unauthorized)|status:\s*:(forbidden|unauthorized)',
        guard=r'^\s*(elsif|while|until)\b|\b(if|unless)\s+\S|&&|\|\|',
        error=r'\brescue\b|^\s*ensure\b|\blogger\.(error|fatal|warn)\b',
        define=r'^\s*(it|specify|scenario|example|test|describe|context)\b\s*(\(|[\'"]|do\b|\{)|^\s*def\s+test_\w*',
        assertion=r'\bexpect\s*[({]|\bassert\w*|\brefute\w*|\.should\b|\.must_\w+|\bis_expected\b',
        skip=r'^\s*(xit|xspecify|xdescribe|xcontext|xscenario|pending)\b|^\s*skip\b|\bskip\s*\(|\bskip:\s*true',
        tls=r'VERIFY_NONE|ssl_verify(_mode)?:\s*false|verify_ssl:\s*false',
        disabled=r'#\s*rubocop:disable\b|#\s*brakeman:ignore|\bif\s+false\b|\.html_safe\b|\braw\(|<%==',
        opened=r'\bskip_before_action\b|\bskip_forgery_protection\b|\bskip_authorization\w*|\bskip_policy_scope\b'
        r'|protect_from_forgery\s+with:\s*:null_session|\.permit!'),
    # Java/Spring, Kotlin, Scala, C#/.NET, Swift.
    lang_row(
        'jvm/dotnet/swift', r'\.(java|kt|cs|scala|swift)$', C_COMMENT,
        test_file=r'(Test|Tests|IT|Spec)\.(java|kt|cs|scala|swift)$|(^|/)src/test/',
        func=r'\b(?:def|func|fun)\s+(?:<[^>]+>\s*)?(?:\w+\.)?(\w+)\s*[\[(<]|^\s*(?:(?:public|protected|private|internal|static'
        r'|final|override|virtual|abstract|async|synchronized|open|suspend)\s+)+[\w<>\[\],.?]*\s*(\w+)\s*\(',
        access=r'@(PreAuthorize|PostAuthorize|Secured|RolesAllowed|DenyAll|AuthenticationPrincipal|Valid|Validated)\b'
        r'|\[Authorize\b|\[ValidateAntiForgeryToken\b|\bRequireAuthorization\(|\bIsInRole\(|\b(hasRole|hasAnyRole|hasAuthority'
        r'|hasAnyAuthority|hasPermission|isAuthenticated|isFullyAuthenticated|authenticated|authorizeHttpRequests'
        r'|authorizeRequests|authorizeExchange|requestMatchers|securityMatcher|checkPermission|isAdmin)\b|\bcsrf\b'
        r'|\bHtmlUtils\.htmlEscape|\bStringEscapeUtils\.escape|\bEncode\.for\w+|\bHtmlEncoder\b|\bJsoup\.clean\b|\bsanitiz\w*\(',
        effect=r'\.(delete\w*|save\w*|persist|merge|remove\w*|flush|commit|rollback|send\w*|publish\w*|dispatch|evict'
        r'|invalidate\w*|purge|lock|unlock|release|executeUpdate|update\w*|insert\w*|SaveChanges\w*)\s*\('
        r'|@(Transactional|CacheEvict|CachePut|Async|Scheduled|EventListener|TransactionalEventListener)\b',
        throw=r'\bthrow\b|HttpStatus\.(UNAUTHORIZED|FORBIDDEN)|\b(Forbid|Unauthorized|Challenge)\(\)|\bfatalError\(',
        guard=r'^\s*(}\s*)?(if|else\s+if|while)\b|^\s*guard\b|&&|\|\||\?\?|\?:|\brequire\(|\bcheck\(|requireNonNull\(',
        error=r'\bcatch\b|\btry\s*\{|^\s*finally\b|\brunCatching\b|\.onError\w*\(|\blog(ger)?\.(error|warn)\('
        r'|\bLog(Error|Critical|Warning)\(',
        define=r'@(Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b|\[(Fact|Theory|Test|TestMethod|TestCase)\b'
        r'|^\s*func\s+test\w*\s*\(|^\s*(@\w+\s+)*fun\s+`|\btest\(\s*"',
        assertion=r'\bassert\w*\s*\(|\bAssert\.\w+\(|\bAssertions\.\w+\(|\bverify\(|\bXCTAssert\w*\(|\.Should\(\)'
        r'|\bshould\w*\b|\bexpect\w*\s*\(|#(expect|require)\(',
        skip=r'@(Disabled|Ignore)\w*\b|\[(Ignore|Skip)\b|\bSkip\s*=\s*"|\bXCTSkip\w*\(|\bassumeTrue\(|\bAssume\.\w+\(',
        tls=r'\b(TrustAll\w*|NoopHostnameVerifier|ALLOW_ALL_HOSTNAME_VERIFIER|InsecureTrustManagerFactory)\b'
        r'|ServerCertificateCustomValidationCallback\s*=|DangerousAcceptAnyServerCertificateValidator',
        disabled=r'@SuppressWarnings\b|@Suppress\(|#pragma\s+warning\s+disable|//\s*NOSONAR|^\s*if\s*\(\s*false\s*\)'
        r'|swiftlint:disable',
        opened=r'\bpermitAll\(\)|csrf\(\)\.disable\(\)|\.csrf\(\s*\w+\s*->\s*\w+\.disable\(\)\)|csrf\s*\{\s*disable\(\)'
        r'|\[AllowAnonymous\]|@PermitAll\b|\bIgnoreAntiforgeryToken\b|\bAllowAnonymous\(\)'),
    lang_row(
        'elixir', r'\.exs?$', r'^\s*#', test_file=r'_test\.exs$', func=r'^\s*defp?\s+(\w+[?!]?)',
        access=r'\bplug\s+:?[\w.]*(auth|Auth|require|ensure|Guardian|verify|protect_from_forgery|permission|admin)\w*'
        r'|\bcan\?|\bBodyguard\b|\bauthoriz\w*|\bcurrent_user\b|\bon_mount\b|\bpipe_through\b|CSRFProtection|html_escape',
        effect=r'\bRepo\.(delete|insert|update|delete_all|update_all|insert_all|insert_or_update|transaction)\w*!?'
        r'|\bOban\.insert\w*|\bPubSub\.broadcast\w*|\bCachex\.(del|put|clear)\b|\bEcto\.Multi\b|\bFile\.rm\w*',
        throw=r'\braise\b|\bthrow\b|\bsend_resp\(\s*\w+,\s*40[13]|\bput_status\(.*:(forbidden|unauthorized)|\bhalt\(\)',
        guard=r'^\s*(if|unless|cond|with)\b|\bwhen\b|&&|\|\||\band\b|\bor\b',
        error=r'^\s*rescue\b|^\s*catch\b|\{:error,|\bLogger\.(error|warn)',
        define=r'^\s*(test|describe|property)\s+["\']', assertion=r'\b(assert|refute)\w*\b',
        skip=r'@(module)?tag\s+:skip|@tag\s+skip:', tls=r'verify:\s*:verify_none',
        disabled=r'#\s*credo:disable|@dialyzer\s*\{\s*:nowarn|\bif\s+false\b|\braw\(', opened=NEVER),
    # Django/Jinja/Go html templates under a templates/ dir (prepare's generic group only).
    lang_row(
        'templates', r'\.(html?|jinja2?|j2)$', r'^\s*(\{#|<!--)', generic_only=True,
        func=r'\{%-?\s*(?:block|macro)\s+(\w+)|\{\{-?\s*define\s+"([^"]+)"',
        access=r'\{%-?\s*csrf_token\b|\bcsrf_token\(\)|\bcsrf_input\b|\bperms\.|\bhas_perm\b|\bis_authenticated\b|\bis_staff\b'
        r'|\bcurrent_user\b|\|\s*(escape|e|escapejs|force_escape)\b|\bautoescape\s+(on|true)\b',
        effect=NEVER, throw=NEVER, guard=r'\{%-?\s*(if|elif)\b|\{\{-?\s*(if|else\s+if)\b', error=NEVER,
        define=NEVER, assertion=NEVER, skip=NEVER, tls=NEVER, opened=NEVER,
        disabled=r'\|\s*safe\b|\bautoescape\s+(off|false)\b|\bmark_safe\b|\|\s*safeHTML\b'),
]


def row_for(path, in_generic):
    """The language row for a file outside the Drupal/Next.js/infra groups, or None (LEGACY applies)."""
    return next((r for r in ROWS if r['ext'].search(path) and (in_generic or not r['generic_only'])), None)


def git(repo, *a):
    return subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True, errors='replace').stdout


def parse_hunks(diff):
    """Yield (path, old_start, new_start, lines) per hunk from a unified diff."""
    path, hunk = None, None
    for line in diff.splitlines():
        if line.startswith('diff --git'):
            if hunk:
                yield hunk
            hunk, path = None, None
        elif line.startswith('+++ '):
            path = line[6:] if line.startswith('+++ b/') else path
        elif line.startswith('--- ') and path is None:
            path = line[6:] if line.startswith('--- a/') else None
        elif line.startswith('@@'):
            if hunk:
                yield hunk
            m = re.match(r'@@ -(\d+)(?:,\d+)? \+(\d+)', line)
            hunk = {'path': path, 'old': int(m.group(1)), 'new': int(m.group(2)), 'lines': [line]}
        elif hunk is not None:
            hunk['lines'].append(line)
    if hunk:
        yield hunk


def yaml_keypath(lines, idx):
    """Parent keys of base line idx (0-based) plus its own key, by indentation."""
    if idx >= len(lines):
        return []
    indent = lambda l: len(l) - len(l.lstrip(' '))
    own = YAML_KEY.match(lines[idx])
    path, level = ([own.group(1)] if own else []), indent(lines[idx])
    for j in range(idx - 1, -1, -1):
        l = lines[j]
        if not l.strip() or l.lstrip().startswith('#'):
            continue
        if indent(l) < level or (indent(l) == level and not l.lstrip().startswith('-') and lines[idx].lstrip().startswith('-')):
            m = YAML_KEY.match(l)
            if m:
                path.insert(0, m.group(1))
                level = indent(l)
            if level == 0:
                break
    return path


def norm(s):
    return re.sub(r'\s+', '', s)


def enclosing_function(repo, base, rel, old_line, pat=FUNC):
    src = git(repo, 'show', f'{base}:{rel}').splitlines()
    for i in range(min(old_line, len(src)) - 1, -1, -1):
        m = pat.search(src[i])
        if m:
            name = next(g for g in m.groups() if g)
            if name not in ('if', 'for', 'while', 'switch', 'catch', 'function'):
                return name
    return None


def callers(repo, name, rel):
    if not name or name in ('__construct', 'build', 'create', 'get', 'set', 'save', 'render', 'default'):
        return []
    out = git(repo, 'grep', '-n', '-E', rf'(->|::|\.|\b){re.escape(name)}\s*\(', '--',
              ':!*vendor/*', ':!*node_modules/*', ':!*/contrib/*', ':!docroot/core/*', ':!*.min.js')
    hits = [l for l in out.splitlines() if not l.startswith(f'{rel}:') or 'function' not in l]
    hits = [l for l in hits if not re.search(rf'function\s+{re.escape(name)}\b', l)]
    return hits[:8] if len(hits) <= 30 else hits[:8] + [f'... {len(hits)} hits in total, list cut']


ATOM_SPLIT = re.compile(r'&&|\|\||\band\b|\bor\b')


def atoms(text, row=None):
    """Condition atoms with negation and operator direction erased, so `if (a && b)` split into
    `if (!a) return; if (b)` reads as the same guard."""
    row = row or LEGACY
    inner = row['strip'].sub('', text)
    out = set()
    for part in ATOM_SPLIT.split(inner):
        if row['negation']:
            part = row['negation'].sub('', part)
        a = norm(part).replace('!==', '===').replace('!=', '==').lstrip('!(').rstrip(')')
        if a:
            out.add(a)
    return out


def score(hunk, is_test, is_yaml, added_anywhere, added_atoms, base_lines=None, row=None):
    row = row or LEGACY
    body = hunk['lines'][1:]
    old_no, removed_at = hunk['old'], []
    for l in body:
        if l.startswith('-'):
            removed_at.append(old_no)
        if not l.startswith('+'):
            old_no += 1
    removed = [l[1:] for l in body if l.startswith('-')]
    added = [l[1:] for l in body if l.startswith('+')]
    # A dropped or replaced contrib patch silently drops the fix it carried, like a removed side effect.
    if hunk['path'].endswith('.patch'):
        gone = any(t.strip() for t in removed)
        return (3, ['patch file removed or changed'], True, []) if gone else (0, [], False, [])
    if os.path.basename(hunk['path']) == 'composer.json':
        # Only extra.patches is scored; the rest of the manifest is secperf's dependency review.
        kept = {a.rstrip(',') for a in added_anywhere} | {norm(t).rstrip(',') for t in added}
        gone = [t for t, n in zip(removed, removed_at) if PATCH_ENTRY.search(t) and norm(t).rstrip(',') not in kept
                and 'patches' in yaml_keypath(base_lines or [], n - 1)]
        return (3 * len(gone), ['composer patch removed or replaced'] if gone else [], bool(gone), [])
    pts, labels, blocker, comments = 0, set(), False, []
    signals = row['tests'] if is_test else YAML_SIGNALS if is_yaml else row['signals']

    def hit(w, label, blk):
        nonlocal pts, blocker
        pts += w
        labels.add(label)
        blocker = blocker or blk

    for text, line_no in zip(removed, removed_at):
        if not text.strip() or norm(text) in added_anywhere:  # blank, or moved rather than removed
            continue
        if is_yaml and base_lines:
            keys = ' > '.join(yaml_keypath(base_lines, line_no - 1))
            if GRANT_KEY.search(keys):
                hit(4, f'grant or requirement removed ({keys})', True)
                continue
            if SWITCH_KEY.search(keys):
                hit(4, f'security switch changed ({keys})', True)
                continue
            if LIMIT_KEY.search(keys):
                # Widget and listing settings are UI; they go to the unselected list, not the challenger.
                ui = re.search(r'core\.entity_(form|view)_display\.|views\.view\.', hunk['path'])
                hit(1 if ui else 3, f'limit changed ({keys})', False)
                continue
        if not is_yaml and row['comment'].match(text):
            comments.append(text.strip())
            continue
        for w, label, pat, blk in signals:
            if pat.search(text):
                if label == 'guard condition' and atoms(text, row) <= added_atoms:
                    continue  # same guard, restructured
                hit(w, label, blk)
    for text in added:
        for w, label, pat, blk in row['added']:
            if pat.search(text):
                hit(w, label, blk)
    added_comments = sum(1 for t in added if row['comment'].match(t))
    if pts and len(comments) > added_comments:
        pts *= 3
        labels.add('removed comment explains it')
    return pts, sorted(labels), blocker, comments


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base')
    ap.add_argument('--pair')
    ap.add_argument('--intent')
    ap.add_argument('--path')
    ap.add_argument('--force-wide', action='store_true')
    ap.add_argument('--cap', type=int, default=CAP)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    root = prepare.git(os.getcwd(), 'rev-parse', '--show-toplevel')
    os.makedirs(a.out, exist_ok=True)
    intent = os.path.abspath(a.intent) if a.intent else None
    if intent and not os.path.isfile(intent):
        sys.exit(f'--intent file not found: {intent}')
    if a.pair:
        pair = prepare.git(os.path.abspath(a.pair), 'rev-parse', '--show-toplevel')
        display = os.path.commonpath([root, pair])
        parts = [prepare.collect(root, a.base, a.path, None, os.path.relpath(root, display), a.force_wide),
                 prepare.collect(pair, a.base, None, None, os.path.relpath(pair, display), a.force_wide)]
    else:
        display = root
        parts = [prepare.collect(root, a.base, a.path, None, '', a.force_wide)]

    candidates, below, reviewed, tests, base_cache, seen_patches = [], [], 0, 0, {}, set()
    not_covered = []
    for p in parts:
        repo, base, label = p['repo']['root'], p['repo']['base'], p['repo']['label'] if a.pair else ''
        show = lambda f: f'{label}/{f}' if label else f
        code = {e['rel'] for g in ('drupal', 'nextjs', 'infra') for e in p['groups'][g] if e['status'] != 'U'}
        generic = {e['rel'] for e in p['groups'].get('generic', []) if e['status'] != 'U'}
        # Tests are excluded from secperf scope but deleted assertions are exactly what we want here.
        changed = git(repo, 'diff', '--name-only', base).splitlines()
        test_files = {f for f in changed if TEST_FILE.search(f) or any(r['test_file'] and r['test_file'].search(f) for r in ROWS)}
        # Manifests and patch files are outside secperf's code groups, but a dropped patch removes a fix.
        # --no-renames: a patch swapped for a similar file must bring its deleted source into the pathspec.
        patch_files = {f for f in git(repo, 'diff', '--name-only', '--no-renames', base).splitlines()
                       if f.endswith('.patch') or os.path.basename(f) == 'composer.json'}
        # Drupal/Next.js/infra code keeps the LEGACY row; other stacks and their tests get a language row.
        rows = {f: row_for(f, f in generic) for f in (generic | test_files) - code}
        lang_files = {f for f, r in rows.items() if r}
        legacy_files = (code | test_files | patch_files) - lang_files
        not_covered += [show(f) for f in sorted(generic - lang_files)] + p.get('unclassified', [])
        reviewed += len(code | generic)
        tests += len(test_files)
        # Separate passes: moved-line and restructured-guard detection stay within one row family.
        for pass_files, lang in ((legacy_files, False), (lang_files, True)):
            # Files git itself marks as binary yield no hunks; these are the ones it may diff as text.
            files = sorted(f for f in pass_files if not BINARY.search(f))
            if not files:
                continue
            diff = git(repo, 'diff', '--diff-algorithm=patience', '-M', '-U3', base, '--', *files)
            hunks = list(parse_hunks(diff))
            added_lines = [l[1:] for h in hunks for l in h['lines'][1:] if l.startswith('+') and l[1:].strip()]
            added = {norm(l) for l in added_lines}
            atom_row = GENERIC_ATOMS if lang else LEGACY
            added_atoms = set().union(*(atoms(l, atom_row) for l in added_lines)) if added_lines else set()
            for h in hunks:
                if not h['path']:
                    continue
                row = (rows.get(h['path']) or LEGACY) if lang else LEGACY
                candidates_from(h, row, repo, base, show, added, added_atoms, base_cache, seen_patches, candidates, below)

    candidates.sort(key=lambda c: (-c['score'], c['file'], c['old_line']))
    selected = candidates[:a.cap]
    unselected = [{k: c[k] for k in ('file', 'old_line', 'score', 'signals')} for c in candidates[a.cap:]] + below
    lines = ['# Unselected candidates', '', 'Hunks that scored but did not reach the challenger (below threshold '
             f'{MIN_SCORE} or beyond the cap {a.cap}). A reviewer clears each in one line or raises it.', '']
    lines += [f"- `{c['file']}` old line {c['old_line']}: score {c['score']}, {', '.join(c['signals'])}" for c in unselected] or ['- none']
    if not_covered:
        lines += ['', '# Not covered', '', 'Changed code files no stack row classifies; nothing above looked at them.', '']
        lines += [f'- `{f}`' for f in not_covered]
    open(os.path.join(a.out, 'candidates.md'), 'w').write('\n'.join(lines) + '\n')
    for i, c in enumerate(selected, 1):
        c['id'] = f'H{i}'
    return finish(a, parts, display, intent, candidates, selected, unselected, reviewed, tests, not_covered)


def candidates_from(h, row, repo, base, show, added, added_atoms, base_cache, seen_patches, candidates, below):
    """Score one hunk with its row; append it to candidates (>= MIN_SCORE) or to below (scored under it)."""
    is_test = bool(TEST_FILE.search(h['path']) or (row['test_file'] and row['test_file'].search(h['path'])))
    is_yaml = h['path'].endswith(('.yml', '.yaml'))
    is_patch = h['path'].endswith(('.patch', 'composer.json'))
    if (is_yaml or is_patch) and h['path'] not in base_cache:
        base_cache[h['path']] = git(repo, 'show', f'{base}:{h["path"]}').splitlines()
    pts, labels, blocker, comments = score(h, is_test, is_yaml, added, added_atoms, base_cache.get(h['path']), row)
    if 0 < pts < MIN_SCORE:
        below.append({'file': show(h['path']), 'old_line': h['old'], 'score': pts, 'signals': labels})
    if pts < MIN_SCORE or (h['path'].endswith('.patch') and h['path'] in seen_patches):
        return  # one question per patch file, however many hunks a reroll produces
    seen_patches.add(h['path'])
    fn = None if is_patch else enclosing_function(repo, base, h['path'], h['old'], row['func'])
    candidates.append({
        'file': show(h['path']), 'repo': repo, 'rel': h['path'], 'base': base,
        'old_line': h['old'], 'new_line': h['new'], 'score': pts, 'signals': labels, 'blocker': blocker,
        'test_file': is_test, 'function': fn, 'removed_comments': comments,
        'callers': [] if is_test else callers(repo, fn, h['path']),
        'hunk': '\n'.join(h['lines'][:HUNK_LINES]) + ('\n... hunk cut' if len(h['lines']) > HUNK_LINES else ''),
    })


def finish(a, parts, display, intent, candidates, selected, unselected, reviewed, tests, not_covered):
    """Write brief.md and hunks.json, print the summary."""
    brief = [f'# Challenge brief', '', f'Repos: ' + '; '.join(f"{p['repo']['label']} = {p['repo']['root']} "
             f"(base {p['repo']['baseLabel']} = {p['repo']['base'][:10]}, branch {p['repo']['branch']})" for p in parts),
             f'Paths are relative to {display}. Read a file as it is after the change from the working tree; '
             f'read it before the change with `git -C <repo> show <base>:<path>`.',
             f'Intent (acceptance criteria): {intent or "NONE AVAILABLE. Do not infer intent from commit messages."}',
             f'Selected {len(selected)} of {len(candidates)} candidate hunks (cap {a.cap}).', '']
    for c in selected:
        brief += [f'## {c["id"]} · {c["file"]} (old line {c["old_line"]}, new line {c["new_line"]})',
                  f'Score {c["score"]}, signals: {", ".join(c["signals"])}{" · BLOCKER-CLASS" if c["blocker"] else ""}'
                  f'{" · test file" if c["test_file"] else ""}',
                  f'Enclosing function (before the change): {c["function"] or "unknown"}']
        if c['removed_comments']:
            brief += ['Removed comments (the author\'s stated reason for the old code):'] + [f'> {x}' for x in c['removed_comments']]
        if c['callers']:
            brief += ['Callers of the enclosing function (git grep, current tree):', '```'] + c['callers'] + ['```']
        brief += ['```diff', c['hunk'], '```', '']

    json.dump({'repos': [p['repo'] for p in parts], 'intent': intent, 'candidates': len(candidates), 'unselected': unselected,
               'selected': selected, 'blocker': any(c['blocker'] for c in selected), 'not_covered': not_covered},
              open(os.path.join(a.out, 'hunks.json'), 'w'), indent=1)
    open(os.path.join(a.out, 'brief.md'), 'w').write('\n'.join(brief))
    print(json.dumps({'brief': os.path.join(a.out, 'brief.md'), 'code_files': reviewed, 'test_files': tests,
                      'candidates': len(candidates), 'unselected': len(unselected), 'selected': [(c['id'], c['file'], c['old_line'], c['score'],
                      c['signals'], c['blocker']) for c in selected], 'blocker': any(c['blocker'] for c in selected),
                      'intent': intent, 'notes': [n for p in parts for n in p['notes']], 'not_covered': not_covered}, indent=1))


if __name__ == '__main__':
    main()
