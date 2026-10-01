#!/usr/bin/env python3
"""Private durable H039 v1 HTTP job service; construction never starts a model.

Only host bytes cross admission. A private single-process ledger is the authority;
HTTP observation has no ownership of admitted execution. Restart never replays it.
"""
import copy
import fcntl
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import socket
import stat
import struct
import threading
import time
import zlib
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

BODY_CAP = 51 * 1024 * 1024
JSON_CAP = 1024 * 1024
IMAGE_CAP = 50 * 1024 * 1024
ID = re.compile(r"[a-zA-Z0-9_-]{1,80}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class Reject(Exception):
    def __init__(self, code="invalid_request", status=400):
        self.code, self.status = code, status


class BackendFailure(Exception):
    """settled only describes actual service-owned execution, never HTTP abort."""
    def __init__(self, settled=False):
        self.settled = settled


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(v):
    return hashlib.sha256(v).hexdigest()


def parse_json(b, cap=JSON_CAP):
    if len(b) > cap:
        raise Reject()
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Reject()
            out[k] = v
        return out
    try:
        return json.loads(b.decode('utf8'), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Reject()))
    except (ValueError, UnicodeError, RecursionError):
        raise Reject()


def obj(v, required, optional=()):
    if not isinstance(v, dict) or not set(required) <= set(v) or set(v) - set(required) - set(optional):
        raise Reject()
    return v


def ident(v):
    if not isinstance(v, str) or not ID.fullmatch(v):
        raise Reject()
    return v


def text(v, cap=8192):
    if not isinstance(v, str) or not v or len(v.encode('utf-16-le','surrogatepass'))//2 > cap or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',v) or re.search(r'data:(?:image|application)/[^;]+;base64,',v,re.I):
        raise Reject()
    return v


def integer(v, lo=0, hi=10000):
    if type(v) is not int or not lo <= v <= hi:
        raise Reject()
    return v


def arr(v, cap=1024):
    if not isinstance(v, list) or len(v) > cap:
        raise Reject()
    return v


def owner(v):
    obj(v, ('sessionId', 'workspaceId', 'runId'))
    for val in v.values():
        ident(val)
    return v


def identity(v):
    obj(v, ('serviceId', 'generation', 'mode', 'interpreter', 'parser'))
    ident(v['serviceId']);integer(v['generation'], 0, 2**53-1)
    if v['mode'] not in ('mock', 'live') or (v['mode'] == 'mock' and v['generation'] != 0):
        raise Reject()
    obj(v['interpreter'], ('model', 'revision', 'precision'));obj(v['parser'], ('model', 'revision'))
    if v['interpreter']['model'] != 'Qwen/Qwen3.5-9B' or v['interpreter']['precision'] != 'BF16' or v['parser']['model'] != 'PaddlePaddle/PaddleOCR-VL-1.6':
        raise Reject()
    for m in (v['interpreter'], v['parser']):
        text(m['revision'], 128)
        if v['mode'] == 'live' and not re.fullmatch('[a-f0-9]{40}', m['revision']):
            raise Reject()
    return v


def box(v):
    obj(v, ('x', 'y', 'width', 'height'))
    integer(v['x']);integer(v['y']);integer(v['width'], 1);integer(v['height'], 1)
    return v


def contains(a, b):
    return b['x'] >= a['x'] and b['y'] >= a['y'] and b['x'] + b['width'] <= a['x'] + a['width'] and b['y'] + b['height'] <= a['y'] + a['height']


