#!/usr/bin/env python3
"""Offline, bounded summary of saved R6/R7 pair; no remote access."""
import argparse,base64,hashlib,json,pathlib,re,statistics
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--r6',type=pathlib.Path,required=True);ap.add_argument('--r7',type=pathlib.Path,required=True);ap.add_argument('--out',type=pathlib.Path,required=True)
a=ap.parse_args()
def sha(b):return hashlib.sha256(b).hexdigest()
def stat(v):
 return {'min':min(v),'mean':statistics.mean(v),'median':statistics.median(v),'max':max(v),'stdev':statistics.stdev(v) if len(v)>1 else 0} if v else None
def J(p,n):return json.loads((p/n).read_text())
T={'scope':'Offline saved request receipts only; one pair per configuration, no quality qualification.','runs':{},'comparison':{}}
A={'scope':'Saved cheap request boundaries, existing telemetry and profile collectors only. No topology rescans.','runs':{},'limits':['Discrete GPU activity and PCIe MB/s are not GPU VRAM GB/s.','Host DRAM GB/s remains unavailable from these VM receipts; user host UMC sample is separate.','One ordered baseline/profile pair per configuration; profile timing combines measurement overhead, ordering, and different A/B outputs.']}
for run,p in [('R6',a.r6),('R7',a.r7)]:
 T['runs'][run]={};A['runs'][run]={'phases':{}}
 tel=[json.loads(x) for x in (p/'TELEMETRY.jsonl').read_text().splitlines()]
 for phase in ['BASELINE128','PROFILE128']:
  r=J(p,phase+'.json');pending=b'';ts=[];ns=[];raw=b''
  for c in r['raw_chunks']:
   b=base64.b64decode(c['base64']);assert len(b)==c['bytes'];raw+=b;pending+=b;n=0
   while b'\n' in pending:
    line,pending=pending.split(b'\n',1)
    if not line.startswith(b'data: ') or line[6:].strip()==b'[DONE]':continue
    e=json.loads(line[6:])
    for ch in e.get('choices',[]):
     d=ch.get('delta',{})
     if d.get('content') or d.get('reasoning_content') or d.get('tool_calls'):ts.append(c['monotonic_seconds']);n+=1
   ns.append(n)
  dt=[y-x for x,y in zip(ts,ts[1:])];span=ts[-1]-ts[0];nt=r['native_timings']
  T['runs'][run][phase]={'receipt_sha256':sha((p/(phase+'.json')).read_bytes()),'request_sha256':r['request_sha256'],'content_sha256':sha(r['content'].encode()),'raw_sse_sha256':sha(raw),'raw_bytes':len(raw),'raw_chunks':len(ns),'output_events':len(ts),'distinct_output_arrivals':len(set(ts)),'max_output_events_per_chunk':max(ns),'arrival_intervals':len(dt),'arrival_interval_seconds':stat(dt),'arrival_interval_rate_per_second':len(dt)/span,'first_to_last_seconds':span,'first_output_monotonic_seconds':ts[0],'last_output_monotonic_seconds':ts[-1],'started_utc':r['started_utc'],'finished_utc':r['finished_utc'],'started_monotonic_seconds':r['started_monotonic_seconds'],'request_sent_monotonic_seconds':r['request_sent_monotonic_seconds'],'drained_monotonic_seconds':r['drained_monotonic_seconds'],'ttft_seconds':ts[0]-r['started_monotonic_seconds'],'send_complete_to_first_output_seconds':ts[0]-r['request_sent_monotonic_seconds'],'full_http_seconds':r['total_seconds'],'native_timings':nt,'native_minus_arrival_decode_ms':nt['predicted_ms']-span*1000,'usage':r['usage'],'finish_reason':r['finish_reason'],'full_http_drain':r['full_http_drain'],'correctness':r['correctness']}
  bd=J(p,phase+'-BOUNDARIES.json');x,y=bd['before'],bd['after'];elapsed=y['monotonic_seconds']-x['monotonic_seconds'];cpu={k:(y['cgroup']['cpu.stat'][k]-x['cgroup']['cpu.stat'][k])/1e6 for k in ['usage_usec','user_usec','system_usec']};samples=[q for q in tel if x['utc']<=q['utc']<=y['utc']]
  z={'source_sha256':sha((p/(phase+'-BOUNDARIES.json')).read_bytes()),'utc':[x['utc'],y['utc']],'wall_seconds':elapsed,'cpu_seconds':cpu,'average_logical_cpus':cpu['usage_usec']/elapsed,'process_major_fault_delta':y['process']['major_faults']-x['process']['major_faults'],'process_minor_fault_delta':y['process']['minor_faults']-x['process']['minor_faults'],'process_read_bytes_delta':y['process']['io']['read_bytes']-x['process']['io']['read_bytes'],'memory_boundary_bytes':[x['cgroup']['memory.current'],y['cgroup']['memory.current']],'swap_boundary_bytes':[x['cgroup']['memory.swap.current'],y['cgroup']['memory.swap.current']],'memory_event_deltas':{k:y['cgroup']['memory.events'][k]-v for k,v in x['cgroup']['memory.events'].items()},'cpu_throttled_usec_delta':y['cgroup']['cpu.stat']['throttled_usec']-x['cgroup']['cpu.stat']['throttled_usec'],'telemetry_samples':len(samples)}
  if samples:z.update({'host_memavailable_bytes':stat([q['host']['MemAvailable'] for q in samples]),'gpu':{g['uuid']:{key:stat([next(u for u in q['gpus'] if u['uuid']==g['uuid'])[key] for q in samples]) for key in ['util_pct','temp_c','free_mib']} for g in samples[0]['gpus']}})
  A['runs'][run]['phases'][phase]=z
 act=J(p,'PROFILE128-ACTIVITY.json');rows=[l.split() for l in act['gpu_activity_pcie']['raw'].splitlines() if l.strip() and not l.startswith('#')]
 A['runs'][run]['gpu_dmon']={'source_sha256':sha((p/'PROFILE128-ACTIVITY.json').read_bytes()),'samples':len(rows),'sm_pct':stat([int(r[3]) for r in rows]),'memory_util_pct':stat([int(r[4]) for r in rows]),'pcie_rx_emitted_MB_s':stat([int(r[9]) for r in rows]),'pcie_tx_emitted_MB_s':stat([int(r[10]) for r in rows]),'limit':'Nominal 5-second snapshots including initial pre-request sample; may miss bursts.'}
 perf=J(p,'PROFILE128-PERF.json');text=next(c['raw_stderr'] for c in perf['collectors'] if c['name']=='stat');counters={}
 for line in text.splitlines():
  m=re.match(r'\s*([\d,.]+)\s+(?:msec\s+)?(task-clock|context-switches|cpu-migrations|page-faults|cycles|instructions|cache-references|cache-misses)\b',line)
  if m:counters[m[2]]=float(m[1].replace(',',''))
 elapsed=float(re.search(r'([\d.]+) seconds time elapsed',text)[1]);counters.update({'wall_seconds':elapsed,'average_logical_cpus':counters['task-clock']/1000/elapsed,'instructions_per_cycle':counters['instructions']/counters['cycles'],'context_switches_per_wall_second':counters['context-switches']/elapsed,'migrations_per_wall_second':counters['cpu-migrations']/elapsed})
 A['runs'][run]['perf_stat']={'source_sha256':sha((p/'PROFILE128-PERF.json').read_bytes()),'counters':counters,'scope':'Entire attached profile collector interval; CPU-time counters, not DRAM byte counters.'}
