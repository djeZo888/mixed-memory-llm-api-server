# Q38VR unchanged fixture invocation

Source: cb2e49c2bea670a3d72f9cce08f8c51c194b6c67; tree dae3d3cfc3acc9c35e81ee2d9d1918533f355114; 764 exact committed files.
Archive SHA256: 632d093f25e1c6fa1541e5169d3052cc231152bbaeeb3ffa7df9be6260d42b6f.
Source manifest SHA256: 4a4dcd9bebb000f71fcd74143b9a433a4d49aa4c2451676ae1d2f3249a074b2d.

One CLI invocation, preserving shipped internal 131072 then conditional 262144 loop:

```text
/usr/bin/python3 -B /data/build/q38vr-20260915/source/tests/lifecycle/sglang38_fixture/run_fixture.py --repo /data/build/q38vr-20260915/source --output /data/logs/q38vr-20260915/q38b-auth.json
```

Worker1 SSH ai-vm; sudo -n; cwd /data/logs/q38vr-20260915/tmp. No additional fixture options, overrides, source rendering or stubs. Shipped Docker command only: pullnever, digest-pinned image, nvidia runtime/devices none, CUDA_VISIBLE_DEVICES empty, network none, readonly root and only readonly source bind, synthetic model/secrets/cache/tmp tmpfs, dropped capabilities, no-new-privileges, 8g memory, 128 pids, 64m shm, no logging driver. HOME remains unchanged.

Shipped create30s, attach600s per context, cleanup30s and CLI drain2s plus signal handling remain unchanged. Host recorder only invokes the reviewed CLI and retains its result; no per-context wrapper or retry. First failure ends the internal loop and no receipt is written. The CLI exposes no intermediate 128K PASS event; publish first observable safe terminal result immediately before postchecks.

Registered-only guard uses the fixed protected source and no overrides. D3 VM-GUARDS.json stays exact as source baseline. Registration 626db7130b644199f5f632b2ac3c04f86cdd382121573aa6f3825bbca8de9c27; installed closure manifest bb0176749bd35deace1643d1a70c42be92a9f0b7bc629d41663c594678365f55; both whole-volume UUID/fsroot and root threshold passed.

Private stdout/stderr/execution and guard evidence: /data/logs/q38vr-20260915/evidence. No live receipt import, model weights/key access, inference, service/network/installer changes. Final receipts if produced stay task-private pending L2 closure refresh.
