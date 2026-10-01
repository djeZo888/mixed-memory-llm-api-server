"""Offline real record/crypto/path fixtures; no root/Linux/native qualification."""
import unittest,tempfile,sys,sqlite3,json,hmac,hashlib,os
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).parent))
import qualification_carrier_host as host
class Fixtures(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.db=self.root/'original.sqlite';self.sql=sqlite3.connect(self.db);self.sql.execute('create table runs(id text primary key,status text,error text,updated_at integer,prompt text)');self.sql.execute("insert into runs values('old','running',null,1,'preserved negation: do not reset')");self.sql.commit()
 def tearDown(self):self.sql.close();self.temp.cleanup()
 def test_real_readonly_wal_snapshot_hashes_chat_fields_and_accepts_explicit_recovery_delta(self):
  self.sql.execute('pragma journal_mode=WAL');before=host.retained_record_snapshot(self.db);self.sql.execute("update runs set status='error',error='application restarted',updated_at=2");self.sql.commit();after=host.retained_record_snapshot(self.db);delta=host.verify_retained_records(before,after);self.assertEqual({x['field'] for x in delta},{'status','error','updated_at'});self.assertNotIn('preserved negation',json.dumps(before))
 def test_original_text_or_id_loss_is_never_recovery(self):
  before=host.retained_record_snapshot(self.db);self.sql.execute("update runs set prompt='lost original'");self.sql.commit()
  with self.assertRaises(host.CarrierError):host.verify_retained_records(before,host.retained_record_snapshot(self.db))
 def test_claimed_success_cannot_be_promoted_by_restore(self):
  before=host.retained_record_snapshot(self.db);self.sql.execute("update runs set status='completed'");self.sql.commit()
  with self.assertRaises(host.CarrierError):host.verify_retained_records(before,host.retained_record_snapshot(self.db))
 def test_protected_input_rejects_symlink_hardlink_write_and_foreign_owner(self):
  p=self.root/'packet';p.write_text('safe');p.chmod(0o600);self.assertEqual(host.checked_bytes(p,uid=os.getuid()),b'safe');q=self.root/'link';q.symlink_to(p)
  with self.assertRaises(host.CarrierError):host.checked_bytes(q,uid=os.getuid())
  q.unlink();os.link(p,q)
  with self.assertRaises(host.CarrierError):host.checked_bytes(p,uid=os.getuid())
 def test_parent_bind_and_hardlink_alias_original_object_cannot_escape_scope(self):
  original=self.root/'original';original.mkdir();file=original/'retained';file.write_text('original');scope=host.object_scope([original]);self.assertTrue(host.mount_overlaps(self.root,scope));alias=self.root/'outside-hardlink';os.link(file,alias);self.assertTrue(host.mount_overlaps(alias,scope));other=self.root/'disjoint';other.mkdir();self.assertFalse(host.mount_overlaps(other,scope));link=self.root/'link';link.symlink_to(original)
  with self.assertRaises(host.CarrierError):host.mount_overlaps(link,scope)
 def test_exact_hmac_rejects_tamper_and_wrong_phase_budget(self):
  value={'schema':'h041-qualification-carrier-v1','actor':'worker1','phase':'stage','nativeActionLimit':9,'settlementReserveMs':120000};raw=json.dumps(value).encode();key=b'k'*32;approved=json.dumps({'inputSHA256':hashlib.sha256(raw).hexdigest(),'mac':hmac.new(key,raw,hashlib.sha256).hexdigest()}).encode()
  with mock.patch.object(host,'checked_bytes',side_effect=[raw,approved,key]):self.assertEqual(host.signed_packet('i','a','k'),value)
  with mock.patch.object(host,'checked_bytes',side_effect=[raw,approved,b'x'*32]):
   with self.assertRaises(host.CarrierError):host.signed_packet('i','a','k')
if __name__=='__main__':unittest.main()

class BarrierFixtures(unittest.TestCase):
 def test_exact_preexec_ack_rejects_pid_start_boot_or_transaction_substitution(self):
  import qualification_task_barrier as barrier
  owner={'pid':100,'startTicks':'200','bootId':'actual-boot'};carrier={'transactionId':'owned'}
  self.assertTrue(barrier.acknowledged({'transactionId':'owned','task':owner},owner,carrier))
  for key,value in [('pid',101),('startTicks','201'),('bootId','other')]:
   self.assertFalse(barrier.acknowledged({'transactionId':'owned','task':{**owner,key:value}},owner,carrier))
  self.assertFalse(barrier.acknowledged({'transactionId':'foreign','task':owner},owner,carrier))

class NormalTupleFixtures(unittest.TestCase):
 def test_exact_release_config_data_fd_and_readiness_required(self):
  import copy
  expected={'process':{'cmdlineSHA256':'source','exe':'/node','cwd':'/release/server','cgroup':'user-unit','mountNamespace':1,'bootId':'boot'},'paths':{'AI_HARNESS_DATA_DIR':'/original'},'files':{'/release/code':{'sha256':'a','uid':1000,'mode':'0o444','nlink':1,'resolved':'/release/code'}},'database':{'path':'/original/harness.sqlite','dev':2,'ino':3,'ownedFDs':['24']},'health':{'http':200,'status':'ok','version':'0.0.3','host':'localhost:8080'}}
  self.assertTrue(host.verify_normal_tuple(expected,copy.deepcopy(expected)))
  for branch,key,value in [('process','cwd','/other'),('process','cmdlineSHA256','other'),('database','ino',4),('database','ownedFDs',[]),('health','http',403),('paths','AI_HARNESS_DATA_DIR','/alternate')]:
   after=copy.deepcopy(expected);after[branch][key]=value
   with self.assertRaises(host.CarrierError):host.verify_normal_tuple(expected,after)
  after=copy.deepcopy(expected);after['files']['/release/code']['sha256']='other'
  with self.assertRaises(host.CarrierError):host.verify_normal_tuple(expected,after)

class ReadoptionFixtures(unittest.TestCase):
 def test_original_worker_must_be_independently_gone_or_pid_reused(self):
  original={'pid':123,'startTicks':'42','bootId':'boot'}
  with mock.patch.object(host,'process_identity',return_value=original):self.assertFalse(host.previous_worker_gone(original))
  with mock.patch.object(host,'process_identity',side_effect=FileNotFoundError):self.assertTrue(host.previous_worker_gone(original))
  with mock.patch.object(host,'process_identity',return_value={**original,'startTicks':'43'}):self.assertTrue(host.previous_worker_gone(original))
  with mock.patch.object(host,'process_identity',side_effect=PermissionError):
   with self.assertRaises(PermissionError):host.previous_worker_gone(original)
