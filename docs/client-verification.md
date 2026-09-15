# Ordinary-user OpenCode verification

V2 runs the reviewed small word-count task with actual pinned OpenCode 1.18.31.
It produces private client evidence. It does not assess the whole API protocol,
server runtime, installer readiness, or a model's maximum practical context.

## Run

Use an existing private prefix configured through the reviewed
[client bootstrap](client-install.md). The configured model, context, output
budget, reasoning option and credential reference are used unchanged. Run from a
complete reviewed source checkout as an ordinary user (UID greater than zero):

```sh
python3 -B scripts/client/verify.py \
  --prefix /absolute/private/client-prefix \
  --output-dir /absolute/private/new-verification-run
```

The output directory must not already exist. It must be outside Git and the
client prefix, under existing safe ancestors, with no symlink components or
`..`. The verifier creates it with mode 0700 and its files with mode 0600.
`--timeout-seconds` accepts 1 through 1800 (default 1800); process cleanup has a
small bounded grace period after timeout. `--help` is offline.

The prefix must use authentication. It is checked against the reviewed launcher,
shared client source, package manifest and lock, generated configuration, and
installed package bytes. Each installed package is checked against its original
SHA512-verified tarball in that prefix's isolated npm cache. A missing/pruned
cache or modified file is a refusal. The verifier never repairs or upgrades an
existing prefix. The actual Node, npm, OpenCode and plugin versions are recorded.

This source currently retains V0's explicit loopback endpoint gate. Direct
separate-host HTTP/TLS support waits for reviewed N1C source integration. Its
approved policy is canonical RFC1918 literal IPv4, HTTP(S), an explicit port and
exact /v1 path; DNS/public IPs/TLS bypass and private unauthenticated access are
refused. N1C owns shared endpoint/auth validation; V2 does not edit it. Do not manually change prefix configuration to
bypass that gate. A live model run also requires its separately coordinated
request lease; the V2 source verification task itself authorizes no live request.

## What PASS requires

The verifier creates `workspace/` using the exact V1G2 fixture bytes. The initial
`split(" ")` implementation must produce five intended assertion failures across
three test methods, with no import errors. The immutable tests explicitly load
the sibling implementation through `importlib` under Python isolated mode.

Actual native OpenCode events must establish this ordered work:

1. Read both `text_utils.py` and `test_text_utils.py`.
2. Edit only `text_utils.py`.
3. Request exactly `python3 -I -B test_text_utils.py` in that workspace.
4. Receive the actual passing test tool result with exit code zero.
5. Produce a final text response and terminal stop.

An independent final execution must also pass. Test bytes are checked before
and after that execution, the implementation must remain stable during it, and
no extra workspace files are accepted. The model list must contain exactly the
configured model before and after the agent run. This observes API discovery;
it does not independently attest the server's runtime/image/deployment identity.

Only the implementation receives edit permission; bash receives only the fixed
test command and external-directory access is denied. A denied attempt may be
retained as failure metadata when the model subsequently performs all required
work successfully, as in V1G2. Executed outside-workspace actions, wrong commands,
edited tests, malformed/partial events, terminal length, and final prose without
the observed test chain cannot pass.

Tools execute with the ordinary user's privileges. This is process supervision
and tool permission enforcement, not an OS sandbox. The runner terminates its
process group, tracks observed descendants (including changed process groups),
waits for cleanup, and reports failure if cleanup cannot be verified. No claim
is made about hostile same-user interference or unobserved daemonization.

## Outputs and privacy

- `report.json`: `ordinary_client_verification`, `status` PASS/FAIL, the eight
  explicit checks, phase/failure codes, baseline/final results, endpoint/model,
  configured settings, actual client versions, artifact hashes, sanitized native
  event counts, tool identities hashed by SHA256, and reported native counters.
- `raw-evidence.json`: bounded stdout/stderr and process results for the baseline,
  actual native run and final tests when reached. Credential text is redacted
  before writing. Its exact file bytes are SHA256-bound in the report.
- `workspace/`: the disposable fixture and model-edited implementation.

Raw data stays private and outside Git. The inference credential is supplied
through the existing protected file/environment mechanism, never argv. The
independent final test receives no injected inference-key environment variable.
Reports never copy raw bodies, arbitrary command arguments, tool output or
untrusted exception messages. Failed and token-exhausted runs remain diagnostic
FAIL reports. Exit code 0 means client PASS; exit code 1 means failure. A preflight
failure before safe output creation prints only a fixed error code.

A model-list transport error records only a safe code and numeric errno/status.
A Python/macOS local-network privacy denial is distinct from server or firewall
failure; this command never changes OS privacy controls.

Native OpenCode counters are preserved only when actually present. They are
client-reported values, not independently captured provider-wire usage. This
verifier does not test unknown-model rejection. The known GLM invalid-model
protocol failure remains in [the V1G2 protocol evidence](../reports/v1g2-agent-measurement.md).
A client PASS cannot override that failure.

Incoming Revision2 explicitly deferred installer receipts, challenges, producer
approval and bootstrap composition. There is no installed `llm-agent-verify`
provisioning, receipt output, acceptance registry entry or installer gate here.

## Artifact contract

[The source manifest](../reports/v2-source-manifest.json) lists exact required
client/verifier files as sorted repository-relative paths and SHA256 of each
file's bytes. `source_sha256` is SHA256 of the UTF-8 canonical JSON path-to-hash
object: `json.dumps(files, sort_keys=True, separators=(",", ":"))`, using Python's
default `ensure_ascii=True`. This matches existing `core.digest` serialization
without importing installer modules. The generated manifest is excluded to
avoid a cycle. Test sources that exercise the verifier are validation material;
the manifest binds the exact runtime producer and required client files.

`test_sha256` hashes the exact immutable test file bytes.
`test_command_sha256` hashes these exact UTF-8 bytes, without a trailing newline:

```text
["python3","-I","-B","test_text_utils.py"]
```

These are reproducibility hashes, not approved-producer pins or signatures.
Q38C or N1 shared-client changes will change this manifest and must be integrated
and reviewed with the corresponding prefix/source compatibility check.

## Reproduce source verification

```sh
python3 -B -m unittest discover -s scripts/client/tests -p 'test_*.py'
python3 -B scripts/client/tests/verify_wire_fixture.py \
  --work-root /absolute/private/new-v2-synthetic-run
```

The second command is an explicit opt-in: it creates a fresh ordinary-user
prefix through the unchanged pinned bootstrap and may download the locked npm
packages. It runs the real native client against a deterministic synthetic
loopback HTTP server. That server requests actual read/read/edit/bash operations
and validates their replay, disk change and test results. It cannot establish
live model quality. The fixture's 32768/2048/low settings are test inputs, not
product limits or approved hardware presets. No VM is contacted or changed.
