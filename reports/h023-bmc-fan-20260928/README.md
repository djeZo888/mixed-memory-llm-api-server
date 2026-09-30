# CHA_FAN3 manual control — verified September 28, 2026

After the user replaced the server Blackwell's cooling, a bounded idle test
proved the BMC can raise **CHA_FAN3 to 100%**. It restored the user's curve at
15:21:14 UTC. No other fan header, temperature breakpoint, source or global
mode changed.

| Observation | Before | Test | Restored |
|---|---:|---:|---:|
| First four curve duty points | 75% | 100% | 75% |
| Final safety point at 100°C | 100% | 100% | 100% |
| Raw CHA_FAN3 tach reading | 4,920 | 6,000 | 5,040 |

The BMC omitted `ReadingUnits`; the readings show a speed response but are not
presented as independently verified RPM. Each changed setting settled for ten
seconds before readback. Both writes returned HTTP200, all four fan-resource
snapshots matched the intended state, 19 actual peer-certificate pin checks
passed, and the owned login was logged out. No errors were recorded.

The installed BMC UI's per-header `PUT /api/fanctrl/PWM` contract was checked
before use. The target was `Zone4(CHA_FAN3)`, array index3/PWMNum3/PWMSrc0.
This used the existing protected administrator credential on ai-harness;
credentials, cookies, CSRF values and raw vendor source remain outside Git.

This proves a **manual remote override and restoration**, not a persistent
GPU-temperature controller. The current curve follows CPU temperature.
Automatic control, sensor/controller-loss fail-safe behavior, minimum account
role and persistence across BMC reboot were not qualified here.

The retained helper is specific to this completed task, its deadline and exact
private authorization. It must not be blindly replayed. Twelve offline fixture
tests passed before the live test. See `FAN-TEST.json`, `FAN-RESTORE.json` and
`OFFLINE-TESTS.txt` for evidence.
