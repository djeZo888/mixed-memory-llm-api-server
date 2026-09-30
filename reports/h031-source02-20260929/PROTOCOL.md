# H031 SOURCE02 protocol — root review required, W1 sole deployer

Source proposal only. Native source worker performed no mutation on ai-vm. One INBOX-authorized bounded read-only fetch recovered the original raw intent and exact stopped files; hashes matched W1 retained evidence. No second stop, new pre-stop intent, inference, repair or baseline restore is permitted by this packet.

Base `9cd941cdbd9170fb56ccacbc87f3238e3bd40f0e`; commit `b2ecf727d1a5192e5e791db4b088ef9b9a3ee865`. All CLI manifest SHA arguments below are **canonical JSON digests**. State, intent, delta, supplement and file checksum arguments are **raw byte SHA256**. Frozen full pins are in SOURCE-MANIFEST.json. The original intent and original delta remain in place, unchanged. The corrected delta replaces only the original proposal's NEW owner hash; both node entries and every OLD pin remain byte-identical. The original proposed manifest is retained privately; the supplement binds its canonical digest, old manifest raw bytes and both delta raw bytes, plus the corrected manifest raw bytes.

The exact disposition is `SAME_BOOT_IDLE_STOP_TIMEOUT_SETTLED` / `IDLE_STOP_TIMEOUT_PHYSICALLY_SETTLED`. Both original failure records remain in the stopped state and archive. It does not record a successful stop or successful historical inference. Current absence and strict negative hardware proof are required at preparation, reconciliation and normal start; failure does not clear a latch or consume a receipt.

## Concrete MiMo sequence

After root exact review, W1 stages this output in a root-owned0700 registered-data directory `/data/build/h031-source02-20260929`, with protected ancestors. Preserve all earlier packages. W1 combines its separately owned image/control activation in this single stopped interval; the commands below fully specify MiMo changes and make no manual state/selection edits. Do not restart the stopped MiMo unit before reconciliation. If any command fails, retain everything and return the actual failure to root; no automatic rerun/stop/receipt renewal.

