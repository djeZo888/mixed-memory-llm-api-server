#!/usr/bin/env python3
"""Generate one FullHD PNG through the fixed local image API (stdlib only)."""

import argparse
import base64
import binascii
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import stat
import struct
import sys
import time
import urllib.error
import urllib.request


ENDPOINT = "http://127.0.0.1:30006/v1/images/generations"
KEY_FILE = "/data/services/secrets/llm-api-key"
OUTPUT_DIR = Path("/data/services/image-api/examples/output")
SIZE = (1920, 1080)
# Covers a FullHD RGB/RGBA PNG plus base64 and the small JSON envelope.
RESPONSE_LIMIT = 16 * 1024 * 1024
PRESETS = {
    'lake-bled': (
        'Photorealistic landscape photograph of Lake Bled in Slovenia on a calm early autumn '
        'morning, viewed from an elevated lakeside overlook. Compose a wide horizontal frame '
        'with the small wooded island slightly left of center, its pale church walls and slender '
        'bell tower rising naturally above the trees. Place the castle on its rocky cliff along '
        'the distant right-hand shore, with layered alpine ridges receding behind it. Soft '
        'sunlight from the left warms the church, treetops and castle while cool blue shadows '
        'retain detail. Clear turquoise water near the shore deepens toward the lake center; '
        'delicate ripples gently break reflections in physically plausible directions. Include a '
        'restrained foreground of dark leaves and rock, balanced open water, faint atmospheric '
        'haze and a lightly clouded sky. Use realistic proportions, natural autumn greens and '
        'golds, subtle contrast and crisp detail with graceful distant softness.'
    ),
    'pcb': (
        'High-end macro product photograph of a compact, professionally assembled electronics '
        'circuit board resting on a matte charcoal studio surface. Show the entire rectangular '
        'board in a three-quarter view, with a USB-C connector on the near edge, a central '
        'integrated circuit, neatly aligned small resistors and capacitors, a shielded inductor '
        'and evenly spaced mounting holes. Deep green solder mask reveals fine copper routes '
        'following orderly paths between pads, with consistent clearances, rounded bends and '
        'tidy groups of vias. Give the board believable fiberglass edges, restrained white '
        'silkscreen, clean metallic connector surfaces and gently rounded solder joints that '
        'catch the light. Component markings remain subtle and secondary to the hardware. A '
        'large soft light from the upper left creates broad highlights, controlled shadows and a '
        'faint contact shadow beneath the board. Keep the component plane sharply detailed, with '
        'gentle background falloff and restrained, realistic color.'
    ),
    'ecohouse': (
        'Polished isometric architectural cutaway illustration of a compact two-storey eco house '
        'on a small landscaped plot. Remove the front walls and the front portion of the roof to '
        'reveal clearly connected rooms: a ground-floor kitchen and living area, a compact '
        'utility room, an internal staircase and two upstairs bedrooms sharing a bathroom. Keep '
        'floor levels, wall thicknesses, doors and stair landings coherent, with warm timber '
        'framing, pale plaster, natural wood floors and visible insulation in the cut edges. '
        'Retain a rear roof section carrying an orderly solar panel array. Show generous '
        'south-facing glazing with external shading, a rainwater tank connected to a gutter '
        'downpipe, a small outdoor heat pump unit and raised vegetable beds beside permeable '
        'paving. Use clean linework, softly shaded materials and a restrained green, cream and '
        'timber palette. Present the house against an uncluttered off-white background with '
        'generous margins and clear separation between rooms and exterior features.'
    ),
}


class ExampleError(Exception):
    pass


def sudo_caller():
    if os.getuid() != 0 and os.geteuid() != 0:
        return None
    message = "Run sudo as an ordinary user; a valid nonroot sudo caller is required."
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ExampleError(message)
    uid, gid = os.environ.get("SUDO_UID", ""), os.environ.get("SUDO_GID", "")
    if not all(re.fullmatch(r"[1-9][0-9]{0,9}", value) for value in (uid, gid)):
        raise ExampleError(message)
    try:
        caller = pwd.getpwuid(int(uid))
    except (KeyError, OverflowError):
        raise ExampleError(message) from None
    if caller.pw_uid != int(uid) or caller.pw_gid != int(gid):
        raise ExampleError(message)
    return caller


def read_key():
    try:
        fd = os.open(KEY_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0
                    or meta.st_nlink != 1 or not 32 <= meta.st_size <= 257
                    or stat.S_IMODE(meta.st_mode) not in (0o400, 0o440, 0o600)
                    or (stat.S_IMODE(meta.st_mode) == 0o440 and meta.st_gid != 0)):
                raise ExampleError("The fixed key file has unsafe metadata.")
            raw = os.read(fd, 258)
            if len(raw) != meta.st_size:
                raise ExampleError("The fixed key file could not be read completely.")
        finally:
            os.close(fd)
    except OSError:
        raise ExampleError("Cannot read the protected fixed key file; use sudo as an ordinary user.") from None
    value = raw[:-1] if raw.endswith(b"\n") else raw
    if not re.fullmatch(rb"[A-Za-z0-9._~+/=-]{32,256}", value):
        raise ExampleError("The fixed key file has an invalid format.")
    return value.decode("ascii")


