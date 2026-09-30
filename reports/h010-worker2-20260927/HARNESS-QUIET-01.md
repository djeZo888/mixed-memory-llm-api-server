# H010 quiet harness receipt

QUIET_APP_STOPPED_SEARCH_STATUS_ADMIN_PRESERVED at 2026-09-26T23:24:21.183369+00:00. App user unit ai-harness.service inactive/MainPID0, still enabled. Search user unit and system status/admin units remain active with unchanged PIDs. Only search container runs.

Fresh owner checks immediately before stop: zero active runs/Flash requests/image jobs/native containers; all three text lanes idle; image lane idle, ownership uncertain=0. One historical quarantined workspace preserved. No atomic drain claim; backend counters remain unknown.

26 sessions, 133 messages, 62 file records, 48 terminal runs and 19 terminal image jobs retained with identical serialized hashes. One fresh private SQLite backup API snapshot integrity=ok at /home/user/ai-harness-build/H010-WORKER2-20260927/harness-before-stop-01.sqlite. 17597 regular files in the raw inventory (excluding .sqlite names and their sidecars) retain identical count/content inventory hash. SQLite transient-file count changed on clean stop; initial receipt comparison caught that expected difference; read-only finalization confirmed data preservation. Image lane is now quarantined by normal shutdown; no manual clear.

Before stop: health/status HTTP200 and fresh canonical Flash/Qwen0/Qwen1/image available/ready; Flash qualified480000/output65536 configuration and protected credential metadata verified. No key values read. No ai-vm contact or inference.

Restore only in fresh recovery session after explicit Worker1 handback: `systemctl --user start ai-harness.service` on ai-harness as ordinary user. Do not restore older databases, clear quarantine or restart during benchmark.
