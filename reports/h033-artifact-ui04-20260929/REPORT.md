# H033 ARTIFACTUI04 result

Completed source-only at 2026-09-29 15:47:14 UTC, before the 15:57 UTC hard stop.
Source commit: `5f8f1790b1c61af799be47a3aef5c6b97508d7fd`. Required base: `ed135c7802f9e0a1c3c30b3b0e527c8bb5f386f6`.

The existing Markdown component now renders inline-code text exactly equal to an unambiguous owned artifact download route as **Download <metadata filename>**. It reuses the existing `artifactDownloadUrl` helper and `MarkdownAnchor` download behavior: same-origin URL and boolean download attribute, matching the artifact card without overriding the server filename/access contract. Rendering leaves the original stored message text unchanged.

Only two owned web files changed:
- `ai-harness/web/src/Markdown.tsx` (24 added / 3 removed lines)
- `ai-harness/web/tests/markdown-downloads.test.tsx` (new focused component tests)

Unknown and cross-run URLs, artifact aliases/paths/preview URLs, substring/query/fragment variants, executable schemes, ambiguous catalog matches and invalid IDs stay code. Fenced/indented examples and inline code within authored links stay code. No Markdown source rewriting, ownership/grouping changes, server changes or policy changes.

## Validation

- Focused web tests: **41 passed across 3 files**, exit 0. Actual component output verified for owned links, cross-run exclusion, unchanged message content, image rendering, and parity with real artifact-card href/download/filename behavior.
- Web build: **passed once**, exit 0 (`tsc --noEmit && vite build`).
- Exact diff read-only review: no blocking findings.
- `git diff --check`: passed. Incremental bundle verified; sole prerequisite is the required base.
- Cached declared and installed dependency versions match; no install performed. Temporary dependency symlink removed after validation.
- INBOX reread immediately before final commit/export; consumed the relative-route confirmation and independent static-packet direction.

## Handoff

`PLAN.md` and initial `EARLY.patch` were first saved at approximately 15:43 UTC (within the first three minutes); early patch later refreshed with focused tests and matches `FINAL.patch`.

- `H033-ARTIFACTUI04.bundle`: incremental source bundle; commit and prerequisite above.
- `EARLY.patch`, `FINAL.patch`: exact source/test diffs.
- `web-focused-tests.log`, `web-build.log`, `dependency-cache-check.log`, `bundle-verify.log`: validation evidence.
- `built-web.tar.gz`: built static `dist` contents, with `index.html` at archive root.
- `RESULT.json`, `SHA256SUMS`, `built-web-files.SHA256SUMS`: result and integrity records.

This is a local source/build result, **not deployment or live acceptance**. No VM/ai-harness calls, generation, deployment, tickets or push occurred. W2 owns any later static deployment at idle. The wrapper must record the real native process exit before cleanup; this report does not claim that exit in advance.
