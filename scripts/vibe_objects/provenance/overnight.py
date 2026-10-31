# Xenoform overnight library run (resume-safe). python overnight.py [stage ...]   stages: objects review klein morphs textures
import os, sys, json, time, glob, shutil, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ov_lib import *
P=json.load(open(os.path.join(HERE,'plan.json'),encoding='utf-8'))
D={k:os.path.join(HERE,k) for k in ('objects','klein','clips','textures')}
for v in D.values(): os.makedirs(v,exist_ok=True)
MATS=P['materials']; NAMES=P['names']
def past_deadline():
    hh,mm=map(int,P['deadline'].split(':')); n=datetime.datetime.now()
    return n.hour<12 and (n.hour,n.minute)>=(hh,mm)
def cull():
    f=os.path.join(HERE,'cull.json')
    return json.load(open(f)) if os.path.exists(f) else {}
def inp_obj(name,mat='gr'): return f'ov_{name}_{mat}.png'
# ---------------- stage: objects (Z-Image) ----------------
def stage_objects():
    todo=P['objects']+[dict(t,silhouette='texture',pose='plate') for t in P['textures']]
    for o in todo:
        if stopped() or not disk_ok(): return
        dst=os.path.join(D['objects'],o['name']+'.png')
        if os.path.exists(dst): continue
        best=None
        for k,seed in enumerate((o['seed'],o['seed']+1000)):
            pre=f"xeno_ov/obj/{o['name']}_s{seed}"
            r=run(zgraph(o['prompt'],seed,pre),'obj_'+o['name'])
            f=latest(os.path.join(OUT,'xeno_ov','obj',f"{o['name']}_s{seed}_*.png"))
            if not f: L('obj_fail',name=o['name'],seed=seed,err=r.get('error')); continue
            gt=still_gate(f) if o.get('pose')!='plate' else dict(ok=True)
            L('obj',name=o['name'],seed=seed,sec=r.get('compute'),gate=gt)
            shutil.copy(f,os.path.join(D['objects'],f"{o['name']}_s{seed}.png"))
            if best is None or gt['ok']: best=(f,seed)
            if gt['ok']: break
        if best:
            shutil.copy(best[0],dst); json.dump(dict(seed=best[1]),open(dst+'.json','w'))
            if o.get('pose')!='plate': crop_to(best[0],os.path.join(INP,inp_obj(o['name'])))
            else: crop_to(best[0],os.path.join(INP,f"ov_{o['name']}.png"))
def stage_review(wait_min=25):
    """Wait for the reviewer (cull.json + review_done flag) for up to wait_min, then apply rerolls/locks."""
    flag=os.path.join(HERE,'review_done'); t0=time.time()
    if wait_min: L('review_wait',minutes=wait_min)
    while not os.path.exists(flag) and time.time()-t0<wait_min*60 and not stopped(): time.sleep(20)
    c=cull()
    if wait_min: L('review',cull=c)
    for name,ov in c.get('reroll',{}).items():   # name -> {"seed":..,"prompt_add":..}
        o=next((x for x in P['objects']+P['textures'] if x['name']==name),None)
        if not o: continue
        tex=o in P['textures']
        dst=os.path.join(D['objects'],name+'.png'); marker=dst+f".reroll{ov['seed']}"
        if os.path.exists(marker): continue
        pr=o['prompt']+(' '+ov.get('prompt_add','') if ov.get('prompt_add') else '')
        pre=f"xeno_ov/obj/{name}_s{ov['seed']}"; r=run(zgraph(pr,ov['seed'],pre),'obj_'+name)
        f=latest(os.path.join(OUT,'xeno_ov','obj',f"{name}_s{ov['seed']}_*.png"))
        if f:
            gt=still_gate(f); L('obj_reroll',name=name,seed=ov['seed'],gate=gt,sec=r.get('compute'))
            shutil.copy(f,os.path.join(D['objects'],f"{name}_s{ov['seed']}.png")); shutil.copy(f,dst); crop_to(f,os.path.join(INP,f'ov_{name}.png' if tex else inp_obj(name)))
            json.dump(dict(seed=ov['seed'],reroll=True),open(dst+'.json','w')); open(marker,'w').close()
# ---------------- stage: klein (material variants, material locks, mid guides) ----------------
KEDIT=("Edit the first image: keep the object's exact shape, outline, size, pose and position, the same black void, the same soft teal glow halo behind it "
       "and the same rim light from the upper left. Change only its material: it is now made entirely of {M}. No text, no lettering, no extra objects.")
KLOCK=("Edit the first image: keep the object's exact shape, size, pose and position. Re-render its material and lighting to match the second image exactly: "
       "glossy black iridescent ferrofluid with purple, teal and gold thin-film sheen, same teal halo, same black void, same rim light. No text.")
