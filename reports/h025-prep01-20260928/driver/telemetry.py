"""H013 UUID joins/resource guards adapted to structured W1 samples, without hardware I/O."""
from contract import LANES, Refusal, digest, number, require, utc_seconds

THROTTLE = ('hw_thermal_slowdown', 'sw_thermal_slowdown', 'hw_power_brake_slowdown')

def validate_sample(m, row, now, baseline=None, previous=None, guest_swap_streak=0):
    """Return normalized diagnostics and exact fault scopes; unknown never means cancel-all."""
    faults = []
    def fault(reason, lane=None, stop_exact=False):
        faults.append({'reason': reason, 'lane': lane, 'stop_exact': stop_exact})
    try:
        require(row.get('boot_id') == m['boot_id'] and row.get('deployment_sha256') == digest(m), 'identity_drift')
        require(row.get('identities') == {l: m['lanes'][l]['identity'] for l in LANES}, 'identity_drift')
        require(row.get('guard_ok') is True, 'guard_failure')
        start, end, due = (row[k] for k in ('start_monotonic', 'end_monotonic', 'due_monotonic'))
        require(all(number(v) for v in (start, end, due, now)) and 0 <= due <= start <= end <= now, 'telemetry_clock')
        utc_seconds(row['utc'])
        max_delay = m['guard']['max_sample_delay_seconds']
        require(end-due <= max_delay and now-end <= max_delay, 'telemetry_loss_or_delay')
        if baseline is not None:
            require(start >= baseline['start_monotonic'], 'telemetry_reversed')
        require(set(row['gpu']) == {m['lanes'][l]['gpu_uuid'] for l in LANES}, 'gpu_UUID_join_drift')
        require(set(row['cgroups']) == set(LANES), 'cgroup_telemetry_missing')
        for lane in LANES:
            spec = m['lanes'][lane]
            gpu = row['gpu'][spec['gpu_uuid']]
            require(gpu.get('type') == spec['gpu_type'] and gpu.get('family') == spec['gpu_family'], 'gpu_type_drift')
            for key in ('temperature_c', 'power_draw_w', 'power_limit_w', 'utilization_pct',
                        'memory_total_mib', 'memory_used_mib', 'memory_free_mib'):
                require(number(gpu.get(key)) and gpu[key] >= 0, 'mandatory_gpu_telemetry_missing')
            require(0 <= gpu['utilization_pct'] <= 100 and gpu['memory_total_mib'] > 0, 'invalid_gpu_telemetry')
            require(set(gpu.get('clocks', {})) >= {'graphics', 'sm', 'memory'}, 'clocks_missing')
            require(all(number(v) and v >= 0 for v in gpu['clocks'].values()), 'clocks_invalid')
            require(set(gpu.get('throttle', {})) >= set(THROTTLE) | {'sw_power_cap', 'hw_slowdown'}, 'throttle_missing')
            require(all(type(v) is bool for v in gpu['throttle'].values()) and type(gpu.get('power_brake')) is bool, 'throttle_invalid')
            require(gpu.get('ecc_current') == spec['ecc_current'] and gpu.get('ecc_pending') == spec['ecc_pending'], 'ECC_identity_drift')
            for key in ('ecc_uncorrected', 'pcie_replay'):
                require((type(gpu.get(key)) is int and gpu[key] >= 0) or (gpu.get(key) is None and gpu.get('counter_unavailable_reason')), 'error_counter_missing')
            fan = gpu.get('integrated_fan', {})
            require(set(fan) >= {'target_pct', 'current_pct', 'rpm', 'unavailable_reason'}, 'integrated_fan_availability_missing')
            for key in ('target_pct', 'current_pct', 'rpm'):
                require(fan[key] is None or (number(fan[key]) and fan[key] >= 0), 'fan_telemetry_invalid')
                if fan[key] is None:
                    require(isinstance(fan['unavailable_reason'], str) and fan['unavailable_reason'], 'fan_unavailable_reason_required')
            if gpu['power_limit_w'] != spec['power_limit_w']:
                fault('power_identity_drift', lane, False)
            if gpu['temperature_c'] >= min(85, spec['critical_c']):
                fault('thermal_limit', lane, True)
            if gpu['power_brake'] or any(gpu['throttle'][k] for k in THROTTLE):
                fault('thermal_or_power_brake', lane, True)
            if gpu['memory_free_mib'] < spec['reserve_mib']:
                fault('GPU_reserve_loss', lane, True)
            cg = row['cgroups'][lane]
            require(all(type(cg.get(k)) is int and cg[k] >= 0 for k in ('memory_current', 'swap_current')), 'cgroup_memory_missing')
            require(set(cg.get('events', {})) >= {'oom', 'oom_kill', 'max'}, 'memory_events_missing')
            require(all(type(v) is int and v >= 0 for v in cg['events'].values()), 'memory_events_invalid')
            require(cg.get('cpu') and all(number(v) for v in cg['cpu'].values()), 'cgroup_cpu_missing')
            if cg['swap_current']:
                fault('owned_swap', lane, True)
            if baseline is not None:
                old = baseline['cgroups'][lane]['events']
                if any(cg['events'][k] > old[k] for k in ('oom', 'oom_kill')):
                    fault('cgroup_OOM_or_limit', lane, True)
                original = baseline['gpu'][spec['gpu_uuid']]
                if any(number(gpu[k]) and number(original[k]) and gpu[k] > original[k] for k in ('ecc_uncorrected', 'pcie_replay')):
                    fault('GPU_error_counter_increase', lane, True)
        guest = row['guest']
        require(all(type(guest.get(k)) is int and guest[k] >= 0 for k in
                    ('ram_total_bytes', 'ram_available_bytes', 'swap_in', 'swap_out')), 'guest_memory_swap_missing')
        require(guest['ram_total_bytes'] > 0 and guest.get('cpu_ticks') and
                all(type(v) is int and v >= 0 for v in guest['cpu_ticks']), 'guest_CPU_missing')
        if guest['ram_available_bytes'] < guest['ram_total_bytes']*m['guard']['min_guest_ram_fraction']:
            fault('guest_RAM_reserve_loss')
        # H013: five consecutive sample-to-sample increases, not growth since
        # phase baseline. One transient bump must not become a persistent streak.
        swap_increased = previous is not None and any(
            guest[k] > previous['guest'][k] for k in ('swap_in', 'swap_out'))
        guest_swap_streak = guest_swap_streak+1 if swap_increased else 0
        if guest_swap_streak >= 5:
            fault('sustained_swap_io_5_intervals')
        kernel = row['kernel']
        require(kernel.get('read_ok') is True and isinstance(kernel.get('events'), list), 'kernel_monitor_lost')
        for event in kernel['events']:
            require(event.get('kind') in ('OOM', 'Xid', 'AER'), 'kernel_event_kind')
            lane = event.get('lane')
            require(lane is None or lane in LANES, 'kernel_event_scope')
            fault('kernel_'+event['kind'], lane, lane is not None)
        from fan_status import validate_fan
        validate_fan(m,row['external_fan'],row['utc'],now)
        # These are GPU draw totals, not host/package/wall or PSU input measurements.
        diagnostics = {'sampling_delay_seconds': end-due, 'query_seconds': end-start,
                       'three_blackwell_draw_w': sum(row['gpu'][m['lanes'][l]['gpu_uuid']]['power_draw_w'] for l in LANES[:3]),
                       'ada_draw_w': row['gpu'][m['lanes']['image']['gpu_uuid']]['power_draw_w'],
                       'host_CPU_package_wall_PSU_power': 'UNAVAILABLE_NOT_MEASURED',
                       'guest_cpu_busy_fraction': None,
                       'guest_swap_increased': swap_increased,
                       'guest_swap_consecutive_intervals': guest_swap_streak}
        if baseline is not None:
            ticks = guest['cpu_ticks']
            prev = baseline['guest']['cpu_ticks']
            require(len(ticks) == len(prev) and len(ticks) >= 4, 'guest_CPU_shape')
            delta = [a-b for a, b in zip(ticks, prev)]
            require(all(x >= 0 for x in delta), 'guest_CPU_counter_reset')
            total = sum(delta[:8])  # guest/guest_nice already included in user/nice
            idle = delta[3]+(delta[4] if len(delta) > 4 else 0)
            if total > 0:
                diagnostics['guest_cpu_busy_fraction'] = (total-idle)/total
        return diagnostics, faults
    except (KeyError, TypeError, ValueError) as exc:
        # Do not hide a previously observed hot lane if a later mandatory field is absent.
        fault(str(exc) if isinstance(exc, Refusal) else 'telemetry_loss_or_invalid_sample')
        return None, faults