def drop_privileges(caller):
    try:
        if caller is not None:
            # The credential fd is already closed. Network and output use only
            # the sudo caller's permanent IDs and their supplementary groups.
            os.initgroups(caller.pw_name, caller.pw_gid)
            os.setgid(caller.pw_gid)
            os.setuid(caller.pw_uid)
        uids = (os.getuid(), os.geteuid())
        gids = (os.getgid(), os.getegid())
        if hasattr(os, "getresuid"):
            uids += os.getresuid()
        if hasattr(os, "getresgid"):
            gids += os.getresgid()
        if (0 in uids + gids or 0 in os.getgroups()
                or (caller is not None and
                    (any(uid != caller.pw_uid for uid in uids)
                     or any(gid != caller.pw_gid for gid in gids)))):
            raise ExampleError("Privilege drop failed; no request or output was made.")
    except OSError:
        raise ExampleError("Privilege drop failed; no request or output was made.") from None


def open_output_directory(output):
    if (output.parent != OUTPUT_DIR or output.suffix.lower() != ".png"
            or any(ord(c) < 32 or ord(c) == 127 for c in str(output))):
        raise ExampleError("Output must be a direct .png child of " + str(OUTPUT_DIR) + ".")
    # Anchor the fixed directory without following symlinks in any component.
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in OUTPUT_DIR.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        try:
            os.stat(output.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return directory
        raise ExampleError("Output already exists; choose a new PNG filename.")
    except BaseException:
        os.close(directory)
        raise


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def http_error_message(status):
    messages = {
        400: "request rejected (FullHD may not yet be qualified)",
        401: "authentication rejected",
        403: "access denied",
        429: "busy; no retry was attempted",
        502: "backend unavailable",
        503: "service not ready",
        504: "request timed out; no retry was attempted",
    }
    return "HTTP {}: {}.".format(status, messages.get(status, "request failed; no retry was attempted"))


def decode_response(raw):
    try:
        if len(raw) > RESPONSE_LIMIT:
            raise ValueError()
        value = json.loads(raw.decode("utf-8"))
        data = value["data"]
        if (not isinstance(data, list) or len(data) != 1
                or not isinstance(data[0], dict) or not isinstance(data[0]["b64_json"], str)):
            raise ValueError()
        png = base64.b64decode(data[0]["b64_json"], validate=True)
        # Signature/IHDR checks only: this helper does not decode PNG pixels.
        if (len(png) < 33 or png[:8] != b"\x89PNG\r\n\x1a\n"
                or png[8:16] != b"\x00\x00\x00\rIHDR"
                or struct.unpack(">II", png[16:24]) != SIZE):
            raise ValueError()
        return png
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError, binascii.Error):
        raise ExampleError("Invalid response: expected one base64 PNG with a 1920x1080 IHDR.") from None


def request_png(prompt, seed, key):
    payload = {"model": "qwen-image-2.1", "prompt": prompt, "size": "1920x1080",
               "n": 1, "background": "opaque", "response_format": "b64_json"}
    if seed is not None:
        payload["seed"] = seed
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > 65536:
        raise ExampleError("The encoded request exceeds the API's 64 KiB limit.")
    request = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=900) as response:
            if response.status != 200:
                raise ExampleError(http_error_message(response.status))
            raw = response.read(RESPONSE_LIMIT + 1)
    except urllib.error.HTTPError as error:
        message = http_error_message(error.code)
        error.close()  # Never read or print arbitrary error bodies or headers.
        raise ExampleError(message) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise ExampleError("Request failed or timed out; no retry was attempted.") from None
    return decode_response(raw)


def save_png(directory, name, png):
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
    except FileExistsError:
        raise ExampleError("Output already exists; choose a new PNG filename.") from None
    with os.fdopen(fd, "wb") as target:
        meta = os.fstat(target.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid()
                or meta.st_uid == 0 or meta.st_gid == 0):
            raise ExampleError("Output ownership is unsafe; no image was written.")
        target.write(png)


def seed_value(value):
    try:
        seed = int(value)
        if 0 <= seed <= 2**63 - 1:
            return seed
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("seed must be an integer from 0 through 9223372036854775807")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example", choices=PRESETS, help="complete creative preset")
    parser.add_argument("--prompt", help="complete prompt; overrides --example")
    parser.add_argument("--output", required=True, type=Path,
                        help="new .png directly in " + str(OUTPUT_DIR))
    parser.add_argument("--seed", type=seed_value, help="optional reproducibility seed")
    args = parser.parse_args(argv)
    prompt = args.prompt if args.prompt is not None else PRESETS.get(args.example)
    if prompt is None:
        parser.error("provide --example or --prompt")
    try:
        if not prompt.strip() or len(prompt.encode("utf-8")) > 16384:
            raise ExampleError("Prompt must contain text and fit within 16384 UTF-8 bytes.")
        caller = sudo_caller()
        key = read_key()
        drop_privileges(caller)
        directory = open_output_directory(args.output)
        try:
            started = time.monotonic()
            png = request_png(prompt, args.seed, key)
            save_png(directory, args.output.name, png)
            elapsed = time.monotonic() - started
        finally:
            os.close(directory)
        width, height = struct.unpack(">II", png[16:24])
        print("Saved {} | {:.1f}s | {}x{}".format(args.output, elapsed, width, height))
        return 0
    except ExampleError as error:
        print("Error: " + str(error), file=sys.stderr)
    except (OSError, UnicodeError):
        print("Error: local file operation failed; check caller access and the output directory.", file=sys.stderr)
    except KeyboardInterrupt:
        print("Interrupted; no retry was attempted.", file=sys.stderr)
        return 130
    return 1


if __name__ == "__main__":
    sys.exit(main())
