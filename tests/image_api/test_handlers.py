"""Offline ASGI fixtures, no SGLang/GPU/runtime or real-image qualification."""
import asyncio
import base64
from contextlib import asynccontextmanager
import copy
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib

import httpx
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from image_api.app import create_app
from image_api.backend import NativeBackend
from image_api import protocol, uploads

KEY = b'fixture-only-image-adapter-credential-1234'
AUTH = {'Authorization': 'Bearer ' + KEY.decode()}


def png(size=(1024, 1024), fmt='PNG', alpha=False, metadata=False):
    result = io.BytesIO()
    im = Image.new('RGBA' if alpha else 'RGB', size, (12, 34, 56, 80) if alpha else (12, 34, 56))
    options = {}
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text('private', '/native/secret/path')
        options['pnginfo'] = info
    im.save(result, format=fmt, **options)
    return result.getvalue()


def config(profiles=None):
    raw = json.loads((ROOT / 'scripts/image_api/qualification.empty.json').read_text())
    raw['runtime_image_digest'] = 'sha256:' + 'a' * 64
    raw['profiles'] = profiles if profiles is not None else [profile('generation', 0), profile('edit', 1), profile('edit', 2)]
    return protocol.qualification(raw)


def profile(operation, references, size='1024x1024', transparent=False):
    return {'operation': operation, 'references': references, 'size': size,
            'transparent': transparent, 'conditioning': 'Generate a transparent background.' if transparent else '',
            'evidence_sha256': 'b' * 64}


class Backend:
    def __init__(self, *, blocked=False, fail=False):
        self.started, self.release = asyncio.Event(), asyncio.Event()
        if not blocked:
            self.release.set()
        self.calls, self.active, self.maximum = [], 0, 0
        self.fail, self.cleaned, self.spool = fail, False, None
        self.retained = None

    async def health(self):
        return True

    async def call(self, request):
        self.calls.append(copy.deepcopy(request.native))
        self.retained = request
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        # Explicit fixture of exact native tempdir ownership, NOT native execution.
        with tempfile.TemporaryDirectory(prefix='image-api-fixture-') as directory:
            self.spool = Path(directory)
            (self.spool / 'owned.png').write_bytes(b'fixture')
            self.started.set()
            try:
                await self.release.wait()
                if self.fail:
                    raise RuntimeError('/native/private/path DO_NOT_LEAK')
                return protocol.public_output(json.dumps({'data': [{'b64_json': base64.b64encode(
                    png(request.native_size, alpha=request.transparent, metadata=True)).decode(),
                    'revised_prompt': '/native/private/path'}]}).encode(), request)
            finally:
                self.active -= 1
        # unreachable after return; directory existence is the cleanup evidence.

    async def close(self):
        pass


@asynccontextmanager
async def fixture(*, backend=None, recovery=None, qualification=None, budget=900):
    backend = backend or Backend()
    recovery_calls = []
    async def reset():
        recovery_calls.append(True)
        return True if recovery is None else await recovery(backend, len(recovery_calls))
    app = create_app(qualification or config(), KEY, backend=backend, recovery=reset, budget=budget)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://adapter',
                                     headers=AUTH) as client:
            yield client, app.state.owner, backend, recovery_calls


