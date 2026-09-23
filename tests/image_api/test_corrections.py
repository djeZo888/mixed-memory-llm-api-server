"""Root correction fixtures: ASGI ownership/health and the sole UHD mapping.

All images and backend responses are local synthetic source fixtures, never
Worker1 qualification or actual native SGLang/GPU acceptance.
"""
import asyncio
import base64
import copy
import io
import json
import time
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from test_handlers import Backend, config, fixture, png, profile
from image_api import backend as wire, protocol


class Health(unittest.IsolatedAsyncioTestCase):
    async def test_idle_death_fails_readiness_and_admission_until_reconciliation(self):
        native = Backend()
        state = {'healthy': True, 'probes': 0}
        async def health():
            state['probes'] += 1
            return state['healthy']
        native.health = health
        async with fixture(backend=native) as (client, owner, _, resets):
            self.assertEqual((await client.get('/health/ready')).status_code, 200)
            state['healthy'] = False
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            state['healthy'] = True
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            self.assertEqual(len(resets), 1)  # GET/health failure never invokes recovery.
            self.assertEqual(native.calls, [])
            await owner.reconcile()  # fixture of required fixed helper reconciliation
            self.assertEqual((await client.get('/health/ready')).status_code, 200)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 200)

    async def test_pre_admission_probe_reserves_slot_before_await(self):
        native = Backend(blocked=True)
        entered, release = asyncio.Event(), asyncio.Event()
        async def health():
            entered.set()
            await release.wait()
            return True
        native.health = health
        async with fixture(backend=native) as (client, owner, _, resets):
            first = asyncio.create_task(client.post('/v1/images/generations', json={'prompt': 'x'}))
            await asyncio.wait_for(entered.wait(), 1)
            self.assertIsNotNone(owner.owner)
            self.assertEqual(native.calls, [])
            contenders = await asyncio.gather(*(client.post('/v1/images/generations', json={'prompt': 'other'}) for _ in range(12)))
            self.assertTrue(all(r.status_code == 429 and r.headers['Retry-After'] == '1' for r in contenders))
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            supervisor = owner.owner
            release.set()
            await asyncio.wait_for(native.started.wait(), 1)
            self.assertEqual(native.maximum, 1)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'other'})).status_code, 429)
            native.release.set()
            await supervisor
            self.assertEqual(len(resets), 1)

    async def test_failed_pre_admission_probe_never_calls_native_or_self_reopens(self):
        native = Backend()
        async def health():
            return False
        native.health = health
        async with fixture(backend=native) as (client, owner, _, resets):
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            self.assertIsNone(owner.owner)
            self.assertFalse(owner.ready)
            self.assertEqual(native.calls, [])
            self.assertEqual(len(resets), 1)

    async def test_concurrent_failed_get_latches_closed_through_active_success(self):
        native = Backend(blocked=True)
        healthy = True
        async def health():
            return healthy
        native.health = health
        async with fixture(backend=native) as (client, owner, _, resets):
            first = asyncio.create_task(client.post('/v1/images/generations', json={'prompt': 'x'}))
            await native.started.wait()
            healthy = False
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual(native.active, 1)
            self.assertTrue(native.spool.exists())
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'other'})).status_code, 429)
            native.release.set()
            self.assertEqual((await first).status_code, 200)
            healthy = True
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            self.assertFalse(owner.ready)
            self.assertEqual(len(resets), 1)

    async def test_late_positive_probe_cannot_erase_concurrent_failure(self):
        native = Backend()
        entered, release = asyncio.Event(), asyncio.Event()
        count = 0
        async def health():
            nonlocal count
            count += 1
            if count == 1:
                entered.set()
                await release.wait()
                return True
            return False
        native.health = health
        async with fixture(backend=native) as (client, owner, _, _):
            first = asyncio.create_task(client.post('/v1/images/generations', json={'prompt': 'x'}))
            await entered.wait()
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            release.set()
            self.assertEqual((await first).status_code, 503)
            self.assertFalse(owner.ready)
            self.assertEqual(native.calls, [])

    async def test_health_wire_invalid_redirect_error_and_total_timeout_close(self):
        async def hang(request):
            await asyncio.Event().wait()
        async def unavailable(request):
            raise httpx.ReadTimeout('fixture path /must/not/leak')
        cases = [httpx.Response(503), httpx.Response(307, headers={'Location': 'http://untrusted'}),
                 httpx.Response(200, json={'status': 'loading'}), httpx.Response(200, text='/native/private'),
                 httpx.Response(200, json={'status': 'ok', 'extra': 'invalid'}),
                 httpx.Response(200, content=b' ' * 1025, headers={'Content-Type': 'application/json'}),
                 httpx.Response(200, content=b'{"status":"ok","status":"ok"}', headers={'Content-Type': 'application/json'}),
                 hang, unavailable]
        for case in cases:
            observed = []
            async def upstream(request):
                observed.append((request.method, str(request.url)))
                return await case(request) if callable(case) else case
            native = wire.NativeBackend(transport=httpx.MockTransport(upstream))
            with patch.object(wire, 'HEALTH_BUDGET', .04):
                async with fixture(backend=native) as (client, owner, _, resets):
                    start = time.monotonic()
                    reply = await asyncio.wait_for(client.post('/v1/images/generations', json={'prompt': 'x'}), 1)
                    self.assertEqual(reply.status_code, 503)
                    self.assertLess(time.monotonic() - start, .8)
                    self.assertNotIn('/native', reply.text)
                    self.assertFalse(owner.ready)
                    self.assertEqual(len(resets), 1)
                    self.assertEqual(observed, [('GET', 'http://127.0.0.1:30007/health')])

    async def test_independent_bounded_health_while_image_stream_is_active(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class ImageStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set()
                await release.wait()
                yield json.dumps({'data': [{'b64_json': base64.b64encode(png()).decode()}]}).encode()
        observed = []
        async def upstream(request):
            observed.append((request.method, str(request.url)))
            if request.method == 'GET':
                return httpx.Response(200, json={'status': 'ok'})
            return httpx.Response(200, stream=ImageStream())
        native = wire.NativeBackend(transport=httpx.MockTransport(upstream))
        self.assertIsNot(native.client, native.health_client)
        self.assertEqual(native.health_client.timeout.pool, .5)
        self.assertEqual(native.health_client.timeout.read, 1)
        self.assertFalse(native.health_client.follow_redirects)
        self.assertFalse(native.health_client.trust_env)
        async with fixture(backend=native) as (client, owner, _, resets):
            first = asyncio.create_task(client.post('/v1/images/generations', json={'prompt': 'x'}))
            await entered.wait()
            reply = await asyncio.wait_for(client.get('/health/ready'), .5)
            self.assertEqual(reply.status_code, 200)
            self.assertTrue(reply.json()['busy'])
            self.assertFalse(reply.json()['admitting'])
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'other'})).status_code, 429)
            release.set()
            self.assertEqual((await first).status_code, 200)
            self.assertEqual(len(resets), 1)
            self.assertEqual(sum(method == 'POST' for method, _ in observed), 1)


