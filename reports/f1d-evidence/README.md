# F1D retained evidence and operation recipes

These files record bounded F1D execution, not a reusable installer or a passed
inference deployment. See [task report](../f1d-qwen-live-acceptance.md).

- `run-auth-gate.sh`: exact reviewed fixture command, unchanged F1S source;
  actual VM exit2 is recorded in `auth-gate.*`.
- `run-auth-diagnostic.sh` and `diagnose-auth-gate.py`: separate sentinel-only
  diagnostic entrypoint, recording exception types and frame locations only.
  It did not change the reviewed launcher or count as auth acceptance.
- `prepare-release.sh`: reviewed-commit checkout, rollback backup, protected
  adapter preparation, and obsolete-unit disable. `--dry-run` preceded
  `--apply`; both completed. It refuses existing release/backup state.
- `seal-qwen.py`: task-specific fail-closed identity/stat validation and narrow
  Qwen protection. `--dry-run` and then apply passed. It refuses existing
  backup/proof/completion outputs. Do not rerun it over this completed seal.
- `qwen-seal-evidence.json`, `qwen-completion.json`, and metadata JSON are exact
  nonsecret copies; the VM retains protected authoritative originals.
- `glm-final-observation.json` is a read-only status snapshot after GLM finished
  independently. It is not GLM payload integrity or model acceptance.
- `SHA256SUMS` binds all packaged evidence/recipe bytes except itself.

All VM operations used Worker1 `ssh ai-vm`. Local JSON syntax, Python AST,
shell `bash -n`/`--help`, and protected receipt/proof copy hashes passed.
Actual apply/dry-run results are evidence for these task-specific recipes;
no additional lifecycle tests or model acceptance were substituted. Common guard
reports retain their M3 template headers and no-mutation statements; those
describe the read-only guard invocation. F1D's actual changes are in the task report.

Two initial supplemental diagnostic setup attempts failed before useful
diagnosis: missing bind source (exit125) and unreadable diagnostic file
(exit2). Their safe stderr files are retained. Correcting only the diagnostic
path and its mode0644 produced the recorded frame-only result. The initial
bundle clone needed explicit checkout of its advertised reviewed branch/commit
because the bundle did not advertise HEAD. None of these setup corrections
changed F1S runtime source, inherited runtime environment, model data or keys.

The rollback archive stays on the VM in the private task backup directory;
it is deliberately not included here because it preserves the old manager
configuration verbatim. No credentials, real key files, weights or session
JSONL are included in this evidence directory.
