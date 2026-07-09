# Model Roles

M9F separates model selection by job instead of treating one model as the final answer for every workflow. The router should eventually choose among role-specific local backends while preserving the one-active-backend policy until concurrency is explicitly designed.

## A. Technical Expert Model

Purpose: strong coding, sysadmin, infrastructure, debugging, and engineering judgment.

Expected traits:

- High coding and terminal reasoning quality.
- Strong Linux, Docker, GPU/runtime, Python, shell, networking, and repository understanding.
- Good at producing structured technical briefs, plans, patches, and failure analyses.
- Does not require 1M context for its primary role.
- Can create high-quality technical chunks that a long-context worker can later consume.

Likely current fit:

- The active `Qwen/Qwen3-30B-A3B-Instruct-2507` SGLang backend is the current practical technical/general local model.
- A future larger MoE may replace or complement it after mixed-memory proof.

## B. General Expert Model

Purpose: broad world/domain knowledge, explanations, research synthesis, and non-technical planning.

Expected traits:

- Strong general knowledge and writing quality.
- Good at summarizing background material for downstream work.
- Good multilingual and domain breadth.
- Does not require 1M context for most direct answers.
- Can prepare concise briefings and structured background packs for the long-context worker.

Likely future fit:

- A large MoE such as `Qwen/Qwen3.5-397B-A17B-FP8` may serve this role if M9G/M9H prove a mixed-memory runtime path.

## C. Long-Context Working Model

Purpose: execute long projects after being fed a dossier, memory pack, source bundle, or structured output from A/B.

Expected traits:

- Preferred context: 250K to 1M tokens.
- Accepts that raw knowledge may be weaker than A/B if the context is rich.
- Strong at maintaining task state over long reports, codebases, logs, and local archives.
- Can cite local memory packs and operate without web access after ingestion.

Likely future fit:

- Qwen3.5 class models are attractive because official cards document 262,144 native context and extension to about 1,010,000 tokens, but this VM must first prove a reduced-context mixed-memory path.

## Human Workflows

Technical project:

1. Technical expert model gathers and structures implementation facts, risks, commands, and source notes.
2. Long-context worker receives the technical brief plus repo/docs/log context.
3. Long-context worker executes or plans the long project.

Non-technical project:

1. General expert model gathers and structures broad background.
2. Long-context worker receives the background pack plus user documents.
3. Long-context worker writes, compares, plans, or synthesizes across the full dossier.

Short questions:

- Technical questions go directly to A.
- General questions go directly to B.
- The router should avoid waking a very large mixed-memory model when a smaller local model is sufficient.

User-supplied dossier:

- The long-context worker handles the full supplied context directly when it fits.
- If it does not fit, the memory/RAG subsystem builds retrieval packs and staged summaries.

## Routing Principles

- Prefer the smallest local model that can do the job well.
- Escalate to the very large mixed-memory model for hard synthesis, deep debugging, long reasoning, and high-stakes offline work.
- Keep model role metadata in repo docs and future profiles so routing remains auditable.
- Do not let public API exposure drive model selection. Local resilience and quality come first.
