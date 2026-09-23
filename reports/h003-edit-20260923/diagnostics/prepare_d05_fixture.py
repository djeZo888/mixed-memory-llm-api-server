"""Authorized TEST-FIXTURE preparation only; never a product upload path."""
from PIL import Image, __version__ as pillow_version
from pathlib import Path
import datetime,hashlib,json
p=Path('artifacts/d05-fixture');source=p/'astronaut-original.png';raw=source.read_bytes()
with Image.open(source) as im:
 im.load();assert im.size==(512,512) and im.mode=='RGB'
 work=im.resize((1024,1024),Image.Resampling.LANCZOS)
 work.save(p/'astronaut-1024.png')
manifest={'source_url':'https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png','source_documentation':'https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut','attribution':'NASA Great Images / photograph of astronaut Eileen Collins, distributed as scikit-image astronaut sample','license':'Public domain / no known copyright restrictions, per official scikit-image documentation','original':{'file':source.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'size':[512,512],'mode':'RGB'},'working_copy':{'file':'astronaut-1024.png','sha256':hashlib.sha256((p/'astronaut-1024.png').read_bytes()).hexdigest(),'size':[1024,1024],'mode':'RGB'},'preparation':{'authorization':'ROOT-D05-D06-REVIEW.md and Coordinator response to D05-FIXTURE-NEEDED.md; explicit user continuation','operation':'uniform2x LANCZOS resampling, original aspect1:1 preserved; no crop or padding','pillow_version':pillow_version,'original_preserved':True,'product_upload_policy_changed':False,'model_generation_calls':0},'provenance':'Public natural photograph, not a model-generated reference; no model generation seed','utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(p/'PREPARATION.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
