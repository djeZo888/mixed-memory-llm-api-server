"""Root correction fixtures: ASGI ownership/health and the sole Full HD mapping.

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

    async def test_cancelled_readiness_get_preserves_health_and_next_image_probes(self):
        native = Backend()
        entered = asyncio.Event()
        probes = 0
        async def health():
            nonlocal probes
            probes += 1
            if probes == 1:
                entered.set()
                await asyncio.Event().wait()
            return True
        native.health = health
        async with fixture(backend=native) as (client, owner, _, resets):
            readiness = asyncio.create_task(client.get('/health/ready'))
            await asyncio.wait_for(entered.wait(), 1)
            readiness.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await readiness
            self.assertTrue(owner.status()['admitting'])
            self.assertEqual(owner.phase, 'ready')
            self.assertEqual(len(resets), 1)
            self.assertEqual(native.calls, [])
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 200)
            self.assertEqual(probes, 2)  # Actual image made its own fresh probe.
            self.assertEqual(len(native.calls), 1)
            self.assertEqual(len(resets), 1)

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


def fhd_profile():
    return {**profile('generation', 0, '1920x1080'), 'native_size': '1920x1088', 'crop_bottom': 8}


def encoded(image):
    result = io.BytesIO()
    image.save(result, format='PNG')
    return result.getvalue()


class FullHD(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_mapping_capability_and_exact_native_crop(self):
        output = Image.new('RGB', (1920, 1088))
        # Every row differs; equality proves retained rows were neither scaled nor shifted.
        for y in range(1088):
            output.paste((y % 256, y // 256, 73), (0, y, 1920, y + 1))
        observed = []
        async def upstream(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'status': 'ok'})
            observed.append(json.loads(await request.aread()))
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(encoded(output)).decode()}]})
        native = wire.NativeBackend(transport=httpx.MockTransport(upstream))
        async with fixture(backend=native, qualification=config([fhd_profile()])) as (client, _, _, _):
            caps = (await client.get('/v1/image-capabilities')).json()
            self.assertEqual(caps['profiles'][0]['native_size'], '1920x1088')
            self.assertEqual(caps['profiles'][0]['crop_bottom'], 8)
            self.assertEqual(caps['limits']['maximum_pixels_when_qualified'], 2073600)
            self.assertEqual({k: caps['limits'][k] for k in protocol.HARD_LIMITS}, protocol.HARD_LIMITS)
            self.assertNotIn('approved_uhd_native_pixels', caps['limits'])
            reply = await client.post('/v1/images/generations', json={
                'prompt': 'full prompt fixture', 'size': '1920x1080', 'seed': 42, 'n': 1})
            self.assertEqual(reply.status_code, 200)
            actual = Image.open(io.BytesIO(base64.b64decode(reply.json()['data'][0]['b64_json'])))
            self.assertEqual(actual.size, (1920, 1080))
            self.assertEqual(actual.mode, 'RGB')
            self.assertEqual(actual.tobytes(), output.crop((0, 0, 1920, 1080)).tobytes())
            self.assertEqual(observed, [{'model': protocol.ALIAS, 'prompt': 'full prompt fixture',
                'n': 1, 'size': '1920x1088', 'response_format': 'b64_json', 'output_format': 'png',
                'background': 'opaque', 'num_inference_steps': 40, 'guidance_scale': 1,
                'true_cfg_scale': 1, 'generator_device': 'cpu', 'seed': 42}])

    async def test_wrong_native_dimensions_fail_instead_of_accepting_or_resizing(self):
        for size in [(1920, 1080), (1920, 1087), (1920, 1089), (1919, 1088), (1921, 1088)]:
            native = Backend()
            async def wrong(request):
                return protocol.public_output(json.dumps({'data': [{'b64_json': base64.b64encode(png(size)).decode()}]}).encode(), request)
            native.call = wrong
            async with fixture(backend=native, qualification=config([fhd_profile()])) as (client, _, _, resets):
                reply = await client.post('/v1/images/generations', json={'prompt': 'x', 'size': '1920x1080'})
                self.assertEqual(reply.status_code, 502, size)
                self.assertEqual(len(resets), 2)

    async def test_five_smaller_profiles_unchanged(self):
        sizes = ['1024x1024', '1024x576', '1216x704', '1472x832', '1760x992']
        async with fixture(qualification=config([profile('generation', 0, s) for s in sizes] + [fhd_profile()])) as (client, _, backend, _):
            caps = (await client.get('/v1/image-capabilities')).json()['profiles']
            self.assertEqual([p['size'] for p in caps], sizes + ['1920x1080'])
            self.assertTrue(all(p['native_size'] == p['size'] and p['crop_bottom'] == 0 for p in caps[:-1]))
            for size in sizes:
                response = await client.post('/v1/images/generations', json={'prompt': 'x', 'size': size})
                self.assertEqual(response.status_code, 200)
                image = Image.open(io.BytesIO(base64.b64decode(response.json()['data'][0]['b64_json'])))
                self.assertEqual(image.size, tuple(map(int, size.split('x'))))
                self.assertEqual(backend.calls[-1]['size'], size)

    async def test_public_bounds_and_unqualified_transparency_refused_before_native(self):
        async with fixture(qualification=config([fhd_profile()])) as (client, _, backend, _):
            for size in ['1920x1088', '3840x2160', '3840x2176', '1921x1', '1x1081', '1920x1081', '4096x4096']:
                response = await client.post('/v1/images/generations', json={'prompt': 'x', 'size': size})
                self.assertEqual(response.status_code, 400, size)
                self.assertEqual(response.json()['error']['code'], 'unsupported_size')
            response = await client.post('/v1/images/generations', json={
                'prompt': 'x', 'size': '1920x1080', 'background': 'transparent'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(backend.calls, [])

    def test_invalid_mapping_and_edit_mapping_refused(self):
        for changes in [{'native_size': '1920x1087'}, {'native_size': '1920x1089'},
                        {'native_size': '1920x1080'}, {'crop_bottom': 0}, {'crop_bottom': 7},
                        {'crop_bottom': True}, {'size': '1024x1024'},
                        {'operation': 'edit', 'references': 1}, {'operation': 'edit', 'references': 2},
                        {'transparent': True, 'conditioning': 'transparent fixture'},
                        {'native_size': '3840x2176'}, {'crop': [0, 0, 1920, 1080]}]:
            with self.subTest(changes=changes), self.assertRaises(protocol.Refusal):
                config([{**fhd_profile(), **changes}])
        for mapping in [{}, {'native_size': '1920x1080', 'crop_bottom': 0}]:
            with self.assertRaises(protocol.Refusal):
                config([{**profile('generation', 0, '1920x1080'), **mapping}])
        for size in ['1920x1088', '3840x2160']:
            with self.assertRaises(protocol.Refusal):
                config([profile('generation', 0, size)])

    def test_native_pixel_exception_only_applies_to_exact_output_crop(self):
        raw = png((1920, 1088))
        with self.assertRaises(protocol.Refusal):
            protocol.decode_image(raw, (1920, 1088))
        with self.assertRaises(protocol.BackendFailure):
            protocol.decode_image(raw, (1920, 1088), output=True)
        for crop in [7, 9, True]:
            with self.assertRaises(protocol.BackendFailure):
                protocol.decode_image(raw, (1920, 1088), output=True, crop_bottom=crop)

    def test_protected_limits_required_exact_and_not_configurable(self):
        valid = config([fhd_profile()])
        self.assertEqual(valid['limits'], protocol.HARD_LIMITS)
        for key in protocol.HARD_LIMITS:
            for value in [True, 1, 8294400]:
                bad = copy.deepcopy(valid)
                bad['limits'][key] = value
                with self.assertRaises(protocol.Refusal):
                    protocol.qualification(bad)
        for value in [None, {}, {**protocol.HARD_LIMITS, 'extra': 1}]:
            bad = {**valid, 'limits': value}
            with self.assertRaises(protocol.Refusal):
                protocol.qualification(bad)
        del valid['limits']
        with self.assertRaises(protocol.Refusal):
            protocol.qualification(valid)