for phase in ['BASELINE128','PROFILE128']:
 x,y=T['runs']['R6'][phase],T['runs']['R7'][phase]
 T['comparison'][phase]={'request_sha256_equal':x['request_sha256']==y['request_sha256'],'content_sha256_equal':x['content_sha256']==y['content_sha256'],'R7_to_R6_native_decode_interval_rate_ratio':x['native_timings']['predicted_ms']/y['native_timings']['predicted_ms'],'R7_decode_time_reduction_pct':100*(1-y['native_timings']['predicted_ms']/x['native_timings']['predicted_ms'])}
for run in T['runs']:
 x,y=T['runs'][run]['BASELINE128'],T['runs'][run]['PROFILE128']
 T['comparison'][run+'_baseline_vs_profile']={'request_sha256_equal':x['request_sha256']==y['request_sha256'],'content_sha256_equal':x['content_sha256']==y['content_sha256'],'profile_native_decode_duration_ratio':y['native_timings']['predicted_ms']/x['native_timings']['predicted_ms']}
T['limits']=['Native predicted_n=128 uses 127 decode intervals in exposed predicted_per_second; arrival event count is not an independent tokenizer count.','Raw timestamps measure reader receipt, not GPU completion.','Fixed seed/temp/thinking and cross-run same-phase request/output equality support this observed comparison; no repetitions or quality score.','A/B fixture tags and output differ, profile follows baseline; their within-run delta is not isolated profiling overhead.']
a.out.mkdir(parents=True,exist_ok=True)
for n,d in [('TIMINGS.json',T),('ACTIVITY.json',A)]: (a.out/n).write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({'comparison':T['comparison'],'cpu':{run:{ph:z['average_logical_cpus'] for ph,z in d['phases'].items()} for run,d in A['runs'].items()},'dmon':{run:d['gpu_dmon'] for run,d in A['runs'].items()}},indent=2))