def manifest(v):
    obj(v, ('reference', 'sha256', 'mediaType', 'coordinateSpace', 'pages', 'crops'))
    ref = v['reference']
    if not isinstance(ref, dict) or len(ref) != 1:
        raise Reject()
    if 'fileId' in ref:
        ident(ref['fileId'])
    elif 'workspacePath' in ref:
        path = text(ref['workspacePath'], 1000)
        if re.search(r'[:\\%?#\r\n\t]', path) or path.startswith('/') or any(s in ('', '.', '..') for s in path.split('/')) or len(path.split('/')) > 32:
            raise Reject()
    else:
        raise Reject()
    if not isinstance(v['sha256'], str) or not SHA.fullmatch(v['sha256']) or v['mediaType'] not in ('image/png', 'image/jpeg', 'application/pdf') or v['coordinateSpace'] != 'oriented_page_pixels':
        raise Reject()
    pages = arr(v['pages'], 4);seen = set()
    if not pages:
        raise Reject()
    for p in pages:
        obj(p, ('page', 'width', 'height', 'originalWidth', 'originalHeight', 'orientation'), ('pdf',))
        integer(p['page'], 1);integer(p['orientation'], 1, 8)
        for k in ('width', 'height', 'originalWidth', 'originalHeight'):
            integer(p[k], 1, 4096)
        swap = p['orientation'] >= 5
        if p['page'] in seen or p['width'] * p['height'] > 16000000 or p['width'] != p['originalHeight' if swap else 'originalWidth'] or p['height'] != p['originalWidth' if swap else 'originalHeight']:
            raise Reject()
        seen.add(p['page'])
        if v['mediaType'] == 'application/pdf':
            pdf = obj(p.get('pdf'), ('widthPoints', 'heightPoints', 'rotation'))
            if pdf['rotation'] not in (0, 90, 180, 270) or any(type(pdf[k]) not in (int, float) or not 0 < pdf[k] <= 100000 for k in ('widthPoints', 'heightPoints')):
                raise Reject()
        elif 'pdf' in p or p['page'] != 1 or len(pages) != 1:
            raise Reject()
    seen = set()
    for c in arr(v['crops'], 8):
        obj(c, ('id', 'page', 'x', 'y', 'width', 'height'));ident(c['id']);integer(c['page'], 1)
        b = box({k: c[k] for k in ('x', 'y', 'width', 'height')})
        p = next((p for p in pages if p['page'] == c['page']), None)
        if c['id'] in seen or p is None or not contains(dict(x=0, y=0, width=p['width'], height=p['height']), b):
            raise Reject()
        seen.add(c['id'])
    return v


def runtime_profile(metadata):
    source=manifest(metadata['source'])
    if len(source['pages'])!=1 or any(p['width']*p['height']>2097152 for p in source['pages']) or len(source['crops'])>8:
        raise Reject('source_too_large',413)
    return source


def decode_png(data, deadline=None):
    """Bounded normalized 8-bit noninterlaced PNG decoder. No filesystem input.
    Reject unsupported palette/16-bit/interlaced/APNG instead of implicit conversion.
    """
    if not isinstance(data, bytes) or len(data) > IMAGE_CAP or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise Reject('invalid_source')
    pos = 8;packed = bytearray();header = None;ended = False;idat_done = False;seen_idat = False
    while pos < len(data):
        if deadline is not None and time.monotonic()>=deadline:raise Reject('timeout',408)
        if pos + 12 > len(data):
            raise Reject('invalid_source')
        n = struct.unpack('>I', data[pos:pos+4])[0];kind = data[pos+4:pos+8]
        if pos+n+12 > len(data) or n > IMAGE_CAP:
            raise Reject('invalid_source')
        chunk = data[pos+8:pos+8+n]
        crc = struct.unpack('>I', data[pos+8+n:pos+12+n])[0]
        if zlib.crc32(kind+chunk) & 0xffffffff != crc:
            raise Reject('invalid_source')
        if header is None and kind != b'IHDR':
            raise Reject('invalid_source')
        if kind == b'IHDR':
            if header is not None or n != 13:
                raise Reject('invalid_source')
            w,h,depth,color,compression,filtration,interlace = struct.unpack('>IIBBBBB', chunk)
            if not 0 < w <= 4096 or not 0 < h <= 4096 or w*h > 16000000 or depth != 8 or color not in (0,2,4,6) or (compression,filtration,interlace) != (0,0,0):
                raise Reject('invalid_source')
            channels = {0:1,2:3,4:2,6:4}[color];header=(w,h,channels,color)
        elif kind == b'IDAT':
            if idat_done:
                raise Reject('invalid_source')
            seen_idat = True;packed.extend(chunk)
        elif kind == b'IEND':
            if n or not seen_idat or pos+n+12 != len(data):
                raise Reject('invalid_source')
            ended=True;break
        elif kind in (b'acTL', b'fcTL', b'fdAT') or not kind[0] & 32:
            raise Reject('invalid_source')
        elif seen_idat:
            idat_done=True
        pos += n+12
    if not ended:
        raise Reject('invalid_source')
    w,h,channels,color=header;stride=w*channels;expected=h*(stride+1)
    try:
        dec=zlib.decompressobj();raw=dec.decompress(bytes(packed), expected+1)
        if len(raw)!=expected or not dec.eof or dec.unused_data or dec.unconsumed_tail:
            raise Reject('invalid_source')
    except zlib.error:
        raise Reject('invalid_source')
    rows=[];prior=bytearray(stride)
    for y in range(h):
        if deadline is not None and time.monotonic()>=deadline:raise Reject('timeout',408)
        flag=raw[y*(stride+1)];row=bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
        if flag > 4:
            raise Reject('invalid_source')
        for x in range(stride):
            a=row[x-channels] if x>=channels else 0;b=prior[x];c=prior[x-channels] if x>=channels else 0
            if flag==1:predict=a
            elif flag==2:predict=b
            elif flag==3:predict=(a+b)//2
            elif flag==4:
                p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c);predict=a if pa<=pb and pa<=pc else b if pb<=pc else c
            else:predict=0
            row[x]=(row[x]+predict)&255
        rows.append(bytes(row));prior=row
    return w,h,channels,color,rows


