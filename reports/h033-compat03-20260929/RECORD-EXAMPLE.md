# Exact protected-record shape (construction example, not an installed record)

Root/W2 must supply real review attribution and timestamps after inspecting the retained workflows and source review. The timestamp/reviewer placeholders below deliberately cannot validate. `pinComparison` means the supplied SPECIALIST-PIN-COMPARISON.json; its complete actualPins/targetPins objects are used verbatim, not projected or relabelled. No file is written by this example.

```js
const testedPins = pinComparison.actualPins;
const targetPins = pinComparison.targetPins;
const sha = text => createHash('sha256').update(text).digest('hex');
const codex = {
  result: 'PASS',
  sessionId: '2b4709f8-baf7-4b63-b2b4-965ad1cecc2c',
  runId: '5d20fb05-3cf3-4722-94eb-99840e2b9e82',
  transcriptSha256: '264925de757e59f07ea1ff081c8566174e2fd49f2bfe1032988823da2e744e76',
  settlementSha256: 'e4847bd247bdbb0f869c6af021c93f2a3309e87748f6eb1817d588e45bbfd033'
};
const minimax = {
  result: 'PASS',
  sessionId: '3fd899cc-5e06-4772-9afb-ac044239b3be',
  runId: 'fbd49990-b80a-4431-b261-81812a1353a8',
  transcriptSha256: 'ca07054f604d77ff181d52ab52e60509b58d7e1572c5ab71cf8f963f3b519261',
  settlementSha256: '3b9d8abc1ed9c056c60d127faae6ce73f7ec4eb239f2dd7b619ee253447791b7'
};
const workflows = {tool_continuation: codex, codex_child: codex, minimax_delegation: minimax};
const review = {
  schema: 1, kind: 'reviewed-frontier-tool-policy-compatibility',
  testedSourceRevision: 'c863d4984f4a75c237b6de97b7ce40b8570fca81',
  testedPins,
  targetSourceRevision: 'eb8ed4283d83cfbdbcc97dfbeec7056d2538c05e',
  targetPins,
  workflowsSha256: sha(JSON.stringify(workflows)),
  reviewedAt: 'REPLACE_WITH_ACTUAL_ROOT_REVIEW_TIME',
  reviewedBy: '' // replace with actual accountable reviewer; never invent attribution
};
const reviewText = JSON.stringify(review); // exact bytes to retain/hash
const evidence = {
  schema: 2, kind: 'retained-live-frontier-reviewed-compatibility', capability: 'frontier',
  pins: testedPins, sourceRevision: review.testedSourceRevision,
  reviewedAt: 'REPLACE_WITH_ACTUAL_EVIDENCE_REVIEW_TIME',
  workflows,
  review: {file: 'h033-frontier-review.json', sha256: sha(reviewText)}
};
const evidenceText = JSON.stringify(evidence);
const record = {
  schema: 1, kind: 'reviewed-codex-specialists', pins: targetPins, image: null,
  frontier: {file: 'h033-frontier-evidence.json', sha256: sha(evidenceText)}
};
```

The workflow transcript digests above bind the supplied CODEX-QUALIFICATION-TRANSCRIPT.json and MINIMAX-QUALIFICATION-TRANSCRIPT.json summary bytes. These preserve actual source/pins, full result and private raw-manifest hashes: Codex `389d5d9bd4b9805c784aff339fc2868d3c85381a8066f4b944efdea5c7da5f25`, MiniMax `fee6e1aea9d3f826976263d6e86ca24950f7ba8d3afe1eaad559df491f40b8f9`. They are not hashes of the raw transcript itself. Both final settlement files were hashed locally and match the summaries. Keep the original private summaries/manifests/archives intact; do not publish private paths/traces.

Review time must be >= evidence reviewedAt and <= validation time. Workflow digest is SHA256 of UTF-8 JavaScript JSON.stringify(evidence.workflows), preserving property insertion order; avoid reordering that object after computing the review digest. File digests cover exact serialized bytes, including any newline actually written. Every record/evidence/review file goes through the existing root-owned /etc/sova-qualification reader, with no links, writable ancestry or task mounts. W2 owns installation after root source GO and its idle/settled gap; no installation was performed here.

Only c863/aee39 -> reviewed eb8ed/b71 is accepted. Every other pin, including image pins, must equal current CODEX_SPECIALIST_PINS. eb8ed is the reviewed implementation basis, not a claim that a later validator-only deployment has that running commit. Current native health, admission and lifecycle checks remain separate. Root must retain the source review of unchanged provider/transport/child protocol bytes (SOURCE-PROVENANCE.json) alongside changed guidance/final-display/Qwen-count review. No current app/source probe or generic compatibility framework was added.