```sh
set -eu
mimo_base=/data/services/mimo-h016-20260927
h031_stage=/data/build/h031-source02-20260929
cd "$h031_stage"
sha256sum -c SHA256SUMS
# OLD pins must still be installed. No state mutation is used to satisfy these checks.
test "$(cat /proc/sys/kernel/random/boot_id)" = '992bf979-efae-495b-9ab2-26e75ed5c5d0'
test "$(sha256sum "$mimo_base/source/owner.py" | cut -d' ' -f1)" = '1cc1ee45eca7c578d9b84411d75c1cfd37c914edd7b5097389ee2f19fae23098'
test "$(sha256sum "$mimo_base/manifest.json" | cut -d' ' -f1)" = 'ad6b438f17154d7434426b3b9a4b0238558a86ba5ab764ccb5c3c2b0f0099c8b'
test "$(sha256sum "$mimo_base/state.json" | cut -d' ' -f1)" = 'b1ba8b36d09aef570a0d90f769268a61d05a6dbb11899720a163a5bab8fa7420'
test "$(sha256sum "$mimo_base/source-stop-992bf979-efae-495b-9ab2-26e75ed5c5d0-fbfd46357f0d4e3482aa1c7da14f5147.json" | cut -d' ' -f1)" = '9cabae3e1335bda0028497638e5e968623e0870ef7cc339bd8d9a576243d8eee'
test "$(sha256sum "$mimo_base/source-successor-delta.json" | cut -d' ' -f1)" = 'cd9b4a0fbb22e9d97f6ab826492282f6560402685c73b7e1023d94a6a7914e59'
mkdir -m 700 "$h031_stage/predecessor" "$h031_stage/prior-inputs"
cp -a "$mimo_base/manifest.json" "$h031_stage/predecessor/manifest.json"
cp -a "$mimo_base/source/owner.py" "$h031_stage/predecessor/owner.py"
for source_input in source-successor-prior-manifest.json source-successor-prior-owner.py; do
  if test -e "$mimo_base/$source_input"; then cp -a "$mimo_base/$source_input" "$h031_stage/prior-inputs/$source_input"; fi
done
test ! -e "$mimo_base/source-successor-corrected-delta.json"
test ! -e "$mimo_base/source-successor-corrected-manifest.json"
install -o root -g root -m 400 source-successor-corrected-delta.json "$mimo_base/source-successor-corrected-delta.json"
install -o root -g root -m 400 private/source-successor-corrected-manifest.json "$mimo_base/source-successor-corrected-manifest.json"
# Staged reviewed source, unchanged installed OLD owner/manifest. Exclusive protected supplement only.
/usr/bin/python3 -I -B "$h031_stage/reviewed-source/owner.py" prepare-source-stop-timeout \
  --expected-state-sha256 'b1ba8b36d09aef570a0d90f769268a61d05a6dbb11899720a163a5bab8fa7420' \
  --expected-boot-id '992bf979-efae-495b-9ab2-26e75ed5c5d0' \
  --expected-manifest-sha256 '5c364e58cba01a569f13f6a239c6383dec1d5b92a94f3ab8d608962c0a178a39' \
  --expected-delta-sha256 'cd9b4a0fbb22e9d97f6ab826492282f6560402685c73b7e1023d94a6a7914e59' \
  --expected-intent-sha256 '9cabae3e1335bda0028497638e5e968623e0870ef7cc339bd8d9a576243d8eee' \
  --expected-corrected-delta-sha256 'bf7c1ad0f197a2191f711c314b5ceccb6ce3a0c3f44c6e7b307cfc4e1dcdb167' \
  --expected-successor-manifest-sha256 '9315a02f73288d9f6041b47316008fdf7502d7755be66278fd4ce0ec0ee0a9e9' > "$h031_stage/prepared.json"
h031_supplement_sha=$(/usr/bin/python3 -c 'import json; print(json.load(open("prepared.json"))["supplement_sha256"])')
test "$(sha256sum "$mimo_base/source-stop-timeout-992bf979-efae-495b-9ab2-26e75ed5c5d0-fbfd46357f0d4e3482aa1c7da14f5147.json" | cut -d' ' -f1)" = "$h031_supplement_sha"

# ONLY after successful supplement preparation, in the one reviewed stopped deployment interval:
install -o root -g root -m 400 predecessor/manifest.json "$mimo_base/source-successor-prior-manifest.json"
install -o root -g root -m 400 predecessor/owner.py "$mimo_base/source-successor-prior-owner.py"
install -o root -g root -m 600 reviewed-source/owner.py "$mimo_base/source/owner.py"
install -o root -g root -m 600 reviewed-source/node.py /usr/local/lib/llm-server/node-api/scripts/control/node.py
install -o root -g root -m 600 reviewed-source/node_collectors.py /usr/local/lib/llm-server/node-api/scripts/control/node_collectors.py
install -o root -g root -m 600 private/source-successor-corrected-manifest.json "$mimo_base/manifest.json"
```

W1 completes its separately reviewed image/control closure activation here, including its node producer lifecycle. No image/app/config operation is granted to SOURCE02. The normal hardware producer must already supply current strict negative proof. These exact owner commands enforce it and refuse stale/unknown/positive proof; do not manufacture a guard or edit a map to bypass a refusal.

```sh
/usr/bin/python3 -I -B "$mimo_base/source/owner.py" reconcile-settled-source \
  --same-boot-intentional-stop --idle-stop-timeout-settled \
  --expected-state-sha256 'b1ba8b36d09aef570a0d90f769268a61d05a6dbb11899720a163a5bab8fa7420' \
  --expected-boot-id '992bf979-efae-495b-9ab2-26e75ed5c5d0' \
  --expected-manifest-sha256 '9315a02f73288d9f6041b47316008fdf7502d7755be66278fd4ce0ec0ee0a9e9' \
  --expected-delta-sha256 'bf7c1ad0f197a2191f711c314b5ceccb6ce3a0c3f44c6e7b307cfc4e1dcdb167' \
  --expected-supplement-sha256 "$h031_supplement_sha"
systemctl start llm-frontier-mimo.service
```

Normal start validates the complete chain, raw current stopped bytes and original intent/supplement, all corrected installed pins, exact proxy zero/nonquarantine, physical absence (only its exact supervisor permitted), native OOMKilled=false, and current strict hardware proof. Successful preflight persists successor ownership, exclusively writes the consumed receipt binding the entire recovery, and renames/preserves the predecessor container. A failed preflight leaves original state and every intent/supplement/archive/receipt unconsumed. A post-admission failure retains consumption and settles under normal rules; no replay is authorized. Protected exclusive names prevent renewing the same launch or rebinding the chain to another manifest.

Keep all prior state, failures, intent/deltas, archive/receipt/consumed, containers/logs, uncertain owners and quarantines. Start is not readiness or acceptance. W1 records fresh readiness and root authorizes retained workflow gates separately. No paid source worker waiting for loading.
