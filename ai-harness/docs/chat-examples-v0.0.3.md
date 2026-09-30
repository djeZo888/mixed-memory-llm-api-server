# Image tasks in ordinary chat

Use a new chat for a new task. Main chat and fresh ordinary workers use the
resident Qwen image tools. Each request creates one versioned PNG; originals
remain unchanged. Download it from the reply's image card/artifact link.

Generation supports 1024×1024, 1024×576, 1216×704, 1472×832, 1760×992 and
1920×1080. Editing supports one reference at 1024×1024 or 1536×864, or two
references at 1024×1024. Output is opaque PNG; masks/transparency and Full HD
editing are unavailable. Two-reference capacity is qualified; this three-edit
browser campaign tested one-reference workflows only.

## Generate one image

> Create one opaque 1920×1080 PNG of a small ceramic teapot and a yellow pear on
> a wooden table in soft morning light. Use the resident image-generation tool.
> Return the image preview and download. Do not make additional variants.

Generation is supported by prior qualification/acceptance; it was not rerun in
the guarded-edit campaign.

## Edit an attached image

Attach a 1024×1024 image, then send:

> Edit this attached image once. Change only the turquoise ceramic teapot to
> cobalt blue. Preserve its shape and reflections, the yellow pear, tabletop,
> framing, background and lighting. Keep 1024×1024, use the native image-edit
> tool and omit the seed for a fresh one. Preserve the original and return the
> new image. Do not generate a replacement or retry through another tool.

For a follow-up, click the result's **Use for next edit**, then send:

> Ask a fresh ordinary worker to edit the attached result once: change only the
> blue teapot to emerald green, preserving everything else and 1024×1024. Use
> the native image-edit tool and omit the seed. Return a separate new artifact.
> If that tool is unavailable, report it without fallback or retry.

## Review a proposed resize

Attach the unchanged larger original, then send:

> Edit this attached 1920×1080 lake image once at the supported 1536×864 output
> size. Change only the island church's orange roof tiles to muted blue. Preserve
> the church shape, tower, island, lake, mountains, composition and lighting.
> Use one native edit and omit the seed. Show the resize proposal and ask me to
> decide through the approval card. Do not alter my original or approve for me.

The card shows original and working dimensions, padding and proposed canvas.
Click **Reject change** to cancel without image inference, or **Approve resize**
to run that exact saved proposal. A refresh restores the pending card. Approval
can finish after the assistant turn; no new message is needed. To request another
proposal after rejection, send a new explicit request. Do not resend an uncertain
accepted request or expect an automatic retry.

Fresh seeds mitigate the known seed-reuse failure; they do not guarantee pixel-exact
preservation. Known source/ancestor seed collisions are rejected, not silently
replaced. Imported files may lack that history. See the [acceptance report](acceptance-v0.0.3.md)
for measured limits, historical failures and evidence boundaries.
