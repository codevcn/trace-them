# Email resolver: source contract and verification

Provider: **Gravatar Public Profiles API v3**, GET
`https://api.gravatar.com/v3/profiles/{sha256}`. Hashing follows provider rules:
trim, lowercase the entire email, then SHA-256. This provider-specific operation
does not change the original input's local part or imply universal email aliases.

Official sources consulted during implementation:

- [REST API](https://docs.gravatar.com/rest-api/): public profile lookup by email
  hash, optional Authorization header, limited anonymous access, 404/429/errors.
- [Email hashing](https://docs.gravatar.com/rest/hash/).
- [Current OpenAPI](https://api.gravatar.com/v3/openapi): live schema retrieved.
- [Profile privacy](https://support.gravatar.com/privacy-and-security/profile-access/):
  users can hide profiles; last-updated date displayed October 17, 2026.

Verification used fresh HTTP requests on 2026-11-16 UTC (2026-11-17 Asia/Saigon).
Only two synthetic/documentation-example identifiers were queried:

| Identifier | HTTP | Response |
|---|---|---|
| `trace-them-probe@example.invalid` | 404 | JSON `Profile not found` |
| `MyEmailAddress@example.com` (official hashing example) | 404 | JSON `Profile not found` |

No unrelated person's real email was used. Raw sanitized verification metadata is
stored locally in `.work/gravatar-verification.json`. These requests verify live
reachability and negative-response behavior. They do **not** establish a live
positive lookup. Positive responses, malformed data, hash mismatch, auth/config,
rate limit, server errors, offline, budget and association scope are fixture-tested.

A successful response must contain a matching email identifier and a valid HTTPS
Gravatar profile URL. The implementation records `source_reported` association
only on that direct provider finding. A matching slug elsewhere remains
`unverified`; provider association evidence never transfers through username reuse.

`GRAVATAR_API_KEY` is optional and read from the environment; no key was requested
or used during verification. 401 becomes `missing_config`, 403 `blocked`, 429
`rate_limited`, 5xx `error`, and 404 source-scoped `not_found`. Offline returns
`unsupported` with an explicit explanation. Hidden or secondary-email profiles
may not resolve; absence is never a conclusion about all registered accounts.

The source exposes public profiles. Registration, login, password-reset and avatar
existence checks are not used. Linked accounts and arbitrary profile URLs returned
by the source are not recursively queried in this version.

A subsequent end-to-end CLI smoke check queried only
`trace-them-probe@example.invalid` with a one-request budget and zero retries.
It returned a source-scoped `not_found`, with exactly one wire request used;
the canonical report is retained in `.work/resolver-live.json`.
