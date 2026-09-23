# User runtime and service

The host server runs as the existing `user` account, outside task containers.
The reviewed official Node pin is in `node-pin.json`: **v24.21.0**, resolved
2026-09-22 from the [official Node 24 index](https://nodejs.org/dist/latest-v24.x/)
and [release SHASUMS256](https://nodejs.org/dist/v24.21.0/SHASUMS256.txt).
The installer verifies both the committed checksum and freshly downloaded
official checksum before extraction, and retains a receipt and the checksum
manifest in the prefix. This is checksum verification over HTTPS, not a claim
that a release-signing key has been independently verified.

As ordinary `user` on ai-harness, after reviewed source staging (the paths below
are examples; substitute the reviewed checkout path):

```sh
bash /home/user/ai-harness/ai-harness/deploy/install-node.sh --dry-run
bash /home/user/ai-harness/ai-harness/deploy/install-node.sh
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin
node --version
```

No host Node package, shell startup edit or account change is needed. A rerun
verifies a managed installation; an unrelated existing destination is refused.
Dependencies are ordinary Ubuntu `curl`, `tar`, `xz`, `python3`, `sha256sum`.
The bootstrap handles rootless Podman/nginx separately. Installing Node does not
require waiting for the privileged bootstrap. Run `npm ci` and `npm run build`
in the separately reviewed `server` and `web` source directories using this
explicit PATH; retain their lockfiles. `run-server.sh` requires the resulting
`server/dist/main.js` and `web/dist`.

The installer can also be staged independently: copy `install-node.sh` and its
sibling `node-pin.json` to the same user-owned directory, then invoke the script
as `user`. Do not copy credentials into that staging directory.

## User service template

`systemd/ai-harness.service.in` is a template, not an installed/started service.
Substitute these absolute paths after source review:

| Placeholder | Example |
| --- | --- |
| `@HARNESS_DIR@` | `/home/user/ai-harness/ai-harness` |
| `@NODE_PREFIX@` | `/home/user/.local/opt/ai-harness/node-v24.21.0` |
| `@DATA_DIR@` | `/home/user/.local/share/ai-harness` |
| `@INFERENCE_KEY_FILE@` | Existing protected inference-only credential file |

Use paths without whitespace or systemd `%` specifiers when substituting this
minimal template. Install the rendered unit as
`~/.config/systemd/user/ai-harness.service` with mode `0600`; then validate with
`systemd-analyze --user verify ~/.config/systemd/user/ai-harness.service`.
After approval to activate, use `systemctl --user daemon-reload` and
`systemctl --user enable --now ai-harness.service`. Bootstrap enables linger for
the existing user; do not add a separate login account. Check
`systemctl --user status ai-harness.service` and bounded `journalctl --user -u
ai-harness.service -n 80 --no-pager` output without sharing credentials.

The server launcher supplies a clean environment and explicit Node PATH,
`AI_HARNESS_DATA_DIR`, `AI_HARNESS_ENGINE_LAUNCHER` and the protected
`AI_HARNESS_INFERENCE_KEY_FILE` **path**. It also explicitly selects the runner
gateway URL `http://10.0.2.2:8081/v1`, public origin `http://10.156.100.61`
and the built web/dist path. The gateway service itself remains bound to
127.0.0.1:8081; the supplied URL is for its rootless workers.
It does not read or export key contents.
The key file must be owned by the service user with mode `0600` or `0400`; the
data directory is private to that user. Use the existing inference-only key,
never a model-lifecycle credential. Per-runner ephemeral tokens are generated
by the backend and passed only through the reviewed engine-launcher contract.
The profile/workspace mounts never include the key or the server data root.

The expected listeners are `127.0.0.1:8080` for HTTP and `127.0.0.1:8081` for the
gateway; nginx alone listens at private `10.156.100.61:80`. The rootless engine
uses the reviewed `slirp4netns:allow_host_loopback=true` route to
`http://10.0.2.2:8081/v1`. Reachability and nested Chromium sandbox support need
live checks after Podman bootstrap. No `--no-sandbox` workaround is authorized.

The unit deliberately omits `NoNewPrivileges` and namespace restrictions that
would prevent Podman's subordinate-ID helpers/nested user namespaces. It uses
the service user's systemd cgroup delegation. The launcher never invokes sudo.
Service stop/restart may interrupt active tasks; backend recovery must mark
them interrupted and must not replay side effects. Reboot, install, runtime
build, activation and end-to-end operation are separate from source/static QA.

The agreed shutdown source contract budgets at most 40 seconds for launcher
cleanup, 45 seconds for SERVER to observe its exact exit, and 60–70 seconds for
overall server exit with parallel cleanup. `TimeoutStopSec=90` leaves the user
service room to complete that sequence. Live shutdown acceptance remains pending;
unconfirmed container settlement retains the backend workspace quarantine.

## v0.0.3 host image broker and browser approval capability

The reviewed server pins Sharp 0.35.4 (lockfile includes its platform codec) on
Node24. Run `npm ci` in server on the deployment host; do not copy macOS native
node_modules to Linux. Main reuses the existing protected inference-key loader
and key for fixed `http://10.156.100.60:30006`. There is no production URL override.
Image health/reconciliation owns no text lane. Missing edit capabilities keep
editing unavailable. This source delivery does not qualify image editing.

Canvas approval now requires a separate host-only nginx-to-server capability.
For later root-reviewed deployment, provision a random secret outside Git, with
an owner-only file readable by the existing harness service user; set
`@BROWSER_APPROVAL_KEY_FILE@` / `--browser-approval-key-file` to that file. The
server loads it using the existing protected file loader. Never mount this file
or expose its value to engines, browser JS, MCP, environment values or logs.
Without this optional file, image generation works but approval-token issuance
fails closed. It must not reuse the inference key or session bearer token.

Install `/etc/ai-harness/image-approval-proxy.conf` root:root0600, containing only
`proxy_set_header X-AI-Harness-Approval-Proxy "<same protected secret>";` with the
real value supplied privately during reviewed activation. The checked-in nginx
configuration includes that file only on the exact approval-token issuance route;
all other routes strip the header. Do not capture `nginx -T` output after install.
The source nginx ACL denies127/8, ::1 and the known harness address10.156.100.61,
allows external10.156.100.0/24 browser clients and denies everything else. Before
activation, root must inventory actual host/container egress addresses and add
all own addresses to the deny list, and review any required external LAN range.
Do not enable real-IP rewriting based on untrusted forwarding headers.

Browser GET `/api/sessions/:id/image-jobs/:jobId/approval-token` returns
`{approvalToken,expiresAt}`; only this route needs the proxy capability header.
The browser includes `approvalToken` with approve/reject. Tokens are random,
10-minute, stored only as hashes and bound to the persisted job/input/adjustment.
Identical token+decision replay only returns the same decision's result; it cannot
execute again. They are never included in job records, SSE, artifacts or MCP.

Offline tests cover missing/spoofed proxy header, bearer-surface rejection,
wrong-job/expired/consumed token handling and immutable approval binding. Later
activation must separately verify actual engine-to8080 and engine-to80 issuance
rejection (including forged Origin/Host/forwarding headers), external LAN browser
issuance and approval success, no proxy secret in responses/logs, and Linux codec
loading. Those are deployment acceptance gates, not claims from these fixtures.
