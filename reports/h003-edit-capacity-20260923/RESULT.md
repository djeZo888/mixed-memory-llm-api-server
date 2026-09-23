# Native Worker1 source checkpoint

Retain session **01a0ce36-b30b-7af2-adf7-a37c9e8a8a5a**. No wrapper/session files edited.
Source: **f6e69d290a3cbf58dafbcfa726f9474f083a7cfd**; base4022dbcd over reviewedb5717d.
Review CANDIDATE.json, CANDIDATE.diff, installed-to-candidate-protocol.diff,
TEST-RESULT.json and CAPACITY-PLAN.md. No publication or activation.

Final clean-window producer: helpers/open_capacity_window.py
SHA256 **2f873367b813a93edbe77cced162fa5ccd26f11fa86aacb48f0412f6979ba6c6**.
It uses root's final SIGTERM-MAIN/no-lease-during-drain procedure, not systemctl stop.
Bounded30s; clean exit0/oldPID+listener absent, then canonical lease/unchanged models
and durable receipt. No forced kill/restart fallback. It has NOT been invoked.
Runner/codec hashes are in CANDIDATE.json; every case binds the producer receipt.

29 adapter +11 runner/codec offline tests PASS. Geometry includes native-equivalent
RGBA/tRNS/EXIF normalization, exact bottom8pad/top1080crop, seed and refcount gates.
Installed API still lacks the reviewed seed source correction; activation diff includes it.
Native processor/resize source audited; no runtime/weights/settings changes.

**0/4 capacity calls; all4 remain.** Original fail42/pass43 preserved; guarded user
acceptance APPROVED; public editing disabled. Next: root exact packet review and
C01GO, then one graceful private window and C01 seed46/exact retained prompt.
Larger/two-ref calls require prior results and conservative reserve forecast. Final
reviewed source+passed manifest activation uses one existing recovery/fixedwarmup,
separately counted. Public API end-to-end acceptance remains Worker2's later work.

Read-only final12:53:18UTC: generationready/idle,6gen/0edit, all model/API identities
unchanged, both480K contexts retained. No new swap in checkpoint; q1 prior148MiB remains.
Outputs/fixtures stay outside Git. Deployment timeline wording corrected and tracked
LakeBled PNG removed; its exact original and hash are preserved at prior task path.
