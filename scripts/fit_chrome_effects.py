"""Fit bounded color-response models to public Fuji OFF/STRONG example pairs.
Run locally; keeps calibration and second-scene evaluation separate.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel
from scipy.optimize import least_squares
ROOT=Path('research/reference-effects')

def read(name):return np.asarray(Image.open(ROOT/(name+'.jpg')).convert('RGB'),dtype=np.float64)/255

def align(a,b):
    h,w=np.minimum(a.shape[:2],b.shape[:2]);a=a[:h,:w];b=b[:h,:w]
    ag=sum(abs(sobel(a.mean(2),axis=d)) for d in (0,1));bg=sum(abs(sobel(b.mean(2),axis=d)) for d in (0,1))
    scores=[]
    for dy in range(-5,6):
      for dx in range(-5,6):
        scores.append((np.mean(abs(ag[8:-8:4,8:-8:4]-bg[8+dy:h-8+dy:4,8+dx:w-8+dx:4])),dy,dx))
    _,dy,dx=min(scores)
    a=a[8:-8,8:-8];b=b[8+dy:h-8+dy,8+dx:w-8+dx]
    return a,b,[dy,dx]

def model(a,p,kind):
    high=a.max(-1);low=a.min(-1);chroma=high-low;sat=chroma/np.maximum(high,1e-6)
    y=np.sum(a*np.array([.2126,.7152,.0722]),axis=-1)
    if kind=='cc':
        hue=np.clip((np.maximum(a[...,0],a[...,1])-a[...,2])/np.maximum(chroma,1e-6),0,1)
        mask=sat**p[2]*hue
        out=a-p[0]*(mask*y)[...,None]+p[1]*mask[...,None]*(a-y[...,None])
    else:
        hue=np.clip((a[...,2]-np.maximum(a[...,0],a[...,1]))/np.maximum(chroma,1e-6),0,1)
        mask=sat**p[1]*hue**p[2]
        out=a-p[0]*(mask*y)[...,None]
    return np.clip(out,0,1)

def old(a,kind):
    if kind=='cc':return a*(1-.2*(a.max(-1)-a.min(-1)))[...,None]
    return a*(1-.4*np.clip(a[...,2]-(a[...,0]+a[...,1])*.5,0,1))[...,None]

def main():
    report={}
    for kind in ['cc','blue']:
     a,b,offset=align(read(kind+'-off'),read(kind+'-strong'))
     # Exclude fine detail/JPEG artifacts; fit on one spatial lattice only.
     a=gaussian_filter(a,(1,1,0));b=gaussian_filter(b,(1,1,0))
     x=a[::9,::9];target=b[::9,::9]
     guess=[.3,.3,1] if kind=='cc' else [.5,1,1]
     bounds=([0,0,.3],[1,1,4]) if kind=='cc' else ([0,.3,.3],[1.5,4,4])
     fit=least_squares(lambda p:(model(x,p,kind)-target).ravel(),guess,bounds=bounds,loss='soft_l1',f_scale=.015)
     entry={'parameters':fit.x.tolist(),'alignment':offset,'fit_source':'FUJIFILM learning centre OFF/STRONG','metrics':{}}
     for label,x,t in [('training_scene_heldout_pixels',a[4::9,4::9],b[4::9,4::9])]:
        entry['metrics'][label]={'old_mae':float(abs(old(x,kind)-t).mean()),'new_mae':float(abs(model(x,fit.x,kind)-t).mean())}
     suffix='ColorChrome_Strong' if kind=='cc' else 'ColorChromeBlue_Strong'
     x,t,shift=align(read('X100V_ColorChromeAll_Off'),read('X100V_'+suffix))
     x=gaussian_filter(x,(2,2,0))[::5,::5];t=gaussian_filter(t,(2,2,0))[::5,::5]
     entry['metrics']['independent_x100v_scene']={'alignment':shift,'old_mae':float(abs(old(x,kind)-t).mean()),'new_mae':float(abs(model(x,fit.x,kind)-t).mean())}
     report[kind]=entry
    print(json.dumps(report,indent=2));(ROOT/'chrome-fit.json').write_text(json.dumps(report,indent=2))

if __name__=="__main__":main()
