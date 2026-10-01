#!/usr/bin/env python3
"""Describe candidate owner graph and argv; never execute any runtime command."""
import argparse
import copy
import json
from pathlib import Path
import re


def plan(config, profile='16k'):
    if config.get('activation')!='DISABLED_SOURCE_PREPARATION':raise ValueError('source_preparation_gate_required')
    legacy=config.get('schema')=='h039-isolated-vision-candidate-v1'
    if profile not in config['profiles'] or (not legacy and profile!='16k'):raise ValueError('unknown_profile')
    image=config['container']['image']
    if not re.fullmatch(r'vllm/vllm-openai@sha256:[0-9a-f]{64}',image):raise ValueError('immutable_runtime_image_required')
    caps=config['profiles'][profile]
    if not 16384<=caps['qwenTotalTokens']<=32768 or caps['ocrTotalTokens']!=8192 or caps['maxOutputTokens']!=4096 or caps['concurrencyPerService']!=1 or caps['pagesPerRequest']!=1 or caps['cropsPerInference']!=1 or caps['maxImagePixels']!=2097152:raise ValueError('bounded_profile_required')
    if sum(m['gpuMemoryUtilization'] for m in config['models'])>.93+1e-9:raise ValueError('combined_vram_reserve_required')
    if not legacy and (config['service']['enabled'] or config['placement']['proposedGpuUuid']!='GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf' or caps['cropsPerRequest']!=8):raise ValueError('disabled_exact_placement_required')
    expected={'interpretation':('Qwen/Qwen3.5-9B','c202236235762e1c871ad0ccb60c8ee5ba337b9a',18191),'ocr':('PaddlePaddle/PaddleOCR-VL-1.6','c5630abae1d940eafe0697512a0325494b02ab42',18192)}
    servers=[]
    for model in config['models']:
        if (model['repo'],model['revision'],model['candidatePort'])!=expected[model['role']]:raise ValueError('exact_models_required')
        argv=['vllm','serve',model['candidateModelPath'],'--served-model-name',model['repo'],'--dtype','bfloat16','--tensor-parallel-size','1','--host','127.0.0.1','--port',str(model['candidatePort']),'--max-num-seqs','1','--gpu-memory-utilization',str(model['gpuMemoryUtilization']),'--max-model-len',str(caps['qwenTotalTokens'] if model['role']=='interpretation' else caps['ocrTotalTokens']),'--max-num-batched-tokens','4096','--mm-processor-cache-gb','0','--limit-mm-per-prompt','{"image":1,"video":0}']
        argv+=['--reasoning-parser','qwen3'] if model['role']=='interpretation' else ['--no-enable-prefix-caching']
        # Future reviewed private files contain the key; no secret is embedded here.
        argv+=['--disable-uvicorn-access-log']
        servers.append(dict(repo=model['repo'],revision=model['revision'],argv=argv,execute=False,remoteCodeExecution=False,owner=f"H043-VISION-{model['role'].upper()}-FUTURE",image=image,gpuUuid=config['placement']['proposedGpuUuid'],artifactReadOnlyMount={'host':model['hostArtifactPath'],'container':model['candidateModelPath']},privateCredentialMount=f"/run/secrets/vision-{model['role']}.key",network='private candidate namespace; loopback only; no external egress',environment={'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','CUDA_VISIBLE_DEVICES':config['placement']['proposedGpuUuid'],'VLLM_API_KEY':'INJECT_FROM_PRIVATE_FD_BY_REVIEWED_SUPERVISOR_NOT_LITERAL','VLLM_NO_USAGE_STATS':'1'},readiness=['owned process/container generation','exact source/image/model artifact binding','authenticated /v1/models exact alias','architecture/processor/kernel/SM8.9 verification','bounded no-generation identity before separately gated model test'],shutdown=['close service admission','retain unsettled job ledger','drain model response or use exact owned runtime stop boundary','prove owned process/container and GPU allocations absent','preserve artifact/history and unrelated owners']))
    graph=dict(execute=False,sourceOwner='root-reviewed source successor',deploymentOwner='UNASSIGNED_REQUIRE_EXACT_FINITE_ROOT_GO',serviceOwner='H043-VISION-JOB-SERVICE-FUTURE',hostOwner='separately gated normal Sova host',serviceConstruction=['PrivateLedger(private0700Path)','LocalVisionBackend(service, protectedKeyCallback, enabled=False)','VisionService(ledger, service, backend, enabled=False)','BoundedHTTPServer((127.0.0.1,18193), service, protectedBearer)'],serviceSourceMount='reviewed read-only scripts/vision service.py/backend.py with per-file hashes',servicePrivateWritableMount='/data/logs/H043-VISION-FUTURE/job-ledger 0700 owner uid; records 0600; no workspace/model path access',serviceRoutes=['GET /v1/technical-vision/capabilities','POST /v1/technical-vision/jobs','POST /v1/technical-vision/requests/:requestId/status','POST /v1/technical-vision/jobs/:jobId/status','POST /v1/technical-vision/jobs/:jobId/cancel'],privateIngress=dict(enabled=False,bindProposal='10.156.100.60:18193 only',forwardOnly='http://127.0.0.1:18193',review='separately owned authenticated fixed-route bridge; private interface firewall allow only approved host; no general proxy/redirects; body/deadline caps; never log Authorization or payload; preserve byte-exact multipart; current TS real-origin policy requires this bridge'),telemetry=['GPU UUID exact before placement','total/used/free VRAM plus per-owned-process memory at residency and workload peak','>=3440 MiB/7% free at every accepted peak','weights + vision encoder + KV/cache 16k/8k + allocator/CUDA graph/runtime + peer owners measured together'],rollback=['gate normal tool/ingress closed','stop only exact new owned service/backend instances','retain durable interrupted/cancelling records and original run owner','remove only candidate routes/mounts after owned shutdown proof','restore saved reviewed prior owner configuration; no blind old GO replay'],compatibility='PENDING: official current sources do not prove candidate digest architecture/kernel/API support',nominalFractions='0.72 + 0.18 proposals only; not GPU-fit evidence',sequentialAlternative='one-at-a-time model residency needs separately reviewed lifecycle owner graph; this service does not launch or retire models')
    return dict(activation=config['activation'],profile=profile,execute=False,gpuUuidProposed=config['placement']['proposedGpuUuid'],servers=servers,gates=config['gates'],ownerGraph=graph)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,default=Path('/opt/vision/candidate.json'));parser.add_argument('--profile',choices=('16k','32k'),default='16k');args=parser.parse_args();print(json.dumps(plan(json.loads(args.config.read_text()),args.profile),indent=2))

if __name__=='__main__':main()
