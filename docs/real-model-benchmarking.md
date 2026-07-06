# Real Model Benchmarking

M9C adds a repeatable local benchmark path for the active first real model. The benchmark targets the localhost-only SGLang OpenAI-compatible endpoint and writes raw results under `/data/logs/benchmarks/m9c`.

## Current Target

- Model: `qwen3-30b-a3b-instruct-2507`
- Backend: SGLang
- Endpoint: `http://127.0.0.1:30001/v1`
- Chat completions URL: `http://127.0.0.1:30001/v1/chat/completions`
- Container: `sglang-qwen3-30b-a3b-instruct-2507`
- Model path: `/data/models/qwen3-30b-a3b-instruct-2507`
- Launch args: `--tp 2 --context-length 32768 --mem-fraction-static 0.75`
- Host bind: `127.0.0.1:30001` only

Public API exposure is not configured. Do not expose this endpoint, bind it to `0.0.0.0`, or place a front door in front of it during benchmarking.

## Run The Suite

Dry-run first:

```bash
cd /data/services/mixed-memory-llm-api-server
scripts/bench/run-m9c-benchmarks.sh --dry-run
```

Actual M9C benchmark run:

```bash
cd /data/services/mixed-memory-llm-api-server
scripts/bench/run-m9c-benchmarks.sh
```

The runner performs storage/GPU/live-model guards, records resource snapshots, runs the controlled cases, captures a SGLang log tail, runs lifecycle dry-runs, and refreshes:

```text
reports/m9c-real-model-benchmark-review.md
```

Raw JSONL stays outside Git:

```text
/data/logs/benchmarks/m9c/m9c-results.jsonl
/data/logs/benchmarks/m9c/run-<timestamp>/
```

Do not commit raw benchmark logs.

## Run One Case

```bash
cd /data/services/mixed-memory-llm-api-server
scripts/bench/bench-openai-chat.py \
  --case technical_short \
  --max-tokens 200 \
  --temperature 0.1
```

Streaming case:

```bash
scripts/bench/bench-openai-chat.py \
  --case streaming_short \
  --max-tokens 300 \
  --temperature 0.1 \
  --stream
```

## Manual Local Request

```bash
curl -fsS http://127.0.0.1:30001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-30b-a3b-instruct-2507","messages":[{"role":"user","content":"Reply with one short sentence confirming the local model is reachable."}],"max_tokens":64,"temperature":0}'
```

For larger prompts, avoid putting huge JSON directly on the shell command line. Use `scripts/bench/bench-openai-chat.py --case ...`, or write the prompt to a file under `/data/logs/benchmarks/m9c` and pass `--prompt-file`. The Python benchmark sends the HTTP body through `urllib.request`, avoiding argument-list-too-long failures from `curl -d huge_string`.

## Context Boundary

The active server was launched with:

```text
--context-length 32768
```

M9C context cases are generated conservatively by character count and remain well below the configured 32K token context. Full 262K context is not part of M9C and must wait for a later tuning milestone with explicit memory planning. A later review can add a 24K generated-context case before attempting anything near the 32K launch limit.

## GPU Monitoring

One-shot GPU query:

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,utilization.memory,power.draw,temperature.gpu --format=csv
```

Container resource snapshot:

```bash
sudo -n docker stats --no-stream sglang-qwen3-30b-a3b-instruct-2507
```

SGLang logs:

```bash
scripts/llmctl logs --dry-run
sudo -n docker logs --tail 300 sglang-qwen3-30b-a3b-instruct-2507
```

## Lifecycle Boundary

M9C uses lifecycle dry-runs only:

```bash
scripts/llmctl status
scripts/llmctl logs --dry-run
scripts/llmctl stop --dry-run
scripts/llmctl restart --dry-run
```

Do not run a real stop or restart in M9C. Real restart testing belongs in a later human-approved lifecycle task.
