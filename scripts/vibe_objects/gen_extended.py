"""Extended-vibe stills: Z-Image Turbo through comfy-sdk -> comfy-api-proxy (:8189). usage: gen_extended.py [prompts.json]. Outputs go to $XENO_STILLS_OUT/<vibe>/; integrate copies them into ui_static/objects."""
import json, os, sys, time, subprocess
os.environ["COMFY_BASE_URL"]="http://127.0.0.1:8189"; os.environ.pop("COMFY_API_KEY",None)
from comfy_sdk import Comfy
G=os.path.join(os.path.dirname(os.path.abspath(__file__)), "zimage_t2i_api.json")
P=json.load(open(sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "extended_prompts.json")))
c=Comfy(client_info="xenoform-vibes", timeout=None); t0=time.time(); jobs=[]
for vibe,items in P.items():
    out=os.path.join(os.environ.get("XENO_STILLS_OUT", "extended_stills"),vibe); os.makedirs(out,exist_ok=True)
    for i,p in enumerate(items):
        dst=os.path.join(out,p["name"]+".jpg")
        if os.path.exists(dst): continue
        wf=c.workflows.from_file(G); wf.set_input("5","text",p["prompt"]); wf.set_input("10","seed",int(p.get("seed",3100+i)))
        wf.set_input("7","width",1024); wf.set_input("7","height",576); wf.set_input("12","filename_prefix","xenoform/vibes")
        jobs.append((dst,c.submit(wf)))
print("queued",len(jobs),flush=True)
for dst,j in jobs:
    r=j.result(); o=list(r.get_outputs("12")) or list(r.outputs); tmp=dst+".png"; o[0].to_file(tmp)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",tmp,"-q:v","3",dst],check=True); os.remove(tmp)
print("DONE",round(time.time()-t0),flush=True)
