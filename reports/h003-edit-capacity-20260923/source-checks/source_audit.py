"""Offline exact-source smart-resize check, no imports of the model framework."""
import ast
import hashlib
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sources = json.loads((root / 'artifacts/native-source-current.json').read_text())
manifest = {p: {k: v for k, v in item.items() if k != 'text'} for p, item in sources.items()}
for item in sources.values():
    if 'text' in item:
        assert hashlib.sha256(item['text'].encode()).hexdigest() == item['sha256']
path = root / 'artifacts/native-source-current/image_processing_qwen2_vl.py'
tree = ast.parse(path.read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'smart_resize')
scope = {'math': math}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), scope)
config = json.loads((root / 'artifacts/native-source-current/preprocessor_config.json').read_text())
rows = []
for case, width, height, refs in [('C01', 1024, 1024, 1), ('C02', 1536, 864, 1), ('C03', 1920, 1088, 1), ('C04', 1024, 1024, 2)]:
    actual = scope['smart_resize'](height, width, factor=config['patch_size'] * config['merge_size'],
        min_pixels=config['size']['shortest_edge'], max_pixels=config['size']['longest_edge'])
    assert actual == (height, width)
    rows.append({'case': case, 'input_width_height': [width, height], 'processor_width_height': list(reversed(actual)),
                 'reference_count': refs, 'reference_vae_tokens': refs * (width // 16) * (height // 16),
                 'target_vae_tokens': (width // 16) * (height // 16)})
result = {'status': 'PASS', 'scope': 'Exact installed smart_resize function executed locally; source proof only, no model import or execution.',
          'cases': rows, 'source_hashes': manifest,
          'not_claimed': ['GPU capacity', 'live fidelity', 'qualified profiles', 'denoiser repair']}
(root / 'artifacts/source-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print('PASS: exact installed smart_resize preserves all four planned working geometries.')
