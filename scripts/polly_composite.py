"""Polly through worlds: matte a Wan Animate 2 take (rembg u2net_human_seg, CPU) and composite it over any 9:16 clip.

  python scripts/polly_composite.py matte take.mp4 take.npz
  python scripts/polly_composite.py comp take.npz background.mp4 out.mp4 F0 F1 [bg_in] [scale] [tint]

Needs `pip install "rembg[cpu]"` for matte. Frames F0..F1 are picked after a hand/face QA pass.
"""
import sys, subprocess, json
import numpy as np
def matte_main(argv):
    from rembg import remove,new_session
    from PIL import Image,ImageFilter
    s=new_session('u2net_human_seg')
    src,out=argv[0],argv[1]; W,H=480,832
    raw=subprocess.run(["ffmpeg","-v","error","-i",src,"-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True).stdout
    n=len(raw)//(W*H*3); fr=np.frombuffer(raw,np.uint8)[:n*W*H*3].reshape(n,H,W,3)
    al=[]
    for f in fr:
        a=np.asarray(remove(Image.fromarray(f),session=s,only_mask=True)).astype(np.float32)/255
        al.append(a)
    al=np.stack(al)
    sm=al.copy()
    pass
    np.savez_compressed(out,rgb=fr,alpha=(sm*255).astype(np.uint8))
    print("ok",out,n)

def comp_main(argv):
    sys_argv=['x']+argv
    from PIL import Image
    npz,bg,out=sys_argv[1],sys_argv[2],sys_argv[3]; f0=int(sys_argv[4]); f1=int(sys_argv[5]); bgin=float(sys_argv[6]) if len(sys_argv)>6 else 0
    scale=float(sys_argv[7]) if len(sys_argv)>7 else 1.0; tint=float(sys_argv[8]) if len(sys_argv)>8 else 0.25
    d=np.load(npz); rgb=d['rgb'][f0:f1]; al=d['alpha'][f0:f1]; n=len(rgb); W,H=1080,1920
    raw=subprocess.run(["ffmpeg","-v","error","-ss",str(bgin),"-stream_loop","-1","-i",bg,"-vf",f"fps=24,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}","-frames:v",str(n),"-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True).stdout
    B=np.frombuffer(raw,np.uint8).reshape(-1,H,W,3)
    enc=subprocess.Popen(["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r","24","-i","-","-c:v","libx264","-crf","16","-pix_fmt","yuv420p",out],stdin=subprocess.PIPE)
    pw=int(1080*scale); ph=int(pw*832/480)
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

if __name__ == "__main__":
    {"matte": matte_main, "comp": comp_main}[sys.argv[1]](sys.argv[2:])
