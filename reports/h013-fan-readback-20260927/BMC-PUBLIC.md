# BMC public discovery

Observed 2026-09-27T04:20:01.681314+00:00; completed 2026-09-27T04:21:23.383633+00:00.
Source base verified: `31522361aee0b2eb3fa0037c0820c9cc1708cecd`.

Only this Mac contacted `10.156.100.40:443`: one unauthenticated GET each to `/` and `/redfish/v1`, plus certificate handshakes. No redirects or advertised links followed, no scripts executed, credentials supplied, authentication attempts, setters, resets, OEM commands, scans, model activity, or other hosts contacted. GET connect/total limits: 4/12 seconds; subprocess cap: 15 seconds; body cap: 131072 bytes per endpoint. TLS socket timeout: 4 seconds. No Git commit.

| Endpoint | HTTP | Server | WWW-Authenticate |
|---|---|---|---|
| `https://10.156.100.40/` | 200 | `lighttpd` | absent |
| `https://10.156.100.40/redfish/v1` | 200 | `AMI MegaRAC Redfish Service` | absent |

Landing page: gzip HTML (1145 received bytes), empty `<title>`, dynamic application shell containing `Processing ...`. Advertised stylesheet `/styles.min.css`; script `/source.min.js` with `data-main="/app/main"`; conditional IE<9 script references `/libs/js/html5shiv.js` and `/libs/js/respond.min.js`. None fetched. AMI copyright 2016–2017 is not firmware version evidence.

Redfish public root advertises `Name: Root Service`, `Product: AMI Redfish Server`, `Vendor: AMI`, `RedfishVersion: 1.11.0`, `Oem.Ami.RtpVersion: 13.03`, `@odata.type: #ServiceRoot.v1_7_0.ServiceRoot`; HTTP `OData-Version: 4.0`, `Allow: GET`. Header schema link separately names `ServiceRoot.v1_5_2.json`; these are recorded as advertised, not reconciled or firmware-qualified. Protocol flags advertise DeepPATCH true, DeepPOST false, DeepOperations MaxLevels 6, ExpandQuery MaxLevels 5 and query features (complete values in JSON). No mutation was attempted; these flags do not establish fan control or role permission.

Advertised JSON resource links (unvisited):

- `/redfish/v1`
- `/redfish/v1/AccountService`
- `/redfish/v1/CertificateService`
- `/redfish/v1/Chassis`
- `/redfish/v1/CompositionService`
- `/redfish/v1/EventService`
- `/redfish/v1/JsonSchemas`
- `/redfish/v1/SessionService/Sessions`
- `/redfish/v1/Managers`
- `/redfish/v1/Oem/Ami/Configurations`
- `/redfish/v1/Oem/Ami/InventoryData/Status`
- `/redfish/v1/Registries`
- `/redfish/v1/SessionService`
- `/redfish/v1/Systems`
- `/redfish/v1/TaskService`
- `/redfish/v1/TelemetryService`
- `/redfish/v1/UpdateService`

Additional header schema links: `http://redfish.dmtf.org/schemas/v1/ServiceRoot.v1_5_2.json` and `/redfish/v1/JsonSchemas/AMIServiceRoot.v1_0_0.json`; unvisited. Complete response headers and bodies are in `bmc-public-receipts/`.

TLS verification **failed** with `unable to get local issuer certificate`. A separate unverified handshake retrieved the leaf for inspection; HTTPS metadata used verification bypass and does not establish trusted identity. TLS observed: `TLSv1.3`, `TLS_AES_256_GCM_SHA384`.

```text
subject=C=US, ST=Georgia, L=Duluth, O=AMI, OU=MEGARAC, CN=ami.com, emailAddress=megarac@ami.com
issuer=C=US, ST=Georgia, L=Norcross, O=American Megatrends International LLC (AMI), OU=Service Processors, CN=megarac.com, emailAddress=support@ami.com
notBefore=Jan  1 05:00:07 1980 GMT
notAfter=Dec 29 05:00:07 1989 GMT
sha256 Fingerprint=0F:1E:E5:47:ED:BD:BC:A3:46:EA:2D:88:4D:32:71:A8:F2:83:51:D5:7A:16:BA:A9:11:C3:88:19:80:63:F7:EC
X509v3 Subject Alternative Name:
    DNS:megarac.com, DNS:169.254.0.17, IP Address:169.254.0.17
```

The leaf expired in 1989 and its SAN does not contain `10.156.100.40`. Subject and issuer differ; this evidence does not justify calling the leaf self-signed. The verification error above is the actual verifier result; expiration/address mismatch are additional certificate observations.

Unknown: availability and privilege mapping of an **Operator** role; existence/creation or sufficiency of the proposed dedicated **sova** account; Redfish fan telemetry/control endpoints, supported setters and OEM behavior; BMC board/model and firmware release; trusted endpoint identity. The AccountService, Chassis and Managers links prove only advertisement of resources. No authentication or account inspection occurred, and these two public pages do not prove fan control.

Independent offline review checked the landing shell and its asset references. JSON preserves exact public API metadata. Raw receipts contain no supplied credentials; Set-Cookie/authorization header values are redacted if present. The original compressed landing body and separately decoded HTML are retained. Receipt SHA-256 values are in `bmc-public-receipts/SHA256SUMS.txt`.
