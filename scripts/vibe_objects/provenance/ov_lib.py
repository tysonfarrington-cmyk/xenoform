# Xenoform overnight library run: shared helpers (graphs, robust ComfyUI runner, gates, disk, log).
import os, sys, json, time, glob, shutil, subprocess, urllib.request, urllib.error, datetime
import numpy as np, cv2
CU=r'C:\Users\tyson\AI\ComfyUI'; OUT=CU+r'\output'; INP=CU+r'\input'
BAT=CU+r'\run_comfy_3080ti_tf32off.bat'
HERE=os.path.dirname(os.path.abspath(__file__))
PAUSE=os.path.join(HERE,'PAUSE'); STOP=os.path.join(HERE,'STOP')
URL='http://127.0.0.1:8188'
LOG=open(os.path.join(HERE,'log.jsonl'),'a',encoding='utf-8')
def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def L(kind,**kw):
    kw=dict(t=now(),kind=kind,**kw); s=json.dumps(kw); print(s,flush=True); LOG.write(s+'\n'); LOG.flush()
def free_gb(drive):
    return shutil.disk_usage(drive+':\\').free/1e9
def disk_ok():
    c,g=free_gb('C'),free_gb('G')
    if c<30 or g<30: L('disk_low',C=round(c,1),G=round(g,1)); return False
    return True
def wait_pause():
    while os.path.exists(PAUSE): time.sleep(20)
def stopped(): return os.path.exists(STOP)
def alive():
    try: urllib.request.urlopen(URL+'/queue',timeout=10).read(); return True
    except Exception: return False
_last_relaunch=[0]
def ensure_comfy():
    if alive(): return True
    t0=time.time()
    while time.time()-t0<60:      # give a busy/slow server a minute
        time.sleep(10)
        if alive(): return True
    if time.time()-_last_relaunch[0]<900: L('comfy_down_wait'); time.sleep(120); return alive()
    _last_relaunch[0]=time.time(); L('comfy_relaunch',bat=BAT)
    subprocess.Popen(['cmd','/c','start','ComfyUI',BAT],cwd=CU,creationflags=0x00000008)
    for _ in range(60):
        time.sleep(10)
        if alive(): L('comfy_back'); time.sleep(20); return True
    L('comfy_relaunch_failed'); return False
def run(g,label,timeout=1800):
    """Submit and wait. Returns dict(status, seconds, compute, files, error). Retries once after a crash."""
    for attempt in range(2):
        wait_pause()
        if not ensure_comfy(): return dict(status='comfy_down',seconds=0,files=[],error=['comfy down'])
        try:
            req=urllib.request.Request(URL+'/prompt',data=json.dumps({'prompt':g,'client_id':'xeno_overnight'}).encode(),headers={'Content-Type':'application/json'})
            pid=json.loads(urllib.request.urlopen(req,timeout=60).read())['prompt_id']
        except urllib.error.HTTPError as e:
            return dict(status='submit_error',seconds=0,files=[],error=[e.read().decode()[:1500]])
        except Exception as e:
            L('submit_exc',label=label,err=str(e)); continue
        t0=time.time(); h=None; bad=0
        while time.time()-t0<timeout:
            time.sleep(3)
            try:
                h=json.loads(urllib.request.urlopen(URL+'/history/'+pid,timeout=30).read()); bad=0
            except Exception:
                bad+=1
                if bad>=20: break   # ~1 min unreachable -> treat as crash
                continue
            if pid in h and h[pid].get('status',{}).get('status_str') in ('success','error'): break
        else:
            L('timeout',label=label); return dict(status='timeout',seconds=round(time.time()-t0,1),files=[],error=['timeout'])
        if bad>=20 or h is None or pid not in h:
            L('crash_during',label=label); continue
        st=h[pid]['status']; files=[]
        for o in h[pid].get('outputs',{}).values():
            for k in ('images','videos','gifs'):
                for f in o.get(k,[]): files.append(os.path.join(OUT,f.get('subfolder',''),f['filename']))
        ts={m[0]:m[1].get('timestamp') for m in st.get('messages',[]) if m[0] in ('execution_start','execution_success','execution_error')}
        comp=None
        if ts.get('execution_start') and (ts.get('execution_success') or ts.get('execution_error')):
            comp=round(((ts.get('execution_success') or ts.get('execution_error'))-ts['execution_start'])/1000,1)
        err=[m[1].get('exception_message','')[:600]+' @'+str(m[1].get('node_type')) for m in st.get('messages',[]) if m[0]=='execution_error']
        return dict(status=st.get('status_str'),seconds=round(time.time()-t0,1),compute=comp,files=files,error=err)
    return dict(status='crashed',seconds=0,files=[],error=['crashed twice'])
