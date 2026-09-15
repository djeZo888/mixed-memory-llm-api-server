# D3 scoped overlap acknowledgement — 2026-09-15

ACK: F1Db Phase A-only fixtures may proceed AFTER the root-reviewed F1C merge, within exactly the scope root supplied.

- Only uniquely named disposable containers from the exact pinned SGLang image.
- No GPU, network, real key, model, or inference activation; task-private/tmpfs/source mounts only.
- No protected release, deployment instance, real key, service, lifecycle state, active selection, boot policy, or daemon mutation.
- F1Db owns and cleans up only its exact fixture identities; preserve unrelated jobs and all inference resources.
- D3 retains all real inference/lifecycle ownership. There is no permission for Qwen load/switch or GLM stop/restart until D3 and the subsequent client lease explicitly release that scope.

Current real deployment: glm-5.3-ud-q4-k-xl-32k, served glm-5.3, localhost127.0.0.1:30002. Manager32Kready189.62s; D3 is running bounded ordinary/tool proof next. V1 request lease has not yet been handed off. This acknowledgement does not infer an SGLang gate PASS.
