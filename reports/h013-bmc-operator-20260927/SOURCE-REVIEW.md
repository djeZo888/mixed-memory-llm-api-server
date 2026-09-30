# H013 BMC Operator: independent source review

2026-09-27, local mac-worker2 child review, public sources only. No SSH, private
BMC, ai-vm, Proxmox, control operation, or account/credential access performed.
This report supplements live filtered receipts; it does not establish installed
capability or actual Operator permission.

## New official source evidence

[ASUS E26328 IPMI manual revision 3](https://dlcdnets.asus.com/pub/ASUS/mb/Add-on_card/IPMI_EXPANSION_CARD/E26328_IPMI_Card_EM_V3_WEB.pdf)
was fetched and text-extracted locally (148 PDF pages; SHA256
`107a73c0cc5344486d95556fec104c1195f83710f732da70474b4b1cb91eb98f`).
The prior ASUS-EVIDENCE report had verified its listing but not its contents.

- Printed 3-61 (PDF 101): onboard fan support depends on motherboard BIOS;
  firmware >=1.1.16 and BIOS Onboard Fan Control Source = IPMI are prerequisites.
  This is a capability/ownership check, not authorization for a BIOS change.
- Printed 3-62 (PDF 102): generic/full-speed UI modes and temperature curves;
  missing selected source falls back to CPU, then 60%. This fails the requested
  unknown/stale/offline-to-100% policy.
- Printed 3-63–3-65 and A-5–A-6 (PDF 103–105,137–138) document OEM IPMI fan
  protocol: full-speed mode value `0x03`; mode setter netfn/command `0x30/0x0E`.
  Its full-speed form has no header index. It is not proved header-specific.
  Read protocol exposes PWM count, name, existing bits/display order and mode.
  No raw invocation was executed or proposed for this TCP443-only discovery.
- These fan sections do not specify a BMC role requirement. Running a Windows
  command prompt as administrator is not evidence of required BMC Administrator.

## Redfish and header evidence

[ASUS Redfish User Manual v1.4.05](https://dlcdnets.asus.com/pub/ASUS/server/ESCN8-E11/Manual/ASUS_Redfish_User_Manual_V1.4.05_20250220_standard.pdf?model=ESC+N8-E11)
printed 18 documents Basic Auth. Printed 39–41 documents GET
`/redfish/v1/Chassis/Self/Thermal`; its example fan carries Name, MemberId,
SensorNumber, RPM and Oem.Ami.OwnerLUN. The reviewed contents/thermal section
provide no fan setter or fan-write privilege mapping. This server manual is
cross-product source context, not confirmation of WRX90 firmware support.

[WRX90E-SAGE SE E23789 board manual](https://dlcdnets.asus.com/pub/ASUS/mb/SocketsTR5/Pro_WS_WRX90E-SAGE_SE/E23789_Pro_WS_WRX90E-SAGE_SE_EM_V2_WEB.pdf)
printed 1-10–1-11 labels CHA_FAN3 and lists its default as Q-Fan controlled,
3A/36W, shared-control column `-`. Only CPU_FAN/CPU_OPT have shared group A.
This is not a mapping to Redfish MemberId, sensor number or PWM index. Current
BIOS/BMC arbitration and installed header routing require live evidence.

The [board-specific ASUS product page](https://www.asus.com/motherboards-components/motherboards/workstation/pro-ws-wrx90e-sage-se/)
explicitly supports IPMI Web UI fan control. It marks BIOS Q-FAN and Windows
Fan Xpert control as requiring BMC_SW disabled. This confirms a vendor-supported
BMC management route for the board, with distinct ownership requirements; no
hardware switch was changed.

A complete local text extraction of ASUS Redfish v1.4.05 found no occurrences of
FanDuty, PWM, full speed or ConfigureManager. Exact public ASUS/AMI searches did
not establish OEM Thermal.Mode/PWM write semantics or its role requirement.

## Review conclusion / next safe verification

There is no currently proved HTTPS full-speed setter with exact body, header
scope and role requirement from public sources alone. Do not copy another
vendor's Redfish Oem fan fields, infer PWM3, or extrapolate generic Operator
privileges. Public documentation now gives a concrete vendor protocol lead,
but the authorized HTTPS path still needs installed UI/schema evidence.

Follow the service's advertised fan/control/schema/privilege links and installed
UI static resources. Correlate a resource explicitly labeled CHA_FAN3 with a
control name/index through vendor-provided data; retain RPM and current duty/mode
separately. Read-only GET success and Allow/PATCH advertisement cannot prove fan
write authorization. If no HTTPS API mapping is exposed, the next safe step is
ASUS confirmation for the exact installed firmware of its HTTPS control API,
CHA_FAN3-to-PWM mapping, required role, ownership and failure/persistence behavior.
No lower-duty automation is ready: the vendor's documented sensor fallback does
not fail full, and a host-dependent loop alone cannot cover loss of that host.

## Offline probe review (initial revision)

`probe.py` was inspected before later discovery phases. Exact HOST/443 are fixed.
`PinnedConnection.connect()` checks SHA256 of the actual connected peer DER;
`request()` calls connect before credential loading/auth-header construction.
Any library reconnect re-enters that check. The probe refuses redirect follow,
accepts GET/OPTIONS only, checks secret-file/parent ownership and modes, bounds
per-request time/body and per-process request count, and filters response fields.
No critical pin-before-auth issue was found. Suggested OwnerLUN whitelist support
and explicit summed multi-invocation request counts. The reviewed 05:19 UTC
internal deadline was later than this child's 05:17 UTC cutoff; root was notified.
No write permission is inferred from these source checks.

Offline `python3 reports/h013-bmc-operator-20260927/test_probe.py -v` passed
11 safety tests in 0.048 seconds after adding bounded-gzip coverage. Tests forbid real
network connection and cover peer-pin ordering/change/reconnect, method/path
restrictions, redirect refusal, compressed/decompressed body bounds, filtering, credential permissions and
symlink refusal. These are client safety tests, not BMC acceptance.

## Final source qualification

The exact official [DMTF Thermal1.5.3 schema](https://redfish.dmtf.org/schemas/v1/Thermal.v1_5_3.json) permits Fan.ReadingUnits RPM or Percent (and null), with no default for omission. The installed fan reading14640 must remain raw/unverified units.

Installed UI source subsequently captured in UI-SOURCE.json distinguishes Administrator-gated global mode/source controls from Operator-gated ManualView per-PWM controls. ManualItemView sends a five-point curve, not a proved volatile duty request. Actual backend write authorization, PWMSrc semantics and persistence remain untested. Public source review does not close the missing live PWMName/PWMNum/index binding.
