# Memory And RAG Architecture

M9F makes local memory/RAG a core feature of the offline-resilience system. The goal is to preserve useful knowledge while online and retrieve it later when the internet is degraded or unavailable.

## Storage Layout

Planned data roots:

```text
/data/memory/raw
/data/memory/processed
/data/memory/indexes
/data/memory/qdrant
/data/memory/manifests
/data/memory/snapshots
/data/logs/memory
```

Directory intent:

- `/data/memory/raw`: original imports, downloaded pages, PDFs, markdown notes, repo exports, and operator-provided files.
- `/data/memory/processed`: normalized text, chunks, extracted metadata, OCR output, and structured representations.
- `/data/memory/indexes`: local search indexes, lexical indexes, and generated retrieval artifacts.
- `/data/memory/qdrant`: vector database storage if Qdrant is selected.
- `/data/memory/manifests`: source manifests, hashes, ingestion records, tags, ACL metadata, and provenance.
- `/data/memory/snapshots`: exportable backups of memory manifests, source bundles, and index snapshots.
- `/data/logs/memory`: ingestion, embedding, reranking, search, attach/detach, and maintenance logs.

## Capabilities

The memory subsystem should support:

- List memories.
- Add or import memory.
- Delete or archive memory.
- Search memories.
- Attach selected memories to the current model session.
- Detach selected memories from the current model session.
- Auto-select relevant memories for a new chat or task.
- Save web-scraped pages with timestamp, URL, source, and content hash.
- Preserve offline provenance and citation metadata.
- Export and back up memory stores.

## CLI And API Plan

Proposed `llmctl` surface:

```bash
scripts/llmctl memory list
scripts/llmctl memory add
scripts/llmctl memory import
scripts/llmctl memory search
scripts/llmctl memory attach
scripts/llmctl memory detach
scripts/llmctl memory delete
scripts/llmctl memory archive
scripts/llmctl memory pack
```

Later API surface:

- `GET /memory` for list/search metadata.
- `POST /memory/import` for ingestion.
- `POST /memory/search` for retrieval.
- `POST /sessions/{id}/memory/attach` for session binding.
- `POST /sessions/{id}/memory/detach` for removal.
- `POST /memory/pack` to build a retrieval pack for a model call.

API exposure remains local-first until a later auth/front-door milestone.

## Architecture

Recommended initial architecture:

- Local vector database, likely Qdrant.
- Local embedding model.
- Local reranker.
- Source document store under `/data/memory/raw` and `/data/memory/processed`.
- Metadata DB or manifest files under `/data/memory/manifests`.
- Retrieval packs passed to the active model as explicit context.
- No internet dependency for retrieval after ingestion.

Qdrant fit:

- Qdrant supports local/self-hosted operation and persistent storage.
- Its storage docs support on-disk vectors and on-disk HNSW index options, which is useful for large local collections.
- Its payload storage can keep large text payloads on disk while indexed fields stay queryable.

LlamaIndex fit:

- LlamaIndex provides document ingestion, vector indexes, retrievers, and query engines.
- It has Qdrant vector-store integration, so the repo can use it as an orchestration layer while keeping Qdrant as the durable vector backend.

OpenClaw fit:

- OpenClaw can connect to localhost SGLang or vLLM through OpenAI-compatible `/v1` providers.
- This is a later integration target after local model serving and memory APIs are stable.
- The AI-server VM should not become the browser/scraper/chat UI VM; it should expose a controlled local API surface for those systems later.

## Web Archive Flow

When online, a scraper/browser VM can save pages for later use:

1. Fetch page.
2. Save raw HTML/text/PDF under `/data/memory/raw` or an ingestion drop path.
3. Record URL, timestamp, retrieval method, content hash, title, source domain, license/terms notes if known, and operator tags.
4. Normalize to markdown/text under `/data/memory/processed`.
5. Chunk and embed locally.
6. Store vectors in Qdrant and metadata in manifests.
7. Make the item searchable and attachable by `llmctl memory`.

## Retrieval Pack

A retrieval pack should include:

- Query.
- Selected memory IDs.
- Chunk text.
- Source URL or local path.
- Content hash.
- Timestamp.
- Relevance scores.
- Reranker scores if used.
- Citation labels.
- Token budget estimate.

The active model should see retrieved material as cited context, not as untrusted system instructions.

## Security

- Do not store secrets in memory.
- Ingestion should reject or quarantine obvious secret files and auth material.
- Memory ACLs and tags should be added before multi-user exposure.
- Operators must be able to inspect and delete memory entries.
- Web captures are untrusted content and must not become system instructions.
- Memory export/backup must preserve provenance but avoid private keys, tokens, auth files, and real environment files.
