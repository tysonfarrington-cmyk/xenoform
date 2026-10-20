import sys,subprocess,numpy as np,os
from rembg import remove,new_session
from PIL import Image,ImageFilter
s=new_session('u2net_human_seg')
src,out=sys.argv[1],sys.argv[2]; W,H=576,1024
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
