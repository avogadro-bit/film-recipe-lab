"""Research-only: constrain scene-linear tone response using public examples.

Fit a log-exposure curve to the published display response along each film's
neutral axis. Then evaluate the local RAF/JPEG pairs without fitting to them.
No production imports this module; monkeypatching is scoped to this process.
"""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from kora import studio
from kora.official_luts import apply_official
from kora.recipe_effects import dynamic_range_compress
from scripts.fit_online_tones import curve
from scripts.paired_fuji_validation import ROOT, OUT as BASE, metrics

OUT=Path('outputs/raw-tone-candidate')
W=np.array([.2126,.7152,.0722],np.float32)
ORIGINAL=studio.linear_tone_curve
P=np.array(json.loads(Path('outputs/online-reference-audit/tone-fit.json').read_text())['parameters_hneg_hpos_sneg_spos'])


def change(y,h,s,pivot,k):
    d=np.log2(np.maximum(y,1e-12)/pivot)
    coefficient=np.where(d<0,k[2 if s<0 else 3],k[0 if h<0 else 1])
    setting=np.where(d<0,s,h)
    shift=(np.exp2(coefficient*setting)-1)*d*np.abs(d)/(1+np.abs(d))
    return y*np.exp2(np.clip(shift,-60,60))


@lru_cache(maxsize=30)
def model(film,dr):
    x=np.exp2(np.linspace(-20,12,4096)).astype(np.float32)
    rgb=np.broadcast_to(x[:,None,None],(len(x),1,3)).copy()
    response=np.sum(apply_official(dynamic_range_compress(rgb,dr),film)[:,0]*W,-1)
    # Exclude the clipped-white tail from the inverse/fit. Some official LUTs
    # turn slightly below white at extreme input (around 13x linear white).
    # Do not silently monotonicize the original LUT or fit that saturated tail.
    end=np.flatnonzero(response>=.98)
    if len(end):
        x=x[:end[0]+1]; response=response[:end[0]+1]
    if np.min(np.diff(response)) < -1e-4:
        raise ValueError('Non-monotonic neutral axis: '+film)
    pivot=float(np.interp(.5,response,x))
    valid=(response>.04)&(response<.96)
    a=x[valid][::8]; b=response[valid][::8]
    def residual(k):
        errors=[]
        for h,s in [(-2,0),(4,0),(0,-2),(0,4)]:
            adjusted=change(a,h,s,pivot,k)
            predicted=np.interp(np.log2(adjusted),np.log2(x),response)
            errors.extend(predicted-curve(b,h,s,P))
        return np.array(errors)
    fit=least_squares(residual,[.2]*4,bounds=(.001,1),diff_step=.01)
    return pivot,fit.x,float(np.sqrt(np.mean(residual(fit.x)**2)))


def render(a,r):
    if r.dr_priority!='off':
        raise ValueError('Priority requires separate validation')
    pivot,k,_=model(r.film,r.dynamic_range)
    def replacement(rgb,h,s):
        y=np.sum(rgb*W,-1)
        target=change(y,h,s,pivot,k)
        return rgb*(target/np.maximum(y,1e-12))[...,None]
    studio.linear_tone_curve=replacement
    try:
        return studio.render(a,r)
    finally:
        studio.linear_tone_curve=ORIGINAL


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=json.loads((BASE/'baseline.json').read_text())
    results=[]
    for row in rows:
        z=np.load(ROOT/'cache'/(row['id']+'.npz'))
        r=studio.StudioRecipe(**row['recipe'])
        # Freeze the exact same per-source exposure in baseline and candidate.
        a=z['linear']*2**row['exposure']['reference_ev']
        original=studio.render(a,r); candidate=render(a,r)
        excluded=not row['alignment']['sane'] or (row['alignment']['correlation'] or 0)<.6
        result={k:row[k] for k in ('id','raf','split','recipe')}
        result.update(baseline=metrics(original,z['target']),candidate=metrics(candidate,z['target']),excluded=excluded)
        results.append(result)
        np.savez_compressed(OUT/(row['id']+'.npz'),baseline=original,candidate=candidate,target=z['target'])
        print(row['id'],r.film,row['split'],round(result['baseline']['de00_median'],2),round(result['candidate']['de00_median'],2),flush=True)
    summary={}
    for film in sorted({r['recipe']['film'] for r in results}):
        group=[r for r in results if r['split']=='test' and not r['excluded'] and r['recipe']['film']==film]
        summary[film]={'count':len(group),**{version:{key:float(np.median([r[version][key] for r in group])) for key in ('de00_median','de00_p90','luma_rmse')} for version in ('baseline','candidate')}}
    fitted={f'{film}/DR{dr}':{'pivot_linear':model(film,dr)[0],'strengths':model(film,dr)[1].tolist(),'neutral_fit_rmse':model(film,dr)[2]} for film,dr in sorted({(r['recipe']['film'],r['recipe']['dynamic_range']) for r in results})}
    report={'production_changed':False,'same_source_exposure':True,'fit_uses_local_pairs':False,
        'limitations':['Neutral-axis constraint inferred from published display examples, not native RAW curve',
            'Local evaluation days have been inspected in earlier experiments; not a new blind test',
            'Per-source exposure still uses embedded JPEG reference', 'No DNG validation'],
        'models':fitted,'summary':summary,'images':results}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
