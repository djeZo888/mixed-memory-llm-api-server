# H032 app source deployment proposal — not executed

Prerequisite: base `5cc21bafa7ecda85bb20e50e45bee86a826ded76` plus the source commit in SOURCE-MANIFEST.json. Root review and W1 lifecycle coordination precede deployment. This worker has made no VM contact, deployment or live inference.

Install the built host server dist from `HOST-DIST.tar.gz`, the updated `ai-harness/deploy/run-codex.sh`, and BOTH exact candidate profile files under `ai-harness/deploy/codex/` (`config.toml`, `config-image-jobs.toml`). Retain other policy files byte-for-byte; verify the six-file aggregate host policy checksum before starting any new native task. Artifact/member hashes are in BUILD-MANIFEST.json. Config copies in output/config are byte-exact repository files.

- Native image remains `d8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad`, tag `localhost/sova-codex:0.158.0-h024-release02`.
- Native image revision remains `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`; its existing patchset label remains `dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec`.
- Host-mounted six-file policy becomes `aee39eea7f559a2f1c1b34c2d99818be1bc4e79ea6dba2ca7ec4075c8e34a956`.
- Model catalog remains `75f39aa38c42d99265101686c15e0f3154aacecc325a3fb6c598e0a185a51823`; logical model policy remains `sova-codex-0.158.0-qwen-text-v2`. No session database migration.
- Both profiles set `[features].view_image = false` and the same generic root `developer_instructions`. No answer, unit conversion, original fixture text, rescue loop, tool namespace rewriting or phase tags are added.

No native image rebuild is required: launcher already mounts both selectable profile configurations over native CODEX_HOME/config.toml. The new instruction is in that mounted config, not the baked catalog. Containerfile's prospective label reflects its changed source inputs for a future separately reviewed build; do not build it or repoint this launcher to a new image for this package.

Use the established coordinated app settlement/restart procedure when root approves installation, preserving existing native histories and workspace files. Do not change maintenance503, MiniMax default, image/frontier capability gates, acceptance/candidate flags, quarantines or uncertain-owner records. This package creates no qualification record and does not assert current backend readiness.

The image specialist evidence pin now denotes actual OCI platform manifest `sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef`, domain `oci_platform_manifest`, config digest `sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad`, with parent `sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8` explicitly separate. Existing binding/profile limits are unchanged. W1's candidate recovery config `a3ca37b0deb2dcc2af5421dde3b5e204dc850ab7034665e576724eca5b1a632a` and service `6b7ac0a1ff946b3b7be62caf24926b33adad566f595abd5398e7db3486b88fa6` are separate source/deployment work, not runtime availability evidence. No W1 source is included here.

## One later original PDF rerun

After reviewed app deployment and W1's coordinated lifecycle readiness, retain the original H031 failure and perform ONE separately authorized affected rerun using the unchanged 702-byte source PDF, SHA256 `7cd11f7c4a0369ce2a8f4c57cd375a1149df9e3b593ac22bf3de7e692b42f03e`, and this unchanged original prompt:

> Read the attached source.pdf using the installed local PDF skill/helper. Extract and render page 1. State its supply voltage and current limit, convert the current to amperes, and cite page 1. Create a one-page summary PDF in artifacts/. Retain the source unchanged; report actual tool failures.

Retain the actual Linux native request declaration proving view_image absent, ordinary exec/PDF tool results, exact provider->Responses->native->app final content, output artifact/page count, source hash before/after, and settlement. Evaluate numeric answer/page citation and summary PDF against the original retained oracle privately. No prompt sweep, automatic rescue/retry, substitute vision path, fabricated tags or relaxed fixture. Offline native declaration proof does not establish live PDF completion.
