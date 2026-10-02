#!/usr/bin/env python3
"""Read exact persisted native JSONL originals; emit a private base64 capture.

This generic reader does not dispatch, SSH, mutate Linux, run a model, or assert
native authorship/provider_finish/PASS. Workflow-specific child acceptance is
owned separately by the frontier coordinator.
"""
import argparse
import base64
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote
from protected_publication import Refused, UUID, ancestry, canonical, exact, load_json, read_bytes, require, sha

def records(raw):
    require(raw.endswith(b'\n'),'Incomplete native JSONL trailing record')
    rows=[]
    for number,line in enumerate(raw.splitlines(),1):
        require(bool(line),'Blank native JSONL record')
        value=json.loads(line.decode('utf-8'))
        require(isinstance(value,dict) and isinstance(value.get('payload'),dict),'Invalid native JSONL record')
        rows.append((number,value))
    return rows

def original(path, thread_id):
    raw=read_bytes(path, maximum=64*1024*1024)
    rows=records(raw)
    first=rows[0][1]
    require(first.get('type')=='session_meta' and first['payload'].get('id')==thread_id
            and first['payload'].get('cli_version')=='0.158.0'
            and first['payload'].get('model_provider')=='sova','Original native thread/runtime identity mismatch')
    return raw,rows

def locate(home, thread_id):
    require(UUID.fullmatch(thread_id),'Exact native UUID required')
    ancestry(home, __import__('os').getuid())
    found=[]
    for root in ('sessions','archived_sessions'):
        base=Path(home)/root
        if not base.exists(): continue
        ancestry(base,__import__('os').getuid())
        for p in base.rglob('*'+thread_id+'*.jsonl'):
            # Native paginated originals require a reviewed paginated reader.
            # Do not substitute a metadata-only snapshot for missing originals.
            try:
                raw,rows=original(p,thread_id)
                found.append((p,raw,rows))
            except Refused:
                raise
    require(len(found)==1,'Exact unique original unavailable (missing/duplicate/paginated): '+thread_id)
    return found[0]

def has_native_turn(value, turn):
    if isinstance(value,dict):
        return any((k in ('nativeTurnId','turnId','turn_id') and v==turn)
                   or has_native_turn(v,turn) for k,v in value.items())
    if isinstance(value,list): return any(has_native_turn(v,turn) for v in value)
    return False

