# Reviewed MiniMax patch set

Apply only to `ae65651df5f97ae1085ab4e19964f4b78c769a4e`.
`0001` aligns the main request default and common OpenAI-compatible adapter
fallback to 151 minutes. Explicit native title timeouts remain 10,000/15,000 ms,
with unchanged 1,000/1,024-token budgets; title failure remains nonfatal and
cancels queued requests. The portal names chats. `agentStop.maxActiveSpanMs=0`
remains the profile setting.
`0002` reports native ACP compaction start/completed/failed without changing
compression or occupied-context calculation. See `compaction-notes.md` and
`../engine/README.md` for source evidence and exact test boundaries.

`SHA256SUMS` pins the two patch files. Its SHA256 is the image/launcher admission
identity: `b583f01e412c3316fe3a5e62f8b5ce83269091e077b3eb6df2e615dd8428402d`.
`source.SHA256SUMS` and `patched.SHA256SUMS` identify all four affected source files.
`identity.json` provides the same mapping in structured form.

The Containerfile checks the original Git HEAD and files, patch checksums,
`git apply --check`, and resulting files before source compilation. The final
image retains these small review artifacts and carries the patchset label.
The upstream tree is not vendored here. Offline patch application and fixture
tests do not constitute a full TypeScript build, container build, ACP transport
or live model/compaction acceptance.
