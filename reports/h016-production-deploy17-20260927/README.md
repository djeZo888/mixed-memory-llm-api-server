# H016 DEPLOY17 — corrected ordinary launch loading

Root-approved corrected ordinary unit started **17:54:58UTC**, before17:55.
Fresh container started17:54:59.739250868. At17:55:47 the same unit/native remained
LOADING with guard ok17:55:45 after the launch SSH process exited. Readiness is
PENDING; no production props/slots, proxy or Sova acceptance is claimed.

Owner `7768181c10bb35c7fcaa02d243913aaedf9ff7396416252b826dc2bbdb814a2c`;
unit `c0c260e2fd554fc74ab045d072bdfa902780d05fa23b88f69f6324079e40573a`.
Only the approved owner plus source/installed unit copies changed. Exact readback
matches. Generation3 binds canonical manifest
`c2d4cb314ce86a6c082faf784a5c3c55a6bb95acc1056f43f8baaeaa43f9016b`.
MainPID3481160/nativePID3481564; invocation2e31e65bdcfe403f9c76bd1ba49f276e;
container57954b459c29ad393c2b30588644ebd2585f94cf2acef8faeec2de65330e16cf.
Image/model/weights/context1M/F16/8spread/64batch/GOMP0 unchanged.

MandatoryGuardTimeout now distinguishes the fatal whole-sample deadline from
pending socket readiness timeouts.19 focused owner tests PASS, including both
fatal contexts and actual SIGALRM type; original-source regression reproduces
the independent socket-timeout bug offline. Original failed start cause remains
UNPROVEN because its diagnostics were discarded. Only ordinary-unit stdout and
stderr changed to journal. No blanket timeout suppression.

Original failed state/manifest/selection/source/unit, exact inspect, logs and
journal were preserved at protected
`/data/build/H016-20260927/worker1-deploy17/failed-original` before removal of only
container144757b104c97ffad8d05158e93f1abcb929d34083a1a944c5690e0e801e7fdc.
Fresh PID0/cgroup/GPU settlement and unchanged other3/source pins passed under
the canonical lease. An initial LeaseBusy occurred before any mutation; a fresh
lslocks observation showed no holder before successful canonical reacquisition.
There was no lock bypass or extra model launch. Historical failure evidence is
in FAILED-* files and private raw receipts, unchanged.

Independent h016-deploy17-cutoff.timer is waiting for **18:10UTC**. It normally
stops this ordinary owner if state is not RUNNING, then records settlement;
RUNNING remains up. Internal1800s load timeout is unchanged. No paid polling
through load. Next single actual read command:

```
python3 /Users/agent/CodexProjects/llm-orchestration/tasks/H016-PRODUCTION-DEPLOY-17-20260927/READ-READINESS.py
```

That prepared read-only command collects exact state/unit/manifest/source,
native/proxy, guard, actual props/slots1M and fresh canonical node data when
RUNNING. It sends no inference. Native/CLI cap18:10; overall root18:33:08.
GLM remains dormant/manual rollback; no GLM restart. Sova remains paused by its
owner. Source/readonly readiness is separate from actual Sova acceptance.

LAST clientefbd8a3f/reader3adf8f43 and README/service source were staged INACTIVE
under protected worker1-final13-long at17:57:45.19 staged/retained host file hashes
matched; all24 local source pins reconciled (22 prior plus2approved repair).
No authority file, installed LAST unit, or dispatch. Existing inactive GO template
still needs repaired-owner/current production pins and actual SovaPASS/rootGO.
No inference or requalification here; immutable R9 qualifierf031/image unchanged.
Raw receipts stay outside Git. RESULT.json, exact executed script archive and
ROOT-REPAIR-LAUNCH.json provide continuation identities.