def encode_png(w,h,color,rows):
    def chunk(k,v):
        return struct.pack('>I',len(v))+k+v+struct.pack('>I',zlib.crc32(k+v)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,color,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r for r in rows)))+chunk(b'IEND',b'')


def crop_png(data, crop):
    w,h,ch,color,rows=decode_png(data);box(crop)
    if not contains(dict(x=0,y=0,width=w,height=h),crop):raise Reject('invalid_source')
    x,y,cw,hh=(crop[k] for k in ('x','y','width','height'))
    return encode_png(cw,hh,color,[r[x*ch:(x+cw)*ch] for r in rows[y:y+hh]])


def multipart(body, content_type):
    match=re.fullmatch(r'multipart/form-data; boundary=([A-Za-z0-9_-]{1,80})',content_type)
    if not match or len(body)>BODY_CAP:raise Reject()
    boundary=match[1].encode();delimiter=b'\r\n--'+boundary
    if not body.startswith(b'--'+boundary+b'\r\n') or not body.endswith(delimiter+b'--\r\n'):raise Reject()
    parts={};pos=len(boundary)+4
    while True:
        end=body.find(b'\r\n\r\n',pos)
        if end<0 or end-pos>2048:raise Reject()
        try:lines=body[pos:end].decode('ascii').split('\r\n')
        except UnicodeError:raise Reject()
        headers={}
        for line in lines:
            if ': ' not in line:raise Reject()
            k,v=line.split(': ',1);k=k.lower()
            if k in headers or k not in ('content-disposition','content-type'):raise Reject()
            headers[k]=v
        if set(headers)!= {'content-disposition','content-type'}:raise Reject()
        m=re.fullmatch(r'form-data; name="(metadata|page-[0-9]{1,5})"(?:; filename="page-[0-9]{1,5}\.png")?',headers['content-disposition'])
        if not m or m[1] in parts:raise Reject()
        stop=body.find(delimiter,end+4)
        if stop<0:raise Reject()
        parts[m[1]]=(headers['content-type'],body[end+4:stop])
        if len(parts)>5:raise Reject()
        pos=stop+len(delimiter)
        if body[pos:pos+4]==b'--\r\n':
            if pos+4!=len(body):raise Reject()
            break
        if body[pos:pos+2]!=b'\r\n':raise Reject()
        pos+=2
    if 'metadata' not in parts or parts['metadata'][0]!='application/json':raise Reject()
    metadata=parse_json(parts.pop('metadata')[1])
    return metadata,parts


