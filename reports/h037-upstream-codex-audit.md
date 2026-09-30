# Codex upstream audit — 30 September 2026

**Decision: hold the upstream upgrade for a separate bounded task.** H037 will
retain Sova's qualified Codex 0.158.0 runtime while completing the independent
default-harness, status and image-placement changes.

The official default branch was `main`, observed at 10:55:58 UTC:

| Source | Revision |
|---|---|
| Sova's pinned upstream release | `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3` |
| Audited upstream main | `0b43721d8d1f734658e41bffe12a6ba6c9240abd` |
| Merge base | `d9275a63ed1c4ff6ed6b56db8669453ad678b6cf` |

The [upstream revision comparison](https://github.com/openai/codex/compare/064c6b8c737f5b41d171fdda80bd9ef10ad06eb3...0b43721d8d1f734658e41bffe12a6ba6c9240abd)
has 17 commits unique to the release side and 206 unique to main. The direct
tip-to-tip diff changes 1,281 files: 53,583 insertions and 14,029 deletions.
Relevant surfaces include 55 app-server protocol files, 50 app-server files,
248 core files, provider/Responses streaming code and Cargo/Bazel lock files.
These are upstream changes, not the size of Sova's local modifications. The
pinned release is not an ancestor of the audited main revision.

Sova installs the official musl binary with its checksum verified. It does not
build or patch Codex Rust code. Its integration consists of external Responses,
tool and status adapters, model catalog/configuration, skills, launch wrappers
and a separately appended instruction overlay. The original upstream prompt
remains byte-identical. No literal Rust merge conflict has been established.

The upgrade is held because those protocol and runtime changes require a new
qualification campaign. Updating the three Macs to CLI 0.159.2 does not update
the separately pinned Sova container.

## Proposed follow-up

1. Compare the current Sova integration against an explicitly selected upstream
   target. Audit stable 0.159.2 separately as a potentially smaller alternative
   to development main; do not assume it has the same diff.
2. Pin the source revision, official binary/image checksums and protocol schema.
   Identify changes to request fields, streaming events, tools, cancellation,
   compaction, subagents and terminal-event ordering.
3. Adapt only affected Sova interfaces in an isolated copy. Preserve native
   prompt provenance, dependency notices and strict local provider contracts.
4. Run protocol fixtures and bounded live Qwen/MiMo/tool/image workflows,
   including follow-up, cancellation, reconnect and job settlement.
5. Review the exact candidate and protected qualification before activation.
   Preserve the old container, deployment and conversations for rollback.

No upstream runtime build, merge, deployment or inference occurred in this
read-only audit. Compact metadata and public file/commit lists are retained in
the H037 project records; private prompts and full worker traces stay outside Git.
