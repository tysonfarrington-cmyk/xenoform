import numpy as np, colorsys
from PIL import Image, ImageFilter
# vibe: (glow hue deg, backdrop top rgb, backdrop bottom rgb, backdrop strength, object warmth tint rgb mult, sat boost)
VIBES = {
 "liquid-gold": dict(hue=38,  top=(70,40,8),   bot=(150,92,24),  k=0.85, tint=(1.18,1.0,0.70), sat=1.0),
 "bloom":       dict(hue=335, top=(70,110,50), bot=(150,185,90), k=0.90, tint=(1.05,1.0,0.95), sat=1.15),
 "neon-night":  dict(hue=338, top=(45,4,30),   bot=(175,22,95),  k=0.95, tint=(1.12,0.95,1.08), sat=1.2, lift=1.6),
 "ocean":       dict(hue=185, top=(4,40,60),   bot=(20,110,120), k=0.85, tint=(0.9,1.02,1.08), sat=1.1),
 "cosmic":      dict(hue=228, top=(2,8,40),    bot=(30,45,135),  k=0.80, tint=(0.95,0.95,1.12), sat=1.2),
}
def grade(src, vibe, size=(1024,576)):
    v = VIBES[vibe]
    im = Image.open(src).convert("RGB").resize(size, Image.LANCZOS)
    hsv = np.asarray(im.convert("HSV")).astype(np.float32)
    h, s, val = hsv[...,0]*360/255, hsv[...,1], hsv[...,2]
    teal = (np.abs(((h-180)+180)%360-180) < 35) & (s > 40)
    nh = np.where(teal, v["hue"], h)
    hsv[...,0] = nh*255/360
    hsv[...,1] = np.clip(s*v["sat"],0,255)
    rgb = np.asarray(Image.fromarray(hsv.astype(np.uint8),"HSV").convert("RGB")).astype(np.float32)
    rgb *= np.array(v["tint"])[None,None,:]
    H,W = size[1],size[0]
    yy,xx = np.mgrid[0:H,0:W]
    t = (yy/H)[...,None]
    back = np.array(v["top"])*(1-t)+np.array(v["bot"])*t
    r = np.sqrt(((xx-W/2)/(W*0.6))**2+((yy-H*0.55)/(H*0.7))**2)[...,None]
    back = back*np.clip(1.25-r,0.25,1.0)
    lum = (rgb.mean(-1,keepdims=True)/255)
    w = v["k"]*np.clip(1-lum*3.0,0,1)       # only where the still is dark
    out = rgb + back*w                       # additive lift of the background
    out = 255*(1-(1-np.clip(out,0,255)/255)**v.get("lift",1.15))  # gentle overall brighten
    return Image.fromarray(np.clip(out,0,255).astype(np.uint8))
