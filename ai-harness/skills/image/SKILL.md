---
name: image
description: Create, edit or creatively transform images using resident Qwen-Image-2.1 through the local image MCP tools. Use image_edit with references for reference-based creation and follow-up edits; ordinary coding, text, scientific plots and image inspection keep their existing tools.
---

# Image work

Use `image_capabilities`, `image_generate` and `image_edit` (configured MCP
server `image`) for all creative image generation, editing and manipulation.
Main agents and native delegated workers share these tools and this skill.
Delegate image work to the native worker role when needed; read-only native
roles can investigate but need not have creative tools. Do not use paid cloud
services, alternate generative models, browser sites, native media tools, or
scripts/painting/compositing as a creative fallback. Ordinary coding, text,
calculations, scientific plots, file inspection and artifact handling keep
their existing tools. Host codec preparation is managed by the image service.

Read capabilities before choosing an operation, size or reference count.
Only advertised qualified profiles are available. Missing/disabled editing
means unavailable: explain the returned reason, never substitute generation.
Default generation is opaque PNG at 1920x1080. Do not promise transparency,
masks, pixel-perfect inpainting or support beyond the advertised profiles.

Use `image_edit` with references for reference-based creation. Current generation
profiles accept zero references. Do not automatically convert an operation or
assume generation-reference qualification; unqualified inputs may fail.

Pass a clear prompt, optional supported `size` and optional nonnegative safe integer `seed`.
References are current-session `{fileId}` records or anchored relative
`{workspacePath}` files supplied by the harness. Use the actual owned IDs/paths,
never infer them from filenames or invent IDs. Never pass URLs, absolute paths,
host/session/run identities, tokens, backend settings or approval flags.
For edits, reference the intended original or prior result explicitly. Ask for
the missing source when it is unavailable. Preserve originals; each result is
a new version. Keep requested changes and preservation instructions clear.

For successive edits, prefer an omitted or fresh seed. The same seed reproduces
a request/recipe, but the server rejects known source/ancestor generation seed
reuse as `source_seed_collision`. Preserve an explicit user seed: never silently
change it or automatically resubmit. Explain a collision and ask the user for
a new seed or permission to omit it. Seed choice does not qualify editing;
capability discovery still governs availability.

Editing preserves original geometry when qualified. Any necessary resize,
padding or canvas adjustment requires the user's approval of exact source and
proposed dimensions on the saved image job card. When the tool returns
`awaiting_approval`, immediately tell the user to use that card's Approve or
Reject button. Do not poll/wait for model approval, simulate a browser click,
call an approval endpoint, resize locally, or submit a replacement request.
Approval continues the same saved job even after this assistant turn ends.

Each invocation submits once with its own stable request ID and then polls
only that job for up to 50 minutes. An uncertain submission must never be
replayed: direct the user to the conversation's persisted image jobs. A timeout,
disconnection or ended assistant turn does not cancel an accepted job. Do not
claim cancellation stopped GPU work: active jobs drain while delivery is
cancelled. Report only real returned states, queue positions and elapsed time;
never invent percent progress or issue a duplicate request to check status.

Return concise status/errors and links to saved artifacts, with relative
workspace path, actual dimensions, seed and model when supplied. Never include
base64 image data, host paths, credentials or raw transport errors in text.
Generated artifacts support preview, download, ZIP and **Use for next edit**;
the next message carries explicit artifact references separately from uploads.
