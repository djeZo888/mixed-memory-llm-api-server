# Manual Proxmox capture — final root-requested revision

Root sends this block only after W1's active stable-decode receipt. Run once in the existing privileged Proxmox **Bash** shell; root aligns the printed UTC bracket with W1's request timestamps. No scheduler or automatic repeat. Private diagnostic files are retained under `/tmp/sova-umc.*`.

```bash
(
set -euo pipefail
umask 077
export LC_ALL=C TZ=UTC
H016_DIR=$(mktemp -d /tmp/sova-umc.XXXXXX)
H016_STAMP=$(date -u +%Y%m%dT%H%M%S.%NZ)
H016_PREFIX="$H016_DIR/$H016_STAMP"
H016_EVENTS=()
for H016_CH in {0..7}; do
  H016_EVENTS+=(-e "amd_umc_${H016_CH}/event=0x0a,rdwrmask=0x1/")
  H016_EVENTS+=(-e "amd_umc_${H016_CH}/event=0x0a,rdwrmask=0x2/")
done
printf 'capture_dir=%s\nstart_utc=%s\n' "$H016_DIR" "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" | tee "$H016_PREFIX.utc.txt"
H016_RC=0
perf stat -a -C 0 --no-scale --no-merge --no-big-num -x ';' -vv \
  -I 5000 --interval-count 4 "${H016_EVENTS[@]}" \
  -o "$H016_PREFIX.stat.txt" 2> "$H016_PREFIX.stderr.txt" || H016_RC=$?
printf 'end_utc=%s\nperf_exit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" "$H016_RC" | tee -a "$H016_PREFIX.utc.txt"
cat "$H016_PREFIX.stat.txt" "$H016_PREFIX.stderr.txt"
exit "$H016_RC"
)
```

Four requested 5-second intervals, about 20 seconds total. Each usable interval must contain **16 distinct PMU/direction rows**: 0–7, mask1 reads/mask2 writes. Preserve any terminal partial interval but do not treat it as another full five seconds. `-C 0` selects the reported representative CPU for all eight uncore PMUs; it **does not filter traffic to CPU0**. This is host-wide traffic, including other VMs, not process attribution or DIMM-slot mapping.

The `.stat.txt` contains semicolon-separated interval rows **and** verbose raw lines, not pure CSV. CSV rows: relative timestamp, optional CPU identifier, count, unit, event, runtime, running percentage, optional metrics. `-vv` writes exact cumulative `value enabled running` triples into the same stat file; stderr goes to its separate file. For interval coverage, subtract successive raw enabled/running values (initial values zero). Require positive deltas and **delta_running == delta_enabled** for every channel/direction; rounded `100.00%` alone is insufficient. Require exit0, all16 events, no unsupported/not-counted/error rows and W1 decode overlap. Keep failures; no retry or silent scaling.

Use actual interval timestamp differences for elapsed seconds (first timestamp minus zero); retain each event's exact enabled/running delta as coverage evidence. Do not assume precisely5 or20 seconds. Report per-channel read/write raw CAS and `CAS/s = CAS / elapsed_s`; only for complete coverage calculate **estimated decimal GB/s = CAS * 64 / elapsed_s / 1e9**. Sum matching channels/directions for the same interval. The two subchannels are already included: no extra factor2. This is estimated CAS-derived bandwidth, not independently measured bytes, a theoretical ceiling or evidence of saturation.

Exact source: AMD PMC58550 Rev0.02 printed pp35–36; retained upstream UMC event/format definitions; [perf v6.12.107 manual](https://github.com/gregkh/linux/blob/v6.12.107/tools/perf/Documentation/perf-stat.txt); [raw enabled/running triples](https://github.com/gregkh/linux/blob/v6.12.107/tools/perf/builtin-stat.c#L353); [merged Linux v7.0.14 estimated-bandwidth formulas, lines305–326](https://github.com/gregkh/linux/blob/v7.0.14/tools/perf/pmu-events/arch/x86/amdzen5/recommended.json#L305). `-I` timestamps are monotonic relative seconds, not UTC; shell UTC markers bracket setup/teardown and alignment needs host/W1 clock agreement. Source review only: installed perf6.12.107 was not contacted or run by W2.
