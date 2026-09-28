#!/usr/bin/env python3
"""Offline summaries only: private captured H026 JSON -> compact metrics."""
import json,pathlib,statistics,sys,hashlib
base=pathlib.Path(sys.argv[1]);dest=pathlib.Path(sys.argv[2]);r=json.loads((base/'RESULTS.json').read_text());tele=[json.loads(s) for s in (base/'telemetry.jsonl').read_text().splitlines()]
uids={'qwen0':'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237','qwen1':'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'}
rows=[]
for x in r['requests']:
 s=x.get('summary')
 if not s:continue
 ct=s['client_timing'];c=s['counters'];beg=s['request_started_monotonic_s'];end=s['request_ended_monotonic_s'];samples=[t for t in tele if beg<=t['monotonic']<=end];g=[t['gpu'][uids[x['lane']]] for t in samples];first=ct['ttft_any_output_seconds'];last=ct['last_output_seconds'];n=c.get('completion_tokens');p=c.get('prompt_tokens')
 row={k:x.get(k) for k in ('sample_id','lane','watts','warmup','status','finish_reason','native_count','cap_readback','capacity','settlement','transport_clock')}
 row.update(native_response_counters=c,prompt_tokens=p,completion_tokens=n,ttft_s=first,last_output_s=last,full_eof_s=s['client_elapsed_seconds'],stream_interval_s=last-first if first is not None else None,
  prefill_proxy_tps=p/first if p and first else None,decode_proxy_tps=(n-1)/(last-first) if n and first is not None and last>first else None,sample_count=len(g),request_sha256=s['request_sha256'],response_sha256=s['response_sha256'],response_bytes=s['response_bytes'])
 if g:
  for field,label in [('power.draw','power_w'),('temperature.gpu','temp_c'),('utilization.gpu','util_pct'),('clocks.current.graphics','graphics_mhz'),('clocks.current.sm','sm_mhz'),('clocks.current.memory','memory_mhz')]:
   v=[t[field] for t in g];row[label]={'mean':statistics.mean(v),'peak':max(v),'min':min(v)}
  row['throttle_active_samples']={f:sum(t[f]=='Active' for t in g) for f in ('sw_power_cap','hw_thermal_slowdown','sw_thermal_slowdown','hw_power_brake_slowdown','hw_slowdown')}
  row['fan_readbacks']={ 'integrated':list({json.dumps(t['fans'][uids[x['lane']]],sort_keys=True) for t in samples}), 'external_duties':sorted({t['external_fan']['readback_duty'] for t in samples}),'external_tach_min':min(t['external_fan']['actual_tach'] for t in samples),'external_tach_max':max(t['external_fan']['actual_tach'] for t in samples)}
 rows.append(row)
for lane in uids:
 measured=[x for x in rows if x['lane']==lane and not x['warmup']]
 if not measured:continue
 baseline=measured[0]
 for x in measured:
  for metric in ('prefill_proxy_tps','decode_proxy_tps'):
   x[metric+'_change_pct']=100*(x[metric]/baseline[metric]-1)
  x['mean_power_change_pct']=100*(x['power_w']['mean']/baseline['power_w']['mean']-1)
result={k:v for k,v in r.items() if k!='requests'};result['rows']=rows
result['definitions']={'prefill_proxy':'actual_prompt_tokens / dispatch-to-first-nonempty-output seconds; includes admission, upload, native prefill, first decode and client overhead; NOT native prefill TPS','decode_proxy':'(actual_completion_tokens - 1) / (last_nonempty_output_arrival - first_nonempty_output_arrival); NOT native decode TPS; first chunk batching and stream buffering bias remain','power':'arithmetic mean and peak of ~1Hz same-request GPU board readings, not whole-machine/wall/PSU power; not transient qualification','timing_native':'native prompt_ms/decode_ms not provided; no native throughput claim','settlement':'terminal SSE/usage/DONE plus full HTTP EOF and exact same owner/readiness/capacity under exclusive ingress; no global idle claim','warmup':'one600Wrequest perGPU discarded fromcomparison','repeatability':'one measurement percap and600Wdriftanchor; no repeats/no statistical significance claim'}
assert all(x['native_response_counters'].get(k) is None for x in rows for k in ('prompt_ms','decode_ms')), 'native timing needs reporting'
result['native_session_id']='01a0e9d7-255c-7153-907a-b9136e22c032';result['unit']={'name':'h026-caps02.service','pid':2845647,'invocation_id':'0ae9605eebdf4ffd94e9e598c82da777'}
result['prior_attempt']={'path':'attempt01-unsent','status':'FAILED_BEFORE_TRANSPORT','reason':'setgid2700private_directory','inference_dispatched':False,'native_stopped':False,'caps_restored_600':True}
dest.mkdir(exist_ok=True,parents=True);(dest/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['| GPU | Cap W | Prompt/output | TTFT s | Prefill proxy tok/s | Decode proxy tok/s | Mean/peak board W | Peak C |','|---|---:|---:|---:|---:|---:|---:|---:|']
for x in rows:
 if x['warmup']:continue
 lines.append(f"| {x['lane']} | {x['watts']} | {x['prompt_tokens']}/{x['completion_tokens']} | {x['ttft_s']:.3f} | {x['prefill_proxy_tps']:.1f} | {x['decode_proxy_tps']:.2f} | {x['power_w']['mean']:.1f}/{x['power_w']['peak']:.1f} | {x['temp_c']['peak']:.0f} |")
(dest/'TABLE.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
