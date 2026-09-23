# FullHD image generation examples

Run these commands from the **ai-vm SSH console**, using the installed
helper and prepared output directory. Python 3 and its standard library are
sufficient. Each command requests one opaque **1920×1080 PNG**.

Full HD is deployed with public `1920x1080` → native `1920x1088`, removing eight
bottom rows. The seed 42 `lake-bled` preset passed the earlier generation acceptance;
[receipt and full decode](../../reports/image21-fhd-20260923/RESULT.md). The PCB
and house presets have not been executed or visually assessed. This example CLI
remains generation-only. The deployed API also exposes measured guarded opaque
edits with one reference at 1024x1024 or 1536x864, or two references at 1024x1024;
see the [API guidance and editing limits](../../docs/image-api.md). Full HD editing
remains excluded. The PCB and house prompts are visual concepts, not verified
engineering designs.

```sh
sudo python3 /usr/local/lib/llm-server/image-api/examples/generate.py --example lake-bled --output /data/services/image-api/examples/output/lake-bled.png
sudo python3 /usr/local/lib/llm-server/image-api/examples/generate.py --example pcb --output /data/services/image-api/examples/output/pcb.png
sudo python3 /usr/local/lib/llm-server/image-api/examples/generate.py --example ecohouse --output /data/services/image-api/examples/output/ecohouse.png
sudo python3 /usr/local/lib/llm-server/image-api/examples/generate.py --prompt "Photorealistic wide landscape of a quiet alpine meadow at sunrise, with wildflowers in the foreground, mist between distant mountains and soft golden light." --output /data/services/image-api/examples/output/custom.png
```

Choose at least one of `--example` or `--prompt`. A complete free-text `--prompt`
overrides the preset when both are supplied. Add `--seed 42` to any command to
specify a seed; the allowed range is `0`–`9223372036854775807`. The output path is
required and must be a direct child ending in `.png` of the fixed directory
`/data/services/image-api/examples/output`. Use a new filename each time: existing
files and symlink outputs are refused.

The helper reads only the existing protected key file
`/data/services/secrets/llm-api-key`. Under `sudo`, it reads and closes that file,
then restores the invoking user's supplementary groups, GID and UID before making
the request or saving an image. Root without a valid ordinary sudo caller is
refused. The saved file belongs to that caller. A nonroot invocation works only
when that user is already authorized to read the fixed key file. No key needs to
be pasted into a command or placed in the shell environment.

## Request and response

The fixed endpoint is `POST http://127.0.0.1:30006/v1/images/generations` with
`Content-Type: application/json` and an in-memory Bearer authorization header.
This readable body uses a complete short free-text prompt; `--example` sends the
full corresponding preset below. Omit `seed` when no seed was supplied; generation
keeps the native default of 42.

```json
{
  "model": "qwen-image-2.1",
  "prompt": "Photorealistic wide view of Lake Bled in soft morning light, with its island church, cliffside castle, distant alpine peaks and calm reflections.",
  "size": "1920x1080",
  "n": 1,
  "background": "opaque",
  "response_format": "b64_json",
  "seed": 42
}
```

The helper uses a 900-second request timeout, disables inherited proxies and
redirects, and makes no automatic retries. HTTP 429 means the service is busy;
wait for the current generation to finish before running the command again.
Errors are reported with bounded, sanitized messages.

After HTTP success, it validates the response structure and base64 in
`data[0].b64_json`, then checks the PNG signature and IHDR dimensions for exactly
1920×1080 before saving. This is a header check, not a full image decode or a
quality assessment. Success prints the output path, elapsed time and actual
dimensions. See the [main image API documentation](../../docs/image-api.md) for
the broader service contract.

## lake-bled

```text
Photorealistic landscape photograph of Lake Bled in Slovenia on a calm early autumn morning, viewed from an elevated lakeside overlook. Compose a wide horizontal frame with the small wooded island slightly left of center, its pale church walls and slender bell tower rising naturally above the trees. Place the castle on its rocky cliff along the distant right-hand shore, with layered alpine ridges receding behind it. Soft sunlight from the left warms the church, treetops and castle while cool blue shadows retain detail. Clear turquoise water near the shore deepens toward the lake center; delicate ripples gently break reflections in physically plausible directions. Include a restrained foreground of dark leaves and rock, balanced open water, faint atmospheric haze and a lightly clouded sky. Use realistic proportions, natural autumn greens and golds, subtle contrast and crisp detail with graceful distant softness.
```

## pcb

```text
High-end macro product photograph of a compact, professionally assembled electronics circuit board resting on a matte charcoal studio surface. Show the entire rectangular board in a three-quarter view, with a USB-C connector on the near edge, a central integrated circuit, neatly aligned small resistors and capacitors, a shielded inductor and evenly spaced mounting holes. Deep green solder mask reveals fine copper routes following orderly paths between pads, with consistent clearances, rounded bends and tidy groups of vias. Give the board believable fiberglass edges, restrained white silkscreen, clean metallic connector surfaces and gently rounded solder joints that catch the light. Component markings remain subtle and secondary to the hardware. A large soft light from the upper left creates broad highlights, controlled shadows and a faint contact shadow beneath the board. Keep the component plane sharply detailed, with gentle background falloff and restrained, realistic color.
```

## ecohouse

```text
Polished isometric architectural cutaway illustration of a compact two-storey eco house on a small landscaped plot. Remove the front walls and the front portion of the roof to reveal clearly connected rooms: a ground-floor kitchen and living area, a compact utility room, an internal staircase and two upstairs bedrooms sharing a bathroom. Keep floor levels, wall thicknesses, doors and stair landings coherent, with warm timber framing, pale plaster, natural wood floors and visible insulation in the cut edges. Retain a rear roof section carrying an orderly solar panel array. Show generous south-facing glazing with external shading, a rainwater tank connected to a gutter downpipe, a small outdoor heat pump unit and raised vegetable beds beside permeable paving. Use clean linework, softly shaded materials and a restrained green, cream and timber palette. Present the house against an uncluttered off-white background with generous margins and clear separation between rooms and exterior features.
```
