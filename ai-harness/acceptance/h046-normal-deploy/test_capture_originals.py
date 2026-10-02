import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import capture_originals as c
import protected_publication as p

PARENT='12345678-1234-1234-1234-123456789abc'
TURN='22345678-1234-1234-1234-123456789abc'
CHILD='32345678-1234-1234-1234-123456789abc'
SESSION='42345678-1234-1234-1234-123456789abc'
RUN='52345678-1234-1234-1234-123456789abc'

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HERE);self.root=Path(self.tmp.name).resolve()
        profile=self.root/'profile';home=profile/'codex-home';(home/'sessions').mkdir(parents=True)
        self.home=home
        db=self.root/'snapshot.db'
        with sqlite3.connect(db) as con:
            con.executescript('CREATE TABLE sessions(id TEXT,native_session_id TEXT);CREATE TABLE runs(id TEXT,session_id TEXT);CREATE TABLE events(session_id TEXT,run_id TEXT,data TEXT);')
            con.execute('INSERT INTO sessions VALUES(?,?)',(SESSION,PARENT))
            con.execute('INSERT INTO runs VALUES(?,?)',(RUN,SESSION))
            con.execute('INSERT INTO events VALUES(?,?,?)',(SESSION,RUN,json.dumps({'nativeTurnId':TURN})))
        db.chmod(0o600)
        launch=self.root/'launch.json';launch.write_bytes(p.canonical({'schema':'codex-launch-v1','sessionId':SESSION,'runId':RUN,'container':{'profileDir':str(profile)}}));launch.chmod(0o600)
        self.b={'schema':'h046-original-capture-binding-v1','sessionId':SESSION,'runId':RUN,
                'nativeThreadId':PARENT,'nativeTurnId':TURN,'profileDir':str(profile),'codexHome':str(home),
                'databaseSnapshotPath':str(db),'databaseSnapshotSha256':p.sha(db.read_bytes()),
                'launchReceiptPath':str(launch),'launchReceiptSha256':p.sha(launch.read_bytes())}
        self.parent=[self.meta(PARENT),self.row('turn_context',{'turn_id':TURN}),
          self.event('collab_agent_spawn_begin',sender_thread_id=PARENT,call_id='dispatch'),
          self.event('collab_agent_spawn_end',sender_thread_id=PARENT,call_id='dispatch',new_thread_id=CHILD),
          self.event('collab_waiting_end',sender_thread_id=PARENT,call_id='wait',statuses={CHILD:'completed'}),
          self.event('task_complete',turn_id=TURN)]
        self.child=[self.meta(CHILD,parent_thread_id=PARENT),self.row('turn_context',{'turn_id':CHILD,'root_turn_id':TURN}),self.event('task_complete',turn_id=CHILD)]
        self.write(PARENT,self.parent);self.write(CHILD,self.child)
    def tearDown(self):self.tmp.cleanup()
    def row(self,type,payload):return {'type':type,'payload':payload}
    def meta(self,id,**kwargs):return self.row('session_meta',{'id':id,'cli_version':'0.158.0','model_provider':'sova',**kwargs})
    def event(self,type,**kwargs):return self.row('event_msg',{'type':type,**kwargs})
    def write(self,id,rows):
        path=self.home/'sessions'/('rollout-fixture-'+id+'.jsonl')
        path.write_bytes(b''.join(p.canonical(row)+b'\n' for row in rows));path.chmod(0o600);return path
    def test_full_original_bytes_and_exact_chain_without_qualification_claim(self):
        r=c.capture(self.b,[CHILD])
        self.assertTrue(r['captureComplete']);self.assertFalse(r['nativeAuthorshipClaim'])
        self.assertFalse(r['providerFinishClaim']);self.assertEqual(r['qualification'],'NOT_TESTED')
        import base64
        self.assertEqual(base64.b64decode(r['captured'][0]['originalJsonlBase64']),self.write(PARENT,self.parent).read_bytes())
        self.assertEqual(r['captured'][1]['parentDispatchLines'],[3,4])
        self.assertEqual(r['captured'][1]['parentWaitLines'],[5])
    def test_missing_child_completion_or_parent_wait_reported(self):
        self.write(CHILD,self.child[:-1]);self.write(PARENT,self.parent[:4]+self.parent[5:])
        r=c.capture(self.b,[CHILD]);self.assertFalse(r['captureComplete']);self.assertEqual(len(r['missing']),2)
    def test_foreign_dispatch_and_metadata_rejected(self):
        self.write(PARENT,self.parent[:2]+self.parent[4:])
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])
        self.write(PARENT,self.parent);self.write(CHILD,[self.meta(CHILD,parent_thread_id=RUN)]+self.child[1:])
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])
    def test_persisted_turn_is_not_inferred(self):
        with self.assertRaises(p.Refused):c.capture({**self.b,'nativeTurnId':RUN})
    def test_missing_duplicate_and_metadata_only_original_rejected(self):
        child_path=self.home/'sessions'/('rollout-fixture-'+CHILD+'.jsonl');child_path.unlink()
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])
        path=self.write(CHILD,self.child);other=path.with_name('rollout-other-'+CHILD+'.jsonl');other.write_bytes(path.read_bytes());other.chmod(0o600)
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])
        other.unlink();path.write_bytes(b'{"thread":{"id":"'+CHILD.encode()+b'"}}\n')
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])
    def test_incomplete_original_line_and_native_version_rejected(self):
        path=self.write(CHILD,self.child);path.write_bytes(path.read_bytes().rstrip(b'\n'))
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])
        self.child[0]['payload']['cli_version']='0.160.0';self.write(CHILD,self.child)
        with self.assertRaises(p.Refused):c.capture(self.b,[CHILD])

if __name__=='__main__':unittest.main()