def admission(metadata, parts, service, key, deadline=None):
    obj(metadata, ('schemaVersion','owner','requestId','service','source','pageImages'), ('question',))
    if type(metadata['schemaVersion']) is not int or metadata['schemaVersion']!=1 or identity(metadata['service'])!=service or ident(metadata['requestId'])!=key:raise Reject()
    owner(metadata['owner']);manifest(metadata['source'])
    if 'question' in metadata:text(metadata['question'],4000)
    images={};pis=arr(metadata['pageImages'],4);pages=metadata['source']['pages']
    if len(pis)!=len(pages) or len(parts)!=len(pages):raise Reject()
    for pi in pis:
        obj(pi,('page','sha256','part'));integer(pi['page'],1)
        if pi['part']!=f"page-{pi['page']}" or pi['page'] in images or pi['part'] not in parts:raise Reject()
        mime,data=parts[pi['part']]
        if mime!='image/png' or digest(data)!=pi['sha256']:raise Reject('invalid_source')
        w,h,*_=decode_png(data,deadline);page=next((p for p in pages if p['page']==pi['page']),None)
        if not page or (w,h)!=(page['width'],page['height']):raise Reject('invalid_source')
        images[pi['page']]=data
    if sum(map(len,images.values()))>IMAGE_CAP:raise Reject('source_too_large')
    return images


def validate_result(r, source, service):
    """Mirror H039 evidence/graph validation; refuse extra model fields."""
    obj(r, ('schemaVersion','service','source','description','evidence','extraction','observations','uncertainties','derivedConclusions','electricalNetReconstruction'))
    if type(r['schemaVersion']) is not int or r['schemaVersion']!=1 or r['service']!=service or r['source']!=source or r['electricalNetReconstruction']!='not_qualified':raise Reject('invalid_evidence')
    text(r['description'],65536);all_ids={};ev=set()
    def register(k,kind):
        ident(k)
        if k in all_ids:raise Reject('invalid_evidence')
        all_ids[k]=kind
    def refs(values,kinds=None,minimum=0):
        arr(values);ids=[ident(k) for k in values]
        if len(ids)<minimum or len(set(ids))!=len(ids) or any(k not in all_ids or (kinds is not None and all_ids[k] not in kinds) for k in ids):raise Reject('invalid_evidence')
    def evidence(values,minimum=1):refs(values,{'evidence'},minimum)
    def grounded(v,kind):register(v['id'],kind);evidence(v['evidenceIds'])
    for e in arr(r['evidence']):
        obj(e,('id','page','box'),('cropId',));register(e['id'],'evidence');ev.add(e['id']);b=box(e['box'])
        p=next((p for p in source['pages'] if p['page']==e['page']),None)
        if not p or not contains(dict(x=0,y=0,width=p['width'],height=p['height']),b):raise Reject('invalid_evidence')
        if 'cropId' in e:
            c=next((c for c in source['crops'] if c['id']==e['cropId'] and c['page']==e['page']),None)
            if not c or not contains(c,b):raise Reject('invalid_evidence')
    ex=obj(r['extraction'],('text','tables','formulas','layout'))
    for t in arr(ex['text']):
        obj(t,('id','kind','exactText','evidenceIds'))
        if t['kind'] not in ('label','reference_designator','value','unit','pin','dimension','text'):raise Reject('invalid_evidence')
        text(t['exactText']);grounded(t,t['kind'])
    for t in arr(ex['tables']):
        obj(t,('id','cells','evidenceIds'));grounded(t,'table');cells=arr(t['cells']);seen=set()
        if not cells:raise Reject('invalid_evidence')
        for c in cells:
            obj(c,('row','column','exactText','evidenceIds'));integer(c['row']);integer(c['column']);text(c['exactText']);evidence(c['evidenceIds']);key=(c['row'],c['column'])
            if key in seen:raise Reject('invalid_evidence')
            seen.add(key)
    for f in arr(ex['formulas']):obj(f,('id','exactText','evidenceIds'));text(f['exactText']);grounded(f,'formula')
    for l in arr(ex['layout']):obj(l,('id','kind','evidenceIds'));text(l['kind'],128);grounded(l,'layout')
    ob=obj(r['observations'],('components','relationships'))
    for c in arr(ob['components']):obj(c,('id','kind','labelIds','valueIds','unitIds','pinLabelIds','evidenceIds'));text(c['kind'],128);grounded(c,'component')
    for c in arr(ob['relationships']):
        obj(c,('id','kind','from','to','description','evidenceIds'));text(c['description']);grounded(c,'relationship')
        if c['kind'] not in ('spatial','visible_connection','crossing','junction','other'):raise Reject('invalid_evidence')
    for u in arr(r['uncertainties']):obj(u,('id','description','evidenceIds','affectedIds'));register(u['id'],'uncertainty');text(u['description']);evidence(u['evidenceIds'],0)
    for d in arr(r['derivedConclusions']):obj(d,('id','description','basisIds','evidenceIds','uncertaintyIds'));register(d['id'],'derived');text(d['description']);evidence(d['evidenceIds'],0)
    for c in ob['components']:
        for key,kinds in [('labelIds',{'label','reference_designator'}),('valueIds',{'value','dimension'}),('unitIds',{'unit'}),('pinLabelIds',{'pin'})]:refs(c[key],kinds)
    for c in ob['relationships']:refs([c['from'],c['to']],{'component'},2)
    for u in r['uncertainties']:refs(u['affectedIds'])
    for d in r['derivedConclusions']:refs(d['basisIds'],set(all_ids.values())-{'derived','uncertainty'},1);refs(d['uncertaintyIds'],{'uncertainty'})
    if len(canonical(r))>JSON_CAP-32768:raise Reject('invalid_evidence')
    return r


