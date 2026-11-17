# Public-source manifest policy

Trace Them retains all 481 original Sherlock records in
`trace_them/resources/data.json`. No removed target is silently rewritten or
replaced. This file is a compatibility input, not a certification of accuracy.

The loader applies public-source policy before any query, including for explicit
`--site` choices, remote manifests and custom manifests with renamed targets.
It recognizes registration/authentication/availability endpoint semantics and
refuses cookie-dependent or mutating PUT probes. A target must have a
username-specific public profile URL. Public read-only profile APIs, including
GraphQL profile queries, remain usable. Public developer pages and group pages
are web presences, not proof of an individual person's identity.

## Static audit and coverage

`trace_them/resources/source-policy.json` records the classification, original
probe URL and rationale for every original target. This was a static review of
the checked-in configuration. It did not make 481 live requests and does not
claim that all allowed sites remain operational or accurate.

Eleven targets are excluded by source policy:

| Target | Reason |
| --- | --- |
| BoardGameGeek | Registration username validation |
| Chess | Username validation |
| Discord | Registration username-attempt |
| Diskusjon.no | Registration usernameExists |
| Holopin | Authentication username validation |
| Kvinneguiden | Registration usernameExists |
| dailykos | Signup nickname validation |
| minds | Registration username validation |
| omg.lol | Address availability |
| HudsonRock | Breach-associated lookup rather than public profile |
| LibraryThing | Manufactured human-verification cookie in legacy headers |

Thus 470 targets remain policy-eligible. Nineteen NSFW targets are additionally
disabled by default, leaving 451 default targets. `--nsfw` enables those 19;
it never overrides source policy. Reports expose skipped targets and reasons.

## Compatibility and source management

The legacy mapping and `errorType` fields remain supported. The loader validates
HTTP(S) URL shape, header values, regex compilation, error markers and request
methods before scanning. Legacy unqualified `errorUrl` values remain accepted,
but ambiguous redirects are unknown rather than assumed absent. Username handles
are URL-encoded before interpolation. Profile matching is still heuristic.

Transport bodies are streamed with a 2 MiB decompressed limit; exceeding that
limit yields a request error, never absence. Sessions do not load environment
proxies or `.netrc` credentials. Explicit proxy configuration is supported.
Cross-origin redirects drop explicit credentials and cookies and clear the
thread-local cookie jar. Redirect method changes follow HTTP semantics and all
hops consume the same run budget. Intermediate authentication redirects remain
visible in evidence and are classified as blocked even if the final page is 200.

Bundled data is the deterministic default. No update checks or remote exclusion
lists are automatically downloaded. An explicit remote manifest uses the same
bounded HTTP transport and request budget as the scan, and is rejected offline.
Remote failures do not silently substitute a different manifest. Upstream data
can be manually supplied through the manifest option; policy still applies.

Endpoint rules are a conservative static filter, not a semantic proof that an
arbitrary external API is public profile data. New source integrations still
need review of their actual response semantics. Keep this audit up to date when
editing the bundled manifest.
