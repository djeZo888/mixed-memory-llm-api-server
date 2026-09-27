#!/usr/bin/env python3
"""Offline H011 exact-occupancy fixture; stdout JSON, no requests or file writes.

Run in the already-running native container with its pinned local tokenizer:
  python -I -B fixture_native.py --target 65536 --seed h011-measured-v1
  python -I -B fixture_native.py --self-test

The self-test exercises construction with a character tokenizer only. It does
not establish native tokenizer parity, which the caller must verify through
/v1/tokenize before inference. Token-ID hashes use compact JSON integer arrays.
"""
import argparse
import hashlib
import json
import random
import string
import time

REVISION = "eb9eb208eb0d988989d07a6a12d0fdeb5f52574a"
MODEL = "glm-5.3-flash"
TEMPLATE_KWARGS = dict(add_generation_prompt=True, reasoning_effort="high",
                       clear_thinking=True, tools=None)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def technical_records(seed, minimum_characters):
    """A deterministic, shuffled mixture of distinct synthetic technical records."""
    rng = random.Random(digest(seed))
    names = ("alder", "basalt", "cedar", "delta", "ember", "fjord", "granite",
             "harbor", "indigo", "juniper", "kelvin", "larch", "mesa", "nickel",
             "onyx", "prairie", "quartz", "raven", "spruce", "tundra")
    kinds = list(range(20))
    records, size, index = [], 0, 0
    while size < minimum_characters:
        rng.shuffle(kinds)
        for kind in kinds:
            index += 1
            name = rng.choice(names)
            ident = "%s-%s-%05d" % (name, rng.getrandbits(40).to_bytes(5, "big").hex(), index)
            a, b, c, d = (rng.randrange(11, 997) for _ in range(4))
            p, q = rng.sample(range(2, 32), 2)
            text = (
                f"Network {ident}: route cost {a}, MTU {b + 1200}, receive window {c * 64} bytes. Compare retransmit counters before changing congestion policy; packet reordering alone does not prove loss.",
                f"Storage {ident}: stripe width {p}, chunk size {q * 4} KiB, logical segment {a}. A checksum mismatch at offset {b * 4096} must preserve the original extent and its previous generation {c}.",
                f"Scheduler {ident}: job duration {a} ms, deadline {a + b} ms, queue depth {p}. Record admission and completion separately; a worker reservation of {q} slots is distinct from active execution.",
                f"Thermal {ident}: samples {p}, sensor interval {q} s, raw sum {a + b + c}. Calibrate offset and unit conversion before interpreting a trend; missing data must remain explicitly unknown.",
                f"Parser {ident}: grammar revision {a}, token budget {b}, nesting bound {q}. Quoted delimiters remain data. Reject incomplete escape sequences before applying the normalization pass numbered {c}.",
                f"Database {ident}: transaction {a}, snapshot {b}, retained versions {p}. Readers use a consistent snapshot. An index scan touching {c} rows does not establish that all committed rows were visited.",
                f"Numerics {ident}: vector length {a}, block width {p}, seed {b}. Accumulate in a wider representation when summing mixed magnitudes; compare absolute tolerance 0.00{q} with a separately stated relative bound.",
                f"Build {ident}: artifact group {a}, source units {p}, cache entries {c}. A cache hit must match compiler options and source digest. Link order is recorded as {name}, core, transport, and diagnostics.",
                f"Memory {ident}: requested {a * 128} bytes, alignment {2 ** (p % 6 + 3)}, live objects {b}. Reserved address space differs from committed physical pages; file-backed pages may be shared by {q} processes.",
                f"Telemetry {ident}: polling interval {p} s, missing samples {q}, monotonic counter {c * 1000}. Compute deltas only within one boot identity and retain reset markers when counters decrease.",
                f"Replication {ident}: epoch {a}, follower lag {b} ms, retained log entries {c}. Require durable acknowledgment from the configured quorum before exposing a new commit index; retries preserve operation identity.",
                f"Geometry {ident}: rectangle sides {a} and {b} mm, aperture radius {p} mm. Keep coordinate-frame transforms explicit. Bounding-box overlap is a preliminary filter and does not prove exact intersection.",
                f"Signal {ident}: sample count {a}, rate {b * 10} Hz, filter width {q}. Account for the group delay before comparing timestamps. Padding is a boundary convention rather than an observed sensor value.",
                f"API {ident}: page limit {p}, result count {b}, request sequence {c}. A cursor is opaque and scoped to its query. Timeout means the caller lacks a complete result, not that the server rolled back its work.",
                f"Control {ident}: actuator limit {a}, observed value {b}, hold interval {q} ms. Distinguish measured feedback from the requested setpoint; stale feedback cannot authorize a state transition.",
                f"Compression {ident}: source bytes {a * 31}, dictionary entries {b}, frame count {p}. Verify the uncompressed digest and exact decoded length; a valid frame checksum does not authenticate its origin.",
                f"Graph {ident}: vertices {a}, sampled edges {b}, component label {c}. Traversal order is deterministic after sorting adjacency lists. A cycle witness records the full sequence of edges, not merely its endpoints.",
                f"Timebase {ident}: local sequence {a}, offset estimate {p} ms, uncertainty {q} ms. Wall-clock ordering may differ from monotonic elapsed time; retain both fields when reconciling distributed events.",
                f"Deployment {ident}: revision {a}, health checks {p}, observation window {b} s. Keep rollback identity and effective configuration. Process existence alone is weaker evidence than a completed authenticated request.",
                f"Queue {ident}: arrivals {a}, completions {b}, initial backlog {c}. Count cancellations separately and reconcile final backlog using conserved job identifiers. Queue capacity {d} is not sustained service throughput.",
            )[kind]
            text += "\n"
            records.append(text)
            size += len(text)
            if size >= minimum_characters:
                break
    return "".join(records), index


