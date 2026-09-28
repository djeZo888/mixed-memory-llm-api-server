#!/bin/sh
# PREPARED ONLY. Execute on ai-harness only after root GO for source739462b7 + manifest.
# Caller must first copy reviewed40-h020-status.conf to /tmp/h020-status01-739462b.conf.
set -eu
[ "$(systemctl show ai-harness-status.service -p MainPID --value)" = 301728 ]
[ "$(systemctl show ai-harness.service -p ActiveState --value)" = inactive ]
[ "$(systemctl show ai-harness-status.service -p WorkingDirectory --value)" = "/opt/ai-harness/releases/34959c67baea0d8a357cbea4cefac1658f3553f0-h019-prep01/ai-harness/server" ]
[ ! -e /etc/systemd/system/ai-harness-status.service.d/40-h020-status.conf ]
sha256sum -c - <<'SHA256'
91fe53ad7228fb11ea48f191bb88177aa2e088672a8b25b5fc1b3f1be68070a9  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/config/system-registry.json
6fac2925b81e0c40154635643a327f8f3149f7211cf8b78a4f321f6d5b09dc22  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/config/active-frontier.json
0b91ec1fa266c38551ece1ba89e9446d2c83360d8d8abb56401c81a51bda1011  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/server/dist/system-registry.d.ts
4a4704c7a63a0e2a79df48aac596152016995dbc9c4e7a63795ec4dfd5cf72fb  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/server/dist/status-ui.js
a278e5e543938f94a764cfbf8daa15b59197c91a6f82ed29848b08b3135d2c8d  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/server/dist/system-registry.js
35e8c57e406c4ab4f7d8357997eaf22ce9323cafb4835dccbdc56162cb1502eb  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/server/dist/status-projection.js
e74c5cceb8a88808447b3b9775e604ccf290502f4cdf9ac2eea8f616336899a1  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/server/dist/status-projection.d.ts
c8e69eb3a33be4427641c7f0c4091892ee19974e371c4f8e4f154f57c790262a  /opt/ai-harness/releases/739462b7e246f92a3c4161c4535a1a2d8a0886f2-h020-status01/ai-harness/server/dist/status-ui.d.ts
1dd0a243708343390e41ecb127728bce18f1c043461fc76ac622132409006d78  /tmp/h020-status01-739462b.conf
6fac2925b81e0c40154635643a327f8f3149f7211cf8b78a4f321f6d5b09dc22  /opt/ai-harness/releases/34959c67baea0d8a357cbea4cefac1658f3553f0-h019-prep01/ai-harness/config/active-frontier.json
SHA256
sudo -n install -o root -g root -m 0644 /tmp/h020-status01-739462b.conf /etc/systemd/system/ai-harness-status.service.d/40-h020-status.conf
sudo -n systemctl daemon-reload
sudo -n systemctl restart ai-harness-status.service
systemctl show ai-harness-status.service -p ActiveState -p SubState -p MainPID -p ExecMainStartTimestamp -p WorkingDirectory -p ExecStart -p DropInPaths
systemctl show ai-harness.service -p ActiveState -p MainPID
