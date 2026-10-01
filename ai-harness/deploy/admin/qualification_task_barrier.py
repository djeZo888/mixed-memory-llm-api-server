"""Fixed root pre-exec barrier. No Node/dispatch before durable guardian ACK.

Exec preserves PID/start/PGID already registered with the guardian. Lost carrier
or missing ACK exits before application acquisition, never guessing cleanup.
"""
import os,sys,json,stat,time
from pathlib import Path

def identity(pid):
 try:return {'pid':pid,'startTicks':(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19],'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
 except FileNotFoundError:return None

def protected(path):
 p=Path(path);s=p.lstat()
 if p.resolve()!=p or not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size>32768:raise ValueError('untrusted_preexec_barrier')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  f=os.fstat(fd)
  if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(f.st_dev,f.st_ino,f.st_size,f.st_mtime_ns,f.st_ctime_ns):raise ValueError('barrier_input_changed')
  raw=os.read(fd,32769);after=os.fstat(fd);current=p.lstat()
  if (f.st_dev,f.st_ino,f.st_size,f.st_mtime_ns,f.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or (f.st_dev,f.st_ino,f.st_size,f.st_mtime_ns,f.st_ctime_ns)!=(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns):raise ValueError('barrier_input_changed')
  return json.loads(raw)
 finally:os.close(fd)

def acknowledged(value,own,carrier):
 return value=={'transactionId':carrier['transactionId'],'task':own}

def main(path):
 if os.geteuid()!=0 or os.getpgid(0)!=os.getpid():raise ValueError('owned_root_task_group_required')
 config=protected(path);own=identity(os.getpid());until=time.monotonic()+3
 if config['argv'][:4]!=['/usr/sbin/runuser','--user',config['user'],'--'] or config['argv'][4:6]!=['/usr/bin/env','-i']:raise ValueError('fixed_task_command_required')
 while time.monotonic()<until:
  if identity(config['carrier']['pid'])!=config['carrier']:raise ValueError('carrier_lost_before_exec')
  try:
   ack=protected(config['ack'])
   if not acknowledged(ack,own,config):raise ValueError('foreign_task_ack')
   os.execve('/usr/sbin/runuser',config['argv'],{'PATH':'/usr/bin:/bin','LANG':'C'})
  except FileNotFoundError:pass
  time.sleep(.01)
 raise ValueError('guardian_ack_missing_before_exec')
if __name__=='__main__':main(sys.argv[1])
