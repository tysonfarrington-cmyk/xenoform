import json,os
E=json.load(open('/workspace/xenoform/demo_v2/excerpt.json')); beats=E['beats']
nb=lambda t:min(beats,key=lambda b:abs(b-t))
R='/workspace/xenoform/demo_v31/'; F=R+'forms/'; S='/workspace/xenoform/footage/seeds916/'; C='/workspace/xenoform/demo_v3/cap/'
BOR='/workspace/xenoform/judge_test/autotune_night/best_of_reel.mp4'
bor=lambda t,**k: dict(src=BOR,**{'in':t},pre='crop=iw:ih-40:0:40',fit='crop',**k)
seed=lambda n,t=0,**k: dict(src=S+n+'.mp4',**{'in':t},fit='crop',**k)
ui=lambda p,t=0,sp=1.0: dict(src=p,**{'in':t},speed=sp,fx=0)
clip=lambda p,t=0,**k: dict(src=R+p,**{'in':t},fit='crop',**k)
FX={'origami':'origami_fix','clock':'clock','ferro':'ferro'}
OFF={'clock':0.34}
form=lambda tag,t=0,**k: dict(src=F+FX[tag]+'.mp4',**{'in':t},fit='crop',**k)
plan=[]
def add(t,s,tr=('cut',0)): plan.append((t,s,tr))
# 1 hook: Polly + forms, beat cuts (no stutter)
hook=[form('origami',1.2),clip('p2_earth.mp4',0.3),form('ferro',1.2),seed('nasa_sdo_x16_flare',0.6),form('clock',1.2),clip('p4_rose.mp4',0.1)]
for j,s in enumerate(hook): add(0.0 if j==0 else beats[j-1+0]+0.0 if False else [0,beats[0],beats[1],beats[2],beats[3],beats[4]][j] if False else ([0.0]+beats[:5])[j],s)
# 2 title: Polly in space
add(beats[5],clip('p1_soyuz.mp4',0.2),('liquid-melt',0.5))
add(nb(7.74),clip('p2_earth.mp4',0.0),('luma-wipe',0.5))
add(nb(9.68),seed('nasa_sdo_x16_flare',0.3),('cut',0))
add(nb(11.61),seed('nasa_iss_earth_night_lightning',0.4),('cut',0))
add(nb(13.55),seed('nasa_sdo_arching_eruption',0.4),('luma-wipe',0.5))
# 3 app
add(nb(15.48),ui(C+'vibes.mp4',0.3,1.35),('liquid-melt',0.7))
add(nb(21.6),ui(C+'remix.mp4',0.0,1.4),('luma-wipe',0.6))
add(27.4,dict(src='/workspace/xenoform/demo_v3/build/black.mp4'),('cut',0))
# 4 forms world (gold): one form per bar-ish, scene morphs, no stutter
add(28.05,form('origami',0.0,speed=0.6),('cut',0))
add(nb(30.6),form('clock',0.34,speed=0.65),('liquid-melt',0.6))
add(nb(33.2),clip('p3_leaf.mp4',0.0),('liquid-melt',0.6))
# 5 MCP -> real render
add(nb(35.8),ui(R+'mcp.mp4',0.0,1.0),('luma-wipe',0.6))
add(nb(43.0),dict(src=R+'mcp_render_42ec7a71.mp4',**{'in':3.0},fit='crop'),('liquid-melt',0.6))
add(nb(48.6),dict(src='/workspace/xenoform/demo_v3/build/stem_viz.mp4',fx=0),('cut',0))
# 6 neon world
add(nb(51.8),form('ferro',0.0,speed=0.7),('chroma-split',0.4))
add(nb(54.9),clip('p5_ferro.mp4',0.0,speed=0.7),('liquid-melt',0.5))
add(nb(56.98),ui(C+'transitions.mp4',0.2,1.2),('luma-wipe',0.6))
add(nb(62.1),ui(C+'vj.mp4',1.5,1.0),('liquid-melt',0.6))
add(nb(66.6),clip('p4_rose.mp4',0.0,speed=0.67),('luma-wipe',0.5))
add(nb(67.9),bor(19.2,speed=0.85),('liquid-melt',0.6))
add(nb(70.5),form('clock',0.34,speed=0.65),('liquid-melt',0.6))
add(nb(73.1),form('ferro',0.0,speed=0.75),('liquid-melt',0.6))
# 7 drop: forms + Polly, beat cuts (clean cuts, no stutter)
i0=beats.index(nb(76.3))
mont=[form('ferro',1.5),clip('p2_earth.mp4',0.8),form('origami',1.5),seed('nasa_iss_soyuz_timelapse',2.0),clip('p3_leaf.mp4',1.0),form('clock',1.2),seed('nasa_sdo_x16_flare',1.5),clip('p5_ferro.mp4',0.3)]
for j,s in enumerate(mont): add(beats[i0+2*j] if 2*j< 20 else 0,s,('cut',0))
add(beats[i0+16],form('origami',0.0,speed=0.6),('liquid-melt',0.6))
add(nb(88.9),clip('p4_rose.mp4',0.0,speed=0.67),('luma-wipe',0.5))
add(nb(90.2),form('ferro',0.0,speed=0.95),('liquid-melt',0.5))
add(nb(92.3),clip('p1_soyuz.mp4',0.0),('liquid-melt',0.6))
add(nb(96.0),dict(src=R+'endcard_v31.mp4'),('liquid-melt',0.6))
END=nb(96.0)+3.6
segs=[];trs=[]
for k,(t,s,tr) in enumerate(plan):
    t1=plan[k+1][0] if k+1<len(plan) else END
    s=dict(s); s['dur']=round(t1-t,4); segs.append(s)
    if k: trs.append(dict(kind=tr[0],win=tr[1],intensity=0.5))
