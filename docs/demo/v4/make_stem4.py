import json,subprocess,sys,numpy as np
sys.path.insert(0,'/workspace/xenoform/v4/rc2/src')
from xenoform import stem_react as SR
from xenoform.scene_edit import _font
from PIL import Image,ImageDraw
T0,DUR,FPS,W,H=float(sys.argv[1]),float(sys.argv[2]),24,1080,1920
env=json.load(open('/workspace/xenoform/demo_v2/stems/env.json'))
src=sys.argv[3]; out=sys.argv[4]
n=int(DUR*FPS)
p=subprocess.Popen(["ffmpeg","-v","error","-stream_loop","-1","-i",src,"-vf",f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=rgb24","-frames:v",str(n),"-f","rawvideo","-"],stdout=subprocess.PIPE)
enc=subprocess.Popen(["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-c:v","libx264","-crf","16","-pix_fmt","yuv420p",out],stdin=subprocess.PIPE)
f=_font(34)
try: f.set_variation_by_axes([14,650])
except: pass
def val(k,t): a=env[k]; i=min(len(a)-1,int(t*env['fps'])); return float(a[i])
sm={}
for k in range(n):
    fr=np.frombuffer(p.stdout.read(W*H*3),np.uint8).reshape(H,W,3)
    t=T0+k/FPS
    fr=SR.apply_frame(fr,env,t,depth=0.05)
    im=Image.fromarray(fr); d=ImageDraw.Draw(im,"RGBA")
    # clean bottom HUD: soft gradient, thin bars, small caps
    g=Image.new("RGBA",(W,420),(0,0,0,0)); gd=ImageDraw.Draw(g)
    for yy in range(420): gd.line([(0,yy),(W,yy)],fill=(0,0,0,int(200*(1-yy/420))))
    im.paste(g,(0,0),g); d=ImageDraw.Draw(im,"RGBA")
    for j,(key,name,col) in enumerate([("drums","DRUMS",(255,120,90)),("bass","BASS",(110,200,255)),("other","MELODY",(200,150,255))]):
        v=val(key,t); sm[key]=max(v,sm.get(key,0)*0.80)
        y=150+j*64
        d.text((90,y-12),name,font=f,fill=(255,255,255,225))
        d.rounded_rectangle([330,y,990,y+12],6,fill=(255,255,255,38))
        d.rounded_rectangle([330,y,330+max(12,int(660*min(1,sm[key]))),y+12],6,fill=col+(240,))
    enc.stdin.write(np.asarray(im).tobytes())
enc.stdin.close();enc.wait();print("ok",out)
