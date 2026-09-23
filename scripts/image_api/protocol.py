"""Strict public contract, reviewed qualification profiles and bounded images."""
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import re
import secrets
import time
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ALIAS = 'qwen-image-2.1'
RUNTIME_REVISION = '0cd8be351d0825488f4b81c8931167bbab618eca'
MODEL_ID = 'Qwen/Qwen-Image-2.1'
MODEL_REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
FILE_LIMIT = 32 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024
ENVELOPE_LIMIT = 64 * 1024
JSON_LIMIT = 64 * 1024
PIXEL_LIMIT = 2073600  # Public Full HD ceiling.
FHD_NATIVE_PIXELS = 2088960
HARD_LIMITS = {'max_width': 1920, 'max_height': 1080, 'max_pixels': PIXEL_LIMIT,
               'native_max_pixels': FHD_NATIVE_PIXELS}
OUTPUT_LIMIT = 48 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = FHD_NATIVE_PIXELS  # Explicit public/native checks below remain mandatory.


class Refusal(Exception):
    def __init__(self, status=400, code='invalid_request'):
        self.status, self.code = status, code
        super().__init__(code)


class BackendFailure(Exception):
    """Unknown native outcome; reset before further admission."""


async def owned_thread(function, *args):
    """Retain CPU work through cancellation so buffers cannot outlive ownership."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(task)
        except Exception:
            pass
        raise


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal() from None


def dimensions(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,3}x[1-9][0-9]{0,3}', value):
        raise Refusal()
    width, height = map(int, value.split('x'))
    if width > HARD_LIMITS['max_width'] or height > HARD_LIMITS['max_height'] or width * height > PIXEL_LIMIT:
        raise Refusal(400, 'unsupported_size')
    return width, height


def profile_geometry(profile):
    """Explicit Full HD transport geometry; support still requires a profile."""
    public = profile['size']
    dimensions(public)
    native = profile.get('native_size', public)
    crop = profile.get('crop_bottom', 0)
    if type(crop) is not int or not isinstance(native, str):
        raise Refusal()
    if public == '1920x1080':
        if (native == '1920x1088' and crop == 8
                and (profile['operation'], profile['references']) in (('generation', 0), ('edit', 1))
                and profile['transparent'] is False):
            return native, crop
        raise Refusal()
    if native == public and crop == 0:
        return native, crop
    raise Refusal()


def qualification(value):
    """Protected local data is authority; no configured size becomes measured."""
    keys = {'schema_version', 'runtime_revision', 'model_id', 'model_revision',
            'runtime_image_digest', 'profiles', 'limits'}
    if not isinstance(value, dict) or set(value) != keys:
        raise Refusal()
    if (type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['runtime_revision'] != RUNTIME_REVISION or value['model_id'] != MODEL_ID
            or value['model_revision'] != MODEL_REVISION):
        raise Refusal()
    limits = value['limits']
    if (not isinstance(limits, dict) or limits != HARD_LIMITS
            or any(type(v) is not int for v in limits.values())):
        raise Refusal()
    digest = value['runtime_image_digest']
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)):
        raise Refusal()
    profiles = value['profiles']
    if not isinstance(profiles, list) or len(profiles) > 100 or (profiles and digest is None):
        raise Refusal()
    seen = set()
    for p in profiles:
        required = {'operation', 'size', 'references', 'transparent', 'conditioning', 'evidence_sha256'}
        if (not isinstance(p, dict) or not required <= set(p)
                or set(p) - required - {'native_size', 'crop_bottom'}):
            raise Refusal()
        dimensions(p['size'])
        if (p['operation'] not in ('generation', 'edit') or type(p['references']) is not int
                or p['references'] not in ((0,) if p['operation'] == 'generation' else (1, 2))
                or type(p['transparent']) is not bool or not isinstance(p['conditioning'], str)
                or len(p['conditioning']) > 2048
                or (p['transparent'] and not p['conditioning'].strip())
                or (not p['transparent'] and p['conditioning'] != '')
                or not isinstance(p['evidence_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', p['evidence_sha256'])):
            raise Refusal()
        profile_geometry(p)
        signature = (p['operation'], p['size'], p['references'], p['transparent'])
        if signature in seen:
            raise Refusal()
        seen.add(signature)
    return value


def pad_edit_reference(raw):
    """Native-equivalent canonical pixels plus eight last rows, no resampling."""
    with Image.open(io.BytesIO(raw)) as image:
        # Match native load_image: apply EXIF orientation then convert to RGBA,
        # including palette/RGB/L tRNS. Reject orientation-swapped geometry.
        pixels = ImageOps.exif_transpose(image).convert('RGBA')
        if pixels.size != (1920, 1080):
            raise Refusal(400, 'invalid_image')
        padded = Image.new('RGBA', (1920, 1088))
        padded.paste(pixels, (0, 0))
        row = pixels.crop((0, 1079, 1920, 1080))
        for y in range(1080, 1088):
            padded.paste(row, (0, y))
        result = io.BytesIO()
        padded.save(result, format='PNG')
        return result.getvalue()


@dataclass
class Validated:
    native: dict
    images: list[bytes]
    size: tuple[int, int]
    transparent: bool
    native_size: tuple[int, int]
    crop_bottom: int


def decode_image(raw, size, *, output=False, transparent=False, crop_bottom=0):
    """Check real content and full decode; never resize or trust MIME/extension."""
    try:
        maximum = PIXEL_LIMIT
        if crop_bottom:
            if not output or crop_bottom != 8 or size != (1920, 1088):
                raise ValueError()
            maximum = FHD_NATIVE_PIXELS
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if (probe.format not in (('PNG',) if output else ('PNG', 'JPEG'))
                        or probe.size != size or probe.width * probe.height > maximum
                        or getattr(probe, 'n_frames', 1) != 1):
                    raise ValueError()
                probe.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if crop_bottom:
                    image = image.crop((0, 0, 1920, 1080))
                if output:
                    if transparent and ('A' not in image.getbands()
                                        or image.getchannel('A').getextrema()[0] == 255):
                        raise ValueError()
                    # Emit only pixels, stripping native text/path/EXIF metadata.
                    clean = Image.frombytes('RGBA' if transparent else 'RGB', image.size,
                                            image.convert('RGBA' if transparent else 'RGB').tobytes())
                    stream = io.BytesIO()
                    clean.save(stream, format='PNG')
                    return stream.getvalue()
    except (ValueError, OSError, SyntaxError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        if output:
            raise BackendFailure() from None
        raise Refusal(400, 'invalid_image') from None


def validate(fields, images, operation, config):
    allowed = {'prompt', 'model', 'n', 'size', 'seed', 'response_format', 'background'}
    if not isinstance(fields, dict) or set(fields) - allowed:
        raise Refusal()
    value = {'model': ALIAS, 'n': 1, 'size': '1024x1024', 'response_format': 'b64_json',
             'background': 'opaque', **fields}
    prompt = value.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > 16384:
        raise Refusal()
    if (value['model'] != ALIAS or type(value['n']) is not int or value['n'] != 1
            or value['response_format'] != 'b64_json' or value['background'] not in ('opaque', 'transparent')):
        raise Refusal()
    if 'seed' in value and (type(value['seed']) is not int or not 0 <= value['seed'] <= 2**63 - 1):
        raise Refusal()
    size = dimensions(value['size'])
    count = len(images)
    if count not in ((0,) if operation == 'generation' else (1, 2)):
        raise Refusal()
    transparent = value['background'] == 'transparent'
    profile = next((p for p in config['profiles'] if p['operation'] == operation
                    and p['size'] == value['size'] and p['references'] == count
                    and p['transparent'] == transparent), None)
    if profile is None:
        raise Refusal(400, 'unqualified_profile')
    if any(len(raw) > FILE_LIMIT for raw in images) or sum(map(len, images)) > TOTAL_LIMIT:
        raise Refusal(413, 'input_too_large')
    native_size, crop_bottom = profile_geometry(profile)
    for raw in images:
        decode_image(raw, size)
    if images and crop_bottom:
        # Keep caller bytes untouched. Native conditioning's area/32 resize is
        # identity only when the reference already has the native padded size.
        images = [pad_edit_reference(raw) for raw in images]
    native = {'model': ALIAS, 'prompt': (profile['conditioning'] + '\n' if transparent else '') + prompt,
              'n': 1, 'size': native_size, 'response_format': 'b64_json', 'output_format': 'png',
              'background': value['background'], 'num_inference_steps': 40,
              'guidance_scale': 1, 'true_cfg_scale': 1, 'generator_device': 'cpu'}
    if 'seed' in value:
        native['seed'] = value['seed']
    elif images:
        # Native omission inherits seed42. Reusing source noise can damage edits.
        # Choose once per owned request; explicit caller seeds remain exact.
        native['seed'] = secrets.randbits(32)
    return Validated(native, images, size, transparent, tuple(map(int, native_size.split('x'))), crop_bottom)


def public_output(raw, request):
    try:
        value = strict_json(raw)
        data = value['data']
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0]['b64_json'], str):
            raise ValueError()
        encoded = data[0]['b64_json']
        if len(encoded) > OUTPUT_LIMIT:
            raise ValueError()
        png = base64.b64decode(encoded, validate=True)
        png = decode_image(png, request.native_size, output=True, transparent=request.transparent,
                           crop_bottom=request.crop_bottom)
        item = {'b64_json': base64.b64encode(png).decode('ascii')}
        if request.images:
            item['seed'] = request.native['seed']
        return {'created': int(time.time()), 'data': [item]}
    except (KeyError, TypeError, ValueError, binascii.Error, Refusal):
        raise BackendFailure() from None
