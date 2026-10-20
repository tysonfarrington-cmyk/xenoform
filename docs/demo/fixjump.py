import sys,subprocess,numpy as np
sys.path.insert(0,'/workspace/xenoform/rc3/repo/src')
from xenoform import transitions_fx as T
src,out,cut,n=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]); W,H=1080,1920
raw=subprocess.run(["ffmpeg","-v","error","-i",src,"-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True).stdout
F=list(np.frombuffer(raw,np.uint8).reshape(-1,H,W,3))
A=F[cut-n:cut]; B=F[cut:cut+n]
M=T.apply(sys.argv[5] if len(sys.argv)>5 else "flow-morph",A,B,0.5)
fr=F[:cut-n]+list(M)+F[cut+n:]
enc=subprocess.Popen(["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r","24","-i","-","-c:v","libx264","-crf","16","-pix_fmt","yuv420p",out],stdin=subprocess.PIPE)
for f in fr: enc.stdin.write(np.ascontiguousarray(f).tobytes())
enc.stdin.close();enc.wait();print(len(F),'->',len(fr))
