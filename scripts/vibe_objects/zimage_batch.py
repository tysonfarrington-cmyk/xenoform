"""Generate stills with Z-Image Turbo through comfy-sdk -> comfy-api-proxy. usage: zimage_batch.py graph.json prompts.json outdir"""
import json, os, sys, time
os.environ["COMFY_BASE_URL"]="http://127.0.0.1:8189"; os.environ.pop("COMFY_API_KEY",None)
from comfy_sdk import Comfy
g, pj, out = sys.argv[1:4]; os.makedirs(out, exist_ok=True)
c = Comfy(client_info="xenoform-stills", timeout=None)
t0=time.time(); jobs=[]
for i,p in enumerate(json.load(open(pj))):
    wf=c.workflows.from_file(g); wf.set_input("5","text",p["prompt"]); wf.set_input("10","seed",1000+i)
    wf.set_input("7","width",1024); wf.set_input("7","height",576)
    jobs.append((p["name"], c.submit(wf)))
for name,j in jobs:
    r=j.result(); o=list(r.get_outputs("12")) or list(r.outputs); o[0].to_file(os.path.join(out,f"{name}.png")); print(f"{name} +{time.time()-t0:.1f}s",flush=True)
print("DONE",round(time.time()-t0,1))
