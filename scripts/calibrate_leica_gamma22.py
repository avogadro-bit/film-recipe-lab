"""Recalibrate fixed Q3 43 brightness using current float RAW decode and gamma22."""
import json
from pathlib import Path
import numpy as np
from kora.studio import _decode_sensor,resize_float,render,StudioRecipe
from kora.source_exposure import estimate_reference_ev

OUT=Path('outputs/classic-negative-adapter')
CACHE=Path('research/classic-negative-adapter/leica-float')

def main():
    CACHE.mkdir(exist_ok=True)
    selection=json.loads(Path('research/leica-input/selection.json').read_text());rows=[]
    for r in selection:
        p=Path(r['SourceFile']);cache=CACHE/(p.stem+'.npz')
        if cache.exists():
            z=np.load(cache);a=z['linear'];ref=z['reference']
        else:
            a,ref=_decode_sensor(p,True,True)
            a=resize_float(a,600)*2**float(r.get('BaselineExposure',0))
            np.savez_compressed(cache,linear=a,reference=ref)
        fit=estimate_reference_ev(resize_float(a,256),ref,lambda v:render(v,StudioRecipe(film='provia')))
        rows.append({'file':str(p),'split':r['split'],**fit})
        print(p.name,r['split'],round(fit['reference_ev'],4),flush=True)
    valid=[r for r in rows if r['reference_matched'] and not r['reference_limit_reached']]
    offset=float(np.median([r['reference_ev'] for r in valid if r['split']=='train']))
    summary={}
    for split in ('train','test'):
        ev=np.array([r['reference_ev'] for r in valid if r['split']==split])
        summary[split]={'count':len(ev),'median_ev':float(np.median(ev)),
            'median_absolute_residual_ev':float(np.median(abs(ev-offset))),
            'p90_absolute_residual_ev':float(np.percentile(abs(ev-offset),90))}
    report={'offset_ev':offset,'summary':summary,'images':rows,'gamma':2.2,
        'method':'Current signed float decode; fixed offset trained on 20 Standard Leica previews, 10 whole-folder holdouts; no Fuji colour calibration'}
    (OUT/'leica-gamma22-calibration.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'offset':offset,'summary':summary},indent=2))

if __name__=='__main__':main()
