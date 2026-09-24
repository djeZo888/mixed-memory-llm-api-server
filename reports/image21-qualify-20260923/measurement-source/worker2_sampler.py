#!/usr/bin/env python3
"""One shared read-only Worker2 baseline telemetry window; no image requests.

SIGTERM/SIGINT stops only the exact owned sampler. Maximum window is900seconds.
The canonical lease covers setup/close only, never waiting or Worker2's request.
Stage beside the reviewed native_rung.py in a protected task directory.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-id',required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f-]{36}',args.session_id):
        raise ValueError('invalid_session_id')
    path = Path(__file__).absolute().with_name('native_rung.py')
    for ancestor in [path,*path.parents]:
        info = ancestor.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise RuntimeError('unprotected_measurement_source')
    spec = importlib.util.spec_from_file_location('native_rung',path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    service = helper.pinned_module('image21_service',helper.BASE/'source/service.py')
    runtime = service.Runtime()
    stop = threading.Event()
    def terminate(_signum,_frame):
        stop.set()
    signal.signal(signal.SIGTERM,terminate)
    signal.signal(signal.SIGINT,terminate)
    relative = helper.CAMPAIGN_REL+'/worker2-baseline-segment2'
    target = helper.BASE/relative
    sampler = None
    with runtime.anchor() as anchor:
        with service.acquire_lease(blocking=False):
            runtime.guards()
            state = runtime.state()
            residency = runtime.verify_resident(state)
            helper.require(not target.exists(),'worker2_window_already_sampled')
            anchor.mkdir(helper.CAMPAIGN_REL)
            anchor.mkdir(relative)
            started = time.monotonic()
            receipt = {'schema_version':1,'campaign_id':helper.TASK,'owner':'Worker2 API baseline',
                       'session_id':args.session_id,'sampler_owner_pid':os.getpid(),
                       'started_monotonic':started,'started_utc':service.now(),
                       'container_id':state['container']['id'],'backend_run_id':state['run_id'],
                       'request_count_by_sampler':0,'residency_before':residency,
                       'tmp_before':runtime.tmp_snapshot(state['run_id']),
                       'telemetry_source_sha256':helper.PINS['telemetry.py'],
                       'sampler_max_seconds':900}
            anchor.atomic_json(relative+'/window-start.json',receipt)
            output = anchor.open(relative+'/telemetry.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        # Registered anchor stays live, while canonical mutation lease is free.
        with output:
            try:
                helper.require(helper.sha((helper.BASE/'source/telemetry.py').read_bytes()) ==
                               helper.PINS['telemetry.py'],'telemetry_source_changed')
                sampler = subprocess.Popen(['/usr/bin/python3','-I','-B',str(helper.BASE/'source/telemetry.py'),
                    '--output-fd',str(output.fileno()),'--output-path',str(target/'telemetry.jsonl'),
                    '--cgroup','/sys/fs/cgroup/system.slice/docker-'+state['container']['id']+'.scope'],
                    pass_fds=(output.fileno(),),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                time.sleep(1.1)
                helper.require(sampler.poll() is None,'sampler_start_failed')
                print(json.dumps({'status':'SAMPLER_READY','owner_pid':os.getpid(),
                                  'window_start':str(target/'window-start.json'),
                                  'canonical_lease':'released','image_requests':0}),flush=True)
                while not stop.wait(0.5) and time.monotonic()-started < 900:
                    helper.require(sampler.poll() is None,'sampler_early_exit')
                    anchor.check()
            finally:
                receipt['sampler_exit'] = service.settle_sampler(sampler)
                output.fsync()
        with service.acquire_lease(blocking=False):
            runtime.guards()
            receipt['finished_monotonic'] = time.monotonic()
            receipt['finished_utc'] = service.now()
            receipt['tmp_after'] = runtime.tmp_snapshot(state['run_id'])
            before_names = {entry['path'] for entry in receipt['tmp_before']['entries']}
            receipt['tmp_new_entries'] = [entry for entry in receipt['tmp_after']['entries']
                                          if entry['path'] not in before_names]
            receipt['residency_after'] = runtime.verify_resident(state)
            receipt['telemetry_sha256'] = helper.sha((target/'telemetry.jsonl').read_bytes())
            receipt['sampling_metrics_entire_window'] = helper.telemetry_metrics(
                target/'telemetry.jsonl',started,time.monotonic())
            receipt['timing_scope'] = 'Whole shared window; intersect raw monotonic/UTC rows with actual Worker2 request timestamps for request-only peak.'
            receipt['source'] = 'Existing exact protected telemetry.py; one sampler; no PSS'
            anchor.atomic_json(relative+'/window-result.json',receipt)
            runtime.guards()
    print(json.dumps({'status':'SAMPLER_STOPPED','result':str(target/'window-result.json'),
                      'result_sha256':helper.sha((target/'window-result.json').read_bytes()),
                      'sampler_exit':receipt['sampler_exit'],'canonical_lease':'released'}),flush=True)
    return 0 if receipt['sampler_exit'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
