# CLIENTTEXT: blank native text fragments

Source-only correction against `0eb91c0ad9c92743afacdf0cefdc955dfe614e2c`.
Scope: native event verifier, its focused parser tests, and this report.

Historical APIACCEPT failure (Worker2 structural metadata supplied through
task-root `incoming.md`, not independently replayed here): zero-based event 3
was a one-character whitespace text fragment between completed reads and step
finish; event 12 was a later 114-character non-whitespace final response.
The original report failed with `native_empty_text` / `client_checks_failed`
despite all eight checks being true and process exit 0, including immutable
tests, independent test rerun, and process cleanup. Original verifier SHA256:
`dbb8eb6b2ee85ff11f42aa49571424e5165082b12c8eb4b55eb1d522c42bd9ca`.
Original private evidence remains unchanged; no raw events or content copied.

Blank string fragments now contribute no text evidence. Non-string or missing
text still fails with the existing diagnostic. Identity, step/terminal order,
read/edit/test evidence, and nonempty final text after a passed test remain
required. Only the text-content conditional changed.

Synthetic regressions cover empty and whitespace fragments before/after tools,
after the passed test, and around the real final response; non-string/missing
text, missing/blank final responses, text preceding the passed test, and invalid
step/message/terminal ordering remain refusals. The original source failed all
12 new positive subcases with `native_empty_text`; the task-root baseline log
preserves that local reproduction separately from historical APIACCEPT evidence.

Focused validation: **PASS**, 25 parser tests in 0.017s, exit 0. From
`scripts/client/tests`, run
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_verify_events.NativeEventTests -v`.
Task-root `focused-tests.log` records the run. No broad or installer suite.
No VM, network inference, control mutation, deployment, or original-event replay.
Root must review the published commit before deployment/replay. Worker2 can
replay the original recorded events with the reviewed correction without a model
rerun; that replay and live acceptance are not established by these source tests.
