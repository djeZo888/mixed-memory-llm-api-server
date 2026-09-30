# Private SearXNG MCP adapter

First-party MIT code. Runs under Node 24 using the official MCP SDK's stdio
transport, initialization, version negotiation, tool schema and cancellation.
No browser server, inference calls, credentials or cloud fallback are required.
The separate SearXNG service is AGPL software; see `../searxng/` for its proposal
and notices. Installation does not start or contact that service.

## Image dependency contract

Copy this entire directory to `/opt/ai-harness/tools/search` and retain its
`package.json`, `package-lock.json` and dependency licenses. PREP's agreed build
context is `ai-harness/`; its Containerfile fragment is:

```dockerfile
COPY tools/ /opt/ai-harness/tools/
COPY skills/ /opt/ai-harness/skills/
RUN cd /opt/ai-harness/tools/search && npm ci --omit=dev --ignore-scripts
```

Direct dependencies are exactly `@modelcontextprotocol/sdk@1.30.0` and
`zod@4.6.5`. The npm v3 lockfile pins transitive versions and integrity hashes.
The SDK v1 maintenance line is intentional: it is upstream maintained and offers
compatible native stdio MCP without introducing v2 protocol requirements.
No extra host mounts or global packages are needed. `npm ci` downloads build-time
packages; runtime search only contacts the configured private endpoint.

PREP should render the following entry into the existing per-session profile
file `${MINIMAX_DATA_DIR}/mcp.json` (no leading dot), merging other reviewed
entries. The endpoint shown is the deployment candidate; profile generation must
write the actual operator-selected literal URL into `env`:

```json
{
  "mcpServers": {
    "searxng": {
      "command": "node",
      "args": ["/opt/ai-harness/tools/search/searxng-mcp.mjs"],
      "timeout": 20000,
      "env": {
        "AI_HARNESS_SEARXNG_URL": "http://10.0.2.2:8082"
      }
    }
  }
}
```

At pinned MiniMax revision `ae65651df5f97ae1085ab4e19964f4b78c769a4e`, profile MCP
configuration passes `env` values through literally; it does **not** expand
`${AI_HARNESS_SEARXNG_URL}`. The separate workspace `.mcp.json` loader does perform
environment expansion. Therefore `mcpServers.example.json` is a **workspace-only
alternative**, for the canonical conversation workspace root, and must not be
copied unchanged into the profile. The deployment contract uses the profile
entry above and needs no extra host mounts. A same-named project or ACP session
entry can override the profile entry under native precedence; configuration
ownership and acceptance belong to PREP/root.

The native `timeout: 20000` is in milliseconds and exceeds the adapter's own
10-second deadline. Entrypoint:
`node /opt/ai-harness/tools/search/searxng-mcp.mjs`. stdout is exclusively MCP
messages during normal operation; safe diagnostics go to stderr. `--help` prints CLI
documentation without making any network request.

`AI_HARNESS_SEARXNG_URL` is required **operator configuration**, never a tool
argument. It accepts an HTTP(S) base URL with a private or loopback literal IPv4
address; credentials, DNS names, non-root paths, queries and fragments fail
startup. Candidate rootless-engine value: `http://10.0.2.2:8082`. PREP must verify
that its private transport can reach the host listener `127.0.0.1:8082`. The
adapter appends `/search`, uses GET with `format=json`, `pageno=1` and
`categories=general`, and never follows redirects. Configure SearXNG to enable
JSON output. The URL is not a user-controlled proxy, browser or download input.

## Tool and output

`searxng_search` accepts only:

```json
{"query":"manufacturer component datasheet", "limit":5}
```

- Query: trimmed, 1–512 UTF-16 code units; no control/formatting characters.
- Limit: integer 1–10, default 5. No URL or endpoint override fields.
- Two simultaneous requests per adapter; excess requests fail with `BUSY`.
- Whole request deadline: 10 seconds, including body reading. SDK cancellation
  aborts the HTTP request; session close and SIGTERM/SIGINT abort active work.
- Body: at most 1 MiB of decompressed bytes; valid UTF-8 JSON with a results
  array. Maximum 100 candidates scanned. No retries or fallback engines here.
- One JSON text content block with `query`, `results: [{title,url,snippet}]`,
  `truncated` (omitted result records), `notice` and optional coverage `warning`.
- HTTP(S) source URLs only, no credentials/controls, at most 2,048 bytes; local
  and private IP literals are filtered. Links are returned **without fetching**.
  DNS resolution and browser destination access are separate native-browser
  responsibilities; this adapter is not their network sandbox.
- HTML-like tags, controls and formatting controls are removed from titles and
  snippets; common HTML entities are decoded. Titles cap at 256 Unicode code
  points, snippets at 1,600, and the JSON text block at 48 KiB. These are lossy
  search summaries. Read the cited page for exact quotations or technical facts.
- Results remain untrusted data; sanitized text is not an instruction boundary.
  The calling agent must ignore instructions embedded in fetched content.

Tool errors use MCP `isError: true` with a bounded JSON `error.code` and
`error.message`. Codes include `BUSY`, `UPSTREAM_HTTP`, `UPSTREAM_FORMAT`,
`UPSTREAM_TOO_LARGE`, `UPSTREAM_UNAVAILABLE`, `TIMEOUT` and `CANCELLED`. The SDK
owns schema/protocol errors. On explicit client cancellation, the SDK may
suppress the tool reply; a cancellation is not a successful search.

The transport rejects an input buffer exceeding 64 KiB using the official SDK
option. The endpoint and queries are never printed to logs. No upstream error
body, redirect location or network exception detail is returned.

## Verification

From this directory, `npm ci --ignore-scripts` then `npm test`. Tests use an
actual SDK client and spawned stdio adapter with a worker-loopback HTTP fixture.
They cover initialization/listing/calls, schema rejection, successful result
limits, malformed/error/oversized bodies, real 10-second header/body deadlines,
redirect refusal, cancellation, concurrency and output byte limits. Test logs
belong outside Git. This does not establish public-search quality, Linux
container reachability or native MiniMax integration; those require separately
authorized acceptance.
