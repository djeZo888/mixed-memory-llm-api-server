#!/usr/bin/env python3
"""Offline exact-artifact trace. No model/API calls; no qualification changes."""
import argparse,base64,hashlib,io,json,pathlib,sys
from PIL import Image
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.image_api import protocol

def pixels(raw,mode='RGB'):
 with Image.open(io.BytesIO(raw)) as im:
  im.load();return im.convert(mode).tobytes()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifacts',type=pathlib.Path);args=p.parse_args();a=args.artifacts
 rgb=(a/'original-rgb.png').read_bytes();rgba=(a/'original-rgba.png').read_bytes()
 assert hashlib.sha256(rgb).hexdigest()=='9756c58b989a7656162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575'
 assert hashlib.sha256(rgba).hexdigest()=='d055af30b1aa6e3f9546a5cec1adf2be25959cd8af796f4001124c6e0024c487'
 assert pixels(rgb)==pixels(rgba)
 with Image.open(io.BytesIO(rgb)) as im:
  assert im.mode=='RGB' and im.size==(1024,1024) and not im.getexif()
  assert im.convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS).convert('RGB').tobytes()==im.tobytes()
 # In-memory fixture allows testing the dormant edit wire path; never deployed.
 cfg={'profiles':[{'operation':'edit','size':'1024x1024','references':1,'transparent':False,'conditioning':'','evidence_sha256':'0'*64}]}
 request=protocol.validate({'prompt':'Change the red teapot to blue, keeping its shape, table, window, and lighting unchanged.','seed':42},[rgb],'edit',cfg)
 assert request.images==[rgb] and request.native_size==(1024,1024) and request.crop_bottom==0
 assert request.native['guidance_scale']==request.native['true_cfg_scale']==1
 assert request.native['num_inference_steps']==40 and request.native['generator_device']=='cpu' and 'negative_prompt' not in request.native
 checks=['original_hashes','RGB_normalization_pixel_identity','no_EXIF','native_square_resize_identity','adapter_input_byte_identity','native_settings']
 outputs=[]
 for prefix,raw_name in [('d02','d02-raw-reconstruction.png'),('d03','d03-raw-output.png')]:
  raw=(a/raw_name).read_bytes();delivered=(a/(prefix+'-delivered-rgb.png')).read_bytes()
  response=json.dumps({'data':[{'b64_json':base64.b64encode(raw).decode()}]}).encode()
  actual=base64.b64decode(protocol.public_output(response,request)['data'][0]['b64_json'])
  assert pixels(actual)==pixels(raw)==pixels(delivered)
  with Image.open(io.BytesIO(actual)) as im:assert im.mode=='RGB' and im.size==(1024,1024) and not im.info
  checks.append(prefix+'_actual_public_output_pixel_identity')
  outputs.append({'case':prefix,'raw_sha256':hashlib.sha256(raw).hexdigest(),'delivered_sha256':hashlib.sha256(delivered).hexdigest()})
 print(json.dumps({'status':'PASS','checks':checks,'outputs':outputs,'scope':'CPU exact-artifact trace only; no edit qualification or GPU inference'},indent=2))
if __name__=='__main__':main()
