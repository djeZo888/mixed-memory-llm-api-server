#!/usr/bin/env python3
"""Offline first49s and full telemetry comparison; never modifies original evidence."""
import argparse,json,pathlib,hashlib
GPUS={'flash':'GPU-69acfa26-8b60-61b5-702d-aee252c163cc','qwen0':'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237','qwen1':'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528','image':'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'}
def summary(root,prefix,limit=None):
 receipt=json.loads((root/(prefix+'.json')).read_text());start=receipt['barrier_monotonic'];rows=[json.loads(l) for l in (root/(prefix+'-telemetry.jsonl')).read_text().splitlines()];rows=[r for r in rows if r['monotonic']>=start and (limit is None or r['monotonic']<=start+limit)]
 if not rows:return {'status':'NO_POST_BARRIER_SAMPLES'}
 out={'status':receipt['status'],'cancel_reason':receipt.get('cancel_reason'),'window_seconds':limit,'samples':len(rows),'actual_last_sample_offset_s':rows[-1]['monotonic']-start,'three_blackwell_same_sample_peak_w':max(r['three_blackwell_w'] for r in rows),'Ada_separate_peak_w':max(r['ada_external_w'] for r in rows),'gpu':{},'overlap':'HTTP intersection and GPU utilization/CPU deltas are separate proxies; actual native progress needs native logs/SSE, no kernel simultaneity claim','CPU_wall_PSU_power':'UNKNOWN_NO_WALL_SENSOR'}
 for lane,uid in GPUS.items():
  out['gpu'][lane]={'peak_c':max(float(r['gpu'][uid]['temperature.gpu']) for r in rows),'peak_board_w':max(float(r['gpu'][uid]['power.draw']) for r in rows),'min_free_mib':min(float(r['gpu'][uid]['memory.free']) for r in rows),'nonzero_util_samples':sum(float(r['gpu'][uid]['utilization.gpu'])>0 for r in rows),'clock_first_last':[rows[i]['gpu'][uid].get('clocks.current.sm') for i in (0,-1)],'fan_first_last':[rows[i].get('fans',{}).get(uid) for i in (0,-1)]}
 return out
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('old',type=pathlib.Path);p.add_argument('new',type=pathlib.Path,nargs='?');p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 raw=(a.old/'H011-FOURWAY03-telemetry.jsonl').read_bytes();assert hashlib.sha256(raw).hexdigest()=='410c2bb545f9859469750455356b8a349c67a8902ec18b3cb275fd8f3660b4f3'
 out={'H011_first49s':summary(a.old,'H011-FOURWAY03',49),'confounders':['Flash configured pool480000 versus1048576','reboot and cache state','warmup recency','integrated fan policy','external fan user setting and unmeasured RPM','ambient/inlet unknown'],'ECC_only_causality':'NOT_IDENTIFIABLE'}
 if a.new:out.update(H013_first49s=summary(a.new,'H013-FOURWAY01',49),H013_full=summary(a.new,'H013-FOURWAY01'))
 else:out['H013']='NOT_DISPATCHED'
 a.output.write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
