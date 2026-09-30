# Exact production RGB comparison result

Transport/decode/memory PASS, visual fidelity FAIL/partialsemanticedit. Runtime remainswarm; nofurtherinference.

ReviewedAPI07d2a495 protocol.decode_image(output=True,transparent=False) producedRGBreference9756c58b... withidenticalRGBpixels. Generationalpha251..255 (96.338%fullyopaque), raweditalpha225..255 (90.245%fullyopaque). Exactnormalizationsourcehash ebca2b024d236d03475dde15a63414c49fb86714733afa1bbf8ca68d88fd5238; runtimePillow11.3.0.

OnecomparisonPOST atsame1024/40steps/CFG1/seed42 took27.346664s; decodedPNGsha256 a76c98a479c2e319677b931e699373b376846e3bfd2769d18ca66c74c99d706b. Sampledminfree9602531328bytes=18.64%, hostmarginPASSswap0. ActualPNGviewed: same excessivecontrast, coarse/oversharpenedsurfaces/background and changedlighting; bluecolorchange/compositiononlypartial. Normalizationdidnotresolvethefidelityproblem; rootcauseNOTestablished.

Originalrawresultremainsintact. NoDiffusersreference, prompt/seed/CFGsweep, ladderoradditionalattempt. ROOT-EDIT-RGB-COMPARISON-GO stopboundaryreached; completingtruthfulhandoff.
