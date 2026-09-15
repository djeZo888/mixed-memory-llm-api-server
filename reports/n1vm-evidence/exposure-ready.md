# N1VM exposure ready — GLM transport only

- UTC verified: 2026-09-15T02:46:51.244732+00:00; enabled UTC: 2026-09-15T02:46:50.260625+00:00.
- Endpoint: `http://10.156.100.60:30002/v1`, interface `enp6s18`, allowed LAN `10.156.100.0/24`.
- Transport gates PASS: actual Linux verify all six units with no diagnostics; exact helper/policy/unit bytes and protected metadata; effective owned first INPUT jump and narrow allow/drop chain; unrelated IPv4 filter unchanged.
- Enabled/active ONLY `llm-private-glm.socket`; control30000 and Qwen30004 sockets disabled/inactive, upstreams absent/not ready. Matching listeners exactly private10.156.100.60:30002 and unchanged native127.0.0.1:30002; no matching IPv6/wildcard listener.
- Native auth readiness PASS: GET /v1/models missing401, wrong401, correct200; model glm-5.3, context32768; correct-key /health200 ok. Key read only via protected descriptor into memory. No generation.
- Running GLM unchanged: container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`; PID149976; started 2026-09-15T00:48:45.235739944Z; restart_count0; command SHA256 `89510f6d1b0ede1ae1bba8a1f9097c42fa063f2196ee14c000e6c9810e7fae00`; native publication127.0.0.1:30002; model boot remains manual/Docker restart=no.
- Exact protected D3 guard hashes/metadata and both mount UUIDs verified; require-data-mounted and root-disk-guard PASS after activation. Root available 5210513408 bytes (4.853 GiB): WARN below6GiB, above4GiB STOP.
- Evidence root: `/data/services/n1vm-20260915`; reviewable local evidence under `../evidence/`.

Worker2 may coordinate its separate-host direct authentication/SSE/agent acceptance now. Worker1 has made no direct private API/generation requests. Socket/TCP openness alone does not prove model readiness. Complete direct acceptance, control and Qwen remain pending their owners.
