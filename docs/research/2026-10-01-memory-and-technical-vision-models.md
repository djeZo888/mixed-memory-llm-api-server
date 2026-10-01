# Models for compaction and technical vision

**Primary-source research — 1 October 2026. No models installed or tested.**
These are candidates, not a new deployment roster or a claim of best-model
ranking across all open releases.

## Recommendation

Keep the deployed Qwen as the default compactor. First improve and qualify
structured state, repeated retention and source retrieval. A dedicated model
should earn its GPU by improving those results or removing measured contention.

For technical vision, first evaluate the existing Qwen3.8 model through a
specialist image-to-text tool. Native Codex image input and model vision
capability are different questions. Compare a smaller dedicated model only
where its quality, latency or crop capacity justifies deployment.

## Summarization shortlist

| Candidate | Intended role | Context and hardware evidence | Main caveat |
| --- | --- | --- | --- |
| ellamind/sui-1-24b-fp8 | Source-grounded document summaries | 131,072 native; longer inputs use chunk/merge. Author reports about 38 GB at 8K and 50 GB at 128K; A6000 48 GB passes 64K, fails 128K. | Requires tagged sentences; no direct repeated-project comparison with Qwen3.8 or MiMo. Ada/runtime fit untested. |
| CoMem / YWZBrandon/summary-sft-qwen3-4b | Learned agent context management | Training input 32K, summaries 2K. Released config allows 262K, which is not long-context quality evidence. | Research release; checkpoint metadata/export and downstream-quality tradeoffs need review. |
| Qwen3.5-9B | Smaller independent general summarizer | BF16 artifact approximately 19.3 GB; native 262,144, with a separately documented YaRN extension. | Not purpose-trained for Sova compaction; weight size is not total runtime memory. |

SUI is Apache-2.0. Its citations enable source checking, but a valid sentence
identifier does not prove that the generated claim follows from that sentence.
The paper's evaluation differs from the card's stated sample count and lacks
the deployed Sova models as baselines. Treat document-summary evidence separately
from technical dialogue or coding-state retention.
[Official card and hardware table](https://huggingface.co/ellamind/sui-1-24b-fp8),
[paper](https://arxiv.org/html/2601.08472v1).

CoMem directly studies agent compaction. Its paper reports a small improvement
for DeepSWE but reduced issue-resolution rates for two stronger agents; it
does not establish unchanged quality for Sova. Code and Qwen base use
Apache-2.0; the checkpoint card lacks an explicit license. The SFT artifact is
approximately 17.7 GB FP32, about 8.9 GB of weights when loaded as BF16, before
cache/workspace. Public GRPO packages need export rather than serving directly.
[Official repository](https://github.com/horizon-llm/CoMem),
[paper](https://arxiv.org/html/2605.30842v1),
[SFT artifact](https://huggingface.co/YWZBrandon/summary-sft-qwen3-4b).

Neither specialist is established as a reliable one-pass compactor for a
400K technical transcript on a 48 GB GPU. Chunked summaries must retain original
references and be evaluated for merge omissions. Qwen remains the first
qualification target; a SUI pilot is most relevant for long documents with
traceable citations, while CoMem is an experimental agent-memory comparison.

## Technical vision shortlist

| Candidate | Publisher evidence | Artifact planning | Role |
| --- | --- | --- | --- |
| Qwen3.8-27B-FP8 | Chart/document/physical reasoning evaluations; official model has a vision encoder | Approximately 30.9 GB files; visual blocks excluded from FP8 conversion | Reuse current model family for the first specialist-to-text evaluation |
| Qwen3.5-9B BF16 | OCR, diagram, scientific-chart and spatial evaluations | Approximately 19.3 GB files | Smaller dedicated-Ada comparison with more crop/workspace room |
| PaddleOCR-VL-1.6 | Document parsing, text spotting, tables, formulas and charts | Approximately 1.92 GB BF16 model weights, plus pipeline components | OCR/document extraction alongside the reasoner |

All three official artifacts declare Apache-2.0. Their published evaluations
are not Sova engineering acceptance, and benchmark versions/annotations differ.
Do not rank electrical-schematic reliability from document or chart scores.

Qwen3.8's official FP8 configuration includes visual modules. Sova's installed
weights/runtime must still be checked before enabling them. Its published native
text context is 262,144; Sova's 480K allocation is an extended configuration,
not proof of equal fidelity at that occupancy.
[Model card](https://huggingface.co/Qwen/Qwen3.8-27B),
[FP8 configuration](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/blob/main/config.json),
[files](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/tree/main).

Qwen3.5-9B is a general multimodal model, not a dedicated schematic parser.
Its smaller BF16 footprint makes it a useful crop-heavy comparison, but neither
its vision benchmarks nor long-context results prove repeated compaction fidelity.
[Model card](https://huggingface.co/Qwen/Qwen3.5-9B),
[files](https://huggingface.co/Qwen/Qwen3.5-9B/tree/main).

PaddleOCR-VL-1.6 supports page-level structured extraction and is a complementary
parser. Its OmniDocBench v1.6 result is not directly comparable with Qwen's
v1.5 measurements. Electrical connectivity reasoning remains unproven.
[Official card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6),
[pipeline documentation](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html).

Preserve page overview and overlapping detailed crops, with original coordinates.
For DWG, first decode geometry/layers/dimensions through a reviewed CAD tool;
an image model cannot directly parse every binary CAD format. DXF parsing and
rendering can use MIT-licensed ezdxf. ODA's DWG converter retains its own terms.
[ezdxf](https://github.com/mozman/ezdxf),
[ODA converter](https://www.opendesign.com/guestfiles/oda_file_converter).

## Evaluation before adoption

The [compaction plan](../../todo/context-compaction-reliability.md) defines
repeated-cycle exact-fact recall, source recovery and failure handling.
The [technical vision plan](../../todo/technical-image-understanding.md) defines
labels, units, connectivity, dimensions, uncertainty and crop evidence.

Pin exact revisions, runtime and precision during comparisons. Measure end-to-end
latency and peak memory including cache, image encoders, activations and temporary
workspace. No dedicated-GPU maximum context or image resolution is established
by these artifact estimates.
