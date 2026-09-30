# Full HD bounded change — deployed and accepted

Public maximum: **1920x1080 / 2073600 pixels**. Six opaque generation sizes:
1024x1024,1024x576,1216x704,1472x832,1760x992 and1920x1080. Full HD uses the
unchanged qualified native 1920x1088 / 2088960-pixel workload and removes exactly
the bottom eight rows. No resize. Public 1920x1088 and UHD are refused;
editing and transparency remain unqualified.

Deployed source: `36c7c2d2ee8d9ed59e9310e708eb640c5aecad5e` (root-approved API
`20e578b` plus example helper); subsequent docs/evidence commits need no redeploy.
Installed protected manifest SHA256:
`12969d9966f222217891791f0a2d6f4202ee2b0a7f83ef36f18d734a96721b07`.
[Deployment receipt](DEPLOYMENT-RECEIPT.json) binds source, config, helper and output.

Exactly **one** public helper generation completed with HTTP 200, seed 42, n=1:
**54.8s** helper time (HTTP request, response check and PNG write, rounded0.1s),
55.0759s SSH command wall time. Native elapsed is not returned by the public API.
The full [actual prompt/request](acceptance-request.json) is the root-selected
reviewed autumn `lake-bled` preset; [root clarification](ROOT-PRESET-CLARIFICATION.md)
supersedes the draft summer prompt. No negative prompt was added;40steps,CFG1,
CPU RNG and all runtime/model/placement settings remain unchanged.

Delivered PNG: **1920x1080 RGB**, fully decoded,3077520bytes, SHA256
`ddb8d52a0f449a809cb1fab006a2eaea23b8f5b95d648b9b86d1640c134e33c5`.
VM: `/data/services/image-api/examples/output/fhd-acceptance-lake-bled.png`;
taskroot copy: `fhd-acceptance-lake-bled.png` (outside Git). Ordinary caller
owns the file uid1000/gid1000. Worker1 visually inspected the scene: coherent
island church, cliffside castle, mountains, water and reflections; no corruption.
Root independently inspected the same hash-bound PNG and marked visual PASS. Other example prompts have
not been executed by this task.

Post-call API: ready=true,admitting=true,busy=false. Owned temporary spool has
no new entries. Both original text container IDs/start times/PIDs are unchanged.
The runtime config hash remains `4ded6e9261b512d952c5033b0634d4eaba79fa115685635c6307defe78c11d76`.
One normal APIowner reconciliation/warm ran after installation. Registered
storage/root-disk guards passed; canonical lease released before systemd and at
closeout. Credential retains root:root0440. No text restart or extra inference.
Exact predecessor source/config bytes and metadata are preserved at
`/data/services/image21-fhd-20260923/rollback`.

14 focused Worker1 fixtures passed; [result](focused-test-result.txt). Root also
reviewed 9 passing Worker2 helper fixtures. No broad suites or campaigns.
[Installed manifest](qualification.json) retains five smaller entries/evidence
hashes and binds the derived FHD profile to [crop evidence](crop-evidence.json).
That immutable predeployment derivation records its then-pending live status;
this separate acceptance receipt completes the live evidence without changing
its protected hash. The fixture proves every retained pixel row equals the native
top 1080 rows. Live output was fully decoded; the native response was not separately
retained. No resize or arbitrary geometry is permitted by installed source.

Historical native 1920x1088:53.3355s,44776.3125MiB sampled device peak,8.8801% free.
This remains prior native workload evidence, **not a new memory benchmark**.
[Original qualification](../image21-qualify-20260923/RESULT.md) and all its receipts
remain byte-exact. Runtimeimage/checkpoint/precision/offload/cache policy unchanged.

[Ready-to-run API examples and full prompts](../../examples/image-api/README.md)
use the protected helper, drop sudo privileges before HTTP/output, and never put
the credential in argv/environment/logs. Acceptance uses a distinct filename, so
the user's example filenames remain available. Root owns final source review and
normal PR5 update; Worker1 has not pushed, merged or force-pushed.
