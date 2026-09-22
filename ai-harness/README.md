# ai-harness

A local, single-user MiniMax Code assistant using the two existing Qwen
inference instances on ai-vm. Version 0.0.1 adds a simple HTTP chat interface,
technical web research, PDFs and coding tools on the separate ai-harness VM.

**Status:** approved plan; implementation and deployment are not yet accepted.

See [the approved v0.0.1 plan](PLAN-v0.0.1.md). Target interface:
`http://10.156.100.61/`, no login, restricted to trusted clients by the operator.
Each model retains 480,000 context; requested output ceiling is 65,536 tokens.

First-party ai-harness code is MIT. Third-party software and model weights
retain their respective licenses; inclusion does not relicense them.