def uhd_profile(operation, references):
    return {**profile(operation, references, '3840x2160'), 'native_size': '3840x2176', 'crop_bottom': 16}


def encoded(image):
    result = io.BytesIO()
    image.save(result, format='PNG')
    return result.getvalue()


class UHD(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_mapping_capability_and_exact_native_crop(self):
        output = Image.new('RGB', (3840, 2176), (10, 20, 30))
        output.paste((1, 2, 3), (0, 2159, 3840, 2160))
        output.paste((250, 0, 0), (0, 2160, 3840, 2176))
        observed = []
        async def upstream(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'status': 'ok'})
            observed.append(json.loads(await request.aread()))
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(encoded(output)).decode()}]})
        native = wire.NativeBackend(transport=httpx.MockTransport(upstream))
        async with fixture(backend=native, qualification=config([uhd_profile('generation', 0)])) as (client, _, _, _):
            caps = (await client.get('/v1/image-capabilities')).json()
            self.assertEqual(caps['profiles'][0]['native_size'], '3840x2176')
            self.assertEqual(caps['profiles'][0]['crop_bottom'], 16)
            self.assertEqual(caps['limits']['maximum_pixels_when_qualified'], 8294400)
            self.assertEqual(caps['limits']['approved_uhd_native_pixels'], 8355840)
            reply = await client.post('/v1/images/generations', json={'prompt': 'x', 'size': '3840x2160'})
            self.assertEqual(reply.status_code, 200)
            actual = Image.open(io.BytesIO(base64.b64decode(reply.json()['data'][0]['b64_json'])))
            self.assertEqual(actual.size, (3840, 2160))
            self.assertEqual(actual.tobytes(), output.crop((0, 0, 3840, 2160)).tobytes())
            self.assertEqual(observed[0]['size'], '3840x2176')
            self.assertEqual(observed[0]['generator_device'], 'cpu')

    async def test_one_reference_bottom_edge_padding_preserves_decoded_pixels(self):
        public = Image.new('RGBA', (3840, 2160), (10, 20, 30, 200))
        public.paste((30, 40, 50, 60), (0, 2159, 3840, 2160))
        original = encoded(public)
        native = Backend()
        received = []
        original_call = native.call
        async def capture(request):
            received.append((copy.deepcopy(request.native), request.images[0]))
            return await original_call(request)
        native.call = capture
        async with fixture(backend=native, qualification=config([uhd_profile('edit', 1)])) as (client, _, _, _):
            reply = await client.post('/v1/images/edits', data={'prompt': 'x', 'size': '3840x2160'},
                                      files={'image': ('fixture.png', original)})
            self.assertEqual(reply.status_code, 200)
            actual = Image.open(io.BytesIO(received[0][1]))
            self.assertEqual(actual.size, (3840, 2176))
            self.assertEqual(actual.crop((0, 0, 3840, 2160)).tobytes(), public.tobytes())
            last_row = public.crop((0, 2159, 3840, 2160)).tobytes()
            self.assertEqual(actual.crop((0, 2160, 3840, 2176)).tobytes(), last_row * 16)
            self.assertEqual(received[0][0]['size'], '3840x2176')
            self.assertEqual(received[0][0]['generator_device'], 'cpu')
            # Native-sized public uploads remain over the public pixel bound.
            reply = await client.post('/v1/images/edits', data={'prompt': 'x', 'size': '3840x2160'},
                                      files={'image': ('too-large.png', received[0][1])})
            self.assertEqual(reply.status_code, 400)
            self.assertEqual(len(received), 1)

    async def test_wrong_native_dimensions_fail_instead_of_accepting_or_resizing(self):
        for size in [(3840, 2160), (3840, 2175), (3840, 2177), (3839, 2176)]:
            native = Backend()
            async def wrong(request):
                return protocol.public_output(json.dumps({'data': [{'b64_json': base64.b64encode(png(size)).decode()}]}).encode(), request)
            native.call = wrong
            async with fixture(backend=native, qualification=config([uhd_profile('generation', 0)])) as (client, _, _, resets):
                reply = await client.post('/v1/images/generations', json={'prompt': 'x', 'size': '3840x2160'})
                self.assertEqual(reply.status_code, 502, size)
                self.assertEqual(len(resets), 2)

    async def test_legacy_profile_native_public_and_transparency_after_crop(self):
        async with fixture() as (client, _, _, _):
            caps = (await client.get('/v1/image-capabilities')).json()['profiles']
            self.assertTrue(all(p['native_size'] == p['size'] and p['crop_bottom'] == 0 for p in caps))
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 200)
        p = {**uhd_profile('generation', 0), 'transparent': True, 'conditioning': 'fixture transparency'}
        image = Image.new('RGBA', (3840, 2176), (1, 2, 3, 255))
        image.paste((1, 2, 3, 0), (0, 2160, 3840, 2176))
        native = Backend()
        async def cropped_alpha(request):
            return protocol.public_output(json.dumps({'data': [{'b64_json': base64.b64encode(encoded(image)).decode()}]}).encode(), request)
        native.call = cropped_alpha
        async with fixture(backend=native, qualification=config([p])) as (client, _, _, _):
            reply = await client.post('/v1/images/generations', json={'prompt': 'x', 'size': '3840x2160', 'background': 'transparent'})
            self.assertEqual(reply.status_code, 502)  # Alpha only in discarded rows is not transparency.

    def test_invalid_native_mappings_and_two_reference_uhd_rejected(self):
        valid = uhd_profile('edit', 1)
        for changes in [{'native_size': '3840x2175'}, {'native_size': '3840x2177'},
                        {'native_size': '3840x2160'}, {'crop_bottom': 0}, {'crop_bottom': 15},
                        {'crop_bottom': True}, {'size': '1024x1024'}, {'references': 2},
                        {'native_size': '4096x2176'}, {'crop': [0, 0, 3840, 2160]},
                        {'references': 2, 'native_size': '3840x2160', 'crop_bottom': 0}]:
            with self.subTest(changes=changes), self.assertRaises(protocol.Refusal):
                config([{**valid, **changes}])
        for operation, references in [('generation', 0), ('edit', 1)]:
            self.assertEqual(len(config([uhd_profile(operation, references)])['profiles']), 1)
        self.assertEqual(config([profile('generation', 0)])['profiles'][0]['size'], '1024x1024')
