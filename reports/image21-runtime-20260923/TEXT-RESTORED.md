# Text restored and warm

Both original Qwen containers are READY, with unchanged UUIDs, masks/caps and 480000 native pools (input479994, request479999). Existing llmctl-boot.service is active/exited and llm-control.service active/running. Canonical Qwen1 then Qwen0 restoration succeeded; both original container IDs were reused. One tiny authenticated response from mac-worker1 through each private endpoint (30004/30002) returned HTTP200 and `OK`. No orphan owned containers, canonical lease free.

Compatibility source b39781d and reviewed receipt amendment are coherent in lifecycle/control copies. Old source and exact rollback bytes remain preserved. See TEXT-RESTORED.json and evidence/compat-activation.jsonl for identities and guards. No old480K benchmark was rerun.
