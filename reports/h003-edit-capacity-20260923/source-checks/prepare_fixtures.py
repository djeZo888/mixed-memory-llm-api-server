"""Explicit diagnostic-only CPU preparation; no product resizing or inference."""
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image

root = Path(__file__).resolve().parents[1]
tasks = root.parent
edit = tasks / 'H003-EDIT-20260923/artifacts'
dest = root / 'artifacts/fixtures'
dest.mkdir(exist_ok=True)
items = [
    ('teapot-original.png', edit / 'original-rgb.png', '9756c58b989a7656162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575', [42]),
    ('teapot-fail42.png', edit / 'prior-sglang-rgb-edit.png', 'a76c98a479c2e319677b931e699373b376846e3bfd2769d18ca66c74c99d706b', [42]),
    ('teapot-pass43.png', edit / 'd04-delivered-rgb.png', 'c718b9feb9c7825cb66b69b69be5e87829b811fb536fcc109346c73533a281bb', [42, 43]),
    ('astronaut-1024.png', edit / 'd05-fixture/astronaut-1024.png', '09fc2049a0c52f366a3fa38cc6cf6e2494cdd934147fe3994192965d78d03bf5', []),
    ('astronaut-original.png', edit / 'd05-fixture/astronaut-original.png', '88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5', []),
    ('lake-bled-fullhd.png', tasks / 'H003-DEPLOY-20260923/artifacts/lake-bled-fullhd.png', '262ac543e0ca4fe6031eda20e8171d65ae42e8b30f681189ec83039f30fde506', [23092301]),
]
manifest = {}
for name, source, digest, seeds in items:
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    (dest / name).write_bytes(raw)
    with Image.open(source) as im:
        manifest[name] = {'source': str(source), 'sha256': digest, 'dimensions': list(im.size), 'mode': im.mode, 'known_ancestor_seeds': seeds}
for name in ('LICENSE.md', 'PREPARATION.json'):
    shutil.copyfile(edit / 'd05-fixture' / name, dest / ('astronaut-' + name))
with Image.open(dest / 'lake-bled-fullhd.png') as im:
    working = im.resize((1536, 864), Image.Resampling.LANCZOS)
    working.save(dest / 'lake-bled-1536x864-diagnostic.png')
manifest['lake-bled-1536x864-diagnostic.png'] = {
    'source': str(dest / 'lake-bled-fullhd.png'), 'source_sha256': manifest['lake-bled-fullhd.png']['sha256'],
    'sha256': hashlib.sha256((dest / 'lake-bled-1536x864-diagnostic.png').read_bytes()).hexdigest(),
    'dimensions': [1536, 864], 'source_dimensions': [1920, 1080], 'known_ancestor_seeds': [23092301],
    'preparation': 'Diagnostic-only uniform 0.8 LANCZOS resize; no crop, stretch or padding; original unchanged.',
    'authorization': 'User C02 permits an explicitly documented diagnostic working copy from main LakeBled. This is not product resize approval.',
    'provenance': 'Retained model-generated Lake Bled scene, seed23092301; native-size fixture, not a natural photograph.'}
(root / 'artifacts/fixture-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Verified and copied bounded retained fixtures; one diagnostic CPU resize; zero model calls.')
