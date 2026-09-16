"""Bounded research: shared chroma correction; no production modification.

Fit only training-day RAF/JPEG pairs. Existing test days are evaluation only.
Because pairs contain recipes, improvements would not isolate film simulation.
"""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.color import rgb2lab,lab2rgb
from scripts.paired_fuji_validation import metrics
OUT=Path('outputs/classic-negative-transfer')
BASE=Path('outputs/classic-negative-adapter/raf-gamma22')

def features(lab):
    # Chroma-linear mapping, identity on every neutral regardless of lightness.
    a=lab[...,1]/100;b=lab[...,2]/100
    tone=(lab[...,0]-50)/50
    return np.stack([a,b,a*tone,b*tone],-1)

def apply(rgb,coef):
    lab=rgb2lab(np.clip(rgb,0,1));lab[...,1:]+=np.einsum('...i,ij->...j',features(lab),coef)*100
    return np.clip(lab2rgb(lab),0,1).astype(np.float32)

def main():
    rows=[r for r in json.loads((BASE/'report.json').read_text())['images'] if r['recipe']['film']=='classic_negative' and not r['excluded']]
    xs=[];ys=[];cache={}
    for r in rows:
        z=np.load(BASE/(r['id']+'.npz'));a=z['candidate'];target=z['target'];cache[r['id']]=(a,target)
        if r['split']!='train':continue
        lab=rgb2lab(gaussian_filter(a,(.7,.7,0)));ref=rgb2lab(gaussian_filter(target,(.7,.7,0)))
        mask=(ref[...,0]>10)&(ref[...,0]<95)&(a.min(-1)>.005)&(a.max(-1)<.995)
        f=features(lab)[mask];res=(ref-lab)[mask,1:]/100
        rng=np.random.default_rng(391);idx=rng.choice(len(f),min(len(f),5000),replace=False)
        xs.append(f[idx]);ys.append(res[idx])
    x=np.concatenate(xs);y=np.concatenate(ys)
    # Ridge shrinkage to identity; fixed before inspecting evaluation images.
    coef=np.linalg.solve(np.einsum('ni,nj->ij',x,x,dtype=np.float64)+np.eye(4)*len(x)*.005,np.einsum('ni,nj->ij',x,y,dtype=np.float64))
    rowsout=[]
    for r in rows:
        a,t=cache[r['id']];b=apply(a,coef)
        rowsout.append({'id':r['id'],'split':r['split'],'baseline':metrics(a,t),'candidate':metrics(b,t)})
    summary={s:{k:float(np.median([r[k]['de00_median'] for r in rowsout if r['split']==s])) for k in ('baseline','candidate')} for s in ('train','test')}
    public=[]
    for name in ('impress','fuji-whitepaper'):
        z=np.load(OUT/(name+'.npz'));a=z['prediction'];t=z['target']
        public.append({'name':name,'baseline':metrics(a,t),'candidate':metrics(apply(a,coef),t)})
    # A consistency gate, not a claim that passing would prove Fuji accuracy.
    improved=sum(r['candidate']['de00_median']<r['baseline']['de00_median'] for r in rowsout if r['split']=='test')
    public_ok=all(r['candidate']['de00_median']<=r['baseline']['de00_median']+.15 for r in public)
    accepted=improved==5 and summary['test']['candidate']<summary['test']['baseline']*.95 and public_ok
    result={'coefficients':coef.tolist(),'summary':summary,'test_images_improved':improved,'public_checks':public,'passes_gate':accepted,'production_changed':False,'images':rowsout,
      'limits':['Training recipes contain DR/tone/Chrome; residual is not pure film response','Existing test images are not new blind data','No same-scene Leica/Fuji raw pair used']}
    (OUT/'chroma-fit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['summary','test_images_improved','public_checks','passes_gate']},indent=2))

if __name__=='__main__':main()
