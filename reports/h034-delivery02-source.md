# H034 DELIVERY02 source delivery seam

Source-only PASS against `d2333dcc7effe0de73bb1cbc48c31264de39da05`.
This closes the source delivery gap; deployment and unchanged live workflow
acceptance are NOT claimed. W2 owns all later activation and live work.

Both launchers now validate fixed reviewed host files and bind them individually
`ro,rprivate` over the baked image adapter paths. MiniMax additionally overlays
the reviewed packaged image skill and changed configurator. The existing Codex
policy-checked skill mount remains current. No image rebuild or dependencies
changed. Source hashes, full file mappings, launcher/helper hashes, unchanged
pins and exact focused test commands are in `h034-delivery02-source.json`.

The install must preserve the reviewed `ai-harness` tree layout: launchers under
`deploy/`, validator under `deploy/engine/`, modules under `tools/image/`, and
ordinary skill under `skills/image/`. Install these reviewed bytes together;
partial delivery fails closed. The host source root and all its ancestors must
be canonical protected directories owned by root or the service user without
group/world writes. Overlay files must be regular, single-link, owned by root or
the service user, without group/world writes, and match fixed SHA256 pins.
Source may not overlap either writable task mount. No environment pin override
or extra launcher argument is accepted. Bind targets are:

| Engine | Reviewed source below ai-harness | Container target |
| --- | --- | --- |
| Both | tools/image/image-mcp.mjs | /opt/ai-harness/tools/image/image-mcp.mjs |
| Both | tools/image/image.mjs | /opt/ai-harness/tools/image/image.mjs |
| MiniMax | skills/image/SKILL.md | /opt/ai-harness/skills/image/SKILL.md |
| MiniMax | deploy/engine/configure-profile.mjs | /opt/ai-harness/engine/configure-profile.mjs |

MiniMax retains the original mismatch refusal and accepts only the exact
`efde32a0bb2057d014d5168b3a613fc3dbccd801` image skill predecessor
`56449a3f...` to current reviewed `824aba75...`. Full roster, unrelated bytes,
paths and metadata validate before replacement. The exact predecessor is saved
once as private `${MINIMAX_DATA_DIR}/.image-skill-h033-56449a3f.md`, outside the
skills roster. Existing backup bytes must match exactly and retain safe private
regular-file metadata; unknown edits, links and FIFOs are refused. The existing
private staging and atomic rename pattern publishes only the new image skill.
Current-profile reuse changes no bytes or inodes. Tests preserve histories,
native identity, retained instructions and every unrelated profile byte.

Final checks: 32 Node migration tests/subtests and 25 Python launcher cases PASS,
zero failures/skips, actual test subprocess exit 0. The launcher checks comprise
16 new overlay cases, four selected existing MiniMax cases and five selected
existing Codex cases, using fake Podman only. They cover exact readonly argv,
spaces, changed/missing files, link and unsafe-mode refusal, source ancestors,
source/task overlap, argument checks and credential isolation. Shell and Node
syntax checks and `git diff --check` pass. The previous broad 39-test suite was
not replayed. Private raw receipts remain outside Git; their hashes are recorded
in the JSON manifest. Focused source review found and resolved ancestor-directory
and nonregular-backup issues; no remaining material finding was reported.

Provider/tool contract, policy `73e00d27...`, instructions `84260e89...`, baked
image pins, runtime dependencies, egress, identity, credential handling and
security arguments are unchanged. No model/API/VM/SSH calls, container runtime
operations, deployment/ticket writes, hardware changes or push occurred.

EARLY.patch was exported while checks were pending. Native CLI thread:
`01a0ee4e-949c-7671-b2c1-93a0e00e1304`. The existing wrapper records actual
`Popen.wait` exit after this CLI returns, before cleanup; this report does not
claim that future exit receipt. The final exported output manifest identifies
this report's exact source commit and bundle against the combined base.
