# Exact Docker engine probe and selected containment

GPU-free probe on installed Docker29.6.1: dedicated internal bridge accepted configured127.0.0.1:30007 publication, but effective NetworkSettings.Ports was null. Tiny in-container dummy server worked; hostloopback connection refused. Exact diagnostic container was stopped/removed, noGPU requested, registeredguards passed. No model retry occurred. `evidence/internal-network-probe.jsonl` records result.

ROOT-NETWORK-CONTAINMENT-GO prefers internal bridge, but it cannot supply requiredhost127.0.0.1backendendpoint on this engine. Select dedicated ordinary bridge (same soleowned name, newrecordednetworkID), publishing ONLY127.0.0.1:30007; keep nativeHTTPinsidecontainer0.0.0.0 and internal30008/9/10UNPUBLISHED. This is the existing text-port publishing pattern in a separateowned image network, preservingtextnetworks and noadhocglobalfirewallrules. Only exactemptytask-owned internalnetwork is removed/replaced aftersavingitsreceipt. SourcechecksconfiguredAND effectiveportbindings, exactnetworkID/name/label/driver, soleattachment andnoforeignmembers.

Rootnotification beforedeployment; this remainswithinroutineownedbackendnetwork/helperauthorization and documentedsmallestconfigurationcorrection. NoPyTorch/upstreamrepair. Requiredcoldload+warm thensoleeditfollows; currentprecontainmentgenerationevidenceretained.
