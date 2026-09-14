# D2CI — hosted workflow diff-base correction

- Date: 2026-09-15; worker: Mac-Worker2, Python 3.14.7, Git 2.54.0.
- Branch: `milestone/d2-ci-diff-base`.
- Reviewed integration base: `35e02ba6d1b781812c7e54628222660de4328e2e`.
- Scope: this report, `.github/workflows/d2-lifecycle.yml`, and the focused
  [regression helper](../tests/ci/test_d2_whitespace.py).
- Status: **PASS — worker verification**; corrected merged hosted run pending.

## Observed failure

Read-only `gh run view` metadata and logs for
[D2 run 34908949832](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34908949832)
confirm that both existing test steps passed. Only `Check whitespace` failed.
The checkout fetched with `--depth=1` and tested PR merge commit
`57353c4c8ed2d8a957ff751792f7bbadc55d8fc3`, for contributor head
`35e02ba6d1b781812c7e54628222660de4328e2e`. The recorded PR base was
`717116717fe9e1fc00c6954c17d4f82941dd04ba`.

With its parent unavailable, `git show --format= --check HEAD` treated the shallow
boundary as a root and scanned unchanged historical content. Failures included
M1/M4B report whitespace and old blank lines at EOF in documentation, storage
scripts and a test. This correction preserves all those bytes.
[General CI run 34908949840](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34908949840)
passed on that original head; that observation does not validate this correction.

## Change and event policy

Checkout now requests `fetch-depth: 0`; the gate additionally refuses a shallow
repository. Existing lifecycle and CLI test commands remain unchanged. One new
focused test step executes the workflow's actual whitespace shell block against
disposable local Git repositories.

| Event | Whitespace range |
| --- | --- |
| Pull request | Exact event `pull_request.base.sha` to checked-out `github.sha` merge commit; verify the base is its ancestor |
| Push with nonzero `before` | Exact event `before` to checked-out `github.sha`; supports multi-commit and non-ancestor force pushes |
| First push, all-zero `before` | Merge-base of the event commit and fetched `refs/remotes/origin/<default branch>`, when distinct from the event commit |
| First push without a distinct usable default-branch merge-base | Empty tree to event commit, explicitly logged as a full initial-content check |

The first-push fallback covers an initial/default-branch push, unrelated or absent
default history, and a branch already at/behind the fetched default tip. It is
deliberately conservative: in those cases historical whitespace can fail the
full-content check. It never treats an ambiguous first push as an automatic pass.
The default-branch snapshot is the one fetched by checkout; PR and ordinary push
endpoints always use recorded event SHAs, irrespective of moving branch refs.

Event values enter through step environment variables only. SHA inputs must be
exactly 40 hexadecimal characters; zeros are allowed only for push `before`.
The checked-out HEAD must match the event SHA. Endpoints must be commit objects;
an absent nonzero endpoint is fetched from `origin` by validated SHA and verified
again. A failed fetch or verification stops the gate without changing its range.
Default branch names pass `git check-ref-format`. Git runs through Python
subprocess argument arrays; event data is never interpolated into shell code.
The gate prints its resolved range and runs `git diff --no-ext-diff --check` over
all changed paths, with no exclusions or report cleanup.

## Verification

