# API Contract

The project targets an OpenAI-compatible API for local model inference.

## Required Future Endpoints

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/chat/completions`

## Required Future Behaviors

- Missing API key rejected when auth is required.
- Wrong API key rejected when auth is required.
- Correct API key accepted when auth is required.
- Non-streaming chat completion works.
- Streaming chat completion works.
- Invalid model name returns a clear client error.

## Binding

Backends bind to `127.0.0.1` by default. Non-local exposure requires the M11 policy and tests.
