"""Read-only NVML fan getters, UUID keyed; no controller/state writes.
RPM ABI verified from installed nvidia-ml-py: version16777228, three uints.
"""
import ctypes as C
class FanSpeedInfo(C.Structure):
 _fields_=[('version',C.c_uint),('fan',C.c_uint),('speed',C.c_uint)]
class FanReader:
 def __init__(self):
  self.lib=C.CDLL('libnvidia-ml.so.1');self.call('nvmlInit_v2',[])
 def call(self,name,types,*args):
  f=getattr(self.lib,name);f.argtypes=types;f.restype=C.c_int
  code=f(*args);assert code==0,'fan_getter_failed:'+name+':'+str(code)
 def sample(self,gpus):
  out={}
  for lane,uid in gpus.items():
   if lane=='qwen1':
    out[uid]={'source':'external_fan_reviewed_phase_readback_no_BMC_contact','intended_percent':None,'rpm':None};continue
   h=C.c_void_p();self.call('nvmlDeviceGetHandleByUUID',[C.c_char_p,C.POINTER(C.c_void_p)],uid.encode(),C.byref(h))
   b=C.create_string_buffer(96);self.call('nvmlDeviceGetUUID',[C.c_void_p,C.c_char_p,C.c_uint],h,b,len(b));assert b.value.decode()==uid
   count=C.c_uint();self.call('nvmlDeviceGetNumFans',[C.c_void_p,C.POINTER(C.c_uint)],h,C.byref(count));assert count.value==(1 if lane=='image' else 2)
   fans=[]
   for i in range(count.value):
    values={'fan':i}
    for field,fn in [('policy','nvmlDeviceGetFanControlPolicy_v2'),('intended_percent','nvmlDeviceGetTargetFanSpeed'),('reported_percent','nvmlDeviceGetFanSpeed_v2')]:
     v=C.c_uint();self.call(fn,[C.c_void_p,C.c_uint,C.POINTER(C.c_uint)],h,i,C.byref(v));values[field]=v.value
    rpm=FanSpeedInfo(16777228,i,0);self.call('nvmlDeviceGetFanSpeedRPM',[C.c_void_p,C.POINTER(FanSpeedInfo)],h,C.byref(rpm));values['rpm']=rpm.speed;fans.append(values)
   out[uid]={'source':'NVML_read_only','fans':fans}
  return out
 def close(self):self.call('nvmlShutdown',[])
