"""Test exposure anchoring to the source RAF recipe and embedded preview.

The external paired JPEG is used only for evaluation, never for exposure fit.
Original files are read-only; dataless iCloud placeholders are refused.
"""
from io import BytesIO
import json
from pathlib import Path
import numpy as np
import rawpy
from PIL import Image
from kora import studio
from kora.raw import require_local
from kora.source_exposure import estimate_reference_ev
from scripts.paired_fuji_validation import ROOT, OUT as BASE, metrics

OUT=Path('outputs/recipe-exposure-candidate')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    selected={r['id']:r for r in json.loads((ROOT/'selection.json').read_text())['selected']}
    results=[]
    for row in json.loads((BASE/'baseline.json').read_text()):
        path=Path(row['raf']);require_local(path)
        with rawpy.imread(str(path)) as raw:
            thumb=raw.extract_thumb()
            im=Image.open(BytesIO(thumb.data)) if thumb.format==rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
            im=im.convert('RGB');im.thumbnail((256,256),Image.Resampling.LANCZOS)
            ref=np.asarray(im,dtype=np.float32)/255
        z=np.load(ROOT/'cache'/(row['id']+'.npz'))
        source=studio.StudioRecipe(**studio.shooting_settings(selected[row['id']]['source_meta']))
        match=estimate_reference_ev(studio.resize_float(z['linear'],256),ref,lambda a:studio.render(a,source))
        candidate=studio.render(z['linear']*2**match['reference_ev'],studio.StudioRecipe(**row['recipe']))
        result={k:row[k] for k in ('id','raf','split','recipe')}
        result.update(baseline=row['gui_reference_guided'],candidate=metrics(candidate,z['target']),
            source_recipe=source.model_dump(),original_ev=row['exposure']['reference_ev'],match=match,
            excluded=not row['alignment']['sane'] or (row['alignment']['correlation'] or 0)<.6)
        results.append(result)
        np.savez_compressed(OUT/(row['id']+'.npz'),baseline=z['gui'],candidate=candidate,target=z['target'])
        print(row['id'],round(result['original_ev'],2),round(match['reference_ev'],2),round(result['baseline']['de00_median'],2),round(result['candidate']['de00_median'],2),flush=True)
    summary={}
    for film in sorted({r['recipe']['film'] for r in results}):
        group=[r for r in results if r['split']=='test' and not r['excluded'] and r['recipe']['film']==film]
        summary[film]={'count':len(group),**{v:{k:float(np.median([r[v][k] for r in group])) for k in ('de00_median','de00_p90','luma_rmse')} for v in ('baseline','candidate')}}
    (OUT/'report.json').write_text(json.dumps({'production_changed':False,'external_jpeg_used_for_fit':False,'summary':summary,'images':results},indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