def render(tokenizer, content):
    messages = [{"role": "user", "content": content}]
    ids = tokenizer.apply_chat_template(messages, tokenize=True, return_dict=False,
                                        **TEMPLATE_KWARGS)
    return [int(token) for token in ids]


def build_fixture(tokenizer, target, seed, long_answer=False):
    started = time.monotonic()
    seed_digest = digest(seed)
    rng = random.Random(seed_digest + ":facts")
    codes = {name: "H11" + name[0].upper() + "-" + "".join(
        rng.choice(string.ascii_uppercase + string.digits) for _ in range(8))
             for name in ("early", "middle", "end")}
    a, b, h = rng.randrange(17, 90), rng.randrange(33, 240), rng.randrange(17, 120)
    expected = {"early": codes["early"], "middle": codes["middle"],
                "end": codes["end"], "aligned_bytes": ((a * b + h + 63) // 64) * 64}
    content = (
        f"Synthetic technical dossier {seed_digest[:16]}. All records are fictional. "
        "Read the full dossier. Exactly three H011 CHECKPOINT records contain the "
        "answer codes and arithmetic inputs. Other records are context only. "
        "At the end answer the task in the requested format.\n"
    )
    suffix = (
        "\nEND DOSSIER. Return one compact JSON object with keys early, middle, end, "
        "aligned_bytes. Copy the three CHECKPOINT codes exactly. Compute total "
        "bytes = batches * bytes_per_batch + header_bytes; aligned_bytes is that "
        "total rounded UP to a multiple of 64. Use only the three CHECKPOINT "
        "inputs. FLASH_LONG_INSTRUCTION\n"
    )
    suffix = suffix.replace("FLASH_LONG_INSTRUCTION", (
        "After the JSON write twenty numbered engineering review paragraphs, one for each technical subject in this dossier. "
        "Each paragraph must explain a specific measurement caveat and a concrete verification procedure in 40 to 60 words. "
        "Complete all twenty paragraphs; do not compress the answer into a summary."
        if long_answer else "No prose or detailed derivation; provide the JSON immediately."))
    corpus, record_count = technical_records(seed, target * 8)
    source_ids = tokenizer.encode(corpus, add_special_tokens=False)
    if len(source_ids) < target + 256:
        corpus, record_count = technical_records(seed, target * 16)
        source_ids = tokenizer.encode(corpus, add_special_tokens=False)
    if len(source_ids) < target + 256:
        raise RuntimeError("synthetic_corpus_token_supply_insufficient")
    cursor = 0
    marker_texts = {}
    for name, fraction, value in (("early", .02, f"batches={a}"),
                                  ("middle", .50, f"bytes_per_batch={b}"),
                                  ("end", .98, f"header_bytes={h}")):
        marker = f"\nH011 CHECKPOINT {name.upper()}: code={codes[name]}; {value}.\n"
        position = round(target * fraction)
        if name == "end":
            position = min(position, target - len(render(tokenizer, marker + suffix)) - 16)
        needed = max(0, position - len(render(tokenizer, content)))
        content += tokenizer.decode(source_ids[cursor:cursor + needed],
                                    skip_special_tokens=False,
                                    clean_up_tokenization_spaces=False)
        cursor += needed
        marker_texts[name] = marker
        content += marker
    # Fit only the final context fragment. The broad corpus is never replayed.
    remaining = target - len(render(tokenizer, content + suffix))
    if remaining < 0:
        raise RuntimeError("checkpoint_and_suffix_exceed_target")
    available = source_ids[cursor:cursor + remaining + 128]
    def candidate(n, pad=""):
        return (content + tokenizer.decode(available[:n], skip_special_tokens=False,
                                           clean_up_tokenization_spaces=False)
                + pad + suffix)
    lo, hi = 0, len(available)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(render(tokenizer, candidate(mid))) <= target:
            lo = mid
        else:
            hi = mid - 1
    # Diverse short labels are only a bounded (<=128 token) boundary correction.
    labels = [" x", " voltage", " current", " phase", " clock", " rate", " load",
              " signal", " cache", " page", " buffer", " node", " port", " block"]
    unit_labels = [label for label in labels
                   if len(tokenizer.encode(label, add_special_tokens=False)) == 1]
    rng.shuffle(unit_labels)
    exact = None
    padding_tokens = 0
    for n in range(lo, max(-1, lo - 33), -1):
        draft = candidate(n)
        ids = render(tokenizer, draft)
        missing = target - len(ids)
        if missing == 0:
            exact = draft, ids
            break
        if 0 < missing <= 128 and unit_labels:
            pad = "".join(unit_labels[i % len(unit_labels)] for i in range(missing))
            draft = candidate(n, pad)
            ids = render(tokenizer, draft)
            if len(ids) == target:
                exact, padding_tokens = (draft, ids), missing
                break
    if exact is None:
        raise RuntimeError("exact_native_template_fixture_failed")
    content, ids = exact
    rendered = tokenizer.apply_chat_template([{"role": "user", "content": content}],
                                             tokenize=False, **TEMPLATE_KWARGS)
    # Offsets are measured in the final rendered string, including all template
    # tokens and the generation prefix. Refuse unverifiable approximate offsets.
    mapped = tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    if list(mapped["input_ids"]) != ids:
        raise RuntimeError("rendered_token_offset_mapping_parity_failed")
    offsets = mapped["offset_mapping"]
    code_locations = {}
    for name, code in codes.items():
        if rendered.count(code) != 1 or content.count(marker_texts[name]) != 1:
            raise RuntimeError("checkpoint_code_uniqueness_failed")
        start = rendered.index(code)
        end = start + len(code)
        matches = [i for i, (left, right) in enumerate(offsets)
                   if left < end and right > start]
        if not matches or offsets[matches[0]][0] > start or offsets[matches[-1]][1] < end:
            raise RuntimeError("checkpoint_code_token_mapping_incomplete")
        code_locations[name] = {
            "code": code, "rendered_character_start": start,
            "rendered_character_end_exclusive": end,
            "content_character_start": content.index(code),
            "token_start": matches[0], "token_end_exclusive": matches[-1] + 1,
            "token_fraction": matches[0] / target,
            "checkpoint_record": marker_texts[name].strip(),
        }
    payload = {"model": MODEL, "messages": [{"role": "user", "content": content}],
               "max_tokens": 256 if target == 65536 else 128, "temperature": 0,
               "reasoning_effort": "high", "chat_template_kwargs": {"clear_thinking": True}}
    canonical_ids = json.dumps(ids, separators=(",", ":"))
    return {
        "schema": "h011.varied-technical-fixture.v1", "seed": seed,
        "content": content, "content_sha256": digest(content),
        "rendered_tokens": len(ids), "requested_input_tokens": target,
        "rendered_text_sha256": digest(rendered),
        "rendered_token_ids_sha256": digest(canonical_ids),
        "token_ids_hash_encoding": "UTF-8 compact JSON integer array",
        "generation_prefix_included": True, "tools": None,
        "reasoning_effort": "high", "clear_thinking": True,
        "tokenizer_revision": REVISION, "template_revision": REVISION,
        "code_locations": code_locations, "expected_result": expected,
        "arithmetic_inputs": {"batches": a, "bytes_per_batch": b, "header_bytes": h,
                              "alignment_bytes": 64},
        "arithmetic_rule": "ceil((batches * bytes_per_batch + header_bytes) / 64) * 64",
        "source_corpus_sha256": digest(corpus), "source_corpus_record_count": record_count,
        "source_corpus_note": "Distinct deterministic records across 20 technical domains; corpus tail may be unused.",
        "boundary_padding_tokens": padding_tokens,
        "payload": payload,
        "payload_sha256": digest(json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        "payload_hash_encoding": "UTF-8 sorted-key compact JSON",
        "construction_seconds": round(time.monotonic() - started, 6),
        "correctness_limit": "An output capped before the final JSON leaves correctness unproven; reasoning shares the output budget.",
    }


class _CharacterTokenizer:
    """Mock construction coverage only; never represents native token counts."""
    def encode(self, text, **_kwargs):
        return list(map(ord, text))

    def decode(self, ids, **_kwargs):
        return "".join(map(chr, ids))

    def apply_chat_template(self, messages, tokenize=True, **_kwargs):
        text = "<user>\n" + messages[0]["content"] + "\n<assistant><think>"
        return self.encode(text) if tokenize else text

    def __call__(self, text, **_kwargs):
        return {"input_ids": self.encode(text),
                "offset_mapping": [(i, i + 1) for i in range(len(text))]}


def self_test():
    tokenizer = _CharacterTokenizer()
    warm = build_fixture(tokenizer, 8192, "offline-warm")
    measured = build_fixture(tokenizer, 65536, "offline-measured")
    repeated = build_fixture(tokenizer, 8192, "offline-warm")
    for result in (warm, measured):
        assert result["rendered_tokens"] == result["requested_input_tokens"]
        assert result["expected_result"]["aligned_bytes"] % 64 == 0
        for name, target_fraction in (("early", .02), ("middle", .50), ("end", .98)):
            # Template/header overhead can exceed the early 2% goal at 8K
            # for the deliberately one-character-per-token mock tokenizer.
            assert abs(result["code_locations"][name]["token_fraction"] - target_fraction) < .08
        assert len(set(result["expected_result"][name] for name in ("early", "middle", "end"))) == 3
    assert warm["content_sha256"] == repeated["content_sha256"]
    assert warm["rendered_token_ids_sha256"] == repeated["rendered_token_ids_sha256"]
    assert warm["source_corpus_sha256"] != measured["source_corpus_sha256"]
    assert not set(warm["expected_result"][name] for name in ("early", "middle", "end")) & set(
        measured["expected_result"][name] for name in ("early", "middle", "end"))
    print(json.dumps({"status": "PASS", "scope": "offline character-tokenizer construction only",
                      "targets": [8192, 65536], "native_tokenizer_parity": "NOT_TESTED"}))


def main():
    import sys
    from transformers import AutoTokenizer
    global MODEL, TEMPLATE_KWARGS, REVISION
    lane=sys.argv[1]
    tokenizer=AutoTokenizer.from_pretrained("/models",local_files_only=True)
    if lane != "flash":
        MODEL="qwen3.8-27b-gpu0" if lane=="qwen0" else "qwen3.8-27b"
        TEMPLATE_KWARGS=dict(add_generation_prompt=True,enable_thinking=False,tools=None)
        REVISION="017b9c7af6b5689d5dd426a76e0bc077eb5ca20a"
    results=[]
    for n in range(1 if lane=="flash" else 12):
        result=build_fixture(tokenizer,65536 if lane=="flash" else 262144,f"H011-corrected-{lane}-fresh-{n}-20260927",lane=="flash")
        result.pop("content")
        payload=result["payload"]
        payload["max_tokens"]=768 if lane=="flash" else 128
        if lane!="flash":
            payload.pop("reasoning_effort"); payload["chat_template_kwargs"]={"enable_thinking":False}
            result["reasoning_effort"]=None; result["clear_thinking"]=None
        result["payload_sha256"]=digest(json.dumps(payload,sort_keys=True,separators=(",",":")))
        results.append(result)
    print(json.dumps(results))
if __name__ == "__main__": main()
