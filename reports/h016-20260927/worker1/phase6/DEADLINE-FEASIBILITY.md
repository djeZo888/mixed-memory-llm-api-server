# R5 live deadline extension feasibility

**UNSUPPORTED: no evidenced live extension control in the exact running R5 source.** Root13:27 extended overall authorization to15:48:08 and revoked early stop; phase6 still ends13:34:05. Neither instruction changes the constants already loaded by owner/proxy/client. No stop, signal, source edit, systemd change or VM call was made by this review.

- Owner lines28–29 set admission13:25 and hard end13:40. Lines313–325 leave the warm loop at13:40 and unconditionally clean the proxy and settle in `finally`.
- Owner lines221–222 define interruption; line339 installs only SIGTERM. This is termination/settlement handling, not reload. CLI options are `--run`, `--settle`, `--dry-run`.
- Proxy lines114–116 separately encode13:25 chat admission and `min(now+7200,13:40)` request deadline; lines164–167 enforce it while draining.
- Benchmark line8 imports the owner constants; lines74/78 enforce admission and `min(start+7200,HARD_END)`. Lines91–93 enforce the saved deadline while draining.
- Systemd launch uses RuntimeMaxSec3754, TimeoutStopSec420, KillMode=mixed and the exact R5 `candidate_owner.py --settle` ExecStopPost. The retained snapshot independently reports RuntimeMaxUSec1h2min34s and that same ExecStopPost for invocation4600b556d5d04305a9157da80149a511/PID2779569.

Extending only systemd would leave the Python owner cutoff intact. A source-file edit would not update constants in the active interpreters. No deadline-file polling, control route or reload handler is evidenced in the reviewed source. A continuity-preserving extension therefore has no supported mechanism established by this review; this is not permission to improvise process injection, signal changes or replacement ownership.

Source SHA256 and exact line excerpts follow. All three Python files match the remote source hashes retained in the phase6 snapshot; JSON includes each excerpt SHA256 and snapshot linkage. The snapshot is historical readback, not a new live observation.

`scripts/h016/r5/candidate_owner.py` SHA256 `11041d78f05bb0522d48b293f0a4283629d4a15f787e8477be6591b4b7faa483`

```text
28: ADMIT_END = datetime.datetime(2026, 9, 27, 13, 25, tzinfo=datetime.timezone.utc).timestamp()
29: HARD_END = datetime.datetime(2026, 9, 27, 13, 40, tzinfo=datetime.timezone.utc).timestamp()
```

```text
208: def cleanup_proxy_and_settle(h, proxy):
209:     try:
210:         if proxy and proxy.poll() is None:
211:             proxy.terminate()
212:             try:
213:                 proxy.wait(timeout=3)
214:             except subprocess.TimeoutExpired:
215:                 proxy.kill()
216:                 proxy.wait(timeout=3)
217:     finally:
218:         settle(h)
219:
220:
221: def interrupted(*_):
222:     raise RuntimeError('owned_supervisor_interrupted')
```

```text
313:         while time.time() < HARD_END:
314:             h.require(not failed.is_set() and proxy.poll() is None and inspect(state['candidate_id'])['State']['Running'], 'warm_owner_guard_failed')
315:             time.sleep(5)
316:         # No persistent adoption in initial packet: bounded deadline always settles.
317:         # Later adoption code must be separately reviewed before any W2 activation.
318:         state['status'] = 'DEADLINE_SETTLING_UNADOPTED_CANDIDATE'
319:         save(h, 'OWNER.json', state)
320:     except BaseException as exc:
321:         state.update(status='FAILED_SETTLING', error_type=type(exc).__name__, error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
322:         save(h, 'OWNER.json', state)
323:     finally:
324:         failed.set()
325:         cleanup_proxy_and_settle(h, proxy)
```

```text
329: if __name__ == '__main__':
330:     parser = argparse.ArgumentParser(description=__doc__)
331:     parser.add_argument('--run', action='store_true')
332:     parser.add_argument('--settle', action='store_true')
333:     parser.add_argument('--dry-run', action='store_true')
334:     args = parser.parse_args()
335:     if args.settle:
336:         h = dependency()
337:         settle(h)
338:     else:
339:         signal.signal(signal.SIGTERM, interrupted)
340:         raise SystemExit(main(run=args.run and not args.dry_run) or 0)
```

`scripts/h016/r5/private_proxy.py` SHA256 `82d88ed7e13de4a4a36b1a74a4186927e7e03a5380e109860e4e076f3baeb50c`

```text
112:             chat = self.path == '/v1/chat/completions'
113:             now = time.time()
114:             if chat and now >= datetime.datetime(2026, 9, 27, 13, 25, tzinfo=datetime.timezone.utc).timestamp():
115:                 return self.error(503)
116:             deadline = min(now + 7200, datetime.datetime(2026, 9, 27, 13, 40, tzinfo=datetime.timezone.utc).timestamp())
117:             if now >= deadline:
118:                 return self.error(503)
```

```text
163:                 while True:
164:                     if time.time() >= deadline:
165:                         raise TimeoutError('owned_absolute_deadline')
166:                     if conn.sock:
167:                         conn.sock.settimeout(max(.1, deadline - time.time()))
```

`scripts/h016/r5/benchmark.py` SHA256 `ece4d5d801edc10505ae7d7e9e108a8d4a017e76ac436a220b050f0239e75803`

```text
8: from candidate_owner import ADMIT_END, HARD_END, BASE, LOG, save
```

```text
73: def request(h, key, payload, label, failed):
74:     h.require(time.time() < ADMIT_END and not failed.is_set(), 'benchmark_admission_closed')
75:     expected, raw = count(key, payload)
76:     h.require(expected + payload['max_tokens'] <= 131071, 'context_admission')
77:     start = time.monotonic()
78:     deadline = min(time.time() + 7200, HARD_END)
79:     row = {'label': label, 'started_utc': h.now(), 'expected_input_tokens': expected, 'request_sha256': hashlib.sha256(raw).hexdigest(), 'thinking': payload['chat_template_kwargs']['enable_thinking'], 'output_budget': payload['max_tokens'], 'status': 'SUBMITTED'}
80:     save(h, label + '.json', row)
81:     c = http.client.HTTPConnection('127.0.0.1', 30012, timeout=max(.1, deadline - time.time()))
```

```text
90:         while True:
91:             h.require(time.time() < deadline and not failed.is_set(), 'request_guard_or_deadline')
92:             if c.sock:
93:                 c.sock.settimeout(max(.1, deadline - time.time()))
94:             chunk = response.read1(65536)
```

`reports/h016-20260927/worker1/phase3/r5/R5-LAUNCH.json` SHA256 `17f182bb5c1d531220464fbf63e56690bc7a976e3f19bc7892236b0138c20cc6`

```text
7:     "--property=Restart=no",
8:     "--property=RuntimeMaxSec=3754",
9:     "--property=TimeoutStopSec=420",
10:     "--property=KillMode=mixed",
11:     "--property=UMask=0077",
12:     "--property=StandardOutput=null",
13:     "--property=StandardError=null",
14:     "--property=ExecStopPost=/usr/bin/python3 -B /data/build/H016-20260927/worker1-r5/candidate_owner.py --settle",
```

Snapshot ending 2026-09-27T13:17:49.447621+00:00, SHA256 `c0d11830bc463122046c23b04b44c46c2524404cb586841098a9b74e6acaa157`.
