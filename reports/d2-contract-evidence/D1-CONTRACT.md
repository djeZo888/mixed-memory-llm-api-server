# D1 contract for D2 source integration

Updated from worker1 delegate on 2026-09-15; final build/help evidence still pending.

- D0B storage-ready PASS: /data/models-large UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`, ext4, user:ai mode2775. Existing /data UUID `8daf56f1-5649-4163-9d87-919c2d271875`.
- These are this host's deployment-instance identities, not defaults to hard-code into generic fresh-host installer logic.
- Intended model path `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf`; all11siblings mandatory.
- D1 image tag `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1`.
- ENTRYPOINT `["/opt/llama/llama-server"]`; default CMD `--help`.
- Image ENV `LD_LIBRARY_PATH=/opt/llama`, `LLAMA_ARG_HOST=127.0.0.1`; no webUI built. Still use explicit `--no-webui` in launch.
- Bridge deployment must override server host to `--host 0.0.0.0` inside the container and publish ONLY `127.0.0.1:30002:30002` on the VM. Do not confuse container loopback with host loopback; validating the effective Docker publish mapping is required.
- Runtime v0.4.1 commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, CMakeCUDA `120a-real`, CUDA13.2.1 Ubuntu24.04 amd64, Ubuntu package snapshot20260914T000000Z.
- Pinned CUDA devel base digest `sha256:0e1f7b8e96fa9ec5e36d4709a38c62df7b5665977446081811c12b8234d874bf`; runtime base digest `sha256:285c50be684df76df5cd0e3162687e74b7b67add47134ff55075e3a9cfa94044`.
- New image content digest, exact supported `--api-key-file`/device/CLI behavior still pending successful build; do not label them live validated yet.
- Planned key path `/data/services/secrets/llm-api-key`, host0600, mount read-only; no key in CLI or logs. Runtime flag verification owns D1.
- CPU experts, two GPUs for other work,8192ctx,one slot,Jinja. Proposed served alias `glm-5.3` (coordinate with root if profile chooses another).
- Worker1 build unit `d1-llama-build-20260915.service`, durable source/build root `/data/build/d1-glm53-20260915`. D1 owns Dockerfile, acquisition/build helpers and actual build/download. D2 does not access VM or mutate D1-owned source files.

Evidence inputs: orchestration/tasks/D0B/storage-ready.md and D1 worker report/metadata as finalized. D3 installs/restarts only after reviewed merged source.

## Final D1 build evidence update

D1 build/CUDA/CLI checks now PASS (GLM inference/tool calls still NOT_TESTED). Actual image ID `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`. Full captured facts supplied as sibling `d1-runtime-proof.json` and `d1-cli-selected.txt` in this D2 task root. Version reports0.4.1-dev build62 commitb29c606. Both Blackwell CUDA0/1 devices listed. All required launch flags in initialcontract verified, plus --chat-template-kwargs, --reasoning-format, --reasoning-effort, --reasoning-budget and --[no-]reasoning-preserve (defaultenabled, templatecapability-dependent). Configure and live-test GLMclear_thinking=true preset inD3 rather than assuming omitted/replayed reasoning behavior.

A1keyfilereader rejects trailing newline. D3/I1 must generate exact tokenbytes (no trailingnewline), mode0600, withoutprintingvalue. This source task must not generate/read any actual server key.
