# ASUS external-fan evidence — offline proposal only

Researched 2026-09-27 from primary ASUS and Linux kernel sources. No BMC,
Proxmox, host, VM, NVIDIA device, or installed hwmon interface was contacted.
The server GPU remains **external-control-needed**, never NVML fan success.

## Verified official support and limits

- ASUS's [WRX90E-SAGE SE support page](https://www.asus.com/jp/supportonly/pro%20ws%20wrx90e-sage%20se/helpdesk_manual/)
  lists a shared IPMI manual as applying to ASUS IPMI expansion cards and onboard
  BMC models. Its 2025-07-29 entry links
  [E26328, revision 3](https://dlcdnets.asus.com/pub/ASUS/mb/Add-on_card/IPMI_EXPANSION_CARD/E26328_IPMI_Card_EM_V3_WEB.pdf).
  The support-page listing/link was verified; this revision's complete contents
  were not extracted during this bounded task.
- The readable official [E19387 IPMI manual](https://dlcdnets.asus.com/pub/ASUS/mb/Add-on_card/IPMI_Expansion_Card_EM_WEB_EN.pdf),
  section 3.7.16, printed pages 3-59–3-60 (PDF pages 91–92), documents
  **Settings → Fan Control**, generic/full-speed modes, custom temperature/duty
  curves, and temperature-source selection. This establishes an official
  management path, not installed-board fan identity or an approved programmatic
  write command.
- That manual's temperature-source fallback uses CPU temperature when the
  selected source is missing, then **60%** if CPU temperature is also missing.
  Therefore its documented curve fallback cannot establish the required
  fail-full behavior. The same section says its source settings apply to every
  fan in control mode. A mode change may affect cooling for other host devices.
- ASUS's [board manual, E23789](https://dlcdnets.asus.com/pub/ASUS/mb/SocketsTR5/Pro_WS_WRX90E-SAGE_SE/E23789_Pro_WS_WRX90E-SAGE_SE_EM_V2_WEB.pdf),
  section 1.2, fan/pump headers, printed page 1-10, identifies CHA_FAN1 through
  CHA_FAN5 including CHA_FAN3. A connector label alone does not establish its
  BMC/IPMI fan identifier or Linux PWM index. The expansion-card manual also
  discusses its own eight fan headers; do not transfer that mapping to this
  onboard BMC.
- The current official [Linux asus_ec_sensors documentation](https://docs.kernel.org/hwmon/asus_ec_sensors.html)
  lists Pro WS WRX90E-SAGE SE and describes EC sensor reads protected against
  firmware races using an ACPI mutex. This is sensor-monitoring support, not
  proof of CHA_FAN3 fan-control support on the installed kernel.
- The official [Linux NCT6775 documentation](https://docs.kernel.org/hwmon/nct6775.html)
  documents hardware-monitoring/fan-control capabilities of that driver family.
  Generic driver capabilities cannot identify a motherboard header, confirm
  availability on the installed host, or establish ownership versus firmware.

## Unknown; must remain unqualified

Installed BMC/BIOS/kernel/driver versions, BMC fan inventory and control scope,
the physical fan(s) attached to CHA_FAN3, tachometer identity, supported OEM/API
requests, exact supported full-speed/default semantics and readback, persistence
across failure/reboot, and arbitration with existing BMC/BIOS control are all
**NOT_TESTED**. No IPMI raw command, register, PWM channel number, or write value
is proposed. A fan percentage is an intended setting, not proof of RPM or airflow.

## Safest next verification for root

1. In a separately authorized read-only session, record board and installed
   BMC/BIOS versions, existing fan-control owner and current policy. Inspect the
   authenticated BMC sensor inventory and Fan Control pages without saving,
   changing modes, resetting BMC, or applying a curve. Root relayed the latest
   user-confirmed BMC address as `10.156.100.40`; it was not contacted here.
   Prefer the network BMC route. If using dedicated account `sova`, initially
   consider the Operator role only if its LAN/API access and required privileges
   are supported. No account or privilege is assumed or created here. Keep
   credentials in protected files outside containers, never passwords in chat,
   argv or logs. Exact per-header API, privileges and watchdog mapping remain
   unverified; root/Worker1 owns any later read-only probe.
2. Obtain physical cable/header identification from the responsible operator
   and correlate it with vendor-supported fan sensor IDs and tachometer labels.
   Obtain ASUS confirmation of the exact installed-firmware interface for
   CHA_FAN3, its write scope, default restoration and error behavior. Prefer
   documented read-only inventory/status operations; do not probe by raw writes.
3. If Linux hwmon is considered, inspect existing driver/name/device links and
   readable labels only. Do not load a new module, bypass ACPI resource locks,
   run automatic PWM detection, or infer `pwm3` from CHA_FAN3. Establish which
   controller owns the header and how concurrent firmware control is excluded.
4. Only after that identity/ownership evidence and exact vendor interface are
   reviewed should root design a small host agent. It should consume authenticated
   GPU UUID-bound fresh temperature telemetry and request full speed on stale,
   invalid or missing telemetry. A failed/hung host or BMC cannot be assumed to
   execute a software failsafe; qualify the vendor's independent failure policy.
   No broad status/network daemon is implemented by this candidate.

The requested trigger remains 100% at 70°C; the independent 85°C load-test cutoff
is unchanged. NVIDIA T.Limit is relative and must not replace absolute GPU
temperature. Changing this fan policy together with ECC prevents attributing
the future comparison to ECC alone. Existing 1M request, deadline and scientific
result are outside this proposal and remain untouched.
