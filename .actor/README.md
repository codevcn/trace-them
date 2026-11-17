# Trace Them Actor adapter

This wrapper runs the Trace Them checkout as an Apify Actor. It preserves the
complete versioned JSON report, including candidate origins, source-specific
email associations, evidence, skipped targets and request usage. One Actor run
stores one report as one dataset item. It does not parse TXT or reduce findings
to a list of links.

## Input

Supply exactly one of `usernames` (one to 100 nonempty strings) or `email`:

```json
{
  "usernames": ["example_handle"],
  "sites": ["GitHub"],
  "maxRequests": 20
}
```

```json
{
  "email": "trace-them-test@example.com",
  "candidates": false,
  "maxRequests": 5
}
```

Email uses the public Gravatar resolver. No public match is a valid result; the
adapter never manufactures an email association from the email local-part.
Enable `candidates` explicitly to scan inferred handles, with `candidateLimit`
between 1 and 10. All usernames/candidates and resolver requests share
`maxRequests` (default 500), including retries and redirects. Apify input/storage
operations are separate from the profile-source budget.

Optional `sites` filters username scans. Source-policy exclusions remain enforced.
`offline: true` disables all profile-source network access and records unqueried
results. Actor input and dataset storage still use Apify runtime services.
Unknown fields, simultaneous username/email input and wrong types are rejected.
The runtime wrapper enforces mutual exclusion even though the Console form shows
both optional input fields. No credentials belong in the input object.

## Run the local checkout

Install Python 3.10+ and Node.js 22+, then from the project root:

```bash
python -m pip install .
npm install --global apify-cli@1.12.0
```

In an appropriately configured Apify runtime, execute:

```bash
python .actor/run_actor.py
```

The wrapper uses subprocess argument arrays without a shell. It reads input with
`apify actor get-input`, runs `trace-them find`, and passes canonical JSON on stdin
to `apify actor push-data`. Input emails and report contents are not logged by
the adapter. The CLI report itself intentionally contains the supplied identity;
dataset access should be configured accordingly.

The Dockerfile installs the package from this checkout rather than a released
Sherlock image. Build locally from the project root with:

```bash
docker build -f .actor/Dockerfile -t trace-them-actor .
```

This task did not publish or deploy an Actor. Actual Apify storage, Docker build
and platform execution require their respective runtimes and are separate from
the offline adapter tests. `build_command()` and `run_actor(..., runner=...)`
allow argument safety and evidence round-trip tests without platform access.

Runtime command and stdin behavior were checked against the
[official CLI reference](https://docs.apify.com/cli/docs/reference#actor-push-data)
and [official push-data implementation](https://github.com/apify/apify-cli/blob/master/src/commands/actor/push-data.ts).
The package metadata reports Apify CLI 1.12.0 requires Node.js 22 or newer.

Trace Them is derived from Sherlock; upstream copyright and license information
are retained in the project LICENSE and NOTICE files.
