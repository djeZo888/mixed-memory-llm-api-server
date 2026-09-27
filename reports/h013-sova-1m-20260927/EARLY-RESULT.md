# H013 early source/build receipt

Base f031ce71b1a3a9064ac3d665e86296f0741cee4e; native session and wrapper's
05:18:11Z start / 05:43:11Z deadline are in SESSION.json.

Reviewed H009 packaging/deployment and H013 scientific PASS handoffs. Removed
only the obsolete display suffix, set the 1M candidate qualified=true, retained
1048576/65536 and exact FRONTIER_INSTRUCTIONS. Existing exact-old SHA migration
checks custom content, modes, links and preservation. Local full profile suite:
15 PASS, 1 packaged-skills skip; Linux rerun planned in candidate build.

Read-only ai-harness verification: production unit inactive/MainPID0, release
/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness;
engine c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20.
Search remains active/MainPID190181 and is preserved. Current >20GiB harness
storage guard applies on this separate host (about395GB free); ai-vm registered
storage helpers are not applicable here. No ai-vm/BMC/inference access.

Build/test gates pending: isolated Python full HTTP checks, server/web
lock-verified typechecks/builds and runtime imports, paired native image build.
No activation/tag/unit/profile/config writes to production. Candidate-only until
root GO plus Worker1's fresh authenticated1M backend/pool/tokenizer receipt.

05:24 UTC update: full prepared Python HTTP/capacity/readiness suite now passes
38 tests. First full run exposed a stale HTTP fixture with no pinned native
tokenize routes (5 unexpected_native_tokenize_route errors); fixture now supplies
the exact two routes the production adapter requires. No production relaxation.
Initial build preflight stopped before writes because an added all-ancestor check
rejected existing ~/.local0775; guard now uses H008's canonical protected
graphroot check (share/containers/storage0700). Original preflight log retained.
