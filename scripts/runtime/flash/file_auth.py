#!/usr/bin/env python3
"""Closed H008 launcher. Protected key stays out of argv/env/ServerArgs/logs."""
from pathlib import Path
import argparse
import hashlib
import hmac
import http.client
import json
import os
import stat
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tokenize_adapter import normalized_text_request, count_native, install_tokenize_route, MAX_BODY, MODEL

PORT = 30010
BOUNDS = {'max_input_tokens':479993, 'max_total_tokens':479998}

def verify_sources():
    pins = json.loads(Path(__file__).with_name('native-source-pins.json').read_text())
    import sglang
    root = Path(sglang.__file__).parent
    for relative, digest in pins.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError('flash_native_source_mismatch')


def run_scheduler(*args, **kwargs):
    verify_sources()
    from sglang.srt.managers import scheduler
    from idle import install
    install(scheduler)
    return scheduler.run_scheduler_process(*args, **kwargs)


class ContractMiddleware:
    def __init__(self, app, *, key, server, request_type):
        self.app, self.key, self.server, self.request_type = app, key, server, request_type
        self.active = False

    async def __call__(self, scope, receive, send):
        from starlette.responses import JSONResponse
        async def error(code, status):
            await JSONResponse({'error':{'code':code}}, status_code=status)(scope, receive, send)
        if scope['type'] == 'websocket':
            await send({'type':'websocket.close','code':1008}); return
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = [v for k,v in scope['headers'] if k.lower() == b'authorization']
        if len(headers) != 1 or not hmac.compare_digest(headers[0], b'Bearer ' + self.key):
            return await error('unauthorized', 401)
        path, method = scope['path'], scope['method']
        if (method,path) not in {('POST','/v1/chat/completions'),('POST','/v1/tokenize'),
                ('GET','/v1/models'),('GET','/v1/readiness'),('GET','/get_server_info')}:
            return await error('route_not_available', 404)
        if method != 'POST':
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect': return
            body.extend(event.get('body',b''))
            if len(body) > MAX_BODY: return await error('request_too_large',413)
            if not event.get('more_body'): break
        try:
            normalized = normalized_text_request(json.loads(body))
            # Same normalized request and exact native template for both routes.
            counted = count_native(normalized, request_type=self.request_type,
                                  serving_chat=self.server.app.state.openai_serving_chat)
            requested = normalized.get('max_completion_tokens', normalized.get('max_tokens', 65536 if path == '/v1/chat/completions' else 0))
            if counted['count'] > BOUNDS['max_input_tokens'] or counted['count'] + requested > BOUNDS['max_total_tokens']:
                return await error('native_context_boundary_exceeded',400)
            if path == '/v1/chat/completions' and not any(k in normalized for k in ('max_tokens','max_completion_tokens')):
                normalized['max_tokens'] = 65536
            raw = json.dumps(normalized, ensure_ascii=False).encode()
        except (ValueError, TypeError):
            return await error('invalid_text_request',400)
        if path == '/v1/chat/completions' and self.active:
            return await error('frontier_busy',429)
        chat = path == '/v1/chat/completions'
        if chat: self.active = True
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True
                return {'type':'http.request','body':raw,'more_body':False}
            return await receive()
        scope = dict(scope)
        scope['headers'] = [(k,v) for k,v in scope['headers'] if k.lower()!=b'content-length'] + [(b'content-length',str(len(raw)).encode())]
        try:
            await self.app(scope,replay,send)
        finally:
            if chat: self.active=False


def install_readiness(server):
    from fastapi.responses import JSONResponse
    async def readiness():
        manager = server.get_global_state().tokenizer_manager
        state = getattr(manager.server_status,'value',None)
        ready = manager.server_status == server.ServerStatus.Up and not manager.gracefully_exit
        state = 'up' if ready else ('starting' if manager.server_status == server.ServerStatus.Starting else 'unhealthy')
        return JSONResponse({'schema_version':1,'model_alias':MODEL,'ready':ready,
                             'state':state,'admitting':None},status_code=200 if ready else 503)
    server.app.add_api_route('/v1/readiness',readiness,methods=['GET'],include_in_schema=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.parse_args()
    verify_sources()
    fd=os.open('/run/secrets/llm-api-key',os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd);key=os.read(fd,4097)
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o600 or st.st_uid!=0 or not 1<=len(key)<=4096 or any(c<33 or c>126 for c in key):
            raise RuntimeError('invalid_key_file')
    finally: os.close(fd)
    from sglang.srt.server_args import ServerArgs
    from sglang.srt.entrypoints import http_server as server
    from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
    argv=['--model-path','/models','--served-model-name',MODEL,'--host','127.0.0.1','--port',str(PORT),
          '--tp-size','1','--context-length','480000','--max-total-tokens','480000',
          '--max-running-requests','1','--mem-fraction-static','0.65','--chunked-prefill-size','2048',
          '--kt-method','FP8','--kt-cpuinfer','64','--kt-threadpool-count','2','--kt-num-gpu-experts','0',
          '--kt-gpu-prefill-token-threshold','2048','--tool-call-parser','glm47','--reasoning-parser','glm45',
          '--cuda-graph-bs','1','2','4','--disable-overlap-schedule','--disable-radix-cache',
          '--log-level','warning']
    native_parser=argparse.ArgumentParser()
    ServerArgs.add_cli_args(native_parser)
    args=ServerArgs.from_cli_args(native_parser.parse_args(argv))
    assert args.context_length==args.max_total_tokens==480000 and args.api_key is None
    install_tokenize_route(server,ChatCompletionRequest)
    install_readiness(server)
    server.app.add_middleware(ContractMiddleware,key=key,server=server,request_type=ChatCompletionRequest)
    def warmup(server_args):
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            conn=http.client.HTTPConnection('127.0.0.1',PORT,timeout=300)
            try:
                conn.request('POST','/v1/chat/completions',json.dumps({'model':MODEL,'messages':[{'role':'user','content':'Hello'}],'max_tokens':1}),{'Authorization':'Bearer '+key.decode(),'Content-Type':'application/json'})
                response=conn.getresponse();response.read()
                if response.status==200:
                    server.get_global_state().tokenizer_manager.server_status=server.ServerStatus.Up
                    return True
                raise RuntimeError('flash_warmup_failed')
            except ConnectionRefusedError: time.sleep(.1)
            finally: conn.close()
        return False
    from sglang.srt.utils import kill_process_tree
    try:
        server.launch_server(args,run_scheduler_process_func=run_scheduler,execute_warmup_func=warmup)
    finally:
        kill_process_tree(os.getpid(), include_parent=False)

if __name__=='__main__': main()
