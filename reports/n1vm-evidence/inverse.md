# N1VM owned inverse — NOT EXECUTED, retain evidence

Run through worker SSH ai-vm under current authorization. Verify the exact protected D3 guards and require both guards PASS, with report under /data/services/n1vm-20260915. Stop if root available <4GiB.

1. sudo systemctl disable --now llm-private-glm.socket
2. sudo systemctl stop llm-private-glm.service
3. Verify all six llm-private-{control,glm,qwen38}.{socket,service} units inactive/failed, all three sockets disabled, all services static/disabled. Control/Qwen should already be off; do not alter any backend.
4. sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py remove --dry-run
5. sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py remove

On any refusal retain files/evidence and stop; never flush/restore all rules. Keep all eight exact files until reviewed helper inverse passes. Verify every destination against deploy-manifest-planned.json and created-resources.jsonl, including SHA256, ownership, regular/single-link type. Remove only those proven-new files; never remove changed/preexisting assets. Remove only empty proven-new parent dirs, in reverse order; preserve /etc/llm-server while it retains private-network-state.json. Keep receipt and its original filter snapshot, evidence directory and backup. Record exact removal and rerun daemon-reload only after owned unit removal. Recheck protected guards and native model identity without generation.

The preexisting multi-user.target.wants parent is not owned and must be retained. The newly created GLM enable symlink is owned and removed by systemctl disable. The helper lock is an owned root0600 runtime artifact; only consider removal after all owned helper/service activity is quiescent. No arbitrary PID kill, Docker/model stop, registry/key/control mutation, disk operation or unrelated cleanup.
