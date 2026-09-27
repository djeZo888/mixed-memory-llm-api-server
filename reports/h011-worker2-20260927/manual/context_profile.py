"""Closed offline H011 candidate profiles; production remains the default.

Pinned scheduler margins must be checked against source and actual allocation.
Neither these numbers nor a profile selection establishes occupied-context proof.
"""
from dataclasses import dataclass

REVISION = 'eb9eb208eb0d988989d07a6a12d0fdeb5f52574a'
TARGET = 1_000_000
OUTPUT = 1024

@dataclass(frozen=True)
class Profile:
    name: str
    context: int
    port: int

    @property
    def bounds(self):
        return {'max_input_tokens': self.context - 7,
                'max_total_tokens': self.context - 2}

    @property
    def allocation(self):
        return {'context': self.context, 'pool': self.context,
                'max_req_len': self.context - 1,
                'max_req_input_len': self.context - 6}

PROFILES = {'production480k': Profile('production480k', 480000, 30010),
            'manual1m': Profile('manual1m', 1048576, 30011)}

def select(name='production480k'):
    if type(name) is not str or name not in PROFILES:
        raise ValueError('context_profile_not_allowlisted')
    return PROFILES[name]

def from_context(context):
    if type(context) is not int:
        raise ValueError('context_profile_not_allowlisted')
    for profile in PROFILES.values():
        if context == profile.context:
            return profile
    raise ValueError('context_profile_not_allowlisted')

def require_budget(count, output, profile):
    if (type(count) is not int or type(output) is not int or count < 1
            or not 1 <= output <= 65536
            or count > profile.bounds['max_input_tokens']
            or count + output > profile.bounds['max_total_tokens']):
        raise ValueError('native_context_boundary_exceeded')

def verify_allocation(actual, profile):
    if actual != profile.allocation:
        raise ValueError('flash_native_allocation_mismatch')

def verify_count(count, *, target=TARGET, output=OUTPUT, profile=None):
    profile = profile or select('manual1m')
    expected = {'count': target, 'tokenizer_revision': REVISION,
                'template_revision': REVISION, 'context_limit': profile.context}
    if count != expected:
        raise ValueError('native_fixture_parity_failure')
    require_budget(target, output, profile)
