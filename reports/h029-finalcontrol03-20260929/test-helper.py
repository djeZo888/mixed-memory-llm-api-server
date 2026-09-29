import ast, copy, hashlib, json
from pathlib import Path
source=Path(__file__).with_name('DEPLOY-CONTROL.py').read_text()
names={'require','canonical_mounts','launch_components','require_native_equal'}
module=ast.parse(source)
module.body=[node for node in module.body if isinstance(node,ast.FunctionDef) and node.name in names]
ns={'json':json,'hashlib':hashlib}
exec(compile(module,'DEPLOY-CONTROL.py','exec'),ns)
base={'Config':{'Env':['private-fixture=value']},'HostConfig':{'Binds':['a:b']},'Mounts':[{'Type':'bind','Source':'a','Destination':'b','RW':False,'extra':{'retain':[1,2]}},{'Type':'bind','Source':'c','Destination':'d','RW':True}], 'Path':'run','Args':['x','y']}
def identity(value):
    components,hashes=ns['launch_components'](value)
    return [{'componentSha256':hashes,'launchSha256':hashlib.sha256(json.dumps(components,sort_keys=True).encode()).hexdigest()}]
checks=[]
def equal(label, changed):
    ns['require_native_equal'](identity(base),identity(changed));checks.append({'check':label,'pass':True})
def reject(label,changed,code):
    try:ns['require_native_equal'](identity(base),identity(changed))
    except RuntimeError as error:assert str(error)==code
    else:raise AssertionError(label)
    checks.append({'check':label,'pass':True,'code':code})
v=copy.deepcopy(base);v['Mounts'].reverse();equal('mount_reorder_equality',v)
v=copy.deepcopy(base);v['Mounts'].append(copy.deepcopy(v['Mounts'][0]));reject('duplicate_multiplicity',v,'native_component_changed_Mounts')
for component,value in [('Config',{'Env':['changed']}),('HostConfig',{'Binds':['a:c']}),('Path','other'),('Args',['y','x'])]:
    v=copy.deepcopy(base);v[component]=value;reject(component+'_mutation',v,'native_component_changed_'+component)
for field,value in [('Source','changed'),('Destination','changed'),('RW',True),('extra',{'retain':[2,1]})]:
    v=copy.deepcopy(base);v['Mounts'][0][field]=value;reject('mount_'+field+'_mutation',v,'native_component_changed_Mounts')
for value in [None,{},[None],[[]],[{}],[{'Source':'a','Destination':'b','RW':1}]]:
    v=copy.deepcopy(base);v['Mounts']=value;reject('invalid_mount_shape',v,'native_mounts_invalid_shape')
print(json.dumps({'status':'PASS','tests':len(checks),'checks':checks,'helperSha256':hashlib.sha256(source.encode()).hexdigest()},indent=2))