class PrivateLedger:
    """0700 directory + no-follow dirfd + single writer lock + fsync/rename records.
    No path from a request ever reaches this object. Frozen bytes live in private
    JSON base64 records, not in the public wire result or executable serialization.
    """
    def __init__(self, directory, max_jobs=128, max_bytes=256*1024*1024):
        path=os.path.abspath(directory)
        if path!=os.path.realpath(path):raise ValueError('ledger_symlink')
        s=os.lstat(path)
        if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError('private_ledger_required')
        self.fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.lockfd=os.open('owner.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=self.fd);self._check(self.lockfd)
        try:fcntl.flock(self.lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            os.close(self.lockfd);os.close(self.fd);raise
        self.max_jobs=max_jobs;self.max_bytes=max_bytes;self.records={}
        for name in sorted(os.listdir(self.fd)):
            if name=='owner.lock':continue
            if re.fullmatch(r'\.tmp-[a-f0-9]{32}',name):
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.fd);self._check(fd);os.close(fd);os.unlink(name,dir_fd=self.fd);continue
            if not re.fullmatch(r'[a-f0-9]{64}\.json',name):raise ValueError('unknown_ledger_entry')
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.fd)
            try:
                self._check(fd);s=os.fstat(fd)
                if s.st_size>BODY_CAP*2:raise ValueError('record_too_large')
                with os.fdopen(os.dup(fd),'rb') as f:r=parse_json(f.read(),BODY_CAP*2)
                after=os.fstat(fd)
                if (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns):raise ValueError('record_changed')
            finally:os.close(fd)
            m=r['metadata'];identity(m['service']);owner(m['owner']);manifest(m['source']);ident(m['requestId'])
            images={int(k):base64.b64decode(v,validate=True) for k,v in r['images'].items()}
            admission(m,{f'page-{k}':('image/png',v) for k,v in images.items()},m['service'],m['requestId'])
            if name!=self.scope(m)+'.json' or r['fingerprint']!=digest(canonical(m)) or r['job']['owner']!=m['owner'] or r['job']['requestId']!=m['requestId'] or r['job']['service']!=m['service'] or r['job']['source']!=m['source']:raise ValueError('ledger_corrupt')
            ident(r['job']['jobId'])
            j=r['job']
            if type(j.get('schemaVersion')) is not int or j['schemaVersion']!=1 or type(j.get('settled')) is not bool or type(j.get('cancelRequested')) is not bool or j.get('state') not in ('queued','running','cancelling','completed','failed','cancelled','interrupted'):raise ValueError('ledger_job_corrupt')
            if (j['state'] not in TERMINAL and j['settled']) or (j['state'] in ('completed','failed','cancelled') and not j['settled']) or (j['state'] in ('cancelled','cancelling') and not j['cancelRequested']) or (j['state']=='completed' and j['cancelRequested']):raise ValueError('ledger_state_corrupt')
            if r['job']['state']=='completed':validate_result(r['job']['result'],m['source'],m['service'])
            self.records[name[:-5]]=r
        if len(self.records)>max_jobs or sum(len(canonical(r)) for r in self.records.values())>max_bytes:raise ValueError('ledger_cap')
    def _check(self,fd):
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o600:raise ValueError('private_file_required')
    @staticmethod
    def scope(m):return digest(canonical([m['owner']['workspaceId'],m['owner']['sessionId'],m['owner']['runId'],m['requestId']]))
    def save(self,key,r):
        data=canonical(r)
        if key not in self.records and len(self.records)>=self.max_jobs:raise Reject('queue_full',429)
        if sum(len(canonical(v)) for k,v in self.records.items() if k!=key)+len(data)>self.max_bytes:raise Reject('queue_full',429)
        name='.tmp-'+secrets.token_hex(16);fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            os.rename(name,key+'.json',src_dir_fd=self.fd,dst_dir_fd=self.fd);os.fsync(self.fd)
        finally:
            try:os.unlink(name,dir_fd=self.fd)
            except FileNotFoundError:pass
        self.records[key]=copy.deepcopy(r)
    def close(self):os.close(self.lockfd);os.close(self.fd)


