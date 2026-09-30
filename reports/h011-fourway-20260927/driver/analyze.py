"""Read saved H011 task receipts only; same-sample sums and overlap proxies."""
import argparse,json,pathlib,statistics,datetime

def analyze(root,prefix):
 r=json.loads((root/(prefix+'.json')).read_text());rows=[json.loads(l) for l in (root/(prefix+'-telemetry.jsonl')).read_text().splitlines()]
 gpus={lane:uid for lane,uid in [('flash','GPU-69acfa26-8b60-61b5-702d-aee252c163cc'),('qwen0','GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237'),('qwen1','GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'),('image','GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23')]}
 def active(t,lane):return any(x.get('start_monotonic',1e20)<=t<=x.get('response_end_monotonic',x.get('end_monotonic',1e20)) for x in r['requests'][lane])
 intervals=[]
 for a,b in zip(rows,rows[1:]):
  dt=b['monotonic']-a['monotonic']
  if dt>2.5:continue
  util={lane:float(a['gpu'][uid]['utilization.gpu']) for lane,uid in gpus.items()}
  cpu={lane:(b['cgroups'][lane]['cpu']['usage_usec']-a['cgroups'][lane]['cpu']['usage_usec'])/1e6/dt for lane in gpus}
  all_http=all(active(a['monotonic'],lane) for lane in gpus)
  intervals.append({'dt':dt,'all_http':all_http,'all_gpu_nonzero':all(v>0 for v in util.values()),'three_gpu_heavy_flash_cpu':all(util[l]>=50 for l in ['qwen0','qwen1','image']) and cpu['flash']>=16,'util':util,'cpu':cpu})
 def num(v):
  try:return float(v)
  except (ValueError,TypeError):return None
 peak=max(rows,key=lambda r:r['three_blackwell_w'])
 out={'status':r['status'],'cancel_reason':r['cancel_reason'],'barrier_utc':r.get('barrier_utc'),'end_utc':r['end_utc'],'sample_count':len(rows),'sample_max_gap_s':max(b['monotonic']-a['monotonic'] for a,b in zip(rows,rows[1:])),'three_blackwell_peak_same_sample':{k:peak[k] for k in ['utc','three_blackwell_w','ada_external_w','all_four_diagnostic_w']},'all_four_diagnostic_peak_w':max(x['all_four_diagnostic_w'] for x in rows),'gpu':{},'requests':{},'host_available_min_gib':min(x['ram']['MemAvailable'] for x in rows)/2**30,'overlap_sample_left_interval_proxy_s':{'four_client_intervals':sum(x['dt'] for x in intervals if x['all_http']),'four_gpu_util_nonzero':sum(x['dt'] for x in intervals if x['all_gpu_nonzero']),'qwen_image_util_at_least50_flash_at_least16core':sum(x['dt'] for x in intervals if x['three_gpu_heavy_flash_cpu'])},'overlap_limit':'Samples and CPU deltas show activity; not kernel simultaneity. Left-sample intervals omit gaps >2.5s; no HTTP-only compute claim.','cpu_package_power':r.get('cpu_package_power'),'bmc_devices_exposed':r.get('bmc_devices_exposed'),'native_log_capability':r.get('native_log_capability'),'software_power_limit_not_failure':True}
 for lane,uid in gpus.items():
  out['gpu'][lane]={'uuid':uid,'power_peak_w':max(float(x['gpu'][uid]['power.draw']) for x in rows),'power_at_three_blackwell_peak_w':float(peak['gpu'][uid]['power.draw']),'temp_peak_c':max(float(x['gpu'][uid]['temperature.gpu']) for x in rows),'free_min_mib':min(float(x['gpu'][uid]['memory.free']) for x in rows),'util_nonzero_samples':sum(float(x['gpu'][uid]['utilization.gpu'])>0 for x in rows),'util_at_least50_samples':sum(float(x['gpu'][uid]['utilization.gpu'])>=50 for x in rows),'throttle_active_samples':{k:sum(x['gpu'][uid].get(k)=='Active' for x in rows) for k in rows[0]['gpu'][uid] if k.startswith('clocks_event_reasons.')},'owned_swap_peak_bytes':max(x['cgroups'][lane]['memory.swap.current'] for x in rows),'cgroup_current_peak_gib':max(x['cgroups'][lane]['memory.current'] for x in rows)/2**30,'cgroup_events_delta':{k:rows[-1]['cgroups'][lane]['events'][k]-rows[0]['cgroups'][lane]['events'][k] for k in rows[0]['cgroups'][lane]['events']}}
  out['requests'][lane]=[{k:v for k,v in x.items() if k not in ['content','reasoning','response_metadata']} for x in r['requests'][lane]]
 out['host_swap_pages_delta']={k:rows[-1]['swap'][k]-rows[0]['swap'][k] for k in rows[0]['swap']}
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('raw',type=pathlib.Path);p.add_argument('--prefix',default='H011-FOURWAY02');p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();a.output.write_text(json.dumps(analyze(a.raw,a.prefix),indent=2)+'\n')
