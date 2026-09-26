# Offline tokenizer evidence

`tokenizer-fixtures.json` is an unchanged copy of Worker1's supplied
TOKENIZER-FIXTURES.json dated 2026-09-26T16:56:03.699218+00:00.
Full provenance, inputs, exact counts (36,42,212), output hashes and tool-call
JSON-string normalization are retained. These are actual pinned offline tokenizer
results. Gateway HTTP servers in tests are synthetic loopback responders; backend
HTTP parity and all live inference remain untested. Fixtures contain deliberately
synthetic messages/tool history, no credentials or user documents.
