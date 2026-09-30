import importlib.util,json,pathlib
p=pathlib.Path('/data/services/image21-runtime-20260923/source/service.py');spec=importlib.util.spec_from_file_location('runtime',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);r=m.Runtime()
with m.acquire_lease(blocking=False):
 r.guards();s=r.state();receipt=json.loads((m.BASE/'receipts/H003-D03-receipt.json').read_text());assert receipt['exit_code']==0 and receipt['probe_processes_absent']
 current=r.verify_resident(s);assert current['container_id']==receipt['before']['container_id']
 assert [tuple(row[:2]) for row in current['gpu_processes']]==[tuple(row[:2]) for row in receipt['before']['gpu_processes']]
 top=m.run(['docker','top',s['container']['id'],'-eo','pid,args']).stdout;assert '/H003-D03/probe.py' not in top
 metrics=json.loads((m.BASE/'work/evidence'/s['run_id']/'H003-D03/metrics.json').read_text());assert metrics['http_status']==200 and metrics['completed_outputs']==1 and len(metrics['perf']['denoise_steps_ms'])==40
 m.run(['systemctl','thaw','llm-image-api.service']);r.guards()
 with r.anchor() as a:a.atomic_json('receipts/H003-D03-settlement-correction.json',{'utc':m.now(),'status':'settled_and_thawed','cause':'process identity check erroneously included used_memory; unchanged native PID grew2MiB','current':current,'no_probe_process':True,'http200_and40_steps_and_output':True})
 print('settled_and_thawed')
