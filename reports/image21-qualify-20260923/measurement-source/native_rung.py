#!/usr/bin/env python3
"""Task-local, root-launched single generation measurement; never a service/API.

Run using /data/services/image-api/venv/bin/python -I -B. Caller must have the
explicit returned Worker1 window, stop API, review each image before continuing,
and deploy only root-reviewed PASS receipts. This helper never publishes profiles,
stops/starts a service, retries, recovers, edits, or executes a second image call.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

TASK = 'IMAGE21-QUALIFY-20260923'
SOURCE_COMMIT = 'f188e6de8d151a7e571c7e3b5ecb59ef63d32bb7'
COMBINED_BASE_COMMIT = '43ed79f3905c769f449f48300c7087d7a432f989'
BASE = Path('/data/services/image21-runtime-20260923')
PROTOCOL = Path('/usr/local/lib/llm-server/image-api/scripts/image_api/protocol.py')
PINS = {
    'service.py': '0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586',
    'native_request.py': '91180c1613de1fa113426dba2c534a8c31b851f066a252c1dcfd08fa8012bf6f',
    'telemetry.py': 'a6d5f9262de82a318c7aa86dfef599fa6228463bb712c94d916c653afba2f0e9',
    'protocol.py': 'ebca2b024d236d03475dde15a63414c49fb86714733afa1bbf8ca68d88fd5238',
}
# Frozen once, round previous dimensions *1.2 to nearest32, cap at exact UHD.
SIZES = [(1024,576),(1216,704),(1472,832),(1760,992),(2112,1184),
         (2528,1408),(3040,1696),(3648,2048),(3840,2160)]
CAMPAIGN_REL = 'receipts/' + TASK
MIB = 1024**2


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def pinned_module(name, path):
    # Check every ancestor and the exact reviewed source before evaluating it.
    for ancestor in [path, *path.parents]:
        info = ancestor.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'unprotected_source')
    require(sha(path.read_bytes()) == PINS[path.name], 'source_hash_mismatch')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def api_stopped(service):
    value = service.run(['systemctl','show','llm-image-api.service',
                         '-p','ActiveState','-p','MainPID','-p','SubState']).stdout
    fields = dict(line.split('=',1) for line in value.splitlines())
    require(fields.get('ActiveState') == 'inactive' and fields.get('MainPID') == '0',
            'api_not_cleanly_stopped')
    return fields


def image_info(raw, Image):
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        return {'width':image.width,'height':image.height,'format':image.format,
                'mode':image.mode,'bytes':len(raw),'sha256':sha(raw),'fully_decoded':True}


def telemetry_metrics(path, start, end):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    samples = [r for r in rows if r.get('event') == 'sample']
    require(rows and rows[-1]['event'] == 'stop' and samples, 'incomplete_telemetry')
    valid = [r for r in samples if r.get('device',{}).get('memory_bytes',{}).get('code') == 0]
    require(len(valid) == len(samples), 'incomplete_device_samples')
    during = [r for r in valid if start <= r['monotonic_s'] <= end]
    require(during, 'no_request_window_samples')
    values = [r['device']['memory_bytes']['value'] for r in valid]
    totals = {v['total'] for v in values}
    require(len(totals) == 1, 'physical_device_total_changed')
    total = totals.pop()
    hosts = [r['host'] for r in samples if 'host' in r]
    mem = [h['meminfo_bytes']['value']['values'] for h in hosts
           if h.get('meminfo_bytes',{}).get('status') == 'ok']
    vm = [h['vmstat_counters']['value']['values'] for h in hosts
          if h.get('vmstat_counters',{}).get('status') == 'ok']
    cg = {name:[h['cgroup_bytes'][name]['value'] for h in hosts
                if h.get('cgroup_bytes',{}).get(name,{}).get('status') == 'ok']
          for name in ('memory.current','memory.peak','memory.swap.current')}
    require(mem and vm and all(cg.values()), 'incomplete_host_cgroup_samples')
    delta = {k:vm[-1][k]-vm[0][k] for k in ('pswpin','pswpout','oom_kill','pgmajfault')}
    return {
        'device':{'total_bytes':total,'sampled_peak_used_bytes':max(v['used'] for v in values),
                  'sampled_min_free_bytes':min(v['free'] for v in values),
                  'minimum_free_fraction':min(v['free']/v['total'] for v in values),
                  'request_window_peak_used_bytes':max(r['device']['memory_bytes']['value']['used'] for r in during),
                  'first_sample_used_bytes':values[0]['used'],'last_sample_used_bytes':values[-1]['used']},
        'sampling':{'requested_interval_seconds':0.2,'sample_count':len(samples),
                    'max_observed_interval_seconds':rows[-1]['max_sample_interval_s'],
                    'skipped_schedule_slots':rows[-1]['skipped_schedule_slots']},
        'host':{'min_available_bytes':min(v['MemAvailable'] for v in mem),
                'min_available_fraction':min(v['MemAvailable']/v['MemTotal'] for v in mem),
                'max_swap_used_bytes':max(v['SwapTotal']-v['SwapFree'] for v in mem),
                'vmstat_counter_deltas':delta},
        'cgroup':{name:{'min':min(values),'max':max(values),'sample_count':len(values)}
                  for name,values in cg.items()},
        'limitations':['Device peaks between200ms observations may be missed.',
                      'Cgroup memory.peak is a lifetime high-water mark; never reset here.',
                      'No PSS polling; NVML device totals are not allocator/process peaks.',
                      'NVML PCIe20ms counters and utilization remain in raw telemetry.']}


def observed_case(summary):
    device = summary['metrics']['device']
    resident = device['first_sample_used_bytes']
    peak = device['sampled_peak_used_bytes']
    return {'case_id':summary['case_id'],
            'native_pixels':summary['native_width']*summary['native_height'],
            'resident_bytes':resident,'peak_bytes':peak,
            'transient_bytes':max(0,peak-resident),'total_bytes':device['total_bytes']}


def accepted_observations():
    """Baseline acceptance/returned ownership is an external caller precondition."""
    path = BASE/CAMPAIGN_REL/'worker2-baseline-segment2/window-result.json'
    baseline = json.loads(path.read_text())
    require(baseline['sampler_exit'] == 0 and not baseline['tmp_new_entries'],
            'worker2_baseline_telemetry_not_complete')
    metrics = baseline['sampling_metrics_entire_window']
    require(metrics['device']['minimum_free_fraction'] >= .05 and
            metrics['host']['min_available_fraction'] >= .15 and
            metrics['cgroup']['memory.swap.current']['max'] == 0,
            'worker2_baseline_headroom_failure')
    observations = [observed_case({'case_id':'worker2-api-1024x1024',
                    'native_width':1024,'native_height':1024,'metrics':metrics})]
    observations[0]['evidence_sha256'] = sha(path.read_bytes())
    observations[0]['scope'] = 'Shared exclusive Worker2 window; total-window measured peak'
    for rung,(width,height) in enumerate(SIZES,1):
        path = BASE/CAMPAIGN_REL/f'r{rung:02d}-{width}x{height}'/'receipt.json'
        if path.exists():
            value = json.loads(path.read_text())
            require(value.get('numeric_criteria_pass') is True,'observed_rung_failed_no_continuation')
            entry = observed_case(value)
            entry['evidence_sha256'] = sha(path.read_bytes())
            observations.append(entry)
    return observations


def forecast(observations, next_size):
    if next_size is None:
        return {'decision':'END_OF_FROZEN_LADDER'}
    nw,nh = next_size
    if next_size == (3840,2160):
        nh = 2176
    pixels = nw*nh
    rows = sorted(observations,key=lambda value:value['native_pixels'])
    require(rows and len({r['native_pixels'] for r in rows}) == len(rows),
            'forecast_observation_pixels_missing_or_duplicate')
    totals = {r['total_bytes'] for r in rows}
    require(len(totals) == 1,'forecast_device_total_mismatch')
    total = totals.pop()
    resident = max(r['resident_bytes'] for r in rows)
    adjacent = []
    for lower,upper in zip(rows,rows[1:]):
        adjacent.append({'lower_case':lower['case_id'],'upper_case':upper['case_id'],
            'midpoint_pixels':(lower['native_pixels']+upper['native_pixels'])/2,
            'bytes_per_pixel':(upper['transient_bytes']-lower['transient_bytes'])/
                              (upper['native_pixels']-lower['native_pixels'])})
    # A baseline-only estimate is explicitly linear in actual native area.
    # With observations, anchor at the largest measured area <= candidate.
    lower = [r for r in rows if r['native_pixels'] <= pixels]
    anchor = lower[-1] if lower else rows[0]
    per_pixel = anchor['transient_bytes']/anchor['native_pixels']
    measured_slope = max([0,per_pixel]+[r['bytes_per_pixel'] for r in adjacent])
    trend = {'demonstrated':False,'projected_next_interval_bytes_per_pixel':None}
    if len(adjacent) >= 2 and pixels > rows[-1]['native_pixels']:
        previous,last = adjacent[-2:]
        # Only extend an observed positive rise between the last two secants.
        # Midpoint extrapolation adds no invented power/exponent or extra margin.
        if previous['bytes_per_pixel'] > 0 and last['bytes_per_pixel'] > previous['bytes_per_pixel']:
            target_midpoint = (rows[-1]['native_pixels']+pixels)/2
            increase = (last['bytes_per_pixel']-previous['bytes_per_pixel'])/(
                        last['midpoint_pixels']-previous['midpoint_pixels'])
            projected = last['bytes_per_pixel']+increase*(target_midpoint-last['midpoint_pixels'])
            trend = {'demonstrated':True,'previous_adjacent_slope':previous['bytes_per_pixel'],
                     'latest_adjacent_slope':last['bytes_per_pixel'],
                     'projected_next_interval_bytes_per_pixel':projected,
                     'method':'Linear continuation of observed positive secant-slope rise by interval midpoint'}
            measured_slope = max(measured_slope,projected)
    if pixels < anchor['native_pixels']:
        transient = per_pixel*pixels
        basis = 'First estimate: accepted1024 observed transient times native pixel ratio'
    else:
        transient = anchor['transient_bytes'] + measured_slope*(pixels-anchor['native_pixels'])
        basis = 'Measured anchor transient plus pixel increment times max(anchor transient/pixel, observed adjacent slope, demonstrated recent rising slope)'
    demand = math.ceil(resident + transient + 256*MIB)
    ceiling = math.floor(total*.95)
    return {'next_public_size':f'{next_size[0]}x{next_size[1]}',
            'next_native_size':f'{nw}x{nh}','native_pixels':pixels,
            'basis':basis,'observations_pixel_sorted':rows,'adjacent_transient_slopes':adjacent,
            'anchor_case':anchor['case_id'],'anchor_transient_per_pixel':per_pixel,
            'selected_growth_bytes_per_pixel':measured_slope,'recent_nonlinear_trend':trend,
            'resident_bytes':resident,'predicted_transient_bytes':math.ceil(transient),
            'allocation_allowance_bytes':256*MIB,'policy':'ROOT-FORECAST-AMENDMENT.md',
            'predicted_device_used_bytes':demand,'maximum_allowed_used_bytes':ceiling,
            'decision':'ADMIT_FOR_REVIEW' if demand <= ceiling else 'STOP_UNSAFE_FORECAST',
            'limitation':'Observed200ms peaks can miss transients; unseen kernel/allocation thresholds remain uncertain. Forecast is not measured support.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--rung',type=int,choices=range(1,len(SIZES)+1))
    selection.add_argument('--refinement',action='store_true',
                           help='Root-authorized final1920x1088 once; then stop all qualification')
    parser.add_argument('--session-id',required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f-]{36}',args.session_id), 'invalid_session_id')
    require(os.geteuid() == 0, 'root_required')
    service = pinned_module('image21_service',BASE/'source/service.py')
    native = pinned_module('image21_native_request',BASE/'source/native_request.py')
    protocol = pinned_module('image21_protocol',PROTOCOL)
    require(sha((BASE/'source/telemetry.py').read_bytes()) == PINS['telemetry.py'], 'telemetry_hash_mismatch')
    from PIL import Image
    os.environ['TMPDIR'] = str(BASE/'tmp')
    runtime = service.Runtime()
    # The canonical mutation lease lasts for this one request only. No child in
    # this helper calls lifecycle code or requires the lease; no systemd child.
    with service.acquire_lease(blocking=False):
        runtime.guards()
        api_state = api_stopped(service)
        state = runtime.state()
        require(state['phase'] == 'warm' and state['warm'], 'backend_not_warm')
        before = runtime.verify_resident(state)
        cid = state['container']['id']
        refinement_case = 'refinement-1920x1088'
        require(not (BASE/CAMPAIGN_REL/refinement_case).exists(),
                'authorized_refinement_recorded_stop_all_qualification')
        rung = 'additional_bounded_refinement' if args.refinement else args.rung
        width,height = (1920,1088) if args.refinement else SIZES[rung-1]
        native_height = 2176 if (width,height) == (3840,2160) else height
        case = refinement_case if args.refinement else f'r{rung:02d}-{width}x{height}'
        relative = CAMPAIGN_REL+'/'+case
        target = BASE/relative
        require(not target.exists(), 'case_already_attempted_no_repeat')
        observations = accepted_observations()
        if args.refinement:
            expected = {'worker2-api-1024x1024'} | {
                f'r{i:02d}-{w}x{h}' for i,(w,h) in enumerate(SIZES[:4],1)}
            require({r['case_id'] for r in observations} == expected,
                    'refinement_requires_exactly_first_four_passing_rungs')
            for i,(w,h) in enumerate(SIZES[4:],5):
                require(not (BASE/CAMPAIGN_REL/f'r{i:02d}-{w}x{h}').exists(),
                        'refinement_requires_no_later_ladder_attempt')
        admission = forecast(observations,(width,height))
        if not args.refinement:
            require(admission['decision'] == 'ADMIT_FOR_REVIEW','forecast_requires_stop')
        if not args.refinement and rung > 1:
            pw,ph = SIZES[rung-2]
            prior = json.loads((BASE/CAMPAIGN_REL/f'r{rung-1:02d}-{pw}x{ph}'/'receipt.json').read_text())
            require(prior.get('numeric_criteria_pass') is True, 'previous_rung_failed_or_incomplete')
        perf_name = f'{TASK}-{case}-perf.json'
        perf_path = BASE/'work/evidence'/state['run_id']/perf_name
        require(not perf_path.exists(), 'native_perf_already_exists_no_repeat')
        settings = native.payload('generation',state['run_id'])
        settings.update(size=f'{width}x{native_height}',background='opaque',
                        perf_dump_path=f'/work/evidence/{state["run_id"]}/{perf_name}')
        receipt = {'schema_version':1,'campaign_id':TASK,'case_id':case,'rung':rung,
                   'session_id':args.session_id,'source_commit':SOURCE_COMMIT,
                   'combined_base_commit':COMBINED_BASE_COMMIT,'admission_forecast':admission,
                   'operation':'generation','references':0,'status':'PARTIAL','profile_eligible':False,
                   'visual_verification':{'status':'NOT_TESTED','required':'Caller/root visual task review'},
                   'public_width':width,'public_height':height,'native_width':width,
                   'native_height':native_height,'crop_bottom':native_height-height,
                   'source_sha256':PINS,'runtime_config_sha256':sha((BASE/'config.json').read_bytes()),
                   'runtime_image_digest':runtime.config['image_id'],
                   'runtime_source_commit':runtime.config['source_commit'],
                   'checkpoint_revision':runtime.config['checkpoint_revision'],
                   'checkpoint_receipt_sha256':runtime.config['checkpoint_receipt_sha256'],
                   'container_id':cid,'backend_run_id':state['run_id'],'gpu_uuid':service.GPU_UUID,
                   'api_state':api_state,'residency_before':before,'request_settings':settings,
                   'caller':'Worker1 sole accepted caller; API stopped; native loopback',
                   'request_count':0,'started_utc':native.utc_now(),'started_monotonic':time.monotonic(),
                   'recovery':{'attempted':False,'required_on_ambiguous_or_failed_native_outcome':True},
                   'load_average_before':os.getloadavg(),'evidence_sha256':{}}
        if args.refinement:
            receipt['plan'] = {'type':'additional_bounded_refinement_beyond_frozen_ladder',
                               'authorization':'ROOT-FINAL-REFINEMENT.md',
                               'frozen_ladder_unchanged':True,'planned_r05_not_attempted':True,
                               'limit':'One1920x1088 if same forecast<=95%; stop all after any outcome'}
        sampler = None
        sent = ended = time.monotonic()
        with runtime.anchor() as anchor:
            runtime.guards()
            anchor.mkdir(CAMPAIGN_REL)
            anchor.mkdir(relative)
            def save(name, raw):
                anchor.check()
                with anchor.open(relative+'/'+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL) as out:
                    out.write(raw); out.fsync()
                receipt['evidence_sha256'][name] = sha(raw)
            if args.refinement and admission['decision'] != 'ADMIT_FOR_REVIEW':
                receipt.update(status='NOT_TESTED',numeric_criteria_pass=False,
                    stop_reason='refinement_same_forecast_exceeds95_percent',
                    finished_utc=native.utc_now(),finished_monotonic=time.monotonic(),
                    predicted_next_demand={'decision':'END_OF_AUTHORIZED_REFINEMENT'})
                receipt['recovery']['required_on_ambiguous_or_failed_native_outcome'] = False
                save('receipt.json',encoded(receipt))
                save('receipt.sha256',(receipt['evidence_sha256']['receipt.json']+'  receipt.json\n').encode())
                runtime.guards()
                print(json.dumps({'case_id':case,'status':'NOT_TESTED','request_count':0,
                    'receipt':str(target/'receipt.json'),'receipt_sha256':receipt['evidence_sha256']['receipt.json'],
                    'admission_forecast':admission,'predicted_next_demand':receipt['predicted_next_demand']}))
                return 0
            save('request.json',encoded(settings))
            tmp_before = runtime.tmp_snapshot(state['run_id'])
            receipt['tmp_before'] = tmp_before
            try:
                with anchor.open(relative+'/telemetry.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as telemetry:
                    sampler = subprocess.Popen(['/usr/bin/python3','-I','-B',str(BASE/'source/telemetry.py'),
                      '--output-fd',str(telemetry.fileno()),'--output-path',str(target/'telemetry.jsonl'),
                      '--cgroup','/sys/fs/cgroup/system.slice/docker-'+cid+'.scope'],
                      pass_fds=(telemetry.fileno(),),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    try:
                        time.sleep(1.1)
                        require(sampler.poll() is None,'sampler_failed_before_request')
                        runtime.guards()
                        api_stopped(service)
                        connection = http.client.HTTPConnection('127.0.0.1',30007,timeout=840)
                        sent = time.monotonic()
                        receipt['request_started_monotonic'] = sent
                        receipt['request_started_utc'] = native.utc_now()
                        try:
                            with native.request_deadline():
                                receipt['request_count'] = 1
                                connection.request('POST','/v1/images/generations',body=encoded(settings),
                                                   headers={'Content-Type':'application/json','Accept':'application/json'})
                                response = connection.getresponse()
                                receipt['http_status'] = response.status
                                raw = response.read(native.MAX_RESPONSE_BYTES+1)
                                require(len(raw) <= native.MAX_RESPONSE_BYTES,'native_response_limit')
                                save('native-response.json',raw)  # private; never printed or committed
                        finally:
                            ended = time.monotonic()
                            connection.close()
                            receipt['request_seconds'] = ended-sent
                            receipt['request_finished_monotonic'] = ended
                            receipt['request_finished_utc'] = native.utc_now()
                        require(receipt['http_status'] == 200,'native_http_failure')
                        result = protocol.strict_json(raw)
                        require(isinstance(result.get('data'),list) and len(result['data']) == 1,'native_result_count')
                        png = base64.b64decode(result['data'][0]['b64_json'],validate=True)
                        output = protocol.decode_image(png,(width,native_height),output=True,
                                                       transparent=False,crop_bottom=native_height-height)
                        receipt['native_output'] = image_info(png,Image)
                        receipt['delivered_output'] = image_info(output,Image)
                        save('native.png',png)
                        save('generation.png',output)
                        receipt['native_response_metrics'] = {k:native.numeric_metric(result.get(k))
                            for k in ('inference_time_s','peak_memory_mb')}
                        # Runtime/perf keys are retained exactly; absent values stay absent.
                        if perf_path.exists():
                            info = perf_path.lstat()
                            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                                    and info.st_uid == service.NATIVE_UID and info.st_size <= 8*1024**2,
                                    'native_perf_identity_invalid')
                            save('native-perf.json',perf_path.read_bytes())
                        receipt['residency_after'] = runtime.verify_resident(state)
                        time.sleep(1.1)
                    finally:
                        receipt['sampler_exit'] = service.settle_sampler(sampler)
                        telemetry.fsync()
                require(receipt['sampler_exit'] == 0,'sampler_failed')
                receipt['metrics'] = telemetry_metrics(target/'telemetry.jsonl',sent,ended)
                receipt['tmp_after'] = runtime.tmp_snapshot(state['run_id'])
                names = {e['path'] for e in tmp_before['entries']}
                receipt['tmp_new_entries'] = [e for e in receipt['tmp_after']['entries'] if e['path'] not in names]
                metrics = receipt['metrics']
                criteria = {'correct_decoded_output':receipt['delivered_output']['width'] == width
                            and receipt['delivered_output']['height'] == height,
                            'device_free_at_least_5_percent':metrics['device']['minimum_free_fraction'] >= .05,
                            'host_available_at_least_15_percent':metrics['host']['min_available_fraction'] >= .15,
                            'container_swap_zero':metrics['cgroup']['memory.swap.current']['max'] == 0,
                            'no_observed_swap_activity':metrics['host']['vmstat_counter_deltas']['pswpin'] == 0
                            and metrics['host']['vmstat_counter_deltas']['pswpout'] == 0,
                            'no_observed_host_oom':metrics['host']['vmstat_counter_deltas']['oom_kill'] == 0,
                            'tmp_cleanup':not receipt['tmp_new_entries'],
                            'ready_and_owned_after':bool(receipt.get('residency_after')),
                            'one_generation':receipt['request_count'] == 1}
                receipt['criteria'] = criteria
                receipt['numeric_criteria_pass'] = all(criteria.values())
                receipt['status'] = 'PARTIAL' if receipt['numeric_criteria_pass'] else 'FAIL'
                receipt['predicted_next_demand'] = ({'decision':'END_OF_AUTHORIZED_REFINEMENT'}
                    if args.refinement else forecast(
                    observations+[observed_case(receipt)],SIZES[rung] if rung < len(SIZES) else None))
                receipt['recovery']['required_on_ambiguous_or_failed_native_outcome'] = not receipt['numeric_criteria_pass']
            except BaseException as error:
                receipt['status'] = 'FAIL'
                receipt['numeric_criteria_pass'] = False
                receipt['failure'] = {'type':type(error).__name__,
                    'code':str(error) if type(error) is RuntimeError else 'retained_evidence_diagnostic'}
                receipt['predicted_next_demand'] = {'decision':'END_OF_AUTHORIZED_REFINEMENT'
                    if args.refinement else 'STOP_FAILED_OR_INCOMPLETE_CASE'}
                try:
                    receipt['tmp_after'] = runtime.tmp_snapshot(state['run_id'])
                except Exception as snapshot_error:
                    receipt['tmp_after_error_type'] = type(snapshot_error).__name__
            finally:
                if sampler is not None:
                    service.settle_sampler(sampler)
                receipt['finished_utc'] = native.utc_now()
                receipt['finished_monotonic'] = time.monotonic()
                receipt['load_average_after'] = os.getloadavg()
                for name in ('telemetry.jsonl',):
                    if (target/name).exists():
                        receipt['evidence_sha256'][name] = sha((target/name).read_bytes())
                runtime.guards()
                save('receipt.json',encoded(receipt))
                save('receipt.sha256',(receipt['evidence_sha256']['receipt.json']+'  receipt.json\n').encode())
                anchor.check()
        # Lease exits before any caller reads/inspects the image or waits on root.
    print(json.dumps({'case_id':case,'status':receipt['status'],
        'numeric_criteria_pass':receipt.get('numeric_criteria_pass',False),
        'visual_verification':'NOT_TESTED','receipt':str(target/'receipt.json'),
        'receipt_sha256':receipt['evidence_sha256']['receipt.json'],
        'predicted_next_demand':receipt.get('predicted_next_demand')}))
    return 0 if receipt.get('numeric_criteria_pass') else 1


if __name__ == '__main__':
    raise SystemExit(main())