MIDSRC={'gr':{'pour':'g2_pour.png','splash':'g2_splash.png','spike':'g2_spike2.png','ripple':'g2_ripple.png'}}
def mid_img(kind,mat): return MIDSRC['gr'][kind] if mat=='gr' else f'ov_mid_{kind}_{mat}.png'
def kjob(src_inp,text,refs,name,seed=77):
    dst=os.path.join(D['klein'],name)
    if os.path.exists(dst): return True
    pre=f"xeno_ov/klein/{name[:-4]}"; r=run(kgraph(text,refs,seed,pre),'klein_'+name)
    f=latest(os.path.join(OUT,'xeno_ov','klein',name[:-4]+'_*.png'))
    L('klein',name=name,ok=bool(f),sec=r.get('compute'),err=r.get('error'))
    if not f: return False
    shutil.copy(f,dst); crop_to(f,os.path.join(INP,name)); return True
def klein_for(items):
    drop=set(cull().get('drop',[])); seen=set()
    for cl in items:
        m=cl['material']
        if m=='gr': continue
        R=P['recipes'][cl['recipe']]
        objs=[cl['A'],cl['B']]+([cl['C']] if cl.get('C') else [])
        if any(o in drop for o in objs): continue
        for kind,_,_ in R['mid']:
            if stopped() or not disk_ok(): return
            if (kind,m) in seen: continue
            seen.add((kind,m)); kjob(None,KEDIT.format(M=MATS[m]),[MIDSRC['gr'][kind]],f'ov_mid_{kind}_{m}.png')
        for o in objs:
            if stopped() or not disk_ok(): return
            if (o,m) in seen or not os.path.exists(os.path.join(INP,inp_obj(o))): continue
            seen.add((o,m)); kjob(None,KEDIT.format(M=MATS[m]),[inp_obj(o)],inp_obj(o,m))
def stage_klein():
    c=cull()
    for name in c.get('lock',[]):      # material lock to gr_k0
        if stopped(): return
        if kjob(None,KLOCK,[inp_obj(name),'gr_k0.png'],f'ov_{name}_grlock.png'):
            shutil.copy(os.path.join(INP,f'ov_{name}_grlock.png'),os.path.join(INP,inp_obj(name)))
    klein_for(queue_items()[:12])
def queue_items():
    by={c['id']:c for c in P['clips']+P.get('heroes',[])}
    return [by[i] for i in P.get('queue',[c['id'] for c in P['clips']]) if i in by]
# ---------------- stage: morphs (LTX-2.3) ----------------
def clip_guides(cl):
    R=P['recipes'][cl['recipe']]; m=cl['material']
    g=[(inp_obj(cl['A'],m),0,1.0)]
    g+=[(mid_img(k,m),i,s) for k,i,s in R['mid']]
    if cl.get('guide'): g+=[tuple(x) for x in P['guide_videos'][cl['guide']]]
    if cl.get('C'):
        g+=[(inp_obj(cl['B'],m),i,s) for i,s in R['midB']]+[(inp_obj(cl['C'],m),i,s) for i,s in R['end']]
    else: g+=[(inp_obj(cl['B'],m),i,s) for i,s in R['end']]
    return sorted(g,key=lambda x:x[1])
def stage_morphs():
    drop=set(cull().get('drop',[]))
    Q=queue_items()
    for qi,cl in enumerate(Q):
        if stopped() or past_deadline() or not disk_ok(): L('morphs_stop',stopped=stopped(),deadline=past_deadline()); return
        if qi%12==0:
            stage_review(0); do_retakes(Q); klein_for(Q[qi:qi+12])
        dst=os.path.join(D['clips'],cl['id']+'.mp4')
        if os.path.exists(dst) or os.path.exists(dst+'.failed'): continue
        if cl['A'] in drop or cl['B'] in drop or cl.get('C') in drop: L('clip_skip',id=cl['id'],why='dropped object'); continue
        render_clip(cl,dst,(cl['seed'],cl['seed']+500))
def do_retakes(Q):
    rt=cull().get('retake',{}); by={c['id']:c for c in P['clips']+P.get('heroes',[])}
    for cid,seed in rt.items():
        if stopped() or past_deadline() or not disk_ok(): return
        cl=by.get(cid); 
        if not cl: continue
        dst=os.path.join(D['clips'],cid+'.mp4'); mk=dst+f'.retake{seed}'
        if os.path.exists(mk): continue
        if os.path.exists(dst): os.replace(dst,dst[:-4]+f'_rej{seed}.mp4')
        if os.path.exists(dst+'.json'): os.replace(dst+'.json',dst[:-4]+f'_rej{seed}.mp4.json')
        if os.path.exists(dst+'.failed'): os.remove(dst+'.failed')
        klein_for([cl]); L('retake',id=cid,seed=seed)
        render_clip(cl,dst,(seed,seed+500)); open(mk,'w').close()
