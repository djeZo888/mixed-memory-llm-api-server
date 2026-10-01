"""Qualification-only original selected stderr capture; never mounted in native.

Stdout/stderr have independent order. A record grants no native acceptance.
"""
import hashlib,json,os,time
from pathlib import Path
MODE='post-sampling-token-usage-v1'
PAIR={'RUST_LOG':'off,codex_core::session::turn=trace','LOG_FORMAT':'json'}
class TraceCapture:
 def __init__(self,config):
  self.path,self.binding=config;self.pending=b'';self.offset=0;self.sequence=0;self.events=[];self.digest=hashlib.sha256();self.chain='0'*64;self.total=0;self.complete=False
 def feed(self,data,final=False):
  if self.complete:raise ValueError('trace_after_drain')
  self.digest.update(data);self.total+=len(data)
  if self.total>16*1024*1024:raise ValueError('trace_stream_bound')
  self.pending+=data
  while b'\n' in self.pending:
   line,self.pending=self.pending.split(b'\n',1);self._line(line+b'\n')
  if len(self.pending)>65536:raise ValueError('trace_line_bound')
  if final:
   if self.pending:raise ValueError('trace_truncated_stderr')
   self.complete=True
 def _line(self,line):
  self.sequence+=1;offset=self.offset;self.offset+=len(line);self.chain=hashlib.sha256(bytes.fromhex(self.chain)+line).hexdigest()
  if len(line)>65536:raise ValueError('trace_line_bound')
  text=line.decode('utf-8','strict')
  if not text.strip():return
  # Other stderr is never retained. Malformed target-bearing text fails closed.
  try:v=json.loads(text)
  except ValueError:
   if 'codex_core::session::turn' in text or 'post sampling token usage' in text:raise ValueError('trace_invalid_selected_json')
   return
  if not isinstance(v,dict) or v.get('target')!='codex_core::session::turn' or v.get('level')!='TRACE' or not isinstance(v.get('fields'),dict) or v['fields'].get('message')!='post sampling token usage':return
  fields=v['fields'];turn=fields.get('turn_id')
  if not isinstance(turn,str) or not 1<=len(turn)<=512 or any(ord(c)<33 for c in turn):raise ValueError('trace_turn_identity')
  if len(self.events)>=64:raise ValueError('trace_event_bound')
  name='trace-event-%04d.raw'%len(self.events);fd=os.open(self.path/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  try:
   view=memoryview(line)
   while view:view=view[os.write(fd,view):]
   os.fsync(fd)
  finally:os.close(fd)
  self.events.append({'file':name,'sha256':hashlib.sha256(line).hexdigest(),'bytes':len(line),'stderrSequence':self.sequence,'stderrOffset':offset,'chain':self.chain,'turnId':turn,'nativeTimestamp':v.get('timestamp'),'observedAtMs':int(time.time()*1000),'observedMonotonicNs':time.monotonic_ns()})
 def publish(self,receipts,producer,container_id,raw_exit,requested_stop,cleanup_ok):
  if not self.complete or self.pending:raise ValueError('trace_not_drained')
  env=receipts['read_private'](self.path/'trace-env.json')
  if env.get('containerId')!=container_id or env.get('producer')!=producer or env.get('nonce')!=self.binding['nonce'] or env.get('environment')!=PAIR:raise ValueError('trace_environment_binding')
  receipts['write_once'](self.path,'trace',{'schema':'codex-native-trace-v1','nonce':self.binding['nonce'],'sessionId':self.binding['sessionId'],'runId':self.binding['runId'],'mode':MODE,'producer':producer,'containerId':container_id,'environment':env['environment'],'sources':self.binding['sources'],'events':self.events,'stderrBytes':self.total,'stderrSHA256':self.digest.hexdigest(),'stderrChain':self.chain,'complete':True,'cleanupOk':cleanup_ok,'engineExitStatus':raw_exit,'requestedStop':requested_stop})
