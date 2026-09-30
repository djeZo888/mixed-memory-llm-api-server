#!/usr/bin/env python3
"""Actual-image auth fixture for the closed Qwen480K GPU0/GPU1 production tuples.

Source-only tests cannot mint this receipt. Separately authorized Worker1 must
run this command under the current registered-storage guards and ownership
lease, using a new protected registered-data output. No pull/model/GPU/network.
Native/TP2 fixture defaults remain unchanged; slot fixtures select only closed port/alias tuples.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONTEXT = 480000
PROFILES = {"gpu0": "qwen38-27b-q0-480000-yarn4-bf16kv",
            "gpu1": "qwen38-27b-q1-480000-yarn4-bf16kv"}
PROFILE = PROFILES["gpu1"]
KIND = 'q38pair_actual_image_auth'
INNER = '/fixture/tests/lifecycle/sglang38_fixture/run_pair_pinned_image.py'
OLD_INNER = '/fixture/tests/lifecycle/sglang38_fixture/run_pinned_image.py'
PAIR_FILES = (
    'tests/lifecycle/sglang38_fixture/run_pair_fixture.py',
    'tests/lifecycle/sglang38_fixture/run_pair_pinned_image.py',
    'tests/lifecycle/sglang38_fixture/pair_launcher.py',
    'scripts/runtime/sglang38_pair_file_auth.py',
    'scripts/runtime/sglang38_file_auth.py',
    *("configs/deployments/" + value + ".json" for value in PROFILES.values()),
    'configs/models/qwen38-27b-fp8.json',
    'configs/runtimes/sglang-qwen38-0.5.19.json',
)

spec = importlib.util.spec_from_file_location('q38pair_original_host', HERE / 'run_fixture.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
LEGACY_IMAGE_ID, LEGACY_IMAGE_REFERENCE = host.IMAGE_ID, host.IMAGE_REFERENCE
LEGACY_READ_PROVENANCE = host.read_provenance


def runtime_binding(repo):
    """Load only the reviewed source-side binding, without any host operation."""
    scripts = str(repo / 'scripts')
    sys.path.insert(0, scripts)
    try:
        return host.source_module('q38pair_h005_binding', repo / 'scripts/runtime/h005_runtime_binding.py')
    finally:
        sys.path.remove(scripts)


def legacy_provenance(repo):
    # read_provenance's legacy constants remain authoritative even while the
    # enclosing adapter temporarily selects the derived image for execution.
    with patch.object(host, 'IMAGE_ID', LEGACY_IMAGE_ID), \
            patch.object(host, 'IMAGE_REFERENCE', LEGACY_IMAGE_REFERENCE):
        return LEGACY_READ_PROVENANCE(repo)


def adaptive_provenance(repo):
    provenance, cache = legacy_provenance(repo)
    binding = runtime_binding(repo)
    oci = binding.text_oci()  # Missing completed build receipts fail closed.
    provenance = copy.deepcopy(provenance)
    provenance.update(image_id=oci.IMAGE_ID, image_reference=oci.IMAGE_REFERENCE)
    for name, digest in binding.overlay_source_hashes(repo, provenance).items():
        # Preserve every legacy pin not changed by the exact overlay; the hash
        # authenticates complete bytes for replaced/new files without old sizes.
        if provenance['sources'].get(name, {}).get('sha256') != digest:
            provenance['sources'][name] = {'sha256': digest}
    return provenance, cache


def __getattr__(name):
    # Safe failure parsers used by the unchanged inner fixture.
    return getattr(host, name)


def pair_identity(repo, provenance=None, *, slot="gpu1", adaptive=False):
    host.require(slot in PROFILES, "pair_fixture_slot_invalid")
    provenance, _ = adaptive_provenance(repo) if adaptive else legacy_provenance(repo)
    pair = host.source_module('q38pair_identity_wrapper', repo / 'scripts/runtime/sglang38_pair_file_auth.py')
    base = pair.pinned_base(repo / 'scripts/runtime/sglang38_file_auth.py')
    argv = pair.bind_variant(base, slot)
    host.require(pair.CONTEXT == CONTEXT, 'pair_fixture_context_invalid')
    profile = json.loads((repo / 'configs/deployments' / (PROFILES[slot] + '.json')).read_text())
    host.require(profile['id'] == PROFILES[slot] and profile['launch']['context_size'] == CONTEXT
                 and profile['launch']['max_total_tokens'] == CONTEXT
                 and profile['launch']['tp_size'] == 1, 'pair_fixture_profile_invalid')
    result = {'profile_id': PROFILES[slot], 'slot': slot,
            'native_endpoint': dict(pair.SLOTS[slot]), 'configured_context': CONTEXT, 'tp_size': 1,
            'source_sha256': {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
                              for name in PAIR_FILES},
            'base_launcher_sha256': provenance['launcher_sha256'],
            'fixture_provenance_sha256': hashlib.sha256((HERE / 'provenance.json').read_bytes()).hexdigest(),
            'config_sha256': host.CONFIG_SHA256,
            'backend_argv_sha256': hashlib.sha256(json.dumps(argv, separators=(',', ':')).encode()).hexdigest(),
            'extension_environment': dict(host.EXTENSION_ENVIRONMENT),
            'wrapper_execution': 'PRODUCTION_PINNED_BASE_AND_BIND_VARIANT',
            'fixture_adaptations': ['base_source_location_in_readonly_checkout',
                                    'one_gpu_discovery_stub', 'closed_slot_port_and_alias', 'synthetic_engine_and_model']}
    if adaptive:
        binding = runtime_binding(repo)
        result['adaptive_runtime'] = binding.text_oci().expected_evidence(binding.load()['text']['image_id'])
        for name in ('scripts/runtime/h005_runtime_binding.py', binding.RELATIVE):
            result['source_sha256'][name] = hashlib.sha256((repo / name).read_bytes()).hexdigest()
        result['fixture_adaptations'].append('exact_outer_generation_drain_and_native_application')
    return result


# Names consumed by the unchanged installed-ModelConfig fixture.
extension_identity = pair_identity


def expected_extension_resolution(provenance):
    result = host.expected_extension_resolution(provenance)
    result.update(context_len=CONTEXT, hf_context_len=CONTEXT)
    return result


@contextmanager
def fixture_mode(slot="gpu1", *, adaptive=False):
    host.require(slot in PROFILES, "pair_fixture_slot_invalid")
    """Select only the fixed wrapper/context; preserve every old implementation."""
    command, inspect = host.docker_command, host.verify_fixture_runtime
    resolution = host.expected_extension_resolution
    oci = runtime_binding(ROOT).text_oci() if adaptive else None
    child_extra = ['--adaptive-overlay'] if adaptive else []

    def pair_command(repo, cache, context, **kwargs):
        host.require(type(context) is int and context == CONTEXT, 'pair_fixture_context_invalid')
        result = command(repo, cache, context, **kwargs)
        result[result.index(OLD_INNER)] = INNER
        result += ["--slot", slot, *child_extra]
        return result

    def pair_inspect(container, repo, cache, context):
        observed = container.get('Config', {}).get('Cmd', [])
        host.require(observed == ['-X', 'faulthandler', '-B', INNER, '--actual-image',
                                  '--repo', '/fixture', '--context', str(CONTEXT), '--slot', slot, *child_extra],
                     'pair_fixture_process_invalid')
        translated = copy.deepcopy(container)
        translated['Config']['Cmd'][3] = OLD_INNER
        translated['Config']['Cmd'] = translated['Config']['Cmd'][:-(2 + len(child_extra))]
        return inspect(translated, repo, cache, context)

    def pair_resolution(provenance):
        result = resolution(provenance)
        result.update(context_len=CONTEXT, hf_context_len=CONTEXT)
        return result

    with ExitStack() as stack:
        if adaptive:
            for name, value in {'IMAGE_ID': oci.IMAGE_ID, 'IMAGE_REFERENCE': oci.IMAGE_REFERENCE,
                                'OCI': oci, 'read_provenance': adaptive_provenance}.items():
                stack.enter_context(patch.object(host, name, value))
        for name, value in {
                'EXTENSION_CONTEXT': CONTEXT, 'EXTENSION_PROFILE': PROFILES[slot],
                'docker_command': pair_command, 'verify_fixture_runtime': pair_inspect,
                'extension_identity': lambda repo, provenance=None: pair_identity(repo, provenance, slot=slot,
                                                                                adaptive=adaptive),
                'expected_extension_resolution': pair_resolution}.items():
            stack.enter_context(patch.object(host, name, value))
        yield


def check_pair_receipt(receipt, repo, slot="gpu1", *, adaptive=False):
    """Validate an actual-image receipt, never manufacture proof or acceptance.

    The campaign must additionally bind the raw receipt SHA256 and protected
    registered-data path into its reviewed arm. This pure content validator does
    not claim to authenticate publication or to have executed the actual image.
    """
    provenance, _ = adaptive_provenance(repo) if adaptive else legacy_provenance(repo)
    oci = runtime_binding(repo).text_oci() if adaptive else host.OCI
    inspected = oci.validate_evidence(receipt.get('docker_inspect'))
    expected = {'schema_version': 2, 'kind': KIND, 'status': 'PASS',
        'image_id': provenance['image_id'], 'image_reference': provenance['image_reference'],
        'source_revision': host.SOURCE_REVISION, 'launcher_sha256': provenance['launcher_sha256'],
        'fixture_sha256': provenance['fixture_sha256'], 'support_sha256': provenance['support_sha256'],
        'source_hashes': {name: value['sha256'] for name, value in provenance['sources'].items()},
        'checks': {check: 'PASS' for check in host.CHECKS}, 'contexts': [CONTEXT],
        'image_identity_verification': 'HOST_DOCKER_INSPECT_AND_PINNED_RUN',
        'docker_inspect': inspected, 'model_execution': 'NOT_TESTED', 'native_lifespan': 'NOT_TESTED',
        'live_inference_and_agent_acceptance': 'NOT_TESTED',
        'extension_identity': pair_identity(repo, slot=slot, adaptive=adaptive),
        'model_config_resolution': expected_extension_resolution(provenance)}
    host.require(type(receipt) is dict and set(receipt) == set(expected) | {'native_results', 'container_lifetimes'}
                 and all(host.same_json(receipt.get(k), v) for k, v in expected.items()),
                 'pair_actual_image_receipt_mismatch')
    results, lifetimes = receipt['native_results'], receipt['container_lifetimes']
    host.require(type(results) is list and len(results) == 1 and type(results[0]) is dict
                 and type(lifetimes) is list and len(lifetimes) == 1,
                 'pair_actual_image_observation_missing')
    with fixture_mode(slot, adaptive=adaptive):
        host.check_native_result(results[0], provenance, CONTEXT, repo=repo)
    life = lifetimes[0]
    host.require(type(life) is dict and set(life) == {
            'container_name', 'container_id', 'outcome', 'cleanup', 'runtime_inspect'}
        and re.fullmatch(r'q38b-fixture-[a-f0-9]{32}', life.get('container_name', '')) is not None
        and re.fullmatch(r'[a-f0-9]{64}', life.get('container_id', '')) is not None
        and life.get('outcome') == 'FIXTURE_EXITED' and life.get('cleanup') == 'QUIESCENT_REMOVAL_VERIFIED'
        and host.same_json(life.get('runtime_inspect'), {
            'runtime': 'nvidia', 'visible_devices': 'none', 'driver_capabilities': 'compute,utility',
            'device_requests': [], 'host_devices': [], 'network': 'none', 'root_readonly': True,
            'model_and_secret_mounts': 'EMPTY_PRIVATE_TMPFS', 'entrypoint': ['python3'],
            'context': CONTEXT, 'status': 'PASS_HOST_INSPECT'}), 'pair_fixture_cleanup_unverified')
    return receipt


def run(repo, output, slot="gpu1", *, adaptive=False):
    pair_identity(repo, slot=slot, adaptive=adaptive)
    write = host.write_receipt

    def checked_write(path, receipt):
        receipt['kind'] = KIND
        check_pair_receipt(receipt, repo, slot=slot, adaptive=adaptive)
        write(path, receipt)

    with fixture_mode(slot, adaptive=adaptive), patch.object(host, 'write_receipt', checked_write):
        return host.run(repo, output, PROFILES[slot])


def parse_options(argv):
    parser = host.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--slot', choices=tuple(PROFILES), required=True)
    parser.add_argument('--adaptive-overlay', action='store_true',
                        help='Require the reviewed H005 derived image, source closure and outer drain wrapper')
    return parser.parse_args(argv)


def main(argv=None):
    try:
        options = parse_options(sys.argv[1:] if argv is None else argv)
        receipt = run(options.repo, options.output, options.slot, adaptive=options.adaptive_overlay)
        print(json.dumps({'status': receipt['status'], 'kind': receipt['kind'], 'model_execution': 'NOT_TESTED'}))
        return 0
    except Exception as error:
        failure = {'status': 'FAIL', 'code': 'pair_actual_image_fixture_failed'}
        if isinstance(error, host.LifetimeFailure):
            failure['lifetime'] = error.evidence
        print(json.dumps(failure, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
