"""Finite task controller adapted from H013. Pure state/journal, no live dispatch.

W1's future reviewed owner adapter must call these boundaries in order. The
controller never interprets manifest strings as commands or releases uncertain work.
"""
import copy
import hashlib
import threading
import uuid
from contract import LANES, TEXT, Refusal, digest, require, utc_seconds, validate_body, validate_count, validate_go
from primitives import Journal, interval_report
from telemetry import validate_sample

class Phase:
    def __init__(self, manifest, go, phase, package_sha256, journal_path, clock, *, storage_guard=None, anchored_root=None):
        self.clock = clock
        now = clock()
        validate_go(go, manifest, phase, package_sha256, now['utc'])
        self.m, self.go = copy.deepcopy(manifest), copy.deepcopy(go)
        self.phase = phase
        self.lanes = LANES
        self.start = now['monotonic']
        self.admission_deadline = self.start+utc_seconds(go['admission_deadline_utc'])-utc_seconds(now['utc'])
        self.settlement_deadline = self.start+utc_seconds(go['settlement_deadline_utc'])-utc_seconds(now['utc'])
        self.lock = threading.RLock()
        self.journal = Journal(journal_path, {'phase': phase, 'manifest_sha256': digest(manifest),
                            'go_sha256': digest(go), 'package_sha256': package_sha256, 'started': now,
                            'admission_deadline_monotonic': self.admission_deadline,
                            'settlement_deadline_monotonic': self.settlement_deadline, 'no_replay': True},
                            storage_guard=storage_guard, anchored_root=anchored_root)
        self.claims, self.active, self.requests = {}, {}, {l: [] for l in self.lanes}
        self.prefixes = set()
        self.barrier = None
        self.first_failure = None
        self.admission_closed = False
        self.stop_intents = {}
        self.escalations = []
        self.latest_sample = None
        self.baseline = None
        self.guest_swap_streak = 0
        self.http_intervals = {l: [] for l in self.lanes}
        self.gpu_intervals = {l: [] for l in self.lanes}
        self.gpu_evidence = []
        self.sample_count = 0
        self.journal_errors = []
        self.summary = {'samples':0,'all_four_utilization_nonzero_samples':0,'gpu':{},'guest':{},'cgroups':{},'fan':{},'kernel_event_count':0}

    def save(self):
        # Full receipts remain in exact request files and bounded append history.
        # Current status must not grow with request count or telemetry duration.
        counts = {lane: {state: sum(r['state'] == state for r in rows)
                         for state in ('OWNED_BEFORE_COUNT', 'COUNTED', 'POSSIBLY_SUBMITTED',
                                       'HTTP_COMPLETE', 'UNKNOWN_OWNED', 'SETTLED', 'FAILED_SETTLED')}
                  for lane, rows in self.requests.items()}
        self.journal.write('STATUS', {'phase': self.phase, 'updated': self.clock(), 'barrier': self.barrier,
            'first_failure': self.first_failure, 'admission_closed': self.admission_closed,
            'active': {l: {k:r[k] for k in ('request_id','state','owned','send_started','body_sent') if k in r}
                       for l,r in self.active.items()}, 'request_counts': counts,
            'monitor': {'samples': self.sample_count, 'last_sample_utc': self.latest_sample.get('utc') if self.latest_sample else None},
            'stop_intents': self.stop_intents, 'escalations': self.escalations,
            'journal_errors': self.journal_errors,'telemetry_summary':self.summary})

    def persistence_error(self, operation, exc):
        self.admission_closed = True
        if self.first_failure is None:
            self.first_failure = {'reason': 'persistence_failed:'+operation, 'lane': None, 'observed': self.clock()}
        if len(self.journal_errors) < 8:
            self.journal_errors.append({'operation': operation, 'kind': type(exc).__name__})

    def fail(self, reason, lane=None, stop_exact=False):
        # Close in memory before any potentially failing persistence. The original
        # error survives even complete journal/mount loss; stop dispatch is separate.
        with self.lock:
            self.admission_closed = True
            if self.first_failure is None:
                self.first_failure = {'reason': reason, 'lane': lane, 'observed': self.clock()}
            if lane in self.active:
                self.active[lane].setdefault('first_failure', {'reason': reason, 'observed': self.clock()})
            targets = ([lane] if stop_exact and lane in self.claims else
                       [l for l,r in self.active.items() if r['state'] in
                        ('POSSIBLY_SUBMITTED','HTTP_COMPLETE','UNKNOWN_OWNED')] if lane is None else [])
            for target in targets:
                if target in self.stop_intents:
                    continue
                intent = {'lane': target, 'owner_id': self.claims[target]['owner_id'],
                          'request_id': self.active.get(target, {}).get('request_id'),
                          'identity': self.m['lanes'][target]['identity'], 'boot_id': self.m['boot_id'],
                          'gpu_uuid': self.m['lanes'][target]['gpu_uuid'], 'reason': reason, 'observed': self.clock(),
                          'status': 'EXACT_OWNER_STOP_REQUIRED_NOT_DISPATCHED'}
                self.stop_intents[target] = intent
                try: self.journal.write('STOP-'+target, intent, exclusive=True)
                except Exception as exc: self.persistence_error('STOP-'+target, exc)
            if not stop_exact and len(self.escalations) < 8:
                event = {'reason': reason, 'lane': lane, 'root_scope_review_required': True}
                if event not in self.escalations: self.escalations.append(event)
            try: self.save()
            except Exception as exc: self.persistence_error('STATUS', exc)

    def fresh(self, proof, after=None):
        now = self.clock()
        observed = proof['observed']
        age = now['monotonic']-observed['monotonic']
        wall_age = utc_seconds(now['utc'])-utc_seconds(observed['utc'])
        require(0 <= age <= self.m['guard']['max_sample_delay_seconds'] and
                0 <= wall_age <= self.m['guard']['max_sample_delay_seconds'], 'stale/future owner proof')
        if after is not None:
            require(observed['monotonic'] >= after, 'native proof predates HTTP EOF')

    def owner_proof(self, lane, proof, idle=True, after=None):
        require(proof.get('lane') == lane and proof.get('boot_id') == self.m['boot_id'] and
                proof.get('deployment_sha256') == digest(self.m), 'owner deployment drift')
        require(proof.get('gpu_uuid') == self.m['lanes'][lane]['gpu_uuid'] and
                proof.get('identity') == self.m['lanes'][lane]['identity'], 'owner native identity drift')
        require(proof.get('authenticated') is True and proof.get('guard_ok') is True and
                proof.get('evidence_ref') and proof.get('owner_id'), 'authenticated owner proof missing')
        require(proof.get('global_admission_receipt') == self.go['global_admission_receipt'], 'global ownership drift')
        self.fresh(proof, after)
        if lane in self.claims:
            require(proof['owner_id'] == self.claims[lane]['owner_id'], 'task owner changed')
        if idle:
            if lane in TEXT:
                require(proof.get('request_disposition') in ('EXCLUSIVE_QUIET_PREFLIGHT','REQUEST_SETTLED'), 'source-qualified Qwen request disposition required')
            else:
                require(proof.get('native_idle') is True, 'native physical idle required')
            if lane == 'image':
                require(proof.get('owned_job_idle') is True and proof.get('spool_ready') is True, 'image job/spool not settled')

    def observe(self, sample):
        with self.lock:
            diagnostics, faults = validate_sample(self.m, sample, self.clock()['monotonic'], self.baseline,
                                                 self.latest_sample, self.guest_swap_streak)
            self.sample_count += 1
            self.journal.append('TELEMETRY', {'sample': sample, 'diagnostics': diagnostics, 'faults': faults})
            if diagnostics is not None:
                self.guest_swap_streak = diagnostics['guest_swap_consecutive_intervals']
                if self.baseline is None:
                    self.baseline = copy.deepcopy(sample)
                self.latest_sample = copy.deepcopy(sample)
                self.accumulate(sample,diagnostics)
            for fault in faults:
                self.fail(fault['reason'], fault['lane'], fault['stop_exact'])
            return diagnostics, faults

    def accumulate(self,s,d):
        def bounds(target,key,value):
            if type(value) not in (int,float):return
            row=target.setdefault(key,{'min':value,'max':value})
            row['min']=min(row['min'],value);row['max']=max(row['max'],value)
        out=self.summary;out['samples']+=1
        out['last_utc']=s['utc'];out.setdefault('first_utc',s['utc'])
        if all(s['gpu'][self.m['lanes'][l]['gpu_uuid']]['utilization_pct']>0 for l in self.lanes):
            out['all_four_utilization_nonzero_samples']+=1
        for uuid,g in s['gpu'].items():
            dst=out['gpu'].setdefault(uuid,{})
            for k in ('temperature_c','utilization_pct','power_draw_w','memory_used_mib','memory_free_mib'):bounds(dst,k,g[k])
        for k in ('three_blackwell_draw_w','ada_draw_w','guest_cpu_busy_fraction'):bounds(out,k,d[k])
        for k in ('ram_available_bytes','swap_in','swap_out'):bounds(out['guest'],k,s['guest'][k])
        for resource,raw in s['guest'].get('psi',{}).items():
            for line in raw.splitlines():
                parts=line.split()
                for token in parts[1:]:
                    key,value=token.split('=',1)
                    bounds(out['guest'],'psi_'+resource+'_'+parts[0]+'_'+key,float(value))
        for l,cg in s['cgroups'].items():
            dst=out['cgroups'].setdefault(l,{})
            for k in ('memory_current','swap_current'):bounds(dst,k,cg[k])
            for k,v in cg['events'].items():bounds(dst,'event_'+k,v)
        f=s['external_fan']['controller']
        for k in ('desired_duty','readback_duty','actual_tach','telemetry_age_seconds'):bounds(out['fan'],k,f[k])
        out['kernel_event_count']+=len(s['kernel']['events'])

    def monitoring_tick(self):
        """Call at ~1 Hz through drain, including after STOP admission. Never kill clients."""
        with self.lock:
            now = self.clock()
            if self.latest_sample is None or now['monotonic']-self.latest_sample['end_monotonic'] > self.m['guard']['max_sample_delay_seconds']:
                self.fail('telemetry_loss')
            for lane, row in list(self.active.items()):
                if row['state'] in ('POSSIBLY_SUBMITTED', 'HTTP_COMPLETE'):
                    started = row.get('send_started', row['owned'])['monotonic']
                    if now['monotonic'] >= started+self.m['bounds']['request_seconds'] and row['state'] != 'HTTP_COMPLETE':
                        self.fail('request_deadline_native_work_unknown', lane, True)
            if now['monotonic'] >= self.admission_deadline or utc_seconds(now['utc']) >= utc_seconds(self.go['admission_deadline_utc']):
                self.admission_closed = True
            if now['monotonic'] >= self.settlement_deadline-60 and self.active:
                self.fail('settlement_stop_reserve_reached')
            if now['monotonic'] >= self.settlement_deadline or utc_seconds(now['utc']) >= utc_seconds(self.go['settlement_deadline_utc']):
                if self.active:
                    self.fail('settlement_deadline_unknown_remains_owned')
                self.admission_closed = True
            self.save()

    def admission(self, lane):
        self.monitoring_tick()
        require(lane in self.lanes and not self.admission_closed and self.first_failure is None, 'new admission stopped')
        require(lane not in self.active, 'one in-flight request per lane')
        require(self.settlement_deadline-self.clock()['monotonic'] >= self.m['bounds']['request_seconds']+60,
                'insufficient full request and native settlement reserve')
        cap = self.m['bounds']['max_requests_per_lane']
        require(len(self.requests[lane]) < cap, 'finite serial lane request cap')
    def release_barrier(self, receipts):
        with self.lock:
            require(self.barrier is None and set(receipts) == set(self.lanes), 'all actual phase owner preflights required')
            try:
                self.monitoring_tick()
                require(not self.admission_closed, 'barrier after admission closed')
                for lane, receipt in receipts.items():
                    self.owner_proof(lane, receipt)
                    require(receipt.get('ready') is True, 'native ready preflight required')
                require(self.admission_deadline-self.clock()['monotonic'] >= 300,'full300s admission no longer fits absolute GO cap')
                self.claims = copy.deepcopy(receipts)
                self.journal.write('BARRIER', {'owners': receipts, 'observed': self.clock()}, exclusive=True)
                self.barrier = self.clock()
                self.admission_deadline = self.barrier['monotonic']+300
                self.save()
            except Exception:
                self.fail('barrier_or_owner_preflight_failed')
                raise

    def prepare(self, lane, body, prefix, owner_receipt):
        with self.lock:
            self.admission(lane)
            require(self.barrier is not None, 'owned preflight barrier required')
            try:
                self.owner_proof(lane, owner_receipt)
                require(prefix not in self.prefixes, 'fresh leading prefix required')
                raw = validate_body(self.m, lane, body, prefix)
                row = {'request_id': self.m['task_id']+'-'+lane+'-'+uuid.uuid4().hex, 'lane': lane,
                       'owner_id': owner_receipt['owner_id'], 'body_sha256': hashlib.sha256(raw).hexdigest(),
                       'body_bytes': len(raw), 'count_body_sha256': digest({k:v for k,v in body.items() if k not in ('stream','stream_options')}) if lane.startswith('qwen') else hashlib.sha256(raw).hexdigest(), 'prefix_sha256': hashlib.sha256(prefix.encode()).hexdigest(),
                       'owned': self.clock(), 'state': 'OWNED_BEFORE_COUNT', 'max_tokens': body.get('max_tokens'),
                       'identity': copy.deepcopy(self.m['lanes'][lane]['identity']), 'automatic_retry': False}
                self.journal.write(row['request_id'], row, exclusive=True)
                self.active[lane] = row
                self.requests[lane].append(row)
                self.prefixes.add(prefix)
                self.save()
                return copy.deepcopy(row), raw
            except Exception:
                self.fail('prepare_or_persistence_failed', lane)
                raise

    def counted(self, lane, result):
        with self.lock:
            row = self.active[lane]
            require(row['state'] == 'OWNED_BEFORE_COUNT', 'count state/replay refused')
            try:
                require(lane in TEXT, 'image does not have token count')
                require(result.get('owner_id') == row['owner_id'] and result.get('identity') == row['identity'], 'count owner identity')
                self.fresh(result, row['owned']['monotonic'])
                require(result.get('count_body_sha256') == row['count_body_sha256'], 'normalized count body hash mismatch')
                count = validate_count(self.m, lane, row['body_sha256'], result)
                row.update(native_count=copy.deepcopy(result), input_tokens=count, state='COUNTED')
                self.journal.write(row['request_id'], row)
                self.save()
            except Exception:
                self.fail('native_count_or_accounting_failed', lane)
                raise

    def begin_send(self, lane, raw, owner_receipt):
        """Durable possible-submission before owner sends exact bytes ONCE.

        Future adapter must atomically recheck stop/deadline immediately at send;
        returned intent is not a replayable permit. This core performs no I/O.
        """
        with self.lock:
            self.monitoring_tick()
            require(not self.admission_closed and self.first_failure is None, 'new admission stopped')
            row = self.active[lane]
            try:
                self.owner_proof(lane, owner_receipt)
                require(row['state'] == ('COUNTED' if lane in TEXT else 'OWNED_BEFORE_COUNT'), 'one send only')
                require(hashlib.sha256(raw).hexdigest() == row['body_sha256'], 'counted canonical bytes changed')
                row.update(state='POSSIBLY_SUBMITTED', send_started=self.clock())
                self.journal.write(row['request_id'], row)
                self.save()
                return copy.deepcopy(row)
            except Exception:
                self.fail('send_boundary_failed_no_replay', lane)
                raise

    def body_sent(self, lane):
        with self.lock:
            row = self.active[lane]
            require(row['state'] == 'POSSIBLY_SUBMITTED' and 'body_sent' not in row, 'send state/replay')
            row['body_sent'] = self.clock()
            self.journal.write(row['request_id'], row)
            return copy.deepcopy(row)

    def http_finished(self, lane, capture):
        with self.lock:
            row = self.active[lane]
            try:
                require(row['state'] == 'POSSIBLY_SUBMITTED' and capture['request_id'] == row['request_id']
                        and capture['body_sha256'] == row['body_sha256'], 'HTTP owned request mismatch')
                require(capture.get('response_complete') is True and capture.get('http_drained') is True
                        and capture.get('http_status') == 200, 'full HTTP response required')
                require(capture['body_sent'] == row['body_sent'], 'body timestamp drift')
                times = [capture[k]['monotonic'] for k in ('body_sent', 'first_output', 'last_output', 'eof')]
                require(times == sorted(times) and times[-1] <= self.clock()['monotonic'], 'response timestamp ordering')
                if lane in TEXT:
                    u = capture.get('usage', {})
                    require(capture.get('done') is True and capture.get('finish_reason') in ('stop', 'length') and
                            u.get('prompt_tokens') == row['input_tokens'] and
                            type(u.get('completion_tokens')) is int and 0 < u['completion_tokens'] <= row['max_tokens'] and
                            u.get('total_tokens') == u['prompt_tokens']+u['completion_tokens'], 'finish/DONE/native usage required')
                    require(capture['done_at']['monotonic'] <= times[-1], 'DONE after EOF')
                else:
                    require(capture.get('image', {}).get('decoded') is True and
                            (capture['image']['width'], capture['image']['height']) == (1920, 1080), 'full image decode required')
                row.update(copy.deepcopy(capture))
                row['state'] = 'HTTP_COMPLETE'
                self.http_intervals[lane].append([times[0], times[-1]])
                self.journal.write(row['request_id'], row)
                self.save()
            except Exception:
                self.fail('HTTP_incomplete_or_accounting_failed', lane, True)
                raise

    def ambiguous(self, lane, reason, capture=None):
        with self.lock:
            row = self.active[lane]
            if capture:
                row['partial_capture'] = copy.deepcopy(capture)
            row['state'] = 'UNKNOWN_OWNED'
            self.fail(reason, lane, True)
            try: self.journal.write(row['request_id'], row)
            except Exception as exc: self.persistence_error('ambiguous_request',exc)

    def settled(self, lane, proof):
        with self.lock:
            row = self.active[lane]
            try:
                self.owner_proof(lane, proof, after=row.get('eof', row['owned'])['monotonic'])
                require(proof.get('request_id') == row['request_id'] and proof.get('ownership_released') is True,
                        'exact request release required')
                disposition = proof.get('disposition')
                if disposition == 'COMPLETED':
                    require(proof.get('resident') is True, 'healthy model must remain resident')
                elif disposition == 'STOPPED':
                    require(lane in self.stop_intents and proof.get('resident') is False, 'only exact failed lane may stop')
                elif disposition == 'NOT_SUBMITTED':
                    require(row['state'] in ('OWNED_BEFORE_COUNT', 'COUNTED') and proof.get('resident') is True, 'possible native work cannot be not submitted')
                else:
                    raise Refusal('unproven disposition')
                if lane == 'image':
                    require(proof.get('job_released') is True and proof.get('spool_cleanup') in ('APPROVED_OWNED_CLEANUP','OWNED_SPOOL_UNCHANGED')
                            and proof.get('cleanup_receipt') and proof.get('native_owner_run_id'), 'approved owned image cleanup/release required')
                clean = row['state'] == 'HTTP_COMPLETE' and not row.get('first_failure') and disposition == 'COMPLETED'
                row.update(state='SETTLED' if clean else 'FAILED_SETTLED', settlement=copy.deepcopy(proof))
                self.journal.write(row['request_id'], row)
                self.journal.append('REQUESTS', row)
                del self.active[lane]
                if not clean:
                    self.fail('request_did_not_complete_cleanly', lane)
                self.save()
            except Exception:
                self.fail('native_settlement_unproven', lane)
                raise

    def physical_stopped(self, lane, proof):
        with self.lock:
            require(lane in self.stop_intents and proof.get('intent') == self.stop_intents[lane]
                    and proof.get('physical_stop_proven') is True, 'exact owner physical stop receipt required')
            try: self.journal.write('PHYSICAL-STOP-'+lane, proof, exclusive=True)
            except Exception as exc: self.persistence_error('PHYSICAL-STOP-'+lane, exc)
            self.stop_intents[lane]['status']='PHYSICALLY_SETTLED'
            if lane in self.active:
                row=self.active.pop(lane)
                row.update(state='FAILED_SETTLED',settlement=proof)
                try:
                    self.journal.write(row['request_id'],row)
                    self.journal.append('REQUESTS',row)
                except Exception as exc: self.persistence_error('stopped_request',exc)
            try: self.save()
            except Exception as exc: self.persistence_error('STATUS',exc)

    def report(self):
        with self.lock:
            now = self.clock()
            stop = now['monotonic']
            start = self.barrier['monotonic'] if self.barrier else self.start
            http = interval_report(self.http_intervals, start, stop)
            admission_http = interval_report(self.http_intervals, start, min(stop, self.admission_deadline))
            closed = self.admission_closed or stop >= self.admission_deadline
            measured_seconds = max(0, min(stop,self.admission_deadline)-start)
            fourway_seconds = admission_http['intersection_seconds']
            completed = closed and not self.first_failure and not self.active and all(
                self.requests[l] and all(r['state'] == 'SETTLED' for r in self.requests[l]) for l in self.lanes)
            campaign_complete = completed and measured_seconds >= 300
            status = 'COMPLETED_300S_CAMPAIGN' if campaign_complete else 'INCOMPLETE_OR_FAILED'
            return {'status': status, 'phase': self.phase, 'first_failure': self.first_failure,
                    'measured_window_seconds':measured_seconds,'fourway_http_seconds':fourway_seconds,
                    'all_lanes_completed':completed,'campaign_complete':campaign_complete,
                    'fourway_http_fraction':fourway_seconds/300,
                    'fourway_qualification':'ROOT_REVIEW_REQUIRED_SUBSTANTIAL_OVERLAP_NO_NUMERIC_THRESHOLD_AUTHORIZED',
                    'telemetry_summary':self.summary,
                    'sampled_fourway_activity_basis':'all four utilization_pct>0 in same sample; not exact native processing or full load',
                    'unknown_or_owned': {l:r['request_id'] for l,r in self.active.items()},
                    'HTTP_active_including_drain': http, 'HTTP_active_admission_window': admission_http,
                    'measured_GPU_processing_overlap': {'status': 'NOT_AVAILABLE', 'reason': 'No source-qualified native processing interval collector installed'},
                    'interval_basis': 'body sent to HTTP EOF; includes native queue/warming; excludes unproven open ends',
                    'five_minutes_full_load_claimed': False, 'barrier_is_overlap_evidence': False,
                    'external_fan_baseline': self.m['external_fan'], 'latest_external_fan_readback':
                    self.latest_sample.get('external_fan') if self.latest_sample else None,
                    'stop_intents': self.stop_intents, 'escalations': self.escalations}
