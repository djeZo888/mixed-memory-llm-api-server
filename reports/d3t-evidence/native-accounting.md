# D3T native accounting — bounded non-generation proof

2026-09-15 02:15:35 UTC. Coordination revisions 3–4 authorize this narrow inspection.
**PASS:** actual native template and tokenizer routes on unchanged GLM32K. **NOT_TESTED:** generation, N76 load, native-capacity load, occupied-context correctness/cache reuse.

Container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`, PID `149976`, image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` remains the old D1 baseline. Source `/data/build/d1-glm53-20260915/source` HEAD `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`; scoped server source working tree clean.

## Exact endpoint semantics

1. POST the **entire exact frozen Chat Completions body** to `/apply-template`. Installed `tools/server/server-context.cpp:5059–5069` uses the same `oaicompat_chat_params_parse(body, meta->chat_params, files)` as `/v1/chat/completions` at 4930–4943. This includes actual tools, tool IDs/results, generation prompt, explicit low reasoning and installed CLI template defaults.
2. POST `{"content":<returned prompt>,"add_special":true,"parse_special":true,"with_pieces":false}` to `/tokenize`. Generation tokenizes with `true,true` at `server-context.cpp:4299`. The tokenizer route at 5084–5122 defaults `add_special` to **false**, so the explicit true override is required. `server-common.cpp:860–900,981–1028` routes the text through the same tokenizer. No character estimate, local substitute tokenizer or template reimplementation is needed.
3. Count the actual returned token IDs and hash their canonical JSON array; retain them only in the private worker checkpoint to compare exact stable prefixes. Body and rendered prompt hashes bind the count. Prefix equality does not itself establish backend cache reuse; later generation usage must independently expose cached/evaluated counters.
4. Initial input ceiling is stage target minus **8192**. Continuation input plus its output cap must fit the same window. No truncation, context shift or RoPE scaling is introduced.

Installed source SHA256: `server-context.cpp` `2f5d65ce6ef0504b5c8cf55a74c68d3959c49784ba380ef836566b7a7d5fa12b`; `server-common.cpp` `de3a89422f67b97eb385041fae17e553dc677aac6b67f2e98e9f0beff672b4e0`. Low effort and CLI kwargs merge are at `server-common.cpp:1288–1363`.

## Tiny native fixtures

Each fixture used one apply-template and one tokenize call: **8 route requests, zero generation requests**. The exact A1 `Fixture.schemas[0]` read-file definition was used. Continuation contained a deterministic synthetic matching tool ID/result; no live assistant call was generated. Every native render contained `Reasoning Effort: Low`.

| Fixture | Render bytes | Actual tokens | Render SHA256 | Token-array SHA256 |
| --- | ---: | ---: | --- | --- |
| Ordinary, “Reply briefly.” | 85 | 15 | `dcf6f9856667d778bcd6dcba9ba71f5b00129c1e2d8cf0cca8310e9f2b5da42f` | `ccd4bedf36e6b257bb9f2b7495f795d1828d70285dbb7233727e178719d88be4` |
| Actual A1 tool schema, read calc.py | 810 | 184 | `460d6d83b2ed67ce4c5a6c6e2222817be29caaa01272d24c6bb4e49dd35f08ec` | `7296b695ec96ed74dca6420f080b0a3c382d8580b50f38429bb62dae6516244b` |
| Matching tool continuation | 1037 | 226 | `e03dc779ab0563833e3de77809aac5f943a7e0447a6dbb78c18208a3723a9183` | `bfadb8686156f1ee68e81ddf96ba0f0b0a2aef4b290a107de7ea40e9da44625a` |
| Ordinary with stream/include_usage | 85 | 15 | `dcf6f9856667d778bcd6dcba9ba71f5b00129c1e2d8cf0cca8310e9f2b5da42f` | `ccd4bedf36e6b257bb9f2b7495f795d1828d70285dbb7233727e178719d88be4` |

Body hashes, in table order: `01a3d92f883daaaadd5a4184ec5083b45cfd4aaff78b215fdbbc64e416de69f3`, `bac5ab17ff9d3ae00ee57ab15f8cfe3908ae58b66f9d14eca1025ab53ed28c77`, `20fedc1bbf518c78c4c8545f921e26ee7f9cb23c5412d5313d71fa2ec270568a`, `bfc5df4ba12b0e730713515635b617eb48a9aa51eaccce3fbc67fd4c1d58e608`.

Tool→continuation actual common prefix: **184 tokens**. Native accounting duration per pair was 0.010–0.013 seconds for these tiny inputs; no long-context performance inference follows.

Both exact ext4 UUIDs matched (`/data` `8daf56f1-5649-4163-9d87-919c2d271875`, `/data/models-large` `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`). Root available 5,227,618,304 bytes, above STOP 4 GiB. API key read through root-owned nonsymlink protected file descriptor into remote process memory only; no key in argv/output/log artifact. No reload, generation, install, GPU profiler/allocation or protected-state mutation was requested.

## Concrete helper interface replacing receipts

`native_account(body, container_id, image_id)` performs bounded Worker1 SSH with the request/code on stdin, keeps credentials remote, checks exact current container/image before and after, calls native routes, and returns actual `input_tokens`, private `token_ids`, token/body/render hashes, and runtime identity. The later runner owns stage deadlines/checkpoints and persists token arrays privately. No owner-supplied accounting receipt or new authorization framework remains.

The shipped adapter was separately exercised with the same tiny ordinary fixture: it returned the identical body/render/token hashes and 15 actual tokens, with actual `/props` capacity 32768. The adapter also reads `/props` to hash the actual loaded template. One native-account call makes three bounded route calls, each using a remote 50-second alarm and a worker 60-second subprocess timeout; no retries. Total investigation: **13 non-generation route requests** (8 fixture POSTs, 1 shipped-adapter GET plus 2 POSTs, 2 additional GETs inspecting the loaded template), **zero generation**. No large accounting request was made.

### Loaded template normalization is resolved

Actual `/props` template: 10,504 bytes, SHA256 `347dc716e1e8a9917eb124503836943107686ace6a3848d16bf23ae50964bb49`. Adding exactly one trailing LF gives SHA256 `15d2a7176beb599de0a59af8314b4869011e416cff7f65748b314940d3379b0e`, exactly the 10,505-byte embedded metadata template. Installed `common/chat.h:58–71` stores/returns the lexer source; `common/jinja/lexer.cpp:43–58` normalizes line endings and strips one final LF. Compare **actual loaded** template hashes across phases; do not require raw metadata bytes to equal the normalized loaded source.

### Focused validation

`python3 -m unittest discover -s tests/d3t -p test_accounting.py -v` passes 12 synthetic/native-CPU helper tests: actual wire-body handoff and installed tokenizer flags, property/alias/token rejection, reserved occupancy, exact common prefixes, bounded over-capacity corpus fitting without admission, SSH stdin privacy/route restrictions, shipped A1 stream/nonstream parsing with exact missing counters, early/middle/late checks, and real deterministic worker fixture read/continuation. These tests make no SSH/network/model request. The concrete native adapter verification above is separate evidence under revision 3.

For the later bounded corpus fit only, native accounting may return up to 4,194,304 token IDs within a 64 MiB response cap; final occupied admission remains at or below the selected window minus its reserve. This is CPU tokenizer counting, not model occupancy or generation. `account(body,native_http)` is the factored shipped counting helper; `common_prefix(previous_ids,current_ids)` and `check_occupancy(accounting,body,target,initial=...)` operate on its actual results.
