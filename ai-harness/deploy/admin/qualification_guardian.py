"""Root-owned durable exact-task watcher; no lifecycle replay or container rm.

Keeps inherited SAME canonical open-description locked after carrier death.
Requests Stop only for the positively identified task group; native supervisors
own their cleanup. Unknown closure keeps the lease/hold for operator review.
"""
import os,sys,time,signal,json,stat
from pathlib import Path

def identity(pid):
 p=Path('/proc')/str(pid)
 try:return {'pid':pid,'startTicks':(p/'stat').read_text().rsplit(')',1)[1].split()[19],'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
 except FileNotFoundError:return None

def main(config):
 if os.geteuid()!=0:raise ValueError('root_guardian_only')
 p=Path(config);s=p.lstat()
 if p.resolve()!=p or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>16384:raise ValueError('guardian_config_untrusted')
 v=json.loads(p.read_bytes());fd=v['leaseFD'];info=os.fstat(fd)
 if (info.st_dev,info.st_ino)!=(v['leaseStat']['dev'],v['leaseStat']['ino']) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:raise ValueError('guardian_lease_identity')
 # This inherited descriptor NEVER mints/borrows/releases a LifecycleLease.
 evidence=Path(v['evidenceRoot']);ready=evidence/'guardian.ready';w=os.open(ready,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.write(w,json.dumps({'pid':os.getpid(),'leaseDev':info.st_dev,'leaseIno':info.st_ino}).encode());os.fsync(w);os.close(w)
 died=False
 while True:
  carrier=identity(v['carrier']['pid'])
  if carrier!=v['carrier'] and not died:
   died=True
   if identity(v['task']['pid'])==v['task']:os.killpg(v['task']['pid'],signal.SIGTERM)
   marker=evidence/'GUARDIAN-RESTORE-NEEDED.json';w=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(w,json.dumps({'transactionId':v['transactionId'],'reason':'carrier_lost_no_replay','leaseRetained':True}).encode());os.fsync(w);os.close(w)
  release=evidence/'guardian.release'
  if not died and release.exists():
   s=release.lstat()
   if s.st_uid!=0 or s.st_mode&0o022 or s.st_nlink!=1:raise ValueError('guardian_release_untrusted')
   r=json.loads(release.read_bytes())
   if r!={'carrier':v['carrier'],'transactionId':v['transactionId']}:raise ValueError('guardian_release_foreign')
   # Carrier producer has joined exact process, FD/container/listener proof and
   # actual restoration before publishing. Independently ensure task PID gone.
   if identity(v['task']['pid'])==v['task']:raise ValueError('task_alive_at_guardian_release')
   os.close(fd);return 0
  # On lost carrier retain forever; no automatic restore/replay/unknown cleanup.
  time.sleep(.2)
if __name__=='__main__':sys.exit(main(sys.argv[1]))
