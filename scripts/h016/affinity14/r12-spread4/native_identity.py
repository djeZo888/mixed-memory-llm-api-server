"""Exact artifact versus lexer-effective identity for the pinned H016 runtime."""
import hashlib

RAW_TEMPLATE_SHA256 = '11ea52e156de38a458e6b7720ad45915d65b97d4ec979a09f55e3c9bd1b4d059'
EFFECTIVE_TEMPLATE_SHA256 = '16b2dac352c6cf1aef8b0a976618c76deb28c5bf3aba4c8b788fb846aa3769a4'
MODEL_PATH = '/models/MXFP4/MiMo-V2.6-Pro-RL-MXFP4-00001-of-00013.gguf'
RUNTIME_REVISION = '7ac59a6e3ad851cd41af00f678effab0598ba9a8'


def pinned_lexer_source(raw):
    """Regression model of lexer.cpp43-57; never normalize observed /props."""
    source = raw.replace('\r\n', '\n').replace('\r', '\n')
    return source[:-1] if raw.endswith('\n') else source


def compact_identity(props):
    template = props.get('chat_template')
    encoded = template.encode() if isinstance(template, str) else None
    return {'alias': props.get('model_alias'), 'build_info': props.get('build_info'),
            'model_path': props.get('model_path'),
            'context': props.get('default_generation_settings', {}).get('n_ctx'),
            'slots': props.get('total_slots'), 'is_sleeping': props.get('is_sleeping'),
            'raw_artifact_template_sha256': RAW_TEMPLATE_SHA256,
            'raw_artifact_template_bytes': 3867,
            'expected_effective_template_sha256': EFFECTIVE_TEMPLATE_SHA256,
            'expected_effective_template_bytes': 3866,
            'template_sha256': hashlib.sha256(encoded).hexdigest() if encoded is not None else None,
            'template_bytes': len(encoded) if encoded is not None else None,
            'bos_token': props.get('bos_token'), 'eos_token': props.get('eos_token'),
            'artifact_template_provenance': 'original verified GGUF inventory; not inferred from props'}


def validate_identity(observed):
    checks = [('loaded_alias_mismatch', observed['alias'] == 'mimo-v2.6-pro-rl'),
              ('loaded_build_mismatch', isinstance(observed['build_info'], str) and '7ac59a6' in observed['build_info']),
              ('loaded_model_path_mismatch', observed['model_path'] == MODEL_PATH),
              ('loaded_effective_template_mismatch', observed['template_sha256'] == EFFECTIVE_TEMPLATE_SHA256 and observed['template_bytes'] == 3866),
              ('loaded_capacity_mismatch', observed['context'] == 131072 and observed['slots'] == 1),
              ('loaded_sleeping', observed['is_sleeping'] is False)]
    for reason, passed in checks:
        if not passed:
            raise RuntimeError(reason)
