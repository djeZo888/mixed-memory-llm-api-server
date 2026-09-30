"""CPU-only candidate codec in existing adapter venv; no installed changes."""
import base64, hashlib, json, sys, types

def process(payload):
    source = base64.b64decode(payload['protocol']['data'], validate=True)
    assert hashlib.sha256(source).hexdigest() == payload['protocol']['sha256']
    module = types.ModuleType('capacity_candidate_protocol')
    sys.modules[module.__name__] = module
    exec(compile(source, 'reviewed-candidate-protocol.py', 'exec'), module.__dict__)
    case = payload['case']
    images = [base64.b64decode(x['data'], validate=True) for x in payload['originals']]
    assert len(images) == len(case['references'])
    for raw, ref in zip(images, case['references']):
        assert hashlib.sha256(raw).hexdigest() == ref['sha256']
    private = {'operation': 'edit', 'references': len(images), 'size': case['size'],
               'native_size': case['native_size'], 'crop_bottom': case['crop_bottom'],
               'transparent': False, 'conditioning': ''}
    request = module.validate({'prompt': case['prompt'], 'size': case['size'], 'seed': case['seed']},
                              images, 'edit', {'profiles': [private]})
    for raw, ref in zip(request.images, case['references']):
        assert hashlib.sha256(raw).hexdigest() == ref['working_sha256']
    if payload['action'] == 'prepare':
        import PIL
        return {'native': request.native, 'pillow': PIL.__version__,
                'working': [{'data': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest()}
                            for raw in request.images]}
    assert payload['action'] == 'deliver'
    value = module.public_output(base64.b64decode(payload['response'], validate=True), request)
    return {'delivered': value['data'][0]['b64_json'], 'seed': value['data'][0]['seed']}

if __name__ == '__main__':
    print(json.dumps(process(json.load(sys.stdin))))