# ---------- graphs ----------
def zgraph(text,seed,pre,W=1024,H=576):
    g={}
    def n(i,cls,**inp): g[str(i)]={'class_type':cls,'inputs':inp}
    n(1,'UnetLoaderGGUF',unet_name='z-image-turbo-Q8_0.gguf'); n(2,'CLIPLoader',clip_name='qwen_3_4b.safetensors',type='lumina2',device='default')
    n(3,'VAELoader',vae_name='ae.safetensors'); n(4,'ModelSamplingAuraFlow',model=['1',0],shift=3.0)
    n(5,'CLIPTextEncode',clip=['2',0],text=text); n(6,'ConditioningZeroOut',conditioning=['5',0]); n(7,'EmptySD3LatentImage',width=W,height=H,batch_size=1)
    n(8,'KSampler',model=['4',0],positive=['5',0],negative=['6',0],latent_image=['7',0],seed=seed,steps=9,cfg=1.0,sampler_name='res_multistep',scheduler='simple',denoise=1.0)
    n(9,'VAEDecode',samples=['8',0],vae=['3',0]); n(10,'SaveImage',images=['9',0],filename_prefix=pre); return g
def kgraph(text,refs,seed,pre,W=1024,H=576):
    g={}
    def n(i,cls,**inp): g[str(i)]={'class_type':cls,'inputs':inp}
    n(1,'UNETLoader',unet_name='flux-2-klein-4b.safetensors',weight_dtype='default'); n(2,'CLIPLoader',clip_name='qwen_3_4b.safetensors',type='flux2',device='default')
    n(3,'VAELoader',vae_name='flux2-vae.safetensors'); n(4,'CLIPTextEncode',clip=['2',0],text=text); n(5,'ConditioningZeroOut',conditioning=['4',0])
    pos,neg=['4',0],['5',0]; k=100
    for r in refs:
        n(k,'LoadImage',image=r); n(k+1,'ImageScaleToTotalPixels',image=[str(k),0],upscale_method='lanczos',megapixels=1.0,resolution_steps=1)
        n(k+2,'VAEEncode',pixels=[str(k+1),0],vae=['3',0]); n(k+3,'ReferenceLatent',conditioning=pos,latent=[str(k+2),0]); n(k+4,'ReferenceLatent',conditioning=neg,latent=[str(k+2),0])
        pos,neg=[str(k+3),0],[str(k+4),0]; k+=5
    n(6,'EmptyFlux2LatentImage',width=W,height=H,batch_size=1); n(7,'Flux2Scheduler',steps=4,width=W,height=H)
    n(8,'KSamplerSelect',sampler_name='euler'); n(9,'RandomNoise',noise_seed=seed); n(10,'CFGGuider',model=['1',0],positive=pos,negative=neg,cfg=1.0)
    n(11,'SamplerCustomAdvanced',noise=['9',0],guider=['10',0],sampler=['8',0],sigmas=['7',0],latent_image=['6',0])
    n(12,'VAEDecode',samples=['11',0],vae=['3',0]); n(13,'SaveImage',images=['12',0],filename_prefix=pre); return g
