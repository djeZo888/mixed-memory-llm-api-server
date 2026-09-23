"""Fixed pinned native wire contract and no-argument recovery interface."""
import asyncio
import os
import signal

import httpx

from .protocol import BackendFailure, OUTPUT_LIMIT, Refusal, owned_thread, public_output, strict_json

BACKEND_URL = 'http://127.0.0.1:30007'
RECOVERY_HELPER = '/usr/local/libexec/llm-image-backend-recover'
RECOVERY_COMMAND = ('/usr/bin/sudo', '-n', '--', RECOVERY_HELPER)
RECOVERY_BUDGET = 900
HEALTH_BUDGET = 2
HEALTH_BODY_LIMIT = 1024


async def recover():
    """Root helper owns lock, guards, exact backend stop/restart/warm verification.

    A lost/timed-out helper is never success. No automatic second attempt.
    Suppress stdout/stderr, including sudo diagnostics and backend paths.
    """
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *RECOVERY_COMMAND, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}, start_new_session=True)
        return await asyncio.wait_for(process.wait(), RECOVERY_BUDGET) == 0
    except (OSError, TimeoutError):
        return False
    finally:
        if process is not None and process.returncode is None:
            # This stops only the adapter-owned sudo process group; it is not a
            # backend cancellation guarantee. Privileged helper must self-cap.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # Keep the process object owned; a privileged survivor cannot reopen
            # admission. systemd cgroup shutdown is the final service boundary.
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                pass


class NativeBackend:
    def __init__(self, *, transport=None):
        self.client = httpx.AsyncClient(base_url=BACKEND_URL, trust_env=False,
                                       follow_redirects=False, timeout=None,
                                       limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
                                       transport=transport)
        # Separate pool: a long image response must never occupy health capacity.
        self.health_client = httpx.AsyncClient(
            base_url=BACKEND_URL, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(connect=1, read=1, write=1, pool=.5),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2), transport=transport)

    async def health(self):
        """Pinned /health warm-readiness, one small request with a total budget."""
        try:
            async with asyncio.timeout(HEALTH_BUDGET):
                async with self.health_client.stream('GET', '/health') as response:
                    if (response.status_code != 200 or
                            response.headers.get('content-type', '').split(';')[0] != 'application/json'):
                        return False
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=HEALTH_BODY_LIMIT):
                        if len(raw) + len(chunk) > HEALTH_BODY_LIMIT:
                            return False
                        raw.extend(chunk)
                return strict_json(raw) == {'status': 'ok'}
        except (httpx.HTTPError, TimeoutError, Refusal, ValueError):
            return False

    async def call(self, request):
        if request.images:
            route = '/v1/images/edits'
            arguments = {'data': {key: str(value) for key, value in request.native.items()},
                         'files': [('image', (f'reference-{index}.png' if raw.startswith(b'\x89PNG') else f'reference-{index}.jpg',
                                             raw, 'image/png' if raw.startswith(b'\x89PNG') else 'image/jpeg'))
                                   for index, raw in enumerate(request.images)]}
        else:
            route, arguments = '/v1/images/generations', {'json': request.native}
        try:
            async with self.client.stream('POST', route, **arguments) as response:
                if response.status_code != 200:
                    raise BackendFailure()
                result = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(result) + len(chunk) > OUTPUT_LIMIT:
                        raise BackendFailure()
                    result.extend(chunk)
            return await owned_thread(public_output, result, request)
        except (httpx.HTTPError, ValueError):
            raise BackendFailure() from None

    async def close(self):
        await self.client.aclose()
        await self.health_client.aclose()