labels=[
 dict(t0=3.4,t1=7.4,title='Xenoform',note='Polly morphs through worlds · open weights, your GPU'),
 dict(t0=8.0,t1=15.2,title='Real footage in',note='NASA public-domain library · motion-checked clips'),
 dict(t0=16.0,t1=21.3,title='Pick a vibe',note='song, vibe, Make · the desk on a phone-width screen'),
 dict(t0=22.0,t1=27.1,title='Remix a recipe',note='paste an xf1. code, get the same film on your song'),
 dict(t0=28.4,t1=33.0,title='Scene morph · LTX-2.3',note='rendered locally, native 9:16, autotuned'),
 dict(t0=33.4,t1=35.6,title='Moves · Wan Animate 2',note='a real Pexels dance drives Polly'),
 dict(t0=36.2,t1=42.7,title='Connect any AI · MCP',note='the AI starts the render on your desk'),
 dict(t0=43.3,t1=48.3,title='…and here it is',note='MCP-started draft render, job 42ec7a71'),
 dict(t0=48.8,t1=51.6,title='Stem-reactive',note='Demucs stems drive the edit'),
 dict(t0=57.3,t1=61.9,title='Morph controls',note='keyframe blend · cross clip · video ramp · staged region'),
 dict(t0=62.4,t1=66.3,title='VJ mode',note='live mic in · loops + transitions on the beat'),
]
spec=dict(audio='/workspace/xenoform/demo_v2/track_excerpt.wav',audio_in=0.0,analysis='/workspace/xenoform/demo_v2/excerpt.json',
 out=R+'demo_v31_916.mp4',pulse=True,pulse_depth=0.01,pulse_moments=[[76.0,82.0]],
 label_scale=1.3,label_bottom=150,grade=dict(lift=0.01,gamma=1.0,sat=1.04,grain=0.012),segments=segs,transitions=trs,labels=labels,crf=20)
json.dump(spec,open(R+'demo_v31_spec.json','w'),indent=1)
t=0
for s in segs: print(round(t,2),s['dur'],s['src'].split('/')[-1]); t+=s['dur']
missing={s['src'] for s in segs if not os.path.exists(s['src'])}; print('missing',missing)
