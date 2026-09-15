# Q38VR3 unchanged fixture invocation

Exact integration source: 56aae9ea64a15bb582f89cd20a770985e8d70eac; tree 1de3f03cb7ccdf428eb09b28f88fe1aac62281ba; 1000 committed files.
Archive SHA256: 266751d46455cde481edf185ba6147c6966f6ab5edbd38ce42cba5e5c33265a4.
Source manifest SHA256: 5ababe872b915ce8cdefd00d849c010c997a5158d95b2eab81eaf772e5db9248.

One invocation through Worker1 SSH ai-vm and sudo -n:

```text
/usr/bin/python3 -B /data/build/q38vr3-20260915/source/tests/lifecycle/sglang38_fixture/run_fixture.py --repo /data/build/q38vr3-20260915/source --output /data/logs/q38vr3-20260915/q38b-auth.json
```

Cwd /data/logs/q38vr3-20260915/tmp. No fixture flags or provenance overrides.
Shipped internal contexts 131072 then262144 only after full first PASS and exact owned quiescent cleanup.
Image pullnever; exact pinned image; NVIDIA none/compute,utility; no GPU/device mappings;
network none/no ports; readonly root and sole readonly source bind; exact private tmpfs cache/model/secrets/tmp.
Shipped create30s/attach600s/cleanup30s/drain2s, resources, ownership and signals unchanged.
No model or real key mount/access, kernel/inference/API or service action. Installer STOPPED; D3N32 owns all real lifecycle/model/generation.
Only final source-bound receipts after both PASS, retained privately with no runtime/instance publication.
First observable CLI result published immediately before postchecks. No intermediate 128K event is exposed.