class Handlers(unittest.IsolatedAsyncioTestCase):
    async def test_auth_every_route_missing_wrong_malformed_duplicate(self):
        async with fixture() as (client, owner, backend, _):
            for path in ['/health/live', '/health/ready', '/v1/models', '/v1/image-capabilities',
                         '/v1/images/generations', '/v1/images/edits', '/unknown']:
                for headers in [{}, {'Authorization': 'Bearer wrong'}, {'Authorization': 'Basic abc'},
                                {'Authorization': 'Bearer  ' + KEY.decode()}, {'Authorization': 'Bearer'},
                                [('Authorization', 'Bearer ' + KEY.decode()), ('Authorization', 'Bearer wrong')]]:
                    request = client.build_request('POST' if 'images/' in path else 'GET', path)
                    request.headers.clear()
                    request.headers.update(headers)
                    reply = await client.send(request)
                    self.assertEqual(reply.status_code, 401, (path, headers))
                    self.assertEqual(reply.headers['www-authenticate'], 'Bearer')
            self.assertEqual(backend.calls, [])
            self.assertEqual((await client.get('/health/live', headers={'Authorization': 'bearer ' + KEY.decode()})).status_code, 200)

    async def test_valid_json_seed_output_sanitized_and_spool_cleaned(self):
        async with fixture() as (client, owner, backend, _):
            reply = await client.post('/v1/images/generations', json={'prompt': 'fixture', 'seed': 9})
            self.assertEqual(reply.status_code, 200)
            self.assertEqual(set(reply.json()), {'created', 'data'})
            self.assertEqual(set(reply.json()['data'][0]), {'b64_json'})
            raw = base64.b64decode(reply.json()['data'][0]['b64_json'], validate=True)
            self.assertTrue(raw.startswith(b'\x89PNG'))
            self.assertNotIn(b'/native/', raw)
            self.assertFalse(backend.spool.exists())
            self.assertIsNone(owner.owner)
            self.assertEqual(backend.retained.images, [])
            self.assertEqual(backend.calls[0]['seed'], 9)
            self.assertEqual(backend.calls[0]['num_inference_steps'], 40)
            self.assertEqual(backend.calls[0]['true_cfg_scale'], 1)
            self.assertEqual(backend.calls[0]['generator_device'], 'cpu')

    async def test_unsafe_unknown_fields_and_invalid_model_n_seed_size(self):
        async with fixture() as (client, owner, backend, _):
            invalid = [{'url': 'http://invalid'}, {'mask': 'x'}, {'image': '/private'}, {'output_path': '/tmp'},
                       {'diffusers_kwargs': {}}, {'num_inference_steps': 1}, {'guidance_scale': 8},
                       {'generator_device': 'cpu'}, {'generator_device': 'cuda'}, {'native_size': '3840x2176'}, {'crop_bottom': 16},
                       {'model': 'other'}, {'n': 2}, {'n': True}, {'n': 1.0}, {'n': '1'},
                       {'seed': -1}, {'seed': 2**63}, {'seed': True}, {'seed': None},
                       {'response_format': 'url'}, {'size': '3840x2160'}, {'size': '4096x4096'},
                       {'size': [1024, 1024]}, {'prompt': ''}, {'background': 'transparent'}]
            for change in invalid:
                reply = await client.post('/v1/images/generations', json={'prompt': 'test', **change})
                self.assertEqual(reply.status_code, 400, change)
            for raw in [b'{"prompt":"x","prompt":"y"}', b'{"prompt":NaN}', b'[]', b'null', b'\xff']:
                reply = await client.post('/v1/images/generations', content=raw, headers={'Content-Type': 'application/json'})
                self.assertEqual(reply.status_code, 400)
            self.assertEqual((await client.post('/v1/images/generations?url=x', json={'prompt': 'x'})).status_code, 400)
            self.assertEqual(backend.calls, [])

    async def test_empty_profiles_fail_closed_and_capabilities_distinguish_profiles(self):
        async with fixture(qualification=config([])) as (client, owner, backend, _):
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            caps = (await client.get('/v1/image-capabilities')).json()
            self.assertEqual(caps['profiles'], [])
            self.assertFalse(caps['admitting'])
        measured = [{**profile(operation, references, '3840x2160'),
                     'native_size': '3840x2176', 'crop_bottom': 16}
                    for operation, references in [('generation', 0), ('edit', 1)]] + [profile('edit', 2)]
        async with fixture(qualification=config(measured)) as (client, _, backend, _):
            self.assertEqual((await client.get('/v1/image-capabilities')).json()['profiles'][1]['references'], 1)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 400)
            # Qualified UHD one-reference has no old 4MP ceiling.
            image = png((3840, 2160))
            reply = await client.post('/v1/images/edits', data={'prompt': 'x', 'size': '3840x2160'},
                                      files={'image': ('x.png', image, 'image/png')})
            self.assertEqual(reply.status_code, 200)
            reply = await client.post('/v1/images/edits', data={'prompt': 'x', 'size': '3840x2160'},
                                      files=[('image', ('x', image)), ('image', ('y', image))])
            self.assertEqual(reply.status_code, 400)

    async def test_png_jpeg_references_actual_decode_and_no_resize(self):
        async with fixture() as (client, _, backend, _):
            for fmt in ('PNG', 'JPEG'):
                reply = await client.post('/v1/images/edits', data={'prompt': 'edit', 'seed': '12'},
                                          files={'image[]': ('../../unsafe.bin', png(fmt=fmt), 'text/plain')})
                self.assertEqual(reply.status_code, 200)
            for raw in (png((1024, 1023)), png(fmt='GIF'), b'not image', png()[:80]):
                reply = await client.post('/v1/images/edits', data={'prompt': 'x'}, files={'image': ('x.png', raw)})
                self.assertEqual(reply.status_code, 400)
            # IHDR bomb declares huge dimensions without allocating huge pixels.
            raw = png()
            ihdr = struct.pack('>II', 200000, 200000) + raw[24:29]
            bomb = raw[:16] + ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr)) + raw[33:]
            self.assertEqual((await client.post('/v1/images/edits', data={'prompt': 'x'},
                             files={'image': ('bomb.png', bomb)})).status_code, 400)
            self.assertEqual(len(backend.calls), 2)

    async def test_multipart_unknown_masks_duplicate_fields_and_references(self):
        async with fixture() as (client, _, backend, _):
            for fields, files in [({'prompt': 'x', 'url': 'http://x'}, [('image', ('x', png()))]),
                                  ({'prompt': 'x'}, [('mask', ('x', png())), ('image', ('x', png()))]),
                                  ({'prompt': 'x'}, [('image', ('x', png()))] * 3),
                                  ({'prompt': 'x'}, [('image', ('x', png())), ('image[]', ('x', png()))]),
                                  ({'prompt': 'x', 'n': '1.0'}, [('image', ('x', png()))]),
                                  ({'prompt': 'x'}, [])]:
                reply = await client.post('/v1/images/edits', data=fields, files=files)
                self.assertEqual(reply.status_code, 400)
            duplicate = [('prompt', (None, 'x')), ('prompt', (None, 'y')), ('image', ('x', png()))]
            self.assertEqual((await client.post('/v1/images/edits', files=duplicate)).status_code, 400)
            # Parser finalization must reject a missing closing boundary.
            req = client.build_request('POST', '/v1/images/edits', data={'prompt': 'x'}, files={'image': ('x', png())})
            raw = req.read()
            self.assertEqual((await client.post('/v1/images/edits', content=raw[:-50],
                                               headers={'Content-Type': req.headers['Content-Type']})).status_code, 400)
            self.assertEqual(backend.calls, [])

    async def test_streamed_limits_ignore_content_length(self):
        async with fixture() as (client, _, backend, _):
            async def oversized():
                for _ in range(5):
                    yield b'x' * 16384
            reply = await client.post('/v1/images/generations', content=oversized(),
                                      headers={'Content-Type': 'application/json', 'Content-Length': '1'})
            self.assertEqual(reply.status_code, 413)
            # Real 32MiB+1 file exercised through ASGI multipart handler.
            reply = await client.post('/v1/images/edits', data={'prompt': 'x'},
                                      files={'image': ('x', b'x' * (protocol.FILE_LIMIT + 1))})
            self.assertEqual(reply.status_code, 413)
            # Reduced constants exercise independent total/envelope branches cheaply.
            with patch.object(uploads, 'FILE_LIMIT', 100), patch.object(uploads, 'TOTAL_LIMIT', 150):
                reply = await client.post('/v1/images/edits', data={'prompt': 'x'},
                                          files=[('image', ('x', b'x' * 80)), ('image', ('y', b'x' * 80))])
                self.assertEqual(reply.status_code, 413)
            with patch.object(uploads, 'TOTAL_LIMIT', 10), patch.object(uploads, 'ENVELOPE_LIMIT', 10):
                reply = await client.post('/v1/images/edits', content=b'x' * 21,
                                          headers={'Content-Type': 'multipart/form-data; boundary=x', 'Content-Length': '1'})
                self.assertEqual(reply.status_code, 413)
            self.assertEqual(backend.calls, [])

    async def test_zero_queue_race_and_disconnect_retains_upstream_and_spool(self):
        backend = Backend(blocked=True)
        async with fixture(backend=backend) as (client, owner, _, _):
            first = asyncio.create_task(client.post('/v1/images/edits', data={'prompt': 'x'}, files={'image': ('x', png())}))
            await backend.started.wait()
            replies = await asyncio.gather(*(client.post('/v1/images/generations', json={'prompt': 'other'}) for _ in range(20)))
            self.assertTrue(all(r.status_code == 429 and r.headers['Retry-After'] == '1' for r in replies))
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertTrue(backend.spool.exists())
            self.assertEqual(len(backend.retained.images), 1)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'other'})).status_code, 429)
            self.assertEqual(backend.maximum, 1)
            self.assertIsNotNone(owner.owner)
            supervisor = owner.owner
            backend.release.set()
            await supervisor
            self.assertFalse(backend.spool.exists())
            self.assertEqual(backend.retained.images, [])
            self.assertIsNone(owner.owner)

    async def test_cancelled_client_still_gets_timeout_recovery(self):
        backend = Backend(blocked=True)
        reset_entered, reset_release = asyncio.Event(), asyncio.Event()
        async def recovery(native, count):
            if count > 1:
                reset_entered.set()
                await reset_release.wait()
                native.release.set()  # fixture exact backend stopped/warmed proof
            return True
        async with fixture(backend=backend, recovery=recovery, budget=.1) as (client, owner, _, resets):
            first = asyncio.create_task(client.post('/v1/images/generations', json={'prompt': 'x'}))
            await backend.started.wait()
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            await asyncio.wait_for(reset_entered.wait(), 2)
            self.assertFalse(owner.ready)
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 429)
            self.assertTrue(backend.spool.exists())
            supervisor = owner.owner
            reset_release.set()
            await supervisor
            self.assertTrue(owner.ready)
            self.assertFalse(backend.spool.exists())
            self.assertEqual(len(resets), 2)

    async def test_timeout_failure_stays_closed_after_old_work_settles(self):
        backend = Backend(blocked=True)
        async def recovery(native, count):
            return count == 1
        async with fixture(backend=backend, recovery=recovery, budget=.05) as (client, owner, _, resets):
            reply = await client.post('/v1/images/generations', json={'prompt': 'x'})
            self.assertEqual(reply.status_code, 504)
            self.assertFalse(owner.ready)
            self.assertIsNotNone(owner.owner)
            supervisor = owner.owner
            backend.release.set()
            await supervisor
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            self.assertEqual(len(resets), 2)

    async def test_restart_reconciliation_blocks_and_failure_never_ready(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def recovery():
            entered.set()
            await release.wait()
            return False
        app = create_app(config(), KEY, backend=Backend(), recovery=recovery)
        owner = app.state.owner
        startup = asyncio.create_task(owner.reconcile())
        await entered.wait()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://adapter', headers=AUTH) as client:
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)
            release.set()
            await startup
            self.assertEqual((await client.get('/health/ready')).status_code, 503)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)

    async def test_backend_exception_is_redacted_and_reconciled(self):
        async with fixture(backend=Backend(fail=True)) as (client, owner, backend, resets):
            reply = await client.post('/v1/images/generations', json={'prompt': 'x'})
            self.assertEqual(reply.status_code, 502)
            self.assertNotIn('native', reply.text)
            self.assertNotIn('DO_NOT_LEAK', reply.text)
            self.assertFalse(backend.spool.exists())
            self.assertEqual(len(resets), 2)

    async def test_decode_thread_deadline_retains_slot_and_never_submits_late(self):
        started, release = threading.Event(), threading.Event()
        original = protocol.validate
        def slow_validate(*args):
            started.set()
            release.wait(3)
            return original(*args)
        from image_api import app as module
        async with fixture(budget=.08) as (client, owner, backend, resets):
            with patch.object(module, 'validate', slow_validate):
                first = asyncio.create_task(client.post('/v1/images/generations', json={'prompt': 'x'}))
                await asyncio.to_thread(started.wait, 2)
                second = await client.post('/v1/images/generations', json={'prompt': 'other'})
                self.assertEqual(second.status_code, 429)
                reply = await asyncio.wait_for(first, 1)
                self.assertEqual(reply.status_code, 504)
                self.assertIsNotNone(owner.owner)
                self.assertEqual(backend.calls, [])
                supervisor = owner.owner
                release.set()
                await supervisor
                self.assertTrue(owner.ready)
                self.assertEqual(backend.calls, [])
                self.assertEqual(len(resets), 1)

    async def test_late_settled_result_cannot_be_success_past_deadline(self):
        backend = Backend()
        async def blocking_call(request):
            time.sleep(.08)  # injected faulty synchronous backend; fixture only
            return {'data': []}
        backend.call = blocking_call
        async with fixture(backend=backend, budget=.03) as (client, owner, _, resets):
            reply = await client.post('/v1/images/generations', json={'prompt': 'x'})
            self.assertEqual(reply.status_code, 504)
            if owner.owner:
                await owner.owner
            self.assertTrue(owner.ready)

    async def test_late_transport_failure_still_requires_recovery(self):
        backend = Backend()
        async def blocking_failure(request):
            time.sleep(.08)
            raise protocol.BackendFailure()
        backend.call = blocking_failure
        async def recovery(native, count):
            return count == 1
        async with fixture(backend=backend, recovery=recovery, budget=.03) as (client, owner, _, resets):
            reply = await client.post('/v1/images/generations', json={'prompt': 'x'})
            self.assertEqual(reply.status_code, 504)
            if owner.owner:
                await owner.owner
            self.assertFalse(owner.ready)
            self.assertEqual(len(resets), 2)
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 503)

    async def test_disconnect_during_body_releases_without_backend_recovery(self):
        backend = Backend()
        async def reset():
            return True
        app = create_app(config(), KEY, backend=backend, recovery=reset)
        async with app.router.lifespan_context(app):
            messages = iter([{'type': 'http.request', 'body': b'{"prompt":', 'more_body': True},
                             {'type': 'http.disconnect'}])
            async def receive():
                return next(messages)
            sent = []
            async def send(message):
                sent.append(message)
            await app({'type': 'http', 'http_version': '1.1', 'method': 'POST',
                       'scheme': 'http', 'path': '/v1/images/generations', 'raw_path': b'/v1/images/generations',
                       'query_string': b'', 'root_path': '', 'headers': [(b'authorization', b'Bearer ' + KEY),
                       (b'content-type', b'application/json')], 'server': ('adapter', 80),
                       'client': ('fixture', 1)}, receive, send)
            self.assertEqual(sent[0]['status'], 400)
            self.assertIsNone(app.state.owner.owner)
            self.assertEqual(backend.calls, [])
            self.assertTrue(app.state.owner.ready)

    async def test_transparency_requires_separate_conditioned_profile_and_alpha(self):
        async with fixture(qualification=config([profile('generation', 0, transparent=True)])) as (client, _, backend, _):
            reply = await client.post('/v1/images/generations', json={'prompt': 'x', 'background': 'transparent'})
            self.assertEqual(reply.status_code, 200)
            self.assertTrue(backend.calls[0]['prompt'].startswith('Generate a transparent background.\n'))
            im = Image.open(io.BytesIO(base64.b64decode(reply.json()['data'][0]['b64_json'])))
            self.assertIn('A', im.getbands())
            self.assertLess(im.getchannel('A').getextrema()[0], 255)


