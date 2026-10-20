# Polly (matte npz) over a background clip -> 1080x1920 24fps clip
import sys,subprocess,numpy as np,json
from PIL import Image
npz,bg,out=sys.argv[1],sys.argv[2],sys.argv[3]; f0=int(sys.argv[4]); f1=int(sys.argv[5]); bgin=float(sys.argv[6]) if len(sys.argv)>6 else 0
scale=float(sys.argv[7]) if len(sys.argv)>7 else 1.0; tint=float(sys.argv[8]) if len(sys.argv)>8 else 0.25
d=np.load(npz); rgb=d['rgb'][f0:f1]; al=d['alpha'][f0:f1]; n=len(rgb); W,H=1080,1920
raw=subprocess.run(["ffmpeg","-v","error","-ss",str(bgin),"-stream_loop","-1","-i",bg,"-vf",f"fps=24,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}","-frames:v",str(n),"-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True).stdout
B=np.frombuffer(raw,np.uint8).reshape(-1,H,W,3)
enc=subprocess.Popen(["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r","24","-i","-","-c:v","libx264","-crf","16","-pix_fmt","yuv420p",out],stdin=subprocess.PIPE)
pw=int(1080*scale); ph=int(pw*1024/576)
for i in range(n):
    b=B[min(i,len(B)-1)].astype(np.float32)
    p=np.asarray(Image.fromarray(rgb[i]).resize((pw,ph),Image.LANCZOS)).astype(np.float32)
    a=np.asarray(Image.fromarray(al[i]).resize((pw,ph),Image.LANCZOS)).astype(np.float32)[...,None]/255
    a=np.clip((a-0.4)/0.4,0,1)
    m=b.reshape(-1,3).mean(0); col=m/ max(m.mean(),1)*p.mean()
    p=p*(1-tint)+ (p*m/ max(m.mean(),1))*tint
    x0=(W-pw)//2; y0=H-ph
    ys,ye=max(0,y0),H; py=ys-y0
    reg=b[ys:ye,x0:x0+pw]
    b[ys:ye,x0:x0+pw]=reg*(1-a[py:])+p[py:]*a[py:]
    enc.stdin.write(np.clip(b,0,255).astype(np.uint8).tobytes())
enc.stdin.close();enc.wait();print("ok",out,n)
