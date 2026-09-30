# Exact rollback retained

Active source: `b5717d03416252c8640c47d37baf892a0c4e532a`. Prior release:
`/home/user/.local/share/ai-harness-app/releases/cacfdd43c42d675ab154ba7308404d71c81a64f1`.
Application snapshot: `/home/user/.local/share/ai-harness-deploy/H003-DEPLOY-20260923/rollback-20260923T120139Z` (owner-only), including exact
prior release and dependency files, service unit, profiles/workspaces/uploads/artifacts,
consistent harness.sqlite and final stopped-service harness-final-idle.sqlite.
Root nginx snapshot: `/var/backups/ai-harness-H003-DEPLOY-20260923/20260923T115442Z/nginx`.
Prior engine ID: `4af6da23f70c3bc20d557be623d3d3bed7ef5d889e2b510debe556dc54936da3`;
digest `sha256:e9ab4de40f3b36b2cfa08fc41f61c514800ab417e6d8e5a52683827fac1ca1f3`.

Rollback is NOT executed. Only native Worker1 may perform it after checking active
user runs/image jobs/gateway lanes are idle; never kill or erase user work. Preserve
a fresh consistent DB and new artifacts before rollback. Stop ai-harness.service
gracefully and require successful exit. Restore the exact backed-up user unit,
retag the retained prior immutable image to
`localhost/ai-harness-engine:0.0.2-ae65651df5f9`, restore the root-backed prior
`nginx/sites-available/ai-harness.conf`, validate with nginx-t and systemd-analyze,
daemon-reload, start the prior service, then reload nginx. Verify version80 and
preserved identities. No ai-vm/model/image-API change is involved.

H003 schema uses companion tables for rollback compatibility. Retain the current
application DB by default; do not overwrite postdeployment chats with the old
snapshot. A data restore needs separately assessed exact loss scope. owner.sqlite
is an exclusive process ownership lock and is not a user-data backup/restore target.
Existing inference key remains untouched. Newly prepared host-only approval key
and unused include may remain protected if rolling back; no rotation/deletion needed.