def render_clip(cl,dst,seeds):
    R=P['recipes'][cl['recipe']]; g=clip_guides(cl)
    miss=[x[0] for x in g if '@' not in x[0] and not os.path.exists(os.path.join(INP,x[0]))]+[x[0].split('@')[0] for x in g if '@' in x[0] and not os.path.exists(os.path.join(INP,x[0].split('@')[0]))]
    if miss: L('clip_skip',id=cl['id'],why='missing inputs',miss=miss); open(dst+'.failed','w').write('missing '+','.join(miss)); return
    M=MATS[cl['material']]
    if cl.get('C'): prompt=P['hero_tpl'].format(A=NAMES.get(cl['A'],cl['A']),B=NAMES.get(cl['B'],cl['B']),C=NAMES.get(cl['C'],cl['C']),M=M,verb=R['verb'],verb2=R['verb2'])
    else: prompt=P['prompt_tpl'].format(A=NAMES.get(cl['A'],cl['A']),B=NAMES.get(cl['B'],cl['B']),M=M,verb=R['verb'])
    res=list(cl.get('res') or [768,448])
    best=None
    for k,seed in enumerate(seeds):
        if past_deadline(): break
        pre=f"xeno_ov/clips/{cl['id']}_s{seed}"
        r=run(ltx23(prompt,g,seed,R['L'],pre,W=res[0],H=res[1]),cl['id'])
        f=latest(os.path.join(OUT,'xeno_ov','clips',f"{cl['id']}_s{seed}_*.mp4"))
        if not f:
            L('clip_fail',id=cl['id'],seed=seed,err=r.get('error'),status=r.get('status'),res=res)
            if res!=[768,448]: res=[768,448]; L('res_fallback',id=cl['id'])
            continue
        gt=clip_gate(f); dd=gt.pop('d',None)
        take=os.path.join(D['clips'],f"{cl['id']}_s{seed}.mp4"); shutil.copy(f,take)
        meta=dict(cl,seed_used=seed,prompt=prompt,guides=g,L=R['L'],res=res,fps=24,model='ltx-2.3-22b-distilled-fp8 2-stage + x2 latent upscaler',compute_s=r.get('compute'),wall_s=r.get('seconds'),gate=gt,diffs=dd)
        json.dump(meta,open(take+'.json','w'),indent=1)
        L('clip',id=cl['id'],seed=seed,sec=r.get('compute'),gate=gt)
        if best is None or (gt['ok'] and not best[1]): best=(take,gt['ok'])
        if gt['ok']: break
    if best:
        shutil.copy(best[0],dst); shutil.copy(best[0]+'.json',dst+'.json')
    else: open(dst+'.failed','w').write('no output')
# ---------------- stage: textures (LTX-2.3 i2v, first-frame guide only) ----------------
TEXMOTION={'tex_flow':'The viscous surface flows slowly across the frame in rivers and folds.','tex_ferro_spikes':'The spikes rise, sharpen, sway and pulse as if pulled by a slowly moving magnet.',
 'tex_chrome_ripples':'Concentric ripples keep spreading outward across the pool.','tex_mercury_beads':'The beads roll, collide and merge into larger beads.',
 'tex_oil_swirl':'The marbled film swirls and slowly turns.','tex_pour':'The stream keeps pouring, folding and splashing into the pool.',
 'tex_iridescent_waves':'Slow waves roll through the surface, the colours sliding across the crests.','tex_glass_melt':'The strands stretch, drip and fall in slow motion.'}
def stage_textures():
    for t in P['textures']:
        if stopped() or past_deadline() or not disk_ok(): return
        dst=os.path.join(D['textures'],t['name']+'.mp4')
        if os.path.exists(dst) or os.path.exists(dst+'.failed'): continue
        img=f"ov_{t['name']}.png"
        if not os.path.exists(os.path.join(INP,img)): continue
        prompt=P['tex_prompt'].format(P=t['prompt'].split(', ultra')[0]+'. '+TEXMOTION.get(t['name'],''))
        best=None
        for seed in (9100+t['seed'],9600+t['seed']):
            pre=f"xeno_ov/tex/{t['name']}_s{seed}"; r=run(ltx23(prompt,[(img,0,1.0)],seed,121,pre),t['name'])
            f=latest(os.path.join(OUT,'xeno_ov','tex',f"{t['name']}_s{seed}_*.mp4"))
            if not f: L('tex_fail',name=t['name'],err=r.get('error')); continue
            gt=clip_gate(f); gt.pop('d',None); take=os.path.join(D['textures'],f"{t['name']}_s{seed}.mp4"); shutil.copy(f,take)
            json.dump(dict(t,seed_used=seed,prompt=prompt,L=121,res=[768,448],gate=gt,compute_s=r.get('compute')),open(take+'.json','w'),indent=1)
            L('tex',name=t['name'],seed=seed,sec=r.get('compute'),gate=gt)
            if best is None or (gt['ok'] and not best[1]): best=(take,gt['ok'])
            if gt['ok']: break
        if best: shutil.copy(best[0],dst); shutil.copy(best[0]+'.json',dst+'.json')
        else: open(dst+'.failed','w').write('no output')
ST={'objects':stage_objects,'review':stage_review,'klein':stage_klein,'morphs':stage_morphs,'textures':stage_textures}
if __name__=='__main__':
    stages=sys.argv[1:] or ['objects','review','klein','morphs','textures','morphs']
    L('start',stages=stages,C=round(free_gb('C'),1),G=round(free_gb('G'),1))
    for s in stages:
        if stopped(): break
        L('stage',name=s); ST[s]()
    L('done',C=round(free_gb('C'),1),G=round(free_gb('G'),1)); open(os.path.join(HERE,'ALL_DONE'),'w').write(now())
