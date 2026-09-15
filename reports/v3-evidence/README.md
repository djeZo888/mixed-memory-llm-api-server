# V3 evidence and reproduction

Run only under a newly coordinated request lease. These are the commands
executed against reviewed source `5e713441d9ea164b81860ee795c5ef35972ee8e3`.
`V3_PRIVATE` denotes a fresh absolute owned 0700 directory outside Git;
`V3_KEY_FILE` denotes its protected owned 0600 existing-key copy. Neither
variable contains an actual credential value. Key transfer and curl header
configuration occur privately, never in argv or committed files.

```sh
/usr/bin/nc -vz -G 5 10.156.100.60 30002
/usr/bin/curl -q --noproxy '*' --connect-timeout 5 --max-time 20 \
  --silent --show-error --config "$V3_PRIVATE/correct.curl" \
  --output "$V3_PRIVATE/models.json" \
  --write-out '%{http_code} %{remote_ip} %{local_ip} %{time_connect} %{time_total}' \
  http://10.156.100.60:30002/v1/models

python3 -B scripts/agent/acceptance.py \
  --base-url http://10.156.100.60:30002/v1 --model glm-5.3 \
  --api-key-file "$V3_KEY_FILE" --auth enabled --stream-tools \
  --reasoning-effort low --max-tokens 2048 \
  --request-timeout 300 --overall-timeout 1800 \
  --report "$V3_PRIVATE/a1-report.json" --workspace-parent "$V3_PRIVATE"

python3 -B scripts/client/bootstrap.py \
  --prefix "$V3_PRIVATE/client" \
  --base-url http://10.156.100.60:30002/v1 --model glm-5.3 \
  --api-key-file "$V3_KEY_FILE" \
  --context-tokens 32768 --output-tokens 2048 --reasoning-effort low

python3 -B scripts/client/verify.py \
  --prefix "$V3_PRIVATE/client" \
  --output-dir "$V3_PRIVATE/verification" --timeout-seconds 1800
```

Native auth also ran with no config/header and a separate deliberately wrong
protected config. All three curls suppressed default curlrc loading and proxies.
There were no changes to OS privacy controls or TLS verification. SSH was used
only for the authorized read of the existing inference key.

A1 ran once and exited 1. Its sole invalid-model aggregate failure was retained;
all other checks and the genuine agent passed before dependent native client
verification. The ordinary verifier ran once and exited 0. The bootstrap
performed only client-local locked npm installation and overlapped A1 without
issuing inference. No tests or client modes were silently retried.

## Sanitized artifact contract

- `source-manifest.json`: exact reviewed commit/tree/archive and 33 source hashes.
- `direct-auth.json`: native status/address/timing/model allowlist, no response bodies.
- `a1-stream-tools.json`: allowlisted raw-report derivative with raw SHA256,
  supervisor UTC times, CLI exit, request/model/status/timing/usage, observed
  stream termination, hashed call IDs and real fixture/test/hash evidence.
  No raw messages, reasoning, output, arguments, diff or final reply text.
- `ordinary-client.json`: byte-for-byte unchanged V2 sanitized report. Its
  `raw_evidence_file` refers to private task data, intentionally unpublished.
- `bootstrap.json`: sanitized invocation metadata and selected limits.
- `cleanup.json` and `lease-release.md`: owned-resource closure and explicit release.
- `validation.json`: publication checks. Taskroot `final.md` and `results.json`
  identify the resulting commit, remote branch and verified full bundle.

Absent A1 stream usage is `NOT_REPORTED`; OpenCode native counters are explicitly
separate from provider-wire usage. The A1 aggregate stays FAIL even where an
unknown-model request has transport/parse `success: true`.

## Offline publication verification

```sh
git diff --check
git diff 5e713441d9ea164b81860ee795c5ef35972ee8e3 -- scripts tests configs docs AGENTS.md
python3 -B - <<'PYCODE'
import hashlib, json, pathlib, subprocess
root = pathlib.Path.cwd()
manifest = json.loads((root / 'reports/v3-evidence/source-manifest.json').read_text())
for path, expected in manifest['files'].items():
    data = (root / path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected
    assert data == subprocess.check_output(['git', 'show', manifest['source_commit'] + ':' + path])
a1 = json.loads((root / 'reports/v3-evidence/a1-stream-tools.json').read_text())
assert a1['status'] == 'FAIL' and a1['agent']['status'] == 'PASS'
assert [k for k, v in a1['checks'].items() if v['status'] == 'FAIL'] == ['invalid_model']
assert all(r['stream_done'] for r in a1['agent']['rounds'])
native = json.loads((root / 'reports/v3-evidence/ordinary-client.json').read_text())
assert native['status'] == 'PASS' and all(native['checks'].values())
assert native['observed_model_before'] == native['observed_model_after'] == 'glm-5.3'
assert native['tests_before_sha256'] == native['tests_after_sha256']
assert native['process']['exit_code'] == 0 and native['process']['process_tree_reaped']
print('PASS: source and observed evidence consistency')
PYCODE
```

Before key deletion, an in-memory scan checked actual key bytes, ordinary JSON
escaping and the reviewed OpenCode opening-brace interpolation escaping against
all tracked/publication files and the owned private task tree. Only the intended
key/curl files held the secret; they were removed. No match values were printed.
A grep-based tracked/publication scan and credential-free remote verification
also precede push. All new shell blocks have documented syntax verification;
no source or test implementation was added or changed in V3.
