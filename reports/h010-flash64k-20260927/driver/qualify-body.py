# H010 bounded task qualifier; prepend pinned vm-common.py and FIXTURE_SOURCE.
# Adapted narrowly from H009. No model lifecycle mutation or automatic retry.
import http.client, threading, re, socket, signal, copy
LOG = '/data/logs/flash-h008-20260926'
GPU = 'GPU-69acfa26-8b60-61b5-702d-aee252c163cc'
NAME = 'llm-frontier-flash'
MODEL = 'glm-5.3-flash'
REVISION = 'eb9eb208eb0d988989d07a6a12d0fdeb5f52574a'
GLOBAL_END = datetime.datetime(2026,9,27,0,58,tzinfo=datetime.timezone.utc).timestamp()
PREFIX = 'H010-FLASH64K'
assert not P(LOG, PREFIX+'.json').exists(), 'existing_receipt_no_retry'
MODE = 'preparing'
REQUEST_CAP = 1200
result = {'status':'PREPARING', 'start_utc':now(), 'hardstop_utc':'2026-09-27T00:58:00Z',
 'lane_owner':'Worker1 H010 exclusive Flash request lane', 'automatic_retry':False,
 'model_stop_performed':False, 'active_request':None, 'requests':{},
 'script_sha256':hashlib.sha256(P(__file__).read_bytes()).hexdigest(),
 'fixture_source_sha256':hashlib.sha256(FIXTURE_SOURCE.encode()).hexdigest(),
 'cancellation_is_not_proof_of_native_drain':True}
stop_event = threading.Event()
active_connection = active_response = cancel_reason = None
samples = []
raw_batches = {}
raw_cursors = {}
raw_bytes = 0
persist_lock = threading.Lock()
key = P('/data/services/secrets/llm-api-key').read_text().strip()

def buffer(record, suffix):
    # Hot reader: bounded memory append only. No filesystem, locks, guard or fsync.
    global raw_bytes
    size = len(json.dumps(record, separators=(',',':')))
    raw_bytes += size
    if raw_bytes > 128*1024*1024:
        raise RuntimeError('stream_capture_byte_bound')
    rows = raw_batches.setdefault(MODE+suffix, [])
    if len(rows) >= 8192:
        raise RuntimeError('stream_capture_event_bound')
    rows.append(record)

def persist():
    # Called at boundaries and from the separate sampler; never from SSE loop.
    with persist_lock:
        snapshot = copy.deepcopy(result)
        snapshot['checkpoint_utc'] = now()
        snapshot['telemetry_samples'] = len(samples)
        if samples:
            snapshot['latest_telemetry'] = samples[-1]
        pending = {name:(len(rows),rows[raw_cursors.get(name,0):]) for name,rows in list(raw_batches.items())}
        with transaction() as (lease, guard):
            s.root_payload_guard()
            with AnchoredRoot(LOG,guard) as anchor:
                for name,(end,rows) in pending.items():
                    if not rows: continue
                    with anchor.open(PREFIX+'-'+name, os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600) as f:
                        f.write((''.join(json.dumps(x,separators=(',',':'))+'\n' for x in rows)).encode())
                        f.fsync()
                    raw_cursors[name]=end
            status(LOG+'/'+PREFIX+'.json',snapshot,guard)
            s.root_payload_guard()

def run(argv, timeout=15):
    return subprocess.check_output(argv, text=True, timeout=timeout, stderr=subprocess.PIPE)

def remaining():
    return GLOBAL_END - time.time()

def cancel(reason):
    global cancel_reason
    cancel_reason = cancel_reason or reason
    result['cancel_reason'] = cancel_reason
    result['cancel_utc'] = now()
    stop_event.set()
    # HTTPConnection may relinquish its socket to HTTPResponse on Connection:close.
    sock = getattr(active_connection, 'sock', None)
    if sock is None and active_response is not None:
        sock = getattr(getattr(getattr(active_response, 'fp', None), 'raw', None), '_sock', None)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