def validate_binding(b):
    require(exact(b,('schema','sessionId','runId','nativeThreadId','nativeTurnId','profileDir','codexHome',
                    'databaseSnapshotPath','databaseSnapshotSha256','launchReceiptPath','launchReceiptSha256'))
            and b['schema']=='h046-original-capture-binding-v1'
            and all(UUID.fullmatch(b[n]) for n in ('sessionId','runId','nativeThreadId','nativeTurnId'))
            and b['codexHome']==b['profileDir']+'/codex-home','Invalid approved persisted capture binding')
    db_raw=read_bytes(b['databaseSnapshotPath'],private=True)
    require(sha(db_raw)==b['databaseSnapshotSha256'],'Private original DB snapshot changed')
    launch_raw=read_bytes(b['launchReceiptPath'],private=True,maximum=32768)
    require(sha(launch_raw)==b['launchReceiptSha256'],'Original native launch receipt changed')
    launch=json.loads(launch_raw)
    require(launch.get('schema')=='codex-launch-v1' and launch.get('sessionId')==b['sessionId']
            and launch.get('runId')==b['runId'] and launch.get('container',{}).get('profileDir')==b['profileDir'],
            'Persisted run is not bound to the approved profile')
    # immutable=1 is safe ONLY for the root's closed private backup, never the live DB.
    uri='file:'+quote(b['databaseSnapshotPath'],safe='/')+'?mode=ro&immutable=1'
    with sqlite3.connect(uri,uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        session=db.execute('SELECT native_session_id FROM sessions WHERE id=?',(b['sessionId'],)).fetchone()
        run=db.execute('SELECT session_id FROM runs WHERE id=?',(b['runId'],)).fetchone()
        require(session==(b['nativeThreadId'],) and run==(b['sessionId'],),'Exact persisted session/run/thread mismatch')
        events=db.execute('SELECT data FROM events WHERE session_id=? AND run_id=?',(b['sessionId'],b['runId'])).fetchall()
        require(any(has_native_turn(json.loads(row[0]),b['nativeTurnId']) for row in events),
                'Exact persisted native turn mapping unavailable; do not infer it')
    require(sha(read_bytes(b['databaseSnapshotPath'],private=True))==b['databaseSnapshotSha256'],
            'Private DB snapshot changed during original binding read')
    return launch

def capture(binding, children=()):
    validate_binding(binding)
    home=Path(binding['codexHome'])
    parent_path,parent_raw,parent_rows=locate(home,binding['nativeThreadId'])
    turn=binding['nativeTurnId']
    contexts=[n for n,r in parent_rows if r['type']=='turn_context' and r['payload'].get('turn_id')==turn]
    complete=[n for n,r in parent_rows if r['type']=='event_msg' and r['payload'].get('type')=='task_complete' and r['payload'].get('turn_id')==turn]
    require(contexts,'Exact original parent turn_context missing')
    start=min(contexts)
    end=max(complete) if complete else len(parent_rows)
    collab=[(n,r['payload']) for n,r in parent_rows if start <= n <= end
            and r['type']=='event_msg' and r['payload'].get('type','').startswith('collab_')
            and r['payload'].get('sender_thread_id')==binding['nativeThreadId']]
    captured=[{'threadId':binding['nativeThreadId'],'path':str(parent_path),'sha256':sha(parent_raw),
               'bytes':len(parent_raw),'originalJsonlBase64':base64.b64encode(parent_raw).decode(),
               'turnContextLines':contexts,'taskCompleteLines':complete,'collabLines':[n for n,_ in collab]}]
    missing=[]
    for child_id in children:
        require(UUID.fullmatch(child_id) and child_id!=binding['nativeThreadId'],'Invalid exact child UUID')
        spawn=[(n,p) for n,p in collab if p.get('type')=='collab_agent_spawn_end' and p.get('new_thread_id')==child_id]
        begin=[n for n,p in collab if p.get('type')=='collab_agent_spawn_begin'
               and any(p.get('call_id')==s['call_id'] for _,s in spawn)]
        waits=[n for n,p in collab if p.get('type')=='collab_waiting_end' and child_id in p.get('statuses',{})]
        require(spawn and begin,'Exact original parent dispatch chain missing for '+child_id)
        path,raw,rows=locate(home,child_id)
        meta=rows[0][1]['payload']
        parent=meta.get('parent_thread_id')
        source=meta.get('source',{})
        if parent is None and isinstance(source,dict):
            parent=source.get('subagent',{}).get('thread_spawn',{}).get('parent_thread_id')
        require(parent==binding['nativeThreadId'],'Original child parent identity mismatch')
        boundary=meta.get('subagent_history_start_ordinal')
        own=[(n,r) for n,r in rows if boundary is None or r.get('ordinal',-1)>=boundary]
        child_contexts=[(n,r['payload'].get('turn_id')) for n,r in own if r['type']=='turn_context'
                        and r['payload'].get('root_turn_id')==turn]
        turns={t for _,t in child_contexts}
        child_complete=[n for n,r in own if r['type']=='event_msg' and r['payload'].get('type')=='task_complete'
                        and r['payload'].get('turn_id') in turns]
        if not waits: missing.append(child_id+': exact parent wait missing')
        if not child_contexts: missing.append(child_id+': exact child turn_context/root turn missing')
        if not child_complete: missing.append(child_id+': exact child task_complete missing')
        captured.append({'threadId':child_id,'path':str(path),'sha256':sha(raw),'bytes':len(raw),
                         'originalJsonlBase64':base64.b64encode(raw).decode(),'sessionMetaLine':1,
                         'turnContextLines':[n for n,_ in child_contexts],'taskCompleteLines':child_complete,
                         'parentDispatchLines':begin+[n for n,_ in spawn],'parentWaitLines':waits})
    if not complete: missing.append('parent: exact task_complete missing')
    return {'schema':'h046-private-original-jsonl-capture-v1','bindingSha256':sha(canonical(binding)),
            'captured':captured,'missing':missing,'captureComplete':not missing,
            'nativeAuthorshipClaim':False,'providerFinishClaim':False,'qualification':'NOT_TESTED'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binding-file',required=True)
    p.add_argument('--child-thread',action='append',default=[])
    a=p.parse_args()
    try:
        result=capture(load_json(a.binding_file,private=True,maximum=65536),a.child_thread)
        sys.stdout.buffer.write(canonical(result)+b'\n')
        return 0 if result['captureComplete'] else 3
    except (Refused,OSError,ValueError,KeyError,TypeError,sqlite3.Error) as e:
        print('ORIGINAL_CAPTURE_MISSING: '+str(e),file=sys.stderr)
        return 2

if __name__=='__main__': sys.exit(main())
