"""Offline assertions on exact fixture/capture boundaries and fail-closed safety."""
import ast,copy,importlib.util,pathlib
here=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixture',here/'fixture_native.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
f.self_test()
x=f.build_fixture(f._CharacterTokenizer(),65536,'offline-long',True)
assert x['rendered_tokens']==65536 and 'twenty numbered' in x['content']
tree=ast.parse((here/'job-body.py').read_text());namespace={}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('numeric','safety')],type_ignores=[]),'safety','exec'),namespace)
namespace.update(GPUS={'flash':'f','qwen0':'q','qwen1':'r','image':'i'},limits={x:85 for x in ('flash','qwen0','qwen1','image')},samples=[])
row={'ram':{'MemTotal':100,'MemAvailable':50},'gpu':{x:{'temperature.gpu':40,'memory.total':100000,'memory.free':20000,'clocks_event_reasons.sw_power_cap':'Active'} for x in 'fqri'},'cgroups':{x:{'memory.swap.current':0,'events':{'oom':0,'max':0,'oom_kill':0}} for x in namespace['GPUS']},'swap':{'pswpin':10,'pswpout':20}}
check=namespace['safety'];assert check(row) is None
bad=copy.deepcopy(row);bad['ram']['MemAvailable']=14;assert check(bad)=='host_reserve_below_15pct'
bad=copy.deepcopy(row);bad['gpu']['f']['temperature.gpu']=85;assert check(bad)=='flash_thermal_limit'
bad=copy.deepcopy(row);bad['gpu']['i']['clocks_event_reasons.hw_power_brake_slowdown']='Active';assert check(bad)=='image_thermal_or_power_brake'
bad=copy.deepcopy(row);bad['cgroups']['qwen0']['memory.swap.current']=1;assert check(bad)=='qwen0_owned_swap'
namespace['samples']=[copy.deepcopy(row) for _ in range(5)];assert check(row) is None
for n,r in enumerate(namespace['samples']):r['swap']['pswpout']=n
bad=copy.deepcopy(row);bad['swap']['pswpout']=5;assert check(bad)=='sustained_swap_io_5_intervals'
print('PASS: long fixture exact fit; reserve, thermal, power brake, owned swap; historical swap permitted; sustained swap stopped')
