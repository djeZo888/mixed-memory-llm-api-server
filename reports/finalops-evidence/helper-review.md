# C1 minimal helper source review

Prepared 2026-09-17T07:34:24.183464+00:00; no VM contact. Root authorization is the appended section in incoming.md.

- Source: c1_scoped_cleanup.py, SHA256 `c0270cda697ec29bdb71cd1e23e92a4e646bc610dc14e2715537158df353438e`.
- Local cases: test_c1_scoped_cleanup.py, SHA256 `c7e4bddd5dd1800f7afc8aa3378b05c41a999608bd0b4bace97440211cc6a4ad`.
- `python3 -B c1_scoped_cleanup.py --help`: PASS.
- `python3 -B test_c1_scoped_cleanup.py`: 11/11 PASS, Python3.14.7 macOS, 0.009s. Actual local directory-FD traversal/deletion exercised only inside task-local synthetic temporary trees. Production allowlist was replaced only by test-module mocks; no production path/owner overrides exist.
- Cases: dry-run immutability and exact deletion with retained neighbor; parent/unknown/traversal path refusal; target/descendant symlinks; external hardlink; FIFO; same-device nested mount/wrong fsroot; writable parent; missing/false/unknown gate; root replacement during gate; descendant metadata drift during gate; mid-delete partial failure propagation.

CLI accepts only `--root` (four fixed literals) plus required `--dry-run`; it reports TREE_DRY_RUN_ONLY and non_use_clearance=false. No CLI apply bypass. The approved runner imports `apply_reviewed(root, reviewed, gate)` after root accepts that fresh live snapshot. Gate must return exactly True after canonical-lease, root/client-idle, storage/UUID/root-floor, current-use/process/acquisition/container and reference checks. It must retain ownership through deletion. The helper rechecks complete tree metadata and mount/ancestor/root identity after the gate, calls fd-safe shutil.rmtree, fsyncs and proves absence. No guard/ownership/current-use callback has been implemented or executed against ai-vm yet.

UUID authority, manifests/content identity, privileged process visibility, acquisition ownership, operational-reference retirement and retained-model health remain surrounding runner duties under C1; synthetic tests prove none of those live conditions. Missing/unknown checks must fail the runner gate. No root accepted dry-run exists yet. No deletion is authorized by this source result.
