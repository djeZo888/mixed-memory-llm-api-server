"""Read installed source/config only; no framework import or model load."""
import json
import pathlib
import subprocess

state = json.loads(pathlib.Path('/data/services/image21-runtime-20260923/state.json').read_text())
code = '''import hashlib,json,pathlib
base=pathlib.Path('/opt/image-venv/lib/python3.12/site-packages')
paths=[base/p for p in [
'sglang/multimodal_gen/runtime/pipelines_core/stages/model_specific_stages/qwen_image21.py',
'sglang/multimodal_gen/runtime/pipelines_core/stages/decoding.py',
'sglang/multimodal_gen/runtime/entrypoints/openai/image_api.py',
'sglang/multimodal_gen/runtime/entrypoints/openai/utils.py',
'sglang/multimodal_gen/runtime/loader/component_loaders/processor_loader.py',
'sglang/multimodal_gen/runtime/loader/component_loaders/text_encoder_loader.py',
'transformers/models/qwen3_vl/processing_qwen3_vl.py',
'transformers/models/qwen2_vl/image_processing_qwen2_vl.py',
'transformers/models/qwen2_vl/image_processing_qwen2_vl_fast.py',
'transformers/models/auto/image_processing_auto.py',
'transformers/image_processing_backends.py',
'torchvision/transforms/v2/functional/_geometry.py']]
for p in (base/'sglang/multimodal_gen/runtime/loader/component_loaders').glob('*.py'):
 if 'AutoProcessor' in p.read_text() or 'ProcessorLoader' in p.read_text():paths.append(p)
paths+=[pathlib.Path('/models/processor')/p for p in ('processor_config.json','preprocessor_config.json')]
paths.append(pathlib.Path('/models/model_index.json'))
out={}
for p in paths:
 if p.is_file():
  raw=p.read_bytes();assert len(raw)<300000
  out[str(p)]={'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode()}
 else:out[str(p)]={'missing':True}
print(json.dumps(out))
'''
response = subprocess.run(['docker', 'exec', state['container']['id'], '/opt/image-venv/bin/python', '-I', '-B', '-c', code], capture_output=True, text=True, check=True, timeout=30)
print(response.stdout)
