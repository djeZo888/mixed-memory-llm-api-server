"""One owned async operation, zero queue, closed startup and bounded recovery."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import hmac

from fastapi import FastAPI, Request
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

from .backend import NativeBackend, recover
from .protocol import ALIAS, HARD_LIMITS, BackendFailure, Refusal, owned_thread, profile_geometry, validate
from .uploads import Uploads, read_json

REQUEST_BUDGET = 900


def error(status, code):
    return JSONResponse({'error': {'code': code, 'message': code.replace('_', ' ')}}, status,
                        headers={'Retry-After': '1'} if status == 429 else {})


class Owner:
    """Only supervisor releases admission; response delivery does not own it.

    claim() has no await between inspection and assignment. Exactly one event
    loop/process is enforced by the production launcher and advisory process lock.
    """
    def __init__(self, config, backend, recovery, budget=REQUEST_BUDGET):
        self.config, self.backend, self.recovery, self.budget = config, backend, recovery, budget
        self.ready = False
        self.phase = 'startup'
        self.owner = None
        self.work = None
        self.stopping = False

    async def reconcile(self):
        self.ready, self.phase = False, 'recovering'
        try:
            success = await self.recovery()
        except Exception:
            success = False
        self.ready = success is True and not self.stopping
        self.phase = 'ready' if self.ready else 'closed'
        return self.ready

    async def probe(self):
        # A positive probe is only a check, never recovery authorization. Keep the
        # failure latched even if another in-flight probe later reports success.
        if not self.ready:
            return False
        try:
            healthy = await self.backend.health()
        except asyncio.CancelledError:
            # Caller-only probe cancellation says nothing about backend health.
            raise
        except Exception:
            healthy = False
        if healthy is not True:
            self.ready, self.phase = False, 'closed'
        return self.ready and not self.stopping

    def status(self):
        qualified = bool(self.config['profiles'])
        return {'ready': self.ready and qualified, 'busy': self.owner is not None,
                'admitting': self.ready and qualified and self.owner is None,
                'state': self.phase if qualified else 'unqualified'}

    def claim(self, request, operation):
        if self.owner is not None:
            raise Refusal(429, 'busy')
        if not self.ready or not self.config['profiles']:
            raise Refusal(503, 'not_ready')
        reply = asyncio.get_running_loop().create_future()
        self.owner = asyncio.create_task(self.run(request, operation, reply))
        return reply

    async def execute(self, request, operation):
        uploads = None
        validated = None
        try:
            if operation == 'generation':
                if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                    raise Refusal(415, 'unsupported_media_type')
                fields, images = await read_json(request), []
            else:
                uploads = Uploads(request.headers.get('content-type', ''))
                fields, images = await uploads.read(request)
            validated = await owned_thread(validate, fields, images, operation, self.config)
            if asyncio.get_running_loop().time() >= self.deadline:
                raise Refusal(504, 'request_timeout')
            if not await self.probe():
                raise Refusal(503, 'not_ready')
            if asyncio.get_running_loop().time() >= self.deadline:
                raise Refusal(504, 'request_timeout')
            # No await separates submission marker from entering fixed backend.
            self.submitted = True
            result = await self.backend.call(validated)
            return await owned_thread(JSONResponse, result)
        except (Refusal, ClientDisconnect):
            raise
        except Exception:
            if self.submitted:
                raise BackendFailure() from None
            raise Refusal() from None
        finally:
            # Memory buffers remain strongly owned until the upstream settles or
            # successful recovery proves it was stopped. No unlink of native paths.
            if validated is not None:
                validated.images.clear()
                validated.native.clear()
            if uploads is not None:
                uploads.clear()

    async def run(self, request, operation, reply):
        self.submitted = False
        self.deadline = asyncio.get_running_loop().time() + self.budget
        self.work = asyncio.create_task(self.execute(request, operation))
        needs_recovery = False
        try:
            done, _ = await asyncio.wait({self.work}, timeout=self.budget)
            if not done:
                if self.submitted:
                    self.ready, self.phase = False, 'recovering'
                result = error(504, 'request_timeout')
                needs_recovery = self.submitted
            else:
                # Always inspect even a late completion: a failed HTTP transport
                # is not evidence that native work settled at the deadline tick.
                try:
                    result = self.work.result()
                except Refusal as exc:
                    result = error(exc.status, exc.code)
                except ClientDisconnect:
                    result = error(400, 'client_disconnected')
                except Exception:
                    self.ready, self.phase = False, 'recovering'
                    result, needs_recovery = error(502, 'backend_unavailable'), True
                if asyncio.get_running_loop().time() >= self.deadline:
                    result = error(504, 'request_timeout')
            if not reply.done():
                reply.set_result(result)
            if needs_recovery:
                # Recovery proves the exact old backend was destroyed before any
                # local transport cancellation can release memory/admission.
                recovered = await self.reconcile()
                if not recovered and not self.work.done():
                    # Still own the call and buffers even after recovery failure.
                    with suppress(Exception):
                        await asyncio.shield(self.work)
            if not self.work.done():
                # Either upload timed out before submission, or backend reset is
                # proven. Transport cancellation is never a GPU cancellation claim.
                self.work.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await self.work
        except asyncio.CancelledError:
            self.ready, self.phase = False, 'closed'
            # During forced shutdown preserve child ownership until process death;
            # next launcher must restart/reconcile backend before any admission.
            raise
        finally:
            if self.work.done():
                with suppress(asyncio.CancelledError, Exception):
                    self.work.result()
                self.work = None
                self.owner = None

    async def close(self):
        self.stopping, self.ready, self.phase = True, False, 'closed'
        if self.owner is not None:
            await asyncio.shield(self.owner)
        await self.backend.close()


class Protected:
    """Authenticate before parsing any input, including absent/unknown routes."""
    def __init__(self, app, key):
        self.app, self.key = app, key

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        auth = [value for name, value in scope['headers'] if name.lower() == b'authorization']
        good = False
        if len(auth) == 1:
            parts = auth[0].split(b' ')
            good = (len(parts) == 2 and parts[0].lower() == b'bearer'
                    and hmac.compare_digest(parts[1], self.key))
        if not good:
            response = error(401, 'unauthorized')
            response.headers['WWW-Authenticate'] = 'Bearer'
            return await response(scope, receive, send)
        if scope.get('query_string'):
            return await error(400, 'invalid_request')(scope, receive, send)
        await self.app(scope, receive, send)


def create_app(config, key, *, backend=None, recovery=recover, budget=REQUEST_BUDGET):
    owner = Owner(config, backend or NativeBackend(), recovery, budget)

    @asynccontextmanager
    async def lifespan(app):
        await owner.reconcile()
        try:
            yield
        finally:
            await owner.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None,
                  redirect_slashes=False)
    app.state.owner = owner
    app.add_middleware(Protected, key=key)

    @app.exception_handler(Exception)
    async def unknown_error(request, exc):
        return error(500, 'internal_error')

    @app.get('/health/live')
    async def live():
        return {'live': True}

    @app.get('/health/ready')
    async def ready():
        await owner.probe()
        status = owner.status()
        return JSONResponse(status, 200 if status['ready'] else 503)

    @app.get('/v1/models')
    async def models():
        return {'object': 'list', 'data': [{'id': ALIAS, 'object': 'model', 'owned_by': 'local'}]}

    @app.get('/v1/image-capabilities')
    async def capabilities():
        return {**owner.status(), 'model': ALIAS,
                **{key: config[key] for key in ('runtime_revision', 'runtime_image_digest',
                                               'model_id', 'model_revision')},
                'profiles': [{**{k: p[k] for k in ('operation', 'size', 'references', 'transparent',
                                                  'evidence_sha256')},
                              'native_size': profile_geometry(p)[0], 'crop_bottom': profile_geometry(p)[1],
                              **({'input_padding': {'top': 0, 'right': 0,
                                   'bottom': profile_geometry(p)[1], 'left': 0}}
                                 if p['operation'] == 'edit' else {})}
                             for p in config['profiles']],
                'limits': {'encoded_file_bytes': 33554432, 'encoded_total_bytes': 67108864,
                           'maximum_pixels_when_qualified': HARD_LIMITS['max_pixels'], 'references': 2,
                           **HARD_LIMITS,
                           'n': 1, 'active': 1, 'waiting': 0, 'budget_seconds': 900},
                'defaults': {'size': '1024x1024', 'steps': 40, 'cfg': 1, 'generator_device': 'cpu'},
                'masks': False, 'response_format': 'b64_json', 'output_format': 'png'}

    async def handle(request, operation):
        try:
            reply = owner.claim(request, operation)
        except Refusal as exc:
            return error(exc.status, exc.code)
        return await asyncio.shield(reply)

    @app.post('/v1/images/generations')
    async def generation(request: Request):
        return await handle(request, 'generation')

    @app.post('/v1/images/edits')
    async def edit(request: Request):
        return await handle(request, 'edit')

    return app
