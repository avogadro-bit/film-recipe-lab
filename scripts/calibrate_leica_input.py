"""Local Leica input exposure study, not a Fuji colour calibration.

Standard Leica previews only constrain a fixed camera exposure offset.
Whole folders are withheld. No preview pixels or colours enter the renderer.
"""
import json
from pathlib import Path
import numpy as np
from kora.studio import _decode_sensor, resize_float, render, StudioRecipe
from kora.source_exposure import source_exposure, estimate_reference_ev

ROOT=Path('research/leica-input')
OUT=Path('outputs/leica-input')


def main():
    meta=json.loads((ROOT/'sample-metadata.json').read_text())
    eligible=[r for r in meta if r.get('Model')=='LEICA Q3 43' and r.get('FilmMode')=='Standard']
    folders=sorted({str(Path(r['SourceFile']).parent) for r in eligible})
    # Whole folders, assigned before inspecting decoded pixels or fit values.
    selected=[]
    for i,folder in enumerate(folders):
        group=[r for r in eligible if str(Path(r['SourceFile']).parent)==folder][:2]
        selected.extend([{**r,'split':'test' if i%3==0 else 'train'} for r in group])
    (ROOT/'selection.json').write_text(json.dumps(selected,indent=2))
    results=[]
    for row in selected:
        p=Path(row['SourceFile']);cache=ROOT/(p.stem+'.npz')
        if cache.exists():
            z=np.load(cache);a=z['linear'];ref=z['reference']
        else:
            a,ref=_decode_sensor(p,True)
            if ref is None:continue
            a=resize_float(a,600)*source_exposure(row,'.dng')['gain']
            np.savez_compressed(cache,linear=a,reference=ref)
        fit=estimate_reference_ev(resize_float(a,256),ref,lambda x:render(x,StudioRecipe(film='provia')))
        results.append({**row,**fit})
        print(p.name,row['split'],round(fit['reference_ev'],3),flush=True)
    valid=[r for r in results if r['reference_matched'] and not r.get('reference_limit_reached')]
    offset=float(np.median([r['reference_ev'] for r in valid if r['split']=='train']))
    summary={}
    for split in ('train','test'):
        values=np.array([r['reference_ev'] for r in valid if r['split']==split])
        summary[split]={'count':len(values),'median_ev':float(np.median(values)),
                        'median_abs_offset_difference_ev':float(np.median(abs(values-offset))),
                        'p90_abs_offset_difference_ev':float(np.percentile(abs(values-offset),90))}
    report={'model':'LEICA Q3 43','offset_ev':offset,'summary':summary,'images':results,
        'method':'Median exposure alignment to Standard Leica preview luma on training folders; fixed across files and films',
        'limits':['Empirical default brightness, not a calibrated physical exposure or Fuji colour match',
                  'No Leica stylized or monochrome previews used for fit',
                  'Other Leica models require separate measurements']}
    (OUT/'calibration.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ('offset_ev','summary')},indent=2))


if __name__=='__main__':main()