class NativeWire(unittest.IsolatedAsyncioTestCase):
    async def test_exact_generation_and_edit_wire_no_path_or_caller_headers(self):
        observed = []
        async def upstream(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'status': 'ok'})
            observed.append((request.url, request.headers, await request.aread()))
            return httpx.Response(200, json={'id': 'native', 'data': [{'b64_json': base64.b64encode(png()).decode(),
                                   'file_path': None, 'url': None}], 'unused': '/native/private'})
        native = NativeBackend(transport=httpx.MockTransport(upstream))
        async with fixture(backend=native) as (client, _, _, _):
            self.assertEqual((await client.post('/v1/images/generations', json={'prompt': 'x'})).status_code, 200)
            self.assertEqual((await client.post('/v1/images/edits', data={'prompt': 'x'},
                             files={'image': ('../../private-name.jpg', png(fmt='JPEG'))})).status_code, 200)
        self.assertEqual(str(observed[0][0]), 'http://127.0.0.1:30007/v1/images/generations')
        body = json.loads(observed[0][2])
        self.assertEqual(set(body), {'model', 'prompt', 'n', 'size', 'response_format', 'output_format',
                                    'background', 'num_inference_steps', 'guidance_scale', 'true_cfg_scale', 'generator_device'})
        self.assertEqual(body['generator_device'], 'cpu')
        self.assertIn(b'name="generator_device"\r\n\r\ncpu', observed[1][2])
        self.assertNotIn('authorization', observed[0][1])
        self.assertIn(b'name="image"; filename="reference-0.jpg"', observed[1][2])
        self.assertNotIn(b'private-name', observed[1][2])
        self.assertNotIn(KEY, observed[1][2])

    async def test_redirect_native_error_invalid_output_never_leaks(self):
        for response in [httpx.Response(307, headers={'Location': 'http://untrusted.example'}),
                         httpx.Response(500, text='/native/secret'), httpx.Response(200, text='{invalid'),
                         httpx.Response(200, json={'data': [{'b64_json': 'not-base64', 'file_path': '/native'}]}),
                         httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(png((32, 32))).decode()}]})]:
            calls = []
            async def upstream(request):
                if request.method == 'GET':
                    return httpx.Response(200, json={'status': 'ok'})
                calls.append(str(request.url))
                return response
            native = NativeBackend(transport=httpx.MockTransport(upstream))
            async with fixture(backend=native) as (client, _, _, resets):
                reply = await client.post('/v1/images/generations', json={'prompt': 'x'})
                self.assertEqual(reply.status_code, 502)
                self.assertEqual(calls, ['http://127.0.0.1:30007/v1/images/generations'])
                self.assertNotIn('/native', reply.text)
                self.assertEqual(len(resets), 2)


if __name__ == '__main__':
    unittest.main()
