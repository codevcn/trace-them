# Independent QA plan

The QA role owns tests, not production implementation. Baseline tests were read
before migration. They exercise manifest schema/iteration, live target outcomes,
invalid usernames, NSFW filtering, wildcard expansion, CLI usage/version, and
Unicode exceptions. The upstream source is archived in `.work/baseline.zip`.

## Verification approach

- Offline is the default. A global network guard prevents accidental external
  requests. Mocked HTTP sessions exercise transport without opening sockets.
- Test observable behavior rather than copied implementation logic.
- Model fixtures use fabricated handles and reserved `example.com` addresses.
- Keep online tests explicit and opt-in; never use unrelated personal email.
- Separate existence from association and test that same usernames cannot
  upgrade an email linkage on another platform.

## Test matrix

1. Detector: found/not-found, message/status/redirect methods, login wall,
   captcha/WAF, throttling, server failures, malformed manifest rules.
2. Transport: shared budget per actual request, retry and redirect; retry-after
   bounds; offline; cancellation; timeout settings; domain pacing; close.
3. Scanner: regex invalidation without network; safe Unicode handling; caller
   manifest immutability; error statuses; source evidence and association scope.
4. Manifest: all 481 original records remain available for audit; legacy schema
   compatibility; NSFW/selection handling; auth-enumeration policy; invalid input.
5. Resolver: source-specific direct profiles, no-match/unsupported/error/rate-limit,
   missing configuration, inferred candidates are explicit and bounded.
6. Reporting: schema-valid JSON and consistent TXT/CSV/XLSX evidence, literal
   spreadsheet cells, filenames cannot escape output root, malformed input.
7. CLI/integration: usage/version, exact username, offline never opens network,
   JSON stdout and progress stderr, global budget, bounded candidate estimates,
   packaging metadata and Apify JSON handling.

## Acceptance reporting

Record command, result and meaningful limits. Package, Docker and Apify runtime
checks unavailable locally must not be represented as passing runtime checks.