CKPT='ltx-2.3-22b-distilled-fp8.safetensors'; TE='gemma_3_12B_it_fp4_mixed.safetensors'; UPS='ltx-2.3-spatial-upscaler-x2-1.1.safetensors'
NEG='pc game, cartoon, ugly, blurry, distorted, text, letters, watermark, person, human face, eyes, hands, flat lighting, grey matte plastic'
def ltx23(prompt,guides,seed,L,pre,W=768,H=448,FPS=24):
    """GR morph23v graph (2-stage distilled + x2 latent upscaler, guides re-applied at stage 2). guides: (img or 'vid.mp4@skip@cap', frame_idx, strength)"""
    g={}
    def n(i,cls,**inp): g[str(i)]={'class_type':cls,'inputs':inp}
    n(1,'CheckpointLoaderSimple',ckpt_name=CKPT); n(2,'LTXAVTextEncoderLoader',text_encoder=TE,ckpt_name=CKPT,device='default'); n(3,'LTXVAudioVAELoader',ckpt_name=CKPT)
    n(4,'CLIPTextEncode',clip=['2',0],text=prompt); n(5,'CLIPTextEncode',clip=['2',0],text=NEG)
    n(6,'LTXVConditioning',positive=['4',0],negative=['5',0],frame_rate=float(FPS))
    n(7,'EmptyLTXVLatentVideo',width=W//2,height=H//2,length=L,batch_size=1)
    imgs={}; nid=[100]
    def gd(pos,neg,lat):
        for (img,idx,st) in guides:
            if img not in imgs:
                a=nid[0]
                if '@' in img:
                    vn,sk,cp=img.split('@'); n(a,'VHS_LoadVideo',video=vn,force_rate=float(FPS),custom_width=W,custom_height=H,frame_load_cap=int(cp),skip_first_frames=int(sk),select_every_nth=1)
                else: n(a,'LoadImage',image=img)
                n(a+1,'LTXVPreprocess',image=[str(a),0],img_compression=18); imgs[img]=str(a+1); nid[0]+=2
            k=nid[0]; n(k,'LTXVAddGuide',positive=pos,negative=neg,vae=['1',2],latent=lat,image=[imgs[img],0],frame_idx=idx,strength=st)
            pos,neg,lat=[str(k),0],[str(k),1],[str(k),2]; nid[0]+=1
        return pos,neg,lat
    p1,n1,l1=gd(['6',0],['6',1],['7',0])
    n(9,'LTXVEmptyLatentAudio',frames_number=L,frame_rate=FPS,batch_size=1,audio_vae=['3',0]); n(10,'LTXVConcatAVLatent',video_latent=l1,audio_latent=['9',0])
    n(11,'CFGGuider',model=['1',0],positive=p1,negative=n1,cfg=1.0); n(12,'KSamplerSelect',sampler_name='euler')
    n(13,'ManualSigmas',sigmas='1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0'); n(14,'RandomNoise',noise_seed=seed)
    n(15,'SamplerCustomAdvanced',noise=['14',0],guider=['11',0],sampler=['12',0],sigmas=['13',0],latent_image=['10',0])
    n(16,'LTXVSeparateAVLatent',av_latent=['15',0]); n(30,'LTXVCropGuides',positive=p1,negative=n1,latent=['16',0])
    n(17,'LatentUpscaleModelLoader',model_name=UPS); n(18,'LTXVLatentUpsampler',samples=['30',2],upscale_model=['17',0],vae=['1',2])
    p2,n2,l2=gd(['6',0],['6',1],['18',0])
    n(20,'LTXVConcatAVLatent',video_latent=l2,audio_latent=['16',1]); n(31,'CFGGuider',model=['1',0],positive=p2,negative=n2,cfg=1.0)
    n(21,'ManualSigmas',sigmas='0.85, 0.7250, 0.4219, 0.0'); n(22,'RandomNoise',noise_seed=42)
    n(23,'SamplerCustomAdvanced',noise=['22',0],guider=['31',0],sampler=['12',0],sigmas=['21',0],latent_image=['20',0])
    n(24,'LTXVSeparateAVLatent',av_latent=['23',0]); n(32,'LTXVCropGuides',positive=p2,negative=n2,latent=['24',0])
    n(25,'VAEDecodeTiled',samples=['32',2],vae=['1',2],tile_size=512,overlap=64,temporal_size=64,temporal_overlap=8)
    n(27,'CreateVideo',images=['25',0],fps=float(FPS)); n(28,'SaveVideo',video=['27',0],filename_prefix=pre,**{'format':'auto','format.codec':'auto'})
    return g
# ---------- gates ----------
def still_gate(path):
    im=cv2.imread(path); g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY).astype(np.float32)/255; h,w=g.shape
    b=max(4,int(0.04*min(h,w))); border=np.concatenate([g[:b].ravel(),g[-b:].ravel(),g[:,:b].ravel(),g[:,-b:].ravel()]).mean()
    obj=(g>0.18).mean(); luma=g.mean()
    hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV); spec=((hsv[...,2]>235)&(hsv[...,1]<60)).mean()
    ok=0.03<=luma<=0.45 and 0.02<=obj<=0.65 and border<0.2
    return dict(ok=bool(ok),luma=round(float(luma),3),obj=round(float(obj),3),border=round(float(border),3),spec=round(float(spec),4))
def frames_of(path):
    cap=cv2.VideoCapture(path); fr=[]
    while True:
        ok,f=cap.read()
        if not ok: break
        fr.append(f)
    return fr
def clip_gate(path):
    fr=frames_of(path)
    g=[cv2.cvtColor(cv2.resize(f,(160,96)),cv2.COLOR_BGR2GRAY).astype(np.float32) for f in fr]
    if len(g)<20: return dict(ok=False,n=len(g),why='short')
    d=np.array([np.abs(g[i+1]-g[i]).mean() for i in range(len(g)-1)])
    cuts=[i+1 for i in range(2,len(d)-2) if d[i]>12 and d[i]>=d[i-1] and d[i]>=d[i+1] and d[i]>3*np.median(d[max(0,i-6):i+7])]
    run_=best=0
    for x in d[4:]:
        run_=run_+1 if x<0.4 else 0; best=max(best,run_)
    luma=float(np.mean([x.mean() for x in g]))/255
    first_cut=next((c for c in cuts if c>=12),None)
    live=first_cut if first_cut else len(g)
    med=float(np.median(d[4:live-1])) if live>8 else 0.0
    midcut=any(12<=c<=len(g)-16 for c in cuts)
    ok=(live>=72) and 0.6<=med<=25 and luma>=0.03 and not midcut
    why=[] if ok else [w for w,c in (('midcut',midcut),('cut_early',live<72),('static',med<0.6),('chaos',med>25),('dark',luma<0.03)) if c]
    return dict(ok=bool(ok),n=len(g),med=round(med,2),max=round(float(d[2:].max()),1),cuts=cuts,live=live,freeze=best,luma=round(luma,3),why=why,d=[round(float(x),2) for x in d])
def crop_to(path,dst,W=768,H=448):
    im=cv2.imread(path); h,w=im.shape[:2]; tw=int(round(h*W/H))
    if tw<=w: x=(w-tw)//2; im=im[:,x:x+tw]
    else:
        th=int(round(w*H/W)); y=(h-th)//2; im=im[y:y+th]
    cv2.imwrite(dst,cv2.resize(im,(W,H),interpolation=cv2.INTER_AREA))
def latest(pat):
    fs=sorted(glob.glob(pat),key=os.path.getmtime); return fs[-1] if fs else None
