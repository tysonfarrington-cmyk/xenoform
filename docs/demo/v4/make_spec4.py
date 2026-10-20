import json,os
E=json.load(open('/workspace/xenoform/demo_v2/excerpt.json')); beats=E['beats']
nb=lambda t:min(beats,key=lambda b:abs(b-t))
V='/workspace/xenoform/v4/'; R='/workspace/xenoform/demo_v31/'; F=R+'forms/'; S='/workspace/xenoform/footage/seeds916/'
BOR='/workspace/xenoform/judge_test/autotune_night/best_of_reel.mp4'
c=lambda p,t=0,**k: dict(src=p,**{'in':t},fit='crop',**k)
seed=lambda n,t=0,**k: c(S+n+'.mp4',t,**k)
ui=lambda p,t=0,sp=1.0: dict(src=p,**{'in':t},speed=sp,fx=0)
vj=lambda n,t=0: dict(src=V+n,**{'in':t},fit='crop',fx=0)
plan=[]
def add(t,s,tr='cut'): plan.append((t,s,tr))
# 1 hook: six different shots, clean beat cuts
hook=[c(V+'reshoot_origami.mp4',3.6),c(F+'ferro.mp4',1.2),vj('vj04_916.mp4',2.0),c(V+'reshoot_mcp_koi.mp4',3.8),c(F+'clock.mp4',1.2),seed('nasa_sdo_x16_flare',0.6)]
for j,s in enumerate(hook): add(([0.0]+beats[:5])[j],s)
# 2 Polly in space
add(beats[5],c(V+'p_soyuz_lively.mp4',0.0),'match-cut')
add(nb(6.2),c(R+'p2_earth.mp4',0.0))
add(nb(8.4),seed('nasa_iss_earth_night_lightning',0.4))
add(nb(10.6),c(R+'p3_leaf.mp4',0.0))
add(nb(12.8),seed('nasa_sdo_arching_eruption',0.4))
# 3 pick a vibe -> result fast
add(nb(15.48),ui(V+'ui_vibes.mp4',0.0,1.0),'lens-breath')
add(nb(18.1),c(F+'ferro.mp4',0.4))
add(nb(20.0),c(V+'reshoot_origami.mp4',0.0),'match-cut')
# 4 forms world: true morph plays out
add(nb(25.2),c(F+'clock.mp4',0.34,speed=0.7),'depth-parallax')
add(nb(28.4),c(R+'p4_rose.mp4',0.0,speed=0.75))
# 5 MCP -> hi-res render
add(nb(30.6),ui(R+'mcp.mp4',0.6,1.15))
add(nb(35.8),c(V+'reshoot_mcp_koi.mp4',0.0,speed=0.93),'flow-carry')
# 6 stem-reactive
add(nb(40.9),dict(src=V+'stem4.mp4',fx=0),'chrome-refract')
add(nb(45.4),c(R+'p5_ferro.mp4',0.0,speed=0.62))
# 7 VJ mode, demo-within-demo
add(nb(47.6),vj('vj01_t.mp4',0.4),'depth-parallax')
add(nb(53.4),vj('vj04_916.mp4',6.0))
add(nb(57.3),vj('vj03_916.mp4',1.0))
add(nb(61.2),vj('vj02.mp4',2.0))
add(nb(65.1),c(BOR,19.2,pre='crop=iw:ih-40:0:40',speed=0.85),'echo-trail')
add(nb(69.0),seed('nasa_iss_soyuz_timelapse',1.0))
add(nb(71.6),c(BOR,26.0,pre='crop=iw:ih-40:0:40',speed=0.85))
# 8 drop: clean beat cuts, mostly unseen windows
i0=beats.index(nb(76.3))
mont=[vj('vj01_t.mp4',7.5),c(R+'p5_ferro.mp4',0.5),vj('vj03_916.mp4',8.0),seed('nasa_sdo_x16_flare',2.5),vj('vj02.mp4',9.0),c(R+'p2_earth.mp4',0.8),vj('vj04_916.mp4',10.5),c(V+'stem_base.mp4',2.0)]
for j,s in enumerate(mont): add(beats[i0+2*j],s)
add(beats[i0+16],c(V+'reshoot_origami.mp4',1.2,speed=0.8),'lens-breath')
add(nb(92.3),c(V+'p_soyuz_lively.mp4',0.0,speed=0.68),'flow-carry')
add(nb(96.0),dict(src=R+'endcard_v31.mp4'),'cut')
END=nb(96.0)+3.6
segs=[];trs=[]
for k,(t,s,tr) in enumerate(plan):
    t1=plan[k+1][0] if k+1<len(plan) else END
    s=dict(s); s['dur']=round(t1-t,4); segs.append(s)
    if k: trs.append(dict(kind=tr,win=0 if tr=='cut' else 0.5,intensity=0.5))
labels=[
 dict(t0=3.9,t1=8.2,title='Xenoform',note='Polly morphs through worlds · open weights, your GPU'),
 dict(t0=8.6,t1=15.0,title='Real footage in',note='NASA public-domain library · motion-checked clips'),
 dict(t0=15.8,t1=19.9,title='Pick a vibe',note='tap a vibe, get the film'),
 dict(t0=20.3,t1=25.0,title='True morph · LTX-2.5',note='open weights · crane folds into a dragon'),
 dict(t0=31.0,t1=35.6,title='Connect any AI · MCP',note='the AI starts the render on your desk'),
 dict(t0=36.2,t1=40.6,title='…and here it is',note='the MCP recipe, re-rendered at full quality'),
 dict(t0=41.3,t1=45.2,title='Stem-reactive',note='drums, bass and melody drive the picture'),
 dict(t0=48.0,t1=56.8,title='VJ mode',note='live on the beat · recorded straight from the app'),
]
spec=dict(audio='/workspace/xenoform/demo_v2/track_excerpt.wav',audio_in=0.0,analysis='/workspace/xenoform/demo_v2/excerpt.json',
 out=V+'demo_v4_916.mp4',pulse=True,pulse_depth=0.008,pulse_moments=[[76.0,82.0]],
 label_scale=1.3,label_bottom=150,grade=dict(lift=0.01,gamma=1.0,sat=1.04,grain=0.008),segments=segs,transitions=trs,labels=labels,crf=19)
json.dump(spec,open(V+'demo_v4_spec.json','w'),indent=1)
t=0
for s,tr in zip(segs,['-']+[x['kind'] for x in trs]): print(round(t,2),s['dur'],tr,s['src'].split('/')[-1]); t+=s['dur']
from collections import Counter; print(Counter(x['kind'] for x in trs))
print('missing',{s['src'] for s in segs if not os.path.exists(s['src'])})
print('stem T0',nb(40.9),'dur',round(nb(45.4)-nb(40.9),3))
