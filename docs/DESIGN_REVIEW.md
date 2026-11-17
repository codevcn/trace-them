# Independent design review

Reviewed: `docs/IMPLEMENTATION.md` and original manifest/engine. This is a design
review; implementation findings will be recorded separately after integration.

## Findings and required acceptance cases

1. **High — association must remain scoped to its source.** A direct email match
   establishes a source-reported association on that provider only. Candidate
   evidence can explain discovery but must not populate another platform's
   association evidence. Export tests must assert this in JSON, TXT, CSV and XLSX.
   Source-reported association is not proof of present mailbox ownership.
2. **High — negative-message detectors need ambiguity guards.** An absent
   `errorMsg` in an empty page, generic login wall, JavaScript shell, JSON error,
   WAF response or 5xx must not become FOUND. Prefer UNKNOWN for ambiguous bodies.
   Test empty HTTP 200 and authentication redirects, including HEAD behavior.
3. **High — policy applies to remote/custom manifests too.** The original manifest
   includes registration availability checks (Discord, Chess, Holopin, Minds,
   DailyKos, BoardGameGeek, Diskusjon, Kvinneguiden and omg.lol). Filtering only
   bundled target names would allow the same probe to be renamed or supplied in a
   custom manifest. Match actual endpoint semantics/paths and document residual
   limits. Original records should remain available for audit, not execution.
4. **High — redirects need explicit credential and method rules.** Every network
   hop consumes the run budget. Cross-origin redirects must not forward user
   Authorization/Cookie/Host headers. Honor bounded redirect counts and HTTP
   method semantics. Login redirects should remain BLOCKED/UNKNOWN rather than
   becoming a successful profile response.
5. **Medium — deferred retry must preserve the cause.** If Retry-After exceeds
   the allowed wait, report RATE_LIMITED for 429 rather than an unrelated ERROR;
   budget exhaustion and cancellation must also remain distinguishable.
6. **Medium — bounded request count is not bounded response size.** Profile
   responses can be very large. Avoid unbounded body retention in every finding;
   set a practical body limit or clearly document this limitation. Persist only
   evidence snippets and relevant metadata, not full response bodies by default.
7. **Medium — offline acceptance includes auxiliary integrations.** Test update,
   manifest, resolver, exclusions and subprocess paths, with network denied by
   default. Do not label offline UNKNOWN as NOT_FOUND or email no-match.
8. **Medium — data export needs evidence and literal cell handling.** Protect
   dangerous spreadsheet prefixes even after leading whitespace/control chars;
   preserve distinctions between source association and inferred candidates.
   Filenames derived from Unicode/email must be contained in the output directory,
   safe for Windows reserved names, and collision-resistant.
9. **Medium — no Git baseline requires a reproducible comparison.** Use the
   archived original and hashes for final changed-file reporting. Do not claim
   a Git diff or pre-existing clean working tree.

## Architecture assessment

The proposed module boundaries and JSON-first output suit the project size.
Python 3.10+ is consistent with union syntax already present. A single verified
provider is a reasonable email MVP; provider absence must remain an explicit
unsupported/configuration result rather than synthetic discovery.

The reviewer has not executed network tests, modified production files, or
verified any email provider at this design stage.
