# Separate SearXNG licensing

The first-party ai-harness adapter, configuration and helpers are MIT licensed.
SearXNG is a separate service and is **AGPL-3.0-or-later**, not relicensed by
ai-harness. Its copyright remains with SearXNG contributors. The verbatim license
is retained as `LICENSE-AGPL-3.0.txt` (copied from the pinned source).

- Official source: https://github.com/searxng/searxng
- Exact source: https://github.com/searxng/searxng/tree/df67eb6c2608c5b2f909ed7c42b0a4bd3823f78f
- Version: `2026.9.21-df67eb6c2`
- Official registry: https://github.com/searxng/searxng/pkgs/container/searxng
- Digest and OCI source labels: `image-pin.json`.
- Official registry reference: https://docs.searxng.org/admin/installation-docker.html
- JSON search API: https://docs.searxng.org/dev/search_api.html

When distributing the service/container, retain its notices and provide the
corresponding source and applicable license. Network users of a modified AGPL
service must receive the required source offer. Keep those obligations separate
from first-party MIT source. The proposed configuration uses only public engines
without API keys; no paid or cloud-account fallback is implemented by the adapter.