def terminated(signum, frame):
    cancel('signal_' + str(signum))
    raise InterruptedError('qualification_signal')

def call(path, payload=None, timeout=15):
    assert remaining() > timeout + 2, 'global_deadline_before_control_call'
    connection = http.client.HTTPConnection('127.0.0.1', 30010, timeout=timeout)
    try:
        connection.request('POST' if payload is not None else 'GET', path,
                           json.dumps(payload) if payload is not None else None,
                           {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = response.read(8 * 1024 * 1024)
        return response.status, json.loads(data)
    finally:
        connection.close()

def proc_fields(path):
    return dict(line.split(':', 1) for line in path.read_text().splitlines() if ':' in line)

def sample():
    observed = {'utc': now(), 'monotonic': time.monotonic()}
    row = run(['nvidia-smi', '--id=' + GPU,
               '--query-gpu=uuid,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu',
               '--format=csv,noheader,nounits'], 5).strip().split(',')
    observed['gpu'] = dict(zip(['uuid', 'total_mib', 'used_mib', 'free_mib', 'temp_c', 'util_pct'],
                               [v.strip() for v in row]))
    assert observed['gpu']['uuid'] == GPU
    observed['ram'] = {line.split(':')[0]: int(line.split()[1]) * 1024
                       for line in P('/proc/meminfo').read_text().splitlines()
                       if line.split(':')[0] in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}}
    counters = {line.split()[0]: int(line.split()[1])
                for line in P('/proc/vmstat').read_text().splitlines()
                if line.split()[0] in {'pswpin', 'pswpout'}}
    assert set(counters) == {'pswpin', 'pswpout'}, 'required_swap_io_telemetry_missing'
    occupied = observed['ram']['SwapTotal'] - observed['ram']['SwapFree']
    previous = samples[-1] if samples else None
    baseline = samples[0] if samples else None
    observed['host_swap'] = {'occupied_bytes': occupied,
        'baseline_occupied_bytes': baseline['host_swap']['occupied_bytes'] if baseline else occupied,
        'vmstat_pages': counters, 'page_bytes': os.sysconf('SC_PAGE_SIZE'),
        'interval_seconds': observed['monotonic'] - previous['monotonic'] if previous else None,
        'interval_pages': {key: counters[key] - previous['host_swap']['vmstat_pages'][key]
                           if previous else 0 for key in counters},
        'since_baseline_pages': {key: counters[key] - baseline['host_swap']['vmstat_pages'][key]
                                 if baseline else 0 for key in counters}}
    assert min(observed['host_swap']['interval_pages'].values()) >= 0, 'swap_io_counter_reset'
    root = cgroup_root
    observed['cgroup'] = {name: int((root / name).read_text())
                          for name in ('memory.current', 'memory.peak', 'memory.swap.current')}
    for name in ('memory.events', 'memory.stat', 'cpu.stat'):
        observed[name] = {line.split()[0]: int(line.split()[1])
                          for line in (root / name).read_text().splitlines()}
    observed['memory.numa_stat'] = (root / 'memory.numa_stat').read_text()
    observed['cpuset'] = {name: (root / name).read_text().strip()
                          for name in ('cpuset.cpus.effective', 'cpuset.mems.effective')}
    observed['process_memory'] = []
    observed['expert_threads'] = []
    for pid in (root / 'cgroup.procs').read_text().split():
        proc = P('/proc', pid)
        try:
            fields = proc_fields(proc / 'status')
            observed['process_memory'].append({
                'pid': int(pid), 'name': fields.get('Name', '').strip(),
                'rss_bytes': int(fields.get('VmRSS', '0 kB').split()[0]) * 1024,
                'anon_bytes': int(fields.get('RssAnon', '0 kB').split()[0]) * 1024,
                'file_bytes': int(fields.get('RssFile', '0 kB').split()[0]) * 1024,
                'swap_bytes': int(fields.get('VmSwap', '0 kB').split()[0]) * 1024})
            for task in (proc / 'task').glob('*'):
                try:
                    name = (task / 'comm').read_text().strip()
                    if not name.startswith('numa_'):
                        continue
                    fields = proc_fields(task / 'status')
                    raw = (task / 'stat').read_text()
                    fields_stat = raw[raw.rfind(')') + 2:].split()
                    observed['expert_threads'].append({
                        'pid': int(pid), 'tid': int(task.name), 'name': name,
                        'state': fields_stat[0], 'utime_ticks': int(fields_stat[11]),
                        'stime_ticks': int(fields_stat[12]), 'last_processor': int(fields_stat[36]),
                        'cpus_allowed_list': fields['Cpus_allowed_list'].strip(),
                        'mems_allowed_list': fields['Mems_allowed_list'].strip()})
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
    assert observed['process_memory'], 'container_process_telemetry_empty'
    observed['expert_ticks_hz'] = os.sysconf('SC_CLK_TCK')
    temperatures = []
    for sensor in P('/sys/class/hwmon').glob('hwmon*'):
        try:
            if (sensor / 'name').read_text().strip() in {'coretemp', 'k10temp', 'cpu_thermal'}:
                temperatures += [{'sensor': str(path), 'millidegrees_c': int(path.read_text())}
                                 for path in sensor.glob('temp*_input')]
        except (OSError, ValueError):
            pass
    observed['cpu_temperatures'] = temperatures or 'NOT_AVAILABLE'
    observed['mode'] = MODE
    observed['request_phase'] = (result.get('request') or {}).get('phase')
    observed['last_native_usage'] = (result.get('request') or {}).get('usage')
    return observed

def resource_reason(observed):
    gpu = observed['gpu']
    if float(gpu['temp_c']) >= thermal_limit:
        return 'gpu_thermal_cutoff'
    if any(x['millidegrees_c'] >= 85000 for x in observed['cpu_temperatures']
           if isinstance(x, dict)):
        return 'cpu_thermal_cutoff_85C'
    if float(gpu['free_mib']) < float(gpu['total_mib']) * .07:
        return 'gpu_free_reserve_below_7pct'
    if observed['ram']['MemAvailable'] < observed['ram']['MemTotal'] * .15:
        return 'host_available_reserve_below_15pct'
    if any(observed['memory.events'].get(k, 0) > baseline_events.get(k, 0)
           for k in ('oom', 'oom_kill')):
        return 'new_cgroup_oom'
    # Host occupancy can be old pages from unrelated processes: it is evidence,
    # not current swap activity. Three samples must span at least four seconds.
    sustained = len(samples) >= 3 and samples[-1]['monotonic'] - samples[-3]['monotonic'] >= 9
    if observed['cgroup']['memory.swap.current'] > 0:
        return 'owned_cgroup_swap'
    if sustained and len(samples) >= 4 and all(
            sum(x['host_swap']['interval_pages'].values()) > 0 for x in samples[-3:]):
        return 'sustained_host_swap_io_three_intervals'
    return None

def request_payload(content, output=64):
    return {'model': MODEL, 'messages': [{'role': 'user', 'content': content}],
            'max_tokens': output, 'temperature': 0, 'reasoning_effort': 'high',
            'chat_template_kwargs': {'clear_thinking': True}}

def stream(payload):
    global active_connection, active_response
    cap = min(REQUEST_CAP, remaining() - 8)
    assert cap >= 15, 'insufficient_request_budget'
    row = {'status': 'RUNNING', 'phase': 'awaiting_headers', 'start_utc': now(),
           'requested_output': payload['max_tokens'], 'actual_cap_seconds': cap,
           'request_deadline_utc': datetime.datetime.fromtimestamp(time.time()+cap, datetime.timezone.utc).isoformat(),
           'first_nonempty_delta_seconds': None, 'first_positive_native_usage_seconds': None,
           'last_nonempty_delta_seconds': None, 'usage': None, 'output': '', 'reasoning': '',
           'tool_deltas': [], 'finish_reason': None, 'sse_done': False, 'body_drained': False,
           'nonempty_delta_count': 0, 'native_usage_samples': [],
           'ttft_basis': 'request start to first nonempty native content, reasoning, or tool delta; transport included',
           'native_phase_observation_limit': 'no inference of compile or prefill phase from silence alone'}
    result['request'] = row
    result['active_request'] = MODE
    result['status'] = 'REQUEST_RUNNING'
    wire_body = json.dumps({**payload, 'stream': True,
        'stream_options': {'include_usage': True, 'continuous_usage_stats': True}})
    row['wire_payload_sha256'] = hashlib.sha256(wire_body.encode()).hexdigest()
    persist()
    cap = min(REQUEST_CAP, remaining() - 8)
    assert cap >= 15, 'insufficient_request_budget_after_boundary_write'
    row['actual_cap_seconds'] = cap
    row['request_deadline_utc'] = datetime.datetime.fromtimestamp(time.time()+cap, datetime.timezone.utc).isoformat()
    row['start_utc'] = now()
    connection = http.client.HTTPConnection('127.0.0.1', 30010, timeout=cap)
    active_connection = connection
    started = time.monotonic()
    timer = threading.Timer(cap, lambda: cancel('whole_request_cap'))
    timer.daemon = True
    failure = None
    try:
        timer.start()
        connection.request('POST', '/v1/chat/completions', wire_body,
                           {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        active_response = response
        row['http_status'] = response.status
        row['phase'] = 'awaiting_first_nonempty_delta'
        if response.status != 200:
            row['http_error_body'] = response.read(8192).decode(errors='replace')
            raise RuntimeError('native_http_' + str(response.status))
        while True:
            if cancel_reason:
                raise RuntimeError(cancel_reason)
            raw = response.readline(1024 * 1024)
            elapsed = time.monotonic() - started
            if not raw:
                row['body_drained'] = True
                break
            receipt = {'utc': now(), 'seconds': elapsed, 'line': raw.decode(errors='replace')}
            # Buffer exact bytes-as-text before parsing; separate writer batches durability.
            buffer(receipt, '-SSE.jsonl')
            if not raw.startswith(b'data:'):
                continue
            data = raw[5:].strip()
            if data == b'[DONE]':
                row['sse_done'] = True
                row['phase'] = 'draining_http_body'
                tail = response.read(8 * 1024 * 1024)
                if tail:
                    buffer({'utc': now(), 'seconds': time.monotonic() - started,
                             'post_done_bytes': tail.decode(errors='replace')}, '-SSE.jsonl')
                assert len(tail) < 8 * 1024 * 1024, 'post_done_body_bound_no_eof_proof'
                row['body_drained'] = True
                break
            value = json.loads(data)
            usage = value.get('usage')
            if usage:
                row['usage'] = usage
                row['native_usage_samples'].append({'seconds': elapsed, 'usage': usage})
                if usage.get('completion_tokens', 0) > 0 and row['first_positive_native_usage_seconds'] is None:
                    row['first_positive_native_usage_seconds'] = elapsed
            nonempty = False
            for choice in value.get('choices', []):
                if choice.get('finish_reason') is not None:
                    row['finish_reason'] = choice['finish_reason']
                delta = choice.get('delta', {})
                content = delta.get('content') or ''
                reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
                tools = delta.get('tool_calls') or []
                if content or reasoning or tools:
                    nonempty = True
                row['output'] += content
                row['reasoning'] += reasoning
                row['tool_deltas'] += tools
            if nonempty:
                row['nonempty_delta_count'] += 1
                if row['first_nonempty_delta_seconds'] is None:
                    row['first_nonempty_delta_seconds'] = elapsed
                    row['first_native_delta_client_utc'] = receipt['utc']
                row['last_nonempty_delta_seconds'] = elapsed
                row['last_native_delta_client_utc'] = receipt['utc']
                row['phase'] = 'receiving_native_deltas'
            buffer({'utc': now(), 'seconds': elapsed, 'usage': usage,
                     'nonempty_delta': nonempty, 'finish_reason': row['finish_reason']}, '-PROGRESS.jsonl')
        if cancel_reason:
            raise RuntimeError(cancel_reason)
        assert row['usage'], 'missing_native_usage'
        assert row['finish_reason'] is not None and row['sse_done'], 'native_stream_incomplete'
        row['status'] = 'TRANSPORT_PASS'
    except BaseException as exc:
        failure = exc
        row.update(status='CLIENT_CANCELLED' if cancel_reason else 'PARTIAL_OR_FAIL',
                   error_type=type(exc).__name__, error_code=cancel_reason or (
                       str(exc) if isinstance(exc, (RuntimeError, AssertionError)) else 'request_exception'),
                   failure_origin='qualifier_cancellation' if cancel_reason else 'request_or_transport',
                   cancellation_is_native_failure_evidence=False if cancel_reason else None)
    finally:
        timer.cancel()
        connection.close()
        if active_response is not None:
            active_response.close()
        active_response = None
        active_connection = None
        row.update(end_utc=now(), elapsed_seconds=time.monotonic() - started,
                   request_socket_closed=True, settle_seconds=0)
        row['phase'] = 'client_closed'
        result['active_request'] = None
        usage = row['usage'] or {}
        row['input_tokens'] = usage.get('prompt_tokens')
        row['output_tokens'] = usage.get('completion_tokens')
        row['cached_input_tokens'] = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
        first = row['first_nonempty_delta_seconds']
        row['ttft_seconds'] = first
        row['effective_input_tokens_per_second_ttft_basis'] = (row['input_tokens'] / first
            if row['input_tokens'] is not None and first else None)
        observations = [(v['seconds'], v['usage'].get('completion_tokens'))
                        for v in row['native_usage_samples'] if v['usage'].get('completion_tokens', 0) > 0]
        increasing = []
        for elapsed, tokens in observations:
            if not increasing or tokens > increasing[-1][1]:
                increasing.append((elapsed, tokens))
        row['decode_tokens_per_second'] = None
        row['decode_rate_status'] = 'INVALID_BUFFERED_OR_INSUFFICIENT_NATIVE_USAGE'
        if len(increasing) >= 3 and increasing[-1][0] - increasing[0][0] >= 1:
            a, b = increasing[0], increasing[-1]
            row['decode_rate_window'] = {'start_seconds': a[0], 'end_seconds': b[0],
                                        'start_native_tokens': a[1], 'end_native_tokens': b[1]}
            row['decode_tokens_per_second'] = (b[1] - a[1]) / (b[0] - a[0])
            row['decode_rate_status'] = 'NATIVE_INCREMENTAL_USAGE_OBSERVED_CLIENT_TIME_WINDOW'
        row['output_cap_reached'] = row['finish_reason'] == 'length'
        persist()
    if failure:
        raise failure
    return row

def sampling():
    failures = 0
    last_log = result['start_utc']
    while not stop_event.is_set():
        started = time.monotonic()
        try:
            if remaining() <= 0:
                cancel('global_deadline'); break
            observed = sample()
            samples.append(observed)
            assert len(samples) <= 1600, 'telemetry_sample_bound'
            buffer(observed, '-TELEMETRY.jsonl')
            result['latest_sample_utc'] = observed['utc']
            failure = resource_reason(observed)
            if failure:
                result['resource_failure'] = observed
                cancel(failure)
            log_end = now()
            native = subprocess.run(['docker','logs','--timestamps','--since',last_log,'--until',log_end,'--tail','150',NAME],capture_output=True,text=True,timeout=5)
            assert native.returncode == 0, 'native_log_capture_failed'
            logs = native.stdout + native.stderr
            last_log = log_end
            if logs:
                buffer({'utc':log_end,'text':logs}, '-NATIVE.jsonl')
            failures = 0
        except Exception as exc:
            failures += 1
            result['telemetry_error'] = {'utc':now(),'type':type(exc).__name__,'consecutive':failures}
            if failures >= 3:
                cancel('required_resource_telemetry_lost'); break
        stop_event.wait(max(.05,5-(time.monotonic()-started)))


def periodic_writer():
    failures = 0
    while not stop_event.wait(15):
        try:
            persist(); failures = 0
        except Exception as exc:
            failures += 1
            result['persistence_error'] = {'utc':now(),'type':type(exc).__name__,'consecutive':failures}
            if failures >= 3:
                cancel('durable_checkpoint_failed'); break


def fixture(target, seed, output):
    built = json.loads(run(['docker','exec',NAME,'/opt/conda/bin/python','-I','-B','-c',FIXTURE_SOURCE,
                            '--target',str(target),'--seed',seed],120))
    payload = request_payload(built.pop('content'), output)
    assert built.pop('payload') == payload, 'fixture_payload_mismatch'
    code, count = call('/v1/tokenize',payload,timeout=30)
    assert code == 200 and count == {'count':target,'tokenizer_revision':REVISION,
        'template_revision':REVISION,'context_limit':480000}, 'native_fixture_parity_failure'
    built.update(native_tokenize=count, payload_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                 fixture_source_sha256=result['fixture_source_sha256'])
    result.setdefault('fixtures',{})[MODE] = built
    buffer({'payload':payload,'fixture':built}, '-FIXTURE.jsonl')
    persist()
    return payload


def qualify(row, target):
    assert row['input_tokens'] == target, 'native_usage_input_count_mismatch'
    assert row['cached_input_tokens'] in (0,None), 'benchmark_input_cached'
    expected = result['fixtures'][MODE]['expected_result']
    text = row['output'].strip()
    try:
        answer = json.loads(text.removeprefix('```json').removeprefix('```').removesuffix('```').strip())
    except ValueError:
        answer = None
    row['expected_result'] = expected
    row['semantic_status'] = ('UNPROVEN_OUTPUT_CAP' if row['finish_reason']=='length' else
        'PASS' if answer == expected else 'FAIL_COMPLETED_ANSWER')
    row['output_cap_includes_reasoning'] = True
    row['native_reasoning_usage_caveat'] = 'Preserve native detail; reasoning deltas are not a separate native token count.'


def boundary_identity():
    with MountedStorageGuard(s) as guard:
        for p,h in EXPECTED_IDENTITIES.items():
            assert hashlib.sha256(P(p).read_bytes()).hexdigest()==h, 'source_identity_changed:'+p
        s.root_payload_guard()
        for path in [LOG,'/data/models-large/glm-5.3-flash-eb9eb208']:
            guard.check_path(path)
    assert P('/proc/sys/kernel/random/boot_id').read_text().strip() == '1c706f0b-7243-41a0-aea3-c447ef51664f'
    code, info = call('/get_server_info', timeout=10)
    assert code == 200
    native = lambda k: next((i[k] for i in [info,*info.get('internal_states',[])] if k in i),None)
    capacity = {k:native(k) for k in ['context_length','max_total_tokens','max_total_num_tokens','max_req_len',
      'max_req_input_len','max_running_requests','kv_cache_dtype','kt_cpuinfer','kt_threadpool_count',
      'kt_numa_nodes','disable_radix_cache','chunked_prefill_size','kt_gpu_prefill_token_threshold']}
    for k,v in {'context_length':480000,'max_total_tokens':480000,'max_total_num_tokens':480000,
      'max_running_requests':1,'kv_cache_dtype':'fp8_e4m3','kt_cpuinfer':64,'kt_threadpool_count':8,
      'kt_numa_nodes':list(range(8)),'disable_radix_cache':True}.items():
        assert capacity[k]==v, 'native_setting_changed:'+k
    result['native_capacity']=capacity
    return capacity


def main():
    global cgroup_root, thermal_limit, baseline_events, MODE, REQUEST_CAP
    sampler = writer = None
    try:
        assert remaining() > 1500, 'insufficient_global_budget_before_warm'
        boundary_identity()
        container=json.loads(run(['docker','inspect',NAME]))[0]
        assert container['State']['Running']
        assert container['Image']=='sha256:51791e17c0149019e2ddc032d8c1b2f60b86c3a6c293daff639e20053baa858a'
        result['container']={k:container[k] for k in ['Id','Image']}
        result['container']['started_at']=container['State']['StartedAt']
        root_pid=container['State']['Pid']
        cg=P('/proc',str(root_pid),'cgroup').read_text().split('::')[1].strip()
        cgroup_root=P('/sys/fs/cgroup'+cg)
        assert int((cgroup_root/'memory.max').read_text()) == 650*1024**3
        assert int((cgroup_root/'memory.swap.max').read_text()) == 0
        report=run(['nvidia-smi','--id='+GPU,'-q','-d','TEMPERATURE'])
        match=re.search(r'GPU Slowdown Temp\s*:\s*(\d+)',report)
        thermal_limit=min(85,int(match.group(1))) if match else 85
        result['thermal_limit_c']=thermal_limit
        result['baseline']=sample(); baseline_events=result['baseline']['memory.events']
        samples.append(result['baseline'])
        assert not resource_reason(result['baseline']), 'baseline_resource_guard'
        threads=result['baseline']['expert_threads']
        assert len(threads)==64 and {x['cpus_allowed_list'] for x in threads}=={str(x) for x in [*range(8),*range(16,72)]}
        result['readiness']=call('/v1/readiness',timeout=5)
        assert result['readiness'][0]==200 and result['readiness'][1]['ready']
        assert not run(['ss','-H','-nt4','state','established','( sport = :30010 or dport = :30010 )'],5).strip(), 'observed_established_connection_before_start'
        persist()
        sampler=threading.Thread(target=sampling,daemon=True);sampler.start()
        writer=threading.Thread(target=periodic_writer,daemon=True);writer.start()
        for mode,target,seed,output,cap in [('warm8192',8192,'H010-warm-cobalt-20260927',128,1200),
                                            ('measured65536',65536,'H010-measure-cedar-20260927',256,4200)]:
            MODE=mode; REQUEST_CAP=cap
            assert not cancel_reason, 'previous_resource_cancel'
            assert remaining() > (600 if target==65536 else 300), 'too_late_for_new_request'
            boundary_identity()
            result['status']='PREPARING_'+MODE
            payload=fixture(target,seed,output)
            row=stream(payload)
            qualify(row,target)
            result['requests'][MODE]=row
            result['after_'+MODE]=sample()
            boundary_identity()
            persist()
            # No retry; only transport-complete warm can precede one main request.
            assert row['status']=='TRANSPORT_PASS', 'previous_request_not_settled'
        result['status']='COMPLETE'
    except BaseException as exc:
        result['status']='CLIENT_CANCELLED' if cancel_reason else 'PARTIAL_OR_FAIL'
        result['error_type']=type(exc).__name__
        result['error_code']=cancel_reason or (str(exc) if isinstance(exc,(AssertionError,RuntimeError)) else 'task_exception')
        if result.get('request'):
            result['requests'][MODE]=result['request']
    finally:
        stop_event.set()
        if sampler: sampler.join(12)
        if writer: writer.join(95)
        result['end_utc']=now()
        result['sample_count']=len(samples)
        result['native_active_counter']='NOT_AVAILABLE; socket/job observations do not prove atomic drain'
        try:
            result['established_tcp30010_after_close']=run(['ss','-H','-nt4','state','established','( sport = :30010 or dport = :30010 )'],5)
            fresh=json.loads(run(['docker','inspect',NAME]))[0]
            result['container_warm_preserved']=fresh['State']['Running'] and fresh['Id']==result.get('container',{}).get('Id')
            if remaining()>12:result['readiness_after']=call('/v1/readiness',timeout=5)
            result['final_sample']=sample()
            persist()
        except Exception as exc:
            result['final_error_type']=type(exc).__name__
            persist()
        print(json.dumps({'status':result['status'],'receipt':LOG+'/'+PREFIX+'.json','error':result.get('error_code')}))

if __name__=='__main__':
    signal.signal(signal.SIGTERM,terminated)
    signal.signal(signal.SIGINT,terminated)
    main()
