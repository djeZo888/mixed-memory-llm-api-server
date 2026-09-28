"""W1 H025 status contract. Read-only; no BMC or integrated-fan writes."""
from contract import require,number,utc_seconds

def validate_fan(m, mirror, now_utc, now_monotonic):
    require(mirror.get('task_id')==m['task_id'] and mirror.get('vm_boot_id')==m['boot_id'],'fan mirror task/boot drift')
    require(0<=now_monotonic-mirror['received_monotonic']<=5 and
            0<=utc_seconds(now_utc)-utc_seconds(mirror['received_utc'])<=5,'fan bridge missing/stale')
    s=mirror['controller'];pins=m['fan_controller']
    require(s.get('schema_version')==1 and all(s.get(k)==pins[k] for k in
            ('gpu_uuid','host_boot_id','pid','source_sha256','started_at','invariant_sha256')),'fan controller identity drift')
    require(s.get('gpu_uuid')==m['lanes']['qwen1']['gpu_uuid'] and s.get('node_boot_id')==m['boot_id'],'fan node/UUID drift')
    require(s.get('state')=='healthy' and s.get('errors')==[],'fan controller unhealthy')
    require(s.get('mode')==4 and s.get('source_bits')==[0,0,0] and
            s.get('channel')=='Zone4(CHA_FAN3)/PWMNum3','fan mode/source/channel drift')
    require(s.get('desired_duty')==s.get('readback_duty') and s.get('readback_duty') in (40,80), 'fan command/readback drift')
    require(s.get('readback_kind')=='first_four_curve_duties_not_measured_pwm','fan readback semantics changed')
    for key in ('updated_at','sampled_at','readback_at','tach_at'):
        require(0<=utc_seconds(now_utc)-utc_seconds(s[key])<=15,'fan original timestamp stale/future:'+key)
    require(number(s.get('telemetry_age_seconds')) and 0<=s['telemetry_age_seconds']<=15,'fan telemetry stale')
    require(number(s.get('temperature_c')) and 0<=s['temperature_c']<85,'fan temperature invalid/hot')
    require(number(s.get('actual_tach')) and s['actual_tach']>0 and s.get('actual_tach_units') is None,'fan rotation/units unproven')
    require(pins.get('idle_actuator_receipt_sha256') and pins.get('idle_actuator_result')=='PASS','idle actuator qualification required')
    return s
