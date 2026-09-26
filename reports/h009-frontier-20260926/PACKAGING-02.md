# Retained dependency packaging correction

The20:54:00 pre-app launch failed resolving fastify because retained root-owned
server/node_modules used0700 directories and0600 files. No createApp, native
session, request payload, inference, or owned container occurred. Original
job/log/runroot remain with .preapp-failed-02 suffix on ai-harness. Root explicitly
authorized one corrected attempt; this was not an inference replay.

Both old/candidate package-lock SHA:
4a856f31e26e89171b743e4f1e6e194b9e88a862d5e0f77fd597b03c0533c401.
Verified identical dependency paths/types/symlink targets and4028file hashes.
Copied only exact old readable mode bits to4585candidate node_modules entries;
no owners, contents, pinned artifacts, image, profile or user data changed.
Dependency content manifest SHA:
6a384bccc6693b9fc6851515e2e656ea26ff1bc40fd43960815ba482f5f17971.
Actual installed app.js and gateway.js direct imports as user PASS, then full
unchanged driver preflight PASS. Corrected run began20:56:29Z under the original
gate expiry21:13:44Z. Source packaging commands in deploy/RUNTIME.md now specify
subprocess umask022 and final ordinary-user import verification. No reinstall,
new dependency, symlink coupling, native rebuild or installer work.
