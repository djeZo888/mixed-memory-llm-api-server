"""Fixture-only location adapter for the unchanged production pair wrapper.

No native implementation is replaced. The production pinned-base check and
bind_variant run with the same exact argv; only the base source location differs
inside the existing read-only fixture checkout. Import never reads a key.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('q38pair_fixture_wrapper', ROOT / 'scripts/runtime/sglang38_pair_file_auth.py')
pair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pair)
base = pair.pinned_base(ROOT / 'scripts/runtime/sglang38_file_auth.py')
EXPECTED = pair.bind_variant(base)


def __getattr__(name):
    return getattr(base, name)


def backend_argv(context):
    if type(context) is not int or context != pair.CONTEXT:
        raise base.LaunchError('pair_fixture_context_invalid')
    return pair.backend_argv(base)


def main(argv):
    # The existing fixture's sole launcher fault hook must reach the actual base
    # module used by its functions. Ordinary calls retain the production value.
    original = base.STARTUP_TIMEOUT
    try:
        base.STARTUP_TIMEOUT = globals().get('STARTUP_TIMEOUT', original)
        return base.main(argv)
    finally:
        base.STARTUP_TIMEOUT = original