class VisionService:
    def __init__(self, ledger, service, backend, *, enabled=False, queue_cap=4, job_timeout=120):
        self.ledger=ledger;self.identity=copy.deepcopy(identity(service));self.backend=backend
        if not 1<=queue_cap<=16 or not 1<=job_timeout<=120:raise ValueError('bounds')
        self.faulted=False;self.enabled=enabled;self.queue_cap=queue_cap;self.job_timeout=job_timeout;self.lock=threading.RLock();self.condition=threading.Condition(self.lock);self.stopping=False;self.active_cancel=None
        with self.lock:
            for k,r in list(ledger.records.items()):
                if r['job']['state'] not in TERMINAL:
                    r=copy.deepcopy(r);r['job'].update(state='interrupted',settled=False,error={'code':'interrupted','message':'Original backend execution settlement is unknown'})
                    r['job'].pop('queuePosition',None);ledger.save(k,r)
        self.worker=threading.Thread(target=self._work,name='vision-owned-worker',daemon=True);self.worker.start()
    def blocked(self):return any(r.get('unsettledBackend') or (r['job']['state']=='interrupted' and not r['job']['settled']) for r in self.ledger.records.values())
    def capabilities(self):
        with self.lock:
            ready=self.enabled and not self.stopping and not self.faulted and self.worker.is_alive() and not self.blocked() and bool(self.backend.ready)
            return dict(schemaVersion=1,service=self.identity,ready=ready,admitting=ready)
    def submit(self,m,parts,key,admission_deadline=None):
        runtime_profile(m);images=admission(m,parts,self.identity,key,admission_deadline);scope=PrivateLedger.scope(m);fingerprint=digest(canonical(m))
        with self.condition:
            if admission_deadline is not None and time.monotonic()>=admission_deadline:raise Reject('timeout',408)
            existing=self.ledger.records.get(scope)
            if existing:
                if existing['fingerprint']!=fingerprint:raise Reject('idempotency_conflict',409)
                return 200,copy.deepcopy(existing['job'])
            if not self.capabilities()['admitting']:raise Reject('unavailable',503)
            if sum(r['job']['state'] not in TERMINAL for r in self.ledger.records.values())>=self.queue_cap:raise Reject('queue_full',429)
            job=dict(schemaVersion=1,jobId='vision-'+secrets.token_hex(16),requestId=m['requestId'],owner=m['owner'],service=m['service'],source=m['source'],state='queued',settled=False,cancelRequested=False)
            r=dict(metadata=copy.deepcopy(m),fingerprint=fingerprint,images={str(k):base64.b64encode(v).decode() for k,v in images.items()},job=job,admittedAt=time.time(),backendEvidence=[])
            try:self.ledger.save(scope,r)
            except Exception:
                self.faulted=True;self.condition.notify_all();raise
            self.condition.notify();return 202,copy.deepcopy(job)
    def get(self,who,*,request_id=None,job_id=None,cancel=False):
        owner(who)
        if request_id is not None:ident(request_id)
        if job_id is not None:ident(job_id)
        with self.condition:
            selected=next(((k,r) for k,r in self.ledger.records.items() if r['job']['owner']==who and ((request_id is not None and r['job']['requestId']==request_id) or (job_id is not None and r['job']['jobId']==job_id))),None)
            if not selected:raise Reject('not_found',404)
            k,r=selected;r=copy.deepcopy(r);j=r['job']
            if cancel and j['state'] not in TERMINAL:
                j['cancelRequested']=True
                if j['state']=='queued':j.update(state='cancelled',settled=True)
                else:
                    j['state']='cancelling'
                    if self.active_cancel:self.active_cancel.set()
                try:self.ledger.save(k,r)
                except Exception:
                    self.faulted=True;self.condition.notify_all();raise
                self.condition.notify()
            return copy.deepcopy(j)
    def _work(self):
        try:self._work_inner()
        except BaseException:
            # Keep the last durable state; never forge a terminal transition on
            # persistence failure. Even an unexpected worker death closes admission.
            with self.condition:self.faulted=True;self.condition.notify_all()
    def _work_inner(self):
        while True:
            with self.condition:
                selected=None
                while not self.stopping and selected is None:
                    if not self.faulted and not self.blocked():selected=next(((k,r) for k,r in self.ledger.records.items() if r['job']['state']=='queued'),None)
                    if selected is None:self.condition.wait(.2)
                if self.stopping:return
                key,r=selected;r=copy.deepcopy(r);r['job']['state']='running';self.ledger.save(key,r);cancel=threading.Event();self.active_cancel=cancel
            def checkpoint(evidence):
                # A backend marks intent before every remote dispatch, then records the
                # literal bounded response. If persistence fails, no next dispatch occurs.
                with self.lock:
                    cur=copy.deepcopy(self.ledger.records[key]);cur['backendEvidence'].append(evidence)
                    try:self.ledger.save(key,cur)
                    except BaseException:
                        self.faulted=True;self.condition.notify_all();raise
            deadline=time.monotonic()+self.job_timeout;settled=False;result=None
            try:
                images={int(k):base64.b64decode(v) for k,v in r['images'].items()}
                outcome=self.backend.execute(copy.deepcopy(r['metadata']),images,cancel,deadline,checkpoint)
                settled=outcome.settled
                if settled:result=validate_result(outcome.result,r['metadata']['source'],r['metadata']['service'])
            except BackendFailure as e:settled=e.settled
            except Reject:settled=True # Validation occurs only after a settled backend response.
            except Exception:settled=False
            with self.condition:
                if self.faulted:return # Retain last durable running state after checkpoint failure.
                cur=copy.deepcopy(self.ledger.records[key]);j=cur['job'];self.active_cancel=None
                if not settled:
                    if j['cancelRequested']:j.update(state='cancelling',settled=False)
                    else:j.update(state='interrupted',settled=False,error={'code':'interrupted','message':'Backend dispatch settlement unknown; owned runtime boundary required'})
                    # Also block cancelling unknown jobs, using a durable barrier.
                    cur['unsettledBackend']=True
                elif j['cancelRequested']:j.update(state='cancelled',settled=True)
                elif result is not None:j.update(state='completed',settled=True,result=result)
                else:j.update(state='failed',settled=True,error={'code':'analysis_failed','message':'Bounded model response or evidence rejected'})
                self.ledger.save(key,cur);self.condition.notify()
                if not settled:
                    # Never move to another inference while the remote engine may run.
                    while not self.stopping:self.condition.wait(.2)
                    return
    def close(self,timeout=2):
        with self.condition:
            self.stopping=True
            if self.active_cancel:self.active_cancel.set()
            self.condition.notify_all()
        self.worker.join(timeout)
        # Caller must retain ledger ownership if a non-cooperative backend is alive.
        return not self.worker.is_alive()


