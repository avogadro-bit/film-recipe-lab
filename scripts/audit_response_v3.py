"""Reproduce constrained CC fit and compare revisions on public references."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.optimize import least_squares
from .fit_chrome_effects import read,align,model
from kora.recipe_effects import chrome_effect,dynamic_range_compress


def bounded_chrome(a,p):
    high=a.max(-1);low=a.min(-1);chroma=high-low
    sat=chroma/np.maximum(high,1e-6)
    y=np.sum(a*[.2126,.7152,.0722],-1)
    hue=np.clip((np.maximum(a[...,0],a[...,1])-a[...,2])/np.maximum(chroma,1e-6),0,1)
    mask=sat**p[2]*hue;target=y*(1-p[0]*mask)
    gain=1-p[0]*mask+p[1]*mask*(1-sat)
    gain=np.minimum(gain,target/np.maximum(y-low,1e-6))
    gain=np.minimum(gain,(1-target)/np.maximum(high-y,1e-6))
    return np.clip(target[...,None]+gain[...,None]*(a-y[...,None]),0,1)


def main():
    a,b,offset=align(read('cc-off'),read('cc-strong'))
    a=gaussian_filter(a,(1,1,0));b=gaussian_filter(b,(1,1,0))
    fit=least_squares(lambda p:(bounded_chrome(a[::9,::9],p)-b[::9,::9]).ravel(),
        [.17,.5,1.2],bounds=([0,0,.3],[.5,1,4]),loss='soft_l1',f_scale=.015)
    old=json.loads(Path('research/reference-effects/chrome-fit.json').read_text())['cc']['parameters']
    x,t,shift=align(read('X100V_ColorChromeAll_Off'),read('X100V_ColorChrome_Strong'))
    x=gaussian_filter(x,(2,2,0))[::5,::5];t=gaussian_filter(t,(2,2,0))[::5,::5]
    report={'revision':3,'cc_fit_parameters':fit.x.tolist(),'training_alignment':offset,'evaluation_alignment':shift,
        'limitations':['Only two scenes; compressed public JPEGs','WEAK interpolated, not measured','FX Blue unchanged','Bound on chroma parameter reached; not universal calibration'], 'metrics':{}}
    for name,x,t in [('fuji_heldout_pixels',a[4::9,4::9],b[4::9,4::9]),('independent_x100v',x,t)]:
        report['metrics'][name]={'v2_mae':float(abs(model(x,old,'cc')-t).mean()),'v3_mae':float(abs(chrome_effect(x,'strong')-t).mean())}
        np.testing.assert_allclose(bounded_chrome(x,fit.x),chrome_effect(x,'strong'),atol=1e-6)
    samples=np.array([[[.9,.15,.04],[.9,.02,0],[0,.9,0]]])
    report['saturated_swatches']={'input':samples.tolist(),'v2':model(samples,old,'cc').tolist(),'v3':chrome_effect(samples,'strong').tolist()}
    report['dr_white_mapping']={str(dr):dynamic_range_compress(np.full((1,1,3),dr/100),dr).tolist() for dr in (100,200,400)}
    out=Path('outputs/brightness-dr-audit');out.mkdir(exist_ok=True)
    (out/'response-v3.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report['metrics'],indent=2))

if __name__=='__main__':main()
