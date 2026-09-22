# Reviewed MiniMax patch set

Apply only to `ae65651df5f97ae1085ab4e19964f4b78c769a4e`.
`0001` aligns main, direct OpenAI-compatible provider and title-request timeouts
to151 minutes; it preserves smaller native auxiliary output-token budgets.
`0002` reports native ACP compaction start/completed/failed without changing
compression or occupied-context calculation. See `compaction-notes.md` and
`../engine/README.md` for source evidence and exact test boundaries.

`SHA256SUMS` pins the two patch files. Its SHA256 is the image/launcher admission
identity: `256e6fc91a7b86fcc0073c3755bd0aab6be50bb4125827be36d9b99dc1b09d0c`.
`source.SHA256SUMS` and `patched.SHA256SUMS` identify all six affected source files.
`identity.json` provides the same mapping in structured form.

The Containerfile checks the original Git HEAD and files, patch checksums,
`git apply --check`, and resulting files before source compilation. The final
image retains these small review artifacts and carries the patchset label.
The upstream tree is not vendored here. Offline patch application and fixture
tests do not constitute a full TypeScript build, container build, ACP transport
or live model/compaction acceptance.