class BoundedHTTPServer(ThreadingMixIn,HTTPServer):
    daemon_threads=True
    def __init__(self,address,service,bearer,max_connections=8,request_seconds=10):
        if address[0]!='127.0.0.1':raise ValueError('loopback_required')
        if not isinstance(bearer,str) or not re.fullmatch(r'[\x21-\x7e]{16,256}',bearer):raise ValueError('private_bearer_required')
        if not .05<=request_seconds<=10:raise ValueError('request_deadline')
        self.request_seconds=request_seconds;self.service=service;self.bearer=bearer;self.slots=threading.BoundedSemaphore(max_connections);super().__init__(address,Handler)
    def handle_error(self,request,client_address):pass # No public diagnostic/credential stack traces.
    def process_request(self,request,client_address):
        if not self.slots.acquire(False):request.close();return
        try:super().process_request(request,client_address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass # Never emit bearer, paths, question, or diagnostics.
    def setup(self):
        super().setup();self.expired=threading.Event();self.deadline=time.monotonic()+self.server.request_seconds
        self.connection.settimeout(self.server.request_seconds)
        def expire():
            self.expired.set()
            try:self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.timer=threading.Timer(self.server.request_seconds,expire);self.timer.daemon=True;self.timer.start()
    def finish(self):
        self.timer.cancel()
        try:super().finish()
        except OSError:pass
    def _deadline(self):
        if self.expired.is_set() or time.monotonic()>=self.deadline:raise Reject('timeout',408)
    def _reply(self,status,data):
        raw=canonical(data)
        if len(raw)>JSON_CAP:status=500;raw=b'{"error":{"code":"invalid_response"}}'
        self.close_connection=True
        try:
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Connection','close');self.end_headers();self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError,OSError):pass
    def do_GET(self):self._route(False)
    def do_POST(self):self._route(True)
    def _route(self,post):
        try:
            self._deadline()
            if len(self.headers.get_all('Authorization',[]))!=1 or not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+self.server.bearer):raise Reject('unauthorized',401)
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))>1 or len(self.headers.get_all('Content-Type',[]))>1:raise Reject()
            if not post:
                if self.path!='/v1/technical-vision/capabilities' or self.headers.get('Content-Length','0')!='0':raise Reject('not_found',404)
                return self._reply(200,self.server.service.capabilities())
            value=self.headers.get('Content-Length','')
            if not re.fullmatch(r'[0-9]{1,9}',value):raise Reject()
            n=int(value);cap=BODY_CAP if self.path=='/v1/technical-vision/jobs' else 4096
            if n<1 or n>cap:raise Reject('source_too_large',413)
            body=self.rfile.read(n)
            if len(body)!=n:raise Reject()
            if self.path=='/v1/technical-vision/jobs':
                if len(self.headers.get_all('Idempotency-Key',[]))!=1:raise Reject()
                m,parts=multipart(body,self.headers.get('Content-Type',''));self._deadline();status,job=self.server.service.submit(m,parts,self.headers['Idempotency-Key'],self.deadline);return self._reply(status,job)
            if self.headers.get('Content-Type')!='application/json':raise Reject()
            m=parse_json(body,4096);obj(m,('schemaVersion','owner'))
            if type(m['schemaVersion']) is not int or m['schemaVersion']!=1:raise Reject()
            match=re.fullmatch(r'/v1/technical-vision/(jobs|requests)/([a-zA-Z0-9_-]{1,80})/(status|cancel)',self.path)
            if not match or (match[1]=='requests' and match[3]!='status'):raise Reject('not_found',404)
            job=self.server.service.get(m['owner'],request_id=match[2] if match[1]=='requests' else None,job_id=match[2] if match[1]=='jobs' else None,cancel=match[3]=='cancel');self._reply(200,job)
        except Reject as e:self._reply(e.status,{'error':{'code':e.code}})
        except Exception:self._reply(503,{'error':{'code':'unavailable'}})
