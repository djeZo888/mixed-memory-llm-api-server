# H013 paired Sova 1M production candidate

The source candidate now sets Flash `qualified=true`, context `1048576` and
maximum requested output `65536`, based on root's reviewed H012 native PASS:
exactly 1,000,000 input and 252 output tokens, correct retrieval/arithmetic,
completed 2026-09-27 04:30:46 UTC. See `../../docs/h013-status-20260927.md` for
scientific scope and the retained terminal archive checksum. This is a prepared
production candidate, not evidence of deployment or current backend readiness.

Deployment requires separate root GO plus Worker1's fresh authenticated backend
receipt showing context and native pool 1048576, native bounds P-7/P-2, and the
pinned tokenizer/template identity. Pair the rebuilt engine (including this
profile generator) with the server/web/config release; an old 480K native profile
must never accompany a 1M advertisement. Qwen defaults/limits remain 480000 and
the image configuration is unchanged. The display label is only
`Frontier GLM-5.3-Flash`; ready/down observations and historical scientific/tool
workflow evidence remain independent and unchanged.

The exact `FRONTIER_INSTRUCTIONS` policy remains intact: Qwen coordinates and
handles routine coding/agentic work; Flash is optional for deep research,
many documents, difficult reasoning and independent review. Exceptional stuck
coding escalation requires explicit rationale and Qwen verification.

The existing profile migration accepts only SHA256
`ac773137a850439b9109bc22080071d46d60b8758ad9660d15981f7a7c761dfe`
of the protected old managed 480K agent. It preserves custom bytes by refusing
rather than overwriting them, checks ownership/modes/links, rechecks content
before atomic replacement, and leaves user notes/history/identity untouched.

The native scheduling/compaction estimator is still conservative and is not the
Flash tokenizer. Exact host admission remains authoritative: input <=1048569,
input plus requested output <=1048574. A 65536 output reservation therefore
permits at most 983038 input tokens. The H012 native retrieval/arithmetic PASS
is not full 1M Sova agent occupancy, tokenizer-aware native scheduling, arbitrary
task quality or universal model superiority. Keep the limitations in
`h008-frontier-source.md`; no new inference is part of preparation.
