"""One staged native POST, stdlib only. Codec uses the existing host adapter venv."""
import base64, hashlib, importlib.util, json, os, time, urllib.error, urllib.request
from pathlib import Path

def main():
    here = Path(__file__).resolve().parent
    job = json.loads((here / 'prepared.json').read_text())
    spec = importlib.util.spec_from_file_location('native_owned_io', '/runtime/native_request.py')
    owned = importlib.util.module_from_spec(spec); spec.loader.exec_module(owned)
    parent = owned.open_run_directory(job['run_id'])
    child = os.open(here.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    def write(name, raw):
        owned.write_exclusive(child, name, raw); os.fsync(child)
    metrics = {'dispatch_started': False, 'http_status': None, 'response_complete': False, 'pid': os.getpid()}
    try:
        boundary = 'H003CapacityFixedMultipartBoundary'
        body = bytearray()
        for key, value in job['native'].items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        for i, digest in enumerate(job['working_sha256']):
            raw = (here / f'input-{i + 1}.png').read_bytes()
            assert hashlib.sha256(raw).hexdigest() == digest
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="reference-{i}.png"\r\nContent-Type: image/png\r\n\r\n'.encode())
            body.extend(raw); body.extend(b'\r\n')
        body.extend(f'--{boundary}--\r\n'.encode())
        write('dispatch-intent.json', json.dumps({'pid': os.getpid(), 'seed': job['native']['seed'], 'utc_epoch': time.time()}).encode())
        metrics['dispatch_started'] = True
        started = time.monotonic()
        request = urllib.request.Request('http://127.0.0.1:30007/v1/images/edits', data=bytes(body),
            headers={'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            response = opener.open(request, timeout=800)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            metrics['http_status'] = response.status
            raw = response.read(48 * 1024 * 1024 + 1)
        assert len(raw) <= 48 * 1024 * 1024
        write('native-response.json', raw)  # Before adapter validation can fail.
        metrics.update(response_complete=True, elapsed_seconds=time.monotonic() - started)
        if response.status != 200: raise RuntimeError('native_http_rejection')
        png = base64.b64decode(json.loads(raw)['data'][0]['b64_json'], validate=True)
        write('raw-native.png', png)
        metrics['raw_sha256'] = hashlib.sha256(png).hexdigest()
    except BaseException as error:
        metrics['error_type'] = type(error).__name__
        raise
    finally:
        try: write('probe-result.json', json.dumps(metrics, indent=2).encode())
        finally: os.close(child); os.close(parent)

if __name__ == '__main__': main()
