"""Focused complete-mount identity regression; no Docker/network calls."""
import copy,hashlib,importlib.util,json,sys
from pathlib import Path
p=Path(sys.argv[1]);s=importlib.util.spec_from_file_location('candidate',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=[{'Destination':'/z','Source':'/source-z','RW':False,'Type':'bind','Propagation':'rprivate'},{'Destination':'/a','Source':'/source-a','RW':True,'Type':'bind','Propagation':'rprivate'}]
def digest(v):return hashlib.sha256(json.dumps(m.canonical_mounts(v),sort_keys=True).encode()).hexdigest()
assert digest(a)==digest(list(reversed(a)))
for field,value in [('Source','/changed'),('RW',True),('Type','volume'),('Propagation','shared')]:
 b=copy.deepcopy(a);b[0][field]=value;assert digest(a)!=digest(b),field
try:m.canonical_mounts([a[0],a[0]])
except ValueError as e:assert str(e)=='duplicate_mount_destination'
else:raise AssertionError('duplicate accepted')
assert m.canonical_mounts(a)==[a[1],a[0]]
print(json.dumps({'status':'PASS','checks':['reordered_mounts_equal','changed_Source_unequal','changed_RW_unequal','changed_Type_unequal','changed_Propagation_unequal','duplicate_destinations_refused','all_fields_preserved']}))
