# Q38VR2 unchanged fixture invocation

Exact integration source: 1e65e17534ae6be3a23ec54bda800ad64fcee7d8; tree 98f7f9f59c038025a79b2febc83fe62fcd2dc2a3; 870 committed files.
Archive SHA256: d1887fb969ce9e3423d4f551fc6d1523b71e37f9df72ebd5da71c4ac1a5c87bf.
Source manifest SHA256: 901e56d00abf0ebedc550ace05fde4fa1a73e23b5f72a63915c9f00e6a6a0cec.

One invocation through Worker1 SSH ai-vm and sudo -n:

```text
/usr/bin/python3 -B /data/build/q38vr2-20260915/source/tests/lifecycle/sglang38_fixture/run_fixture.py --repo /data/build/q38vr2-20260915/source --output /data/logs/q38vr2-20260915/q38b-auth.json
```

Cwd /data/logs/q38vr2-20260915/tmp. No fixture flags or provenance overrides.
Shipped internal contexts 131072 then262144 only after full first PASS and exact owned quiescent cleanup.
Image pullnever; exact pinned image; NVIDIA none/compute,utility; no GPU/device mappings;
network none/no ports; readonly root and sole readonly source bind; exact private tmpfs cache/model/secrets/tmp.
Shipped create30s/attach600s/cleanup30s/drain2s, resources, ownership and signals unchanged.
No model or real key mount/access, kernel/inference/API or service action. Installer STOPPED; GLM32K unchanged.
Only final source-bound receipts after both PASS, retained privately with no runtime/instance publication.
First observable CLI result published immediately before postchecks. No intermediate 128K event is exposed.
