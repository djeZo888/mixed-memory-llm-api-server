"""Strict public contract, reviewed qualification profiles and bounded images."""
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import re
import time
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

ALIAS = 'qwen-image-2.1'
RUNTIME_REVISION = '0cd8be351d0825488f4b81c8931167bbab618eca'
MODEL_ID = 'Qwen/Qwen-Image-2.1'
MODEL_REVISION = '790c92633540aa0cb11d9abf19eb46d861714758'
FILE_LIMIT = 32 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024
ENVELOPE_LIMIT = 64 * 1024
JSON_LIMIT = 64 * 1024
PIXEL_LIMIT = 8294400
OUTPUT_LIMIT = 48 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = PIXEL_LIMIT


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
    if width > 3840 or height > 2160 or width * height > PIXEL_LIMIT:
        raise Refusal(400, 'unsupported_size')
    return width, height


def qualification(value):
    """Protected local data is authority; no configured size becomes measured."""
    keys = {'schema_version', 'runtime_revision', 'model_id', 'model_revision',
            'runtime_image_digest', 'profiles'}
    if not isinstance(value, dict) or set(value) != keys:
        raise Refusal()
    if (type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['runtime_revision'] != RUNTIME_REVISION or value['model_id'] != MODEL_ID
            or value['model_revision'] != MODEL_REVISION):
        raise Refusal()
    digest = value['runtime_image_digest']
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)):
        raise Refusal()
    profiles = value['profiles']
    if not isinstance(profiles, list) or len(profiles) > 100 or (profiles and digest is None):
        raise Refusal()
    seen = set()
    for p in profiles:
        if not isinstance(p, dict) or set(p) != {'operation', 'size', 'references', 'transparent',
                                                'conditioning', 'evidence_sha256'}:
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
        signature = (p['operation'], p['size'], p['references'], p['transparent'])
        if signature in seen:
            raise Refusal()
        seen.add(signature)
    return value


@dataclass
class Validated:
    native: dict
    images: list[bytes]
    size: tuple[int, int]
    transparent: bool


def decode_image(raw, size, *, output=False, transparent=False):
    """Check real content and full decode; never resize or trust MIME/extension."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if (probe.format not in (('PNG',) if output else ('PNG', 'JPEG'))
                        or probe.size != size or probe.width * probe.height > PIXEL_LIMIT
                        or getattr(probe, 'n_frames', 1) != 1):
                    raise ValueError()
                probe.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
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
    for raw in images:
        decode_image(raw, size)
    native = {'model': ALIAS, 'prompt': (profile['conditioning'] + '\n' if transparent else '') + prompt,
              'n': 1, 'size': value['size'], 'response_format': 'b64_json', 'output_format': 'png',
              'background': value['background'], 'num_inference_steps': 40,
              'guidance_scale': 1, 'true_cfg_scale': 1}
    if 'seed' in value:
        native['seed'] = value['seed']
    return Validated(native, images, size, transparent)


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
        png = decode_image(png, request.size, output=True, transparent=request.transparent)
        return {'created': int(time.time()), 'data': [{'b64_json': base64.b64encode(png).decode('ascii')}]}
    except (KeyError, TypeError, ValueError, binascii.Error, Refusal):
        raise BackendFailure() from None
