#!/usr/bin/env python3
"""Read only available GGUF headers; partial headers are not hash verification."""
import argparse,collections,hashlib,json,pathlib,struct
FMT={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
def inspect(path):
 with open(path,'rb') as f:
  def read(n):
   b=f.read(n)
   if len(b)!=n:raise EOFError('header_incomplete')
   return b
  def num(fmt):return struct.unpack('<'+fmt,read(struct.calcsize('<'+fmt)))[0]
  def string():
   n=num('Q');assert n<64*1024**2;return read(n).decode('utf-8',errors='replace')
  def value(t):
   if t in FMT:return num(FMT[t])
   if t==8:return string()
   if t==9:
    q,n=num('I'),num('Q');assert n<2000000
    vals=[]
    for i in range(n):
     v=value(q)
     if n<150:vals.append(v)
    return vals if n<150 else {'array_type':q,'count':n}
   raise ValueError('unknown_metadata_type')
  assert read(4)==b'GGUF';version=num('I');assert version==3
  nt,nk=num('Q'),num('Q');assert nt<100000 and nk<10000
  meta={}
  for _ in range(nk):
   k=string();v=value(num('I'))
   if k=='tokenizer.chat_template':meta[k]={'sha256':hashlib.sha256(v.encode()).hexdigest(),'bytes':len(v.encode())}
   elif k.startswith(('general.','split.','mimo2.','tokenizer.ggml.')):meta[k]=v
  types=collections.Counter();tensors=[]
  for _ in range(nt):
   name=string();n=num('I');dims=[num('Q') for _ in range(n)];ty=num('I');offset=num('Q');types[ty]+=1;tensors.append({'name':name,'dims':dims,'type_id':ty})
  return {'file':str(path),'bytes_present':pathlib.Path(path).stat().st_size,'header_bytes':f.tell(),'version':version,'tensor_count':nt,'tensor_type_ids':dict(types),'metadata':meta,'tensors':tensors,'note':'Header observation only; full shard SHA256 remains separate.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('files',nargs='+');a=p.parse_args();out=[]
 for f in a.files:
  try:out.append(inspect(f))
  except Exception as e:out.append({'file':f,'error':type(e).__name__})
 print(json.dumps(out,indent=2))