| Command / check | Result and scope |
| --- | --- |
| `gh run view 34908949832 --repo djeZo888/mixed-memory-llm-api-server --json conclusion,event,headBranch,headSha,name,status,jobs,url` and `--log-failed` / `--log` | PASS: read-only original run metadata, failure and depth-one checkout inspected |
| `gh api repos/djeZo888/mixed-memory-llm-api-server/actions/runs/34908949832` and `gh run list --commit 35e02ba6d1b781812c7e54628222660de4328e2e` with explicit repository | PASS: exact PR base/head and original general CI success verified; no credential output |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -v` | PASS: 116 tests, 6.139s, Mac worker |
| `bash tests/shell/test-llmctl-static.sh` | PASS: retained planning static checks |
| `bash tests/shell/test-llmctl-fixtures.sh` | PASS: retained planning fixtures |
| `bash tests/shell/test-llmctl-lifecycle-static.sh` | PASS: retained lifecycle source/help/refusal checks |
| `bash tests/shell/test-llmctl-lifecycle-fixtures.sh` | PASS: retained CLI fixtures |
| `bash tests/shell/test-sglang-smoke-static.sh` | PASS: retained offline smoke planning check |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/ci/test_d2_whitespace.py -v` | PASS: 13 tests, 6.762s, disposable local Git fixtures; no network or VM |
| `python3 tests/ci/test_d2_whitespace.py --help` | PASS |
| `git diff --check 717116717fe9e1fc00c6954c17d4f82941dd04ba 35e02ba6d1b781812c7e54628222660de4328e2e --` | PASS: actual original PR base to contributor head |
| `git fetch --no-tags origin 57353c4c8ed2d8a957ff751792f7bbadc55d8fc3` and `git diff --check 717116717fe9e1fc00c6954c17d4f82941dd04ba 57353c4c8ed2d8a957ff751792f7bbadc55d8fc3 --` | PASS: actual tested merge commit fetched and its recorded PR range checked |
| `python3 ../reproduce-hosted.py` (external task artifact) | PASS: local depth-one fetch of the actual hosted merge reproduces M1/M4B failures; unshallow fetch plus the corrected production step passes without changing any tree bytes |
| `ruby -` with standard-library YAML/Open3 assertions | PASS: YAML parse, exact event environment bindings, depth zero, unchanged original test steps/triggers/permissions, and `bash -n` for every workflow shell block |
| Changed-file scope, local Markdown links, grep-based secret/forbidden-file scan and `git diff --check` / `git diff --cached --check` | PASS before commit; only the three authorized repository files |
| `git remote -v` and GitHub credential-helper checks | PASS: credential-free expected HTTPS origin and existing `gh auth git-credential` helper; rechecked before feature push |
| Corrected workflow on merged hosted revision | **PENDING**: root review/merge and actual hosted observation required |

The five retained shell suites ran with `PYTHONDONTWRITEBYTECODE=1`; no source
commands inside those suites changed. Worker logs are external task artifacts:
`lifecycle-tests.log`, `shell-tests.log`, `whitespace-tests.log`, and
`hosted-reproduction.log`. No other workflow or application test suite was
modified, and the unrelated client/installer suites were not rerun for this fix.

The focused helper executes the actual workflow shell block, rather than a copy
of its selection algorithm. Coverage includes an inherited-whitespace base;
clean and newly dirty PR and multi-commit push changes; a recorded PR base
different from the first parent; a moving default branch requiring a merge-base;
depth-one refusal/unshallow recovery; non-ancestor force pushes; initial/root,
missing, equal-HEAD and unrelated default-branch fallbacks; missing before-SHA
fetch from a local origin and unavailable-SHA refusal; wrong object types;
mismatched HEAD; malformed/zero SHA inputs; unsupported events; invalid branch
refs; and literal handling of shell-looking metadata.

## References

- [actions/checkout documentation](https://github.com/actions/checkout): default
  single-commit fetch and `fetch-depth: 0` history behavior.
- [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows):
  PR merge `GITHUB_SHA` and push event semantics.
- [GitHub webhook payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads#push):
  push `before` metadata.
- [Git diff documentation](https://git-scm.com/docs/git-diff): two-endpoint diff
  and whitespace errors reported by `--check`.

## Warnings and next action

No packages, services, storage, backend, model, client or installer changes were
made, and no ai-vm access occurred. Worker tests are deterministic source/Git
fixtures. They do not establish hosted execution of this revision or live
inference behavior.

Root reviews and merges the feature branch or full bundle, then observes D2 on
the actual merged revision. Hosted success for that revision remains pending.
Final commit, publication and bundle identities belong in the external task
`final.md` and `progress.md`, avoiding self-referential hashes in this report.
