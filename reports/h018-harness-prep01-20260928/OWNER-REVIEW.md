# W2 early source review — not frozen acceptance

Reviewed input/owner-review/EARLY-SOURCE.patch only; no ai-vm contact or owner edits.

Concrete issue: memory_policy() raises on parent-limit mismatch before returning
its values, and sample_guard calls it before entering the validate_sample try.
Thus parent max/empty/invalid/nonzero failures lose the observed parent literal
and fail to populate resource_memory. Keep failure closed, but attach bounded
parent classification/raw-safe values before refusal, using existing failure
reporting. Add focused fixtures for each bad parent value and its retained
failure evidence; malformed/secret-bearing text must not be echoed.

Exact native cgroup path under llmmimo.slice plus HostConfig.CgroupParent is a
useful covering-parent check. A child scope max is explicitly allowed in this
patch only with a zero parent. This is effective hierarchical enforcement, not
raw child zero; root must explicitly review that distinction against the user's
zero/unlimited wording. Never label child max as0. Unit-only supervisor policy
would not cover a sibling native scope.

Still required in frozen source/evidence: installed slice unit source hash and
controller coverage; parent policy persists after daemon-reload; exact mismatch
fails before inference; all short/LAST units installed and daemon-reloaded before
load. W1 owns disposable live proof. None of that is proven by this early diff.
Keep GPU7%, host15%, thermal/OOM/owned swap and exact settlement unchanged.

Early diff SHA256: `6078132b01413c51768853b552c4cfadc189f0f696191b7b77ca2e3e19600def`.
Base owner SHA256: `dd9c10c75214fbbf8f1d5566618ac35bafa17f709ffc12ec3f84003dc9e30786`.
Frozen source snapshot, slice unit, dispatch-unit sequencing and disposable
reload proof were unavailable at handoff. No repaired-owner test result or
implementation acceptance is claimed. No additional owner regressions executed.
