# F1Db Revision2 auth failure — diagnostic proposal, NOT EXECUTED

Cache: PASS_RESOLVERS_AND_FILESYSTEM_ONLY, exit 0, 9.509 s.
Auth: FAIL, exit 2, 8.597 s, `actual_image_fixture_failed`; stdout SHA256
`7d0072fbcf9652fa6f5814cb62521e663405180055e11c783bf3eb59266f90cb`, empty stderr.
Full restricted-container source preflight passed: all 437 archive entries (377 tracked files and 60 directories).
Source head: c0e1a1dff0ac1647ed5207f05247ff63f72f7cc7.
Image: sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3.
Auth helper: c08ae64da3b04abcebdf241920adb40fbfaf8a93daa075dffd64d5f86013cfc7.
Launcher: 93ddd96d6a3d346b3e62b0eec08d6666c70c1ebc7b2cc727d02c191c9d50a5b2.

Observed phase: actual-image helper `main` returns its fixed failure at
`tests/lifecycle/sglang_fixture/run_pinned_image.py:1000-1007`. The caught class,
inner phase, source file and line were deliberately suppressed. Earlier staging
EACCES is historical and must not be presented as the corrected auth failure.
No case-specific completion receipt was emitted; auth cases and SIGINT are
NOT_PROVEN, not established NOT_REACHED. No further helper execution is authorized
by Revision2 alone.

## Proposed narrow reviewed source diagnostic

Root/F1E2 should review a source-only diagnostic change to the helper. Do not
change launcher/installed modules, environment, assertions, execution flags,
capabilities, engine substitutes, signal scenarios or pass criteria.

1. Add fixed phase markers before `verify_sources` (line 745), launcher load and
   environment validation (746-749), Torch import (750), Transformers/AutoConfig
   setup (752-757), native HTTP/ServerArgs/auth imports (758-760), fixture file
   setup (764), negative-contract cases (778), route/warmup execution, and
   `run_failure_children` (982). Keep an explicit marker for each internal
   scenario; markers must be fixed source literals, never request/key values.
2. In the existing `except BaseException as error` (1000), retain exit 2 and the
   fixed FAIL status/code. Add the fixed phase marker and a safe exception class
   label from a reviewed allowlist; unknown classes become `OTHER_EXCEPTION`.
3. Emit only bounded traceback frame metadata: a reviewed module-path alias,
   source SHA256, integer line number and fixed function name. Permit only the
   reviewed helper/launcher and exact installed SGLang/Torch/Transformers/
   FlashInfer/FastAPI/Starlette/Uvicorn source roots. Reject unknown paths rather
   than print them. No traceback source lines, exception message/repr/args,
   locals, environment, argv, captured native output, response bodies or key
   material may be emitted. Limit frame count and byte size.
4. Add focused synthetic tests: sentinel strings embedded in exception messages,
   args, locals and unknown paths must not appear; known phase/class/file/line
   metadata is emitted; output is bounded; exit/status remain FAIL; successful
   helper output and all current assertions are unchanged.
5. Record new helper hash and diagnostic scope. Root reviews/merges before one
   separately authorized isolated diagnostic invocation. Preserve all historical
   receipts and use new unique container/CID identities and a published plan.

This is a diagnostic proposal only. No patch was applied and no diagnostic
helper was executed. Production auth gate remains false. Protected host key,
native CUDA/model/lifespan and real SIGTERM remain separate NOT_TESTED work.
