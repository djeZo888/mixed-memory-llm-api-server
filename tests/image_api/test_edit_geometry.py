"""Offline adapter wire/pixel checks; synthetic manifests are not qualification."""
import base64
from email import policy
from email.parser import BytesParser
import io
import json
import math
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from test_handlers import config, fixture, png, profile
from test_corrections import encoded, fhd_profile
from image_api import backend as wire, protocol


def edit_profile(size='1920x1080', references=1):
    result = profile('edit', references, size)
    if size == '1920x1080':
        result.update(native_size='1920x1088', crop_bottom=8)
    return result


def patterned(size):
    width, height = size
    # Both axes differ: detect resampling, shifted rows and shifted columns.
    row = bytes(channel for x in range(width) for channel in (x % 256, x // 256, 19))
    image = Image.frombytes('RGB', size, row * height)
    for y in range(height):
        image.putpixel((y % width, y), (y % 256, y // 256, 211))
    return image


class EditGeometry(unittest.IsolatedAsyncioTestCase):
    async def test_fullhd_wire_padding_output_crop_seed_and_capabilities(self):
        source = patterned((1920, 1080))
        original = encoded(source)
        raw_output = patterned((1920, 1088))
        seen = []

        async def upstream(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'status': 'ok'})
            self.assertEqual(request.url.path, '/v1/images/edits')
            body = await request.aread()
            message = BytesParser(policy=policy.default).parsebytes(
                b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + body)
            parts = {p.get_param('name', header='content-disposition'): p.get_payload(decode=True)
                     for p in message.iter_parts()}
            seen.append(parts)
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(encoded(raw_output)).decode()}]})

        native = wire.NativeBackend(transport=httpx.MockTransport(upstream))
        with patch.object(protocol.secrets, 'randbits', side_effect=AssertionError('explicit seed changed')):
            async with fixture(backend=native, qualification=config([edit_profile()])) as (client, _, _, _):
                caps = (await client.get('/v1/image-capabilities')).json()['profiles'][0]
                self.assertEqual(caps['input_padding'], {'top': 0, 'right': 0, 'bottom': 8, 'left': 0})
                self.assertEqual((caps['size'], caps['native_size'], caps['crop_bottom']), ('1920x1080', '1920x1088', 8))
                reply = await client.post('/v1/images/edits', data={'prompt': 'localized edit', 'size': '1920x1080', 'seed': '48'},
                                          files={'image': ('original.png', original)})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()['data'][0]['seed'], 48)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]['size'], b'1920x1088')
        self.assertEqual(seen[0]['num_inference_steps'], b'40')
        self.assertEqual(seen[0]['guidance_scale'], b'1')
        self.assertEqual(seen[0]['true_cfg_scale'], b'1')
        self.assertEqual(seen[0]['generator_device'], b'cpu')
        padded = Image.open(io.BytesIO(seen[0]['image']))
        self.assertEqual(padded.size, (1920, 1088))
        self.assertEqual(padded.crop((0, 0, 1920, 1080)).tobytes(), source.tobytes())
        self.assertEqual(padded.crop((0, 1080, 1920, 1088)).tobytes(), source.crop((0, 1079, 1920, 1080)).tobytes() * 8)
        # Pinned native area/32 geometry must see an identity resize.
        area = 1920 * 1088
        width = max(32, round(math.sqrt(area * padded.width / padded.height) / 32) * 32)
        height = max(32, round(math.sqrt(area * padded.height / padded.width) / 32) * 32)
        self.assertEqual((width, height), padded.size)
        self.assertEqual(padded.resize((width, height), Image.Resampling.LANCZOS).tobytes(), padded.tobytes())
        delivered = Image.open(io.BytesIO(base64.b64decode(reply.json()['data'][0]['b64_json'])))
        self.assertEqual(delivered.size, (1920, 1080))
        self.assertEqual(delivered.tobytes(), raw_output.crop((0, 0, 1920, 1080)).tobytes())
        self.assertEqual(original, encoded(source))

    def test_square_one_two_and_landscape_keep_exact_input_order_bytes(self):
        for size, count, seed in [('1024x1024', 1, 46), ('1024x1024', 2, 49), ('1536x864', 1, 47)]:
            dimensions = tuple(map(int, size.split('x')))
            images = [png(dimensions), encoded(Image.new('RGB', dimensions, 'red'))][:count]
            request = protocol.validate({'prompt': '<image1> and <image2>', 'size': size, 'seed': seed},
                                        images, 'edit', config([edit_profile(size, count)]))
            self.assertEqual(request.images, images)
            self.assertEqual(request.native['seed'], seed)
            self.assertEqual(request.native['size'], size)
            self.assertEqual(request.crop_bottom, 0)

    async def test_two_independent_references_keep_wire_order_and_markers(self):
        originals = [png(), encoded(Image.new('RGB', (1024, 1024), 'red'))]
        prompt = 'Keep <image1> and add the subject from <image2>.'
        seen = []
        async def upstream(request):
            message = BytesParser(policy=policy.default).parsebytes(
                b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + await request.aread())
            parts = list(message.iter_parts())
            seen.extend(p.get_payload(decode=True) for p in parts
                        if p.get_param('name', header='content-disposition') == 'image')
            self.assertEqual(next(p.get_payload(decode=True) for p in parts
                                  if p.get_param('name', header='content-disposition') == 'prompt'), prompt.encode())
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(png()).decode()}]})
        native = wire.NativeBackend(transport=httpx.MockTransport(upstream))
        try:
            request = protocol.validate({'prompt': prompt, 'seed': 49}, originals, 'edit',
                                        config([edit_profile('1024x1024', 2)]))
            result = await native.call(request)
            self.assertEqual(result['data'][0]['seed'], 49)
            self.assertEqual(seen, originals)
        finally:
            await native.close()

    def test_only_exact_operation_refcount_size_profile_admits(self):
        cases = [('1024x1024', 2, [edit_profile('1024x1024', 1)]),
                 ('1536x864', 1, [edit_profile('1024x1024', 1)]),
                 ('1920x1080', 1, [fhd_profile()])]
        with patch.object(protocol.secrets, 'randbits', side_effect=AssertionError('rejected draw')):
            for size, count, profiles in cases:
                with self.subTest(size=size, count=count), self.assertRaises(protocol.Refusal) as error:
                    protocol.validate({'prompt': 'x', 'size': size}, [png(tuple(map(int, size.split('x'))))] * count,
                                      'edit', config(profiles))
                self.assertEqual(error.exception.code, 'unqualified_profile')

    def test_invalid_second_reference_or_fullhd_size_never_draws(self):
        with patch.object(protocol.secrets, 'randbits', side_effect=AssertionError('invalid draw')):
            for size, images, p in [('1024x1024', [png(), b'invalid'], edit_profile('1024x1024', 2)),
                                    ('1920x1080', [png((1920, 1088))], edit_profile())]:
                with self.assertRaises(protocol.Refusal):
                    protocol.validate({'prompt': 'x', 'size': size}, images, 'edit', config([p]))

    def test_missing_seed_after_fullhd_preparation_is_drawn_once(self):
        with patch.object(protocol.secrets, 'randbits', return_value=2**32 - 1) as draw:
            request = protocol.validate({'prompt': 'x', 'size': '1920x1080'}, [png((1920, 1080))],
                                        'edit', config([edit_profile()]))
        draw.assert_called_once_with(32)
        self.assertEqual(request.native['seed'], 2**32 - 1)
        self.assertEqual(Image.open(io.BytesIO(request.images[0])).size, (1920, 1088))

    async def test_generation_only_manifest_has_no_edit_or_padding_claim(self):
        async with fixture(qualification=config([fhd_profile()])) as (client, _, backend, _):
            caps = (await client.get('/v1/image-capabilities')).json()['profiles']
            self.assertEqual(len(caps), 1)
            self.assertEqual(caps[0]['operation'], 'generation')
            self.assertNotIn('input_padding', caps[0])
            reply = await client.post('/v1/images/edits', data={'prompt': 'x', 'size': '1920x1080'},
                                      files={'image': ('x.png', png((1920, 1080)))})
            self.assertEqual(reply.json()['error']['code'], 'unqualified_profile')
            self.assertEqual(backend.calls, [])
