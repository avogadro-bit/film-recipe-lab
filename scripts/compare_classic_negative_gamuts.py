"""Compare official FLog2 and FLog2C paths; no fitted colour coefficients."""
import json
from pathlib import Path
import numpy as np
from fuji_recipe_lab import studio
from fuji_recipe_lab.official_luts import apply_official,interpolate,flog2_encode
from scripts.paired_fuji_validation import metrics
from scripts.audit_official_classic_negative import primaries_matrix
OUT=Path('outputs/classic-negative-adapter')
raw=Path('research/classic-negative-adapter/classic-negative-flog2c.cube').read_text()
TABLE=np.loadtxt([s for s in raw.splitlines() if s.strip() and not s.startswith(('#','LUT_'))],dtype=np.float32).reshape(65,65,65,3)
MATRIX=np.linalg.solve(primaries_matrix([(.7347,.2653),(.0263,.9737),(.1173,-.0224)]),primaries_matrix([(.64,.33),(.3,.6),(.15,.06)])).T.astype(np.float32)

def apply_c(a,film):
    if film!='classic_negative':return apply_official(a,film)
    v=interpolate(TABLE,flog2_encode(np.einsum('...i,ij->...j',a,MATRIX)))
    return np.clip(studio.srgb_encode(np.maximum(v,0)**2.2),0,1)

def main():
    rows=json.loads((OUT/'raf-gamma22/report.json').read_text())['images'];results=[]
    for r in rows:
        if r['recipe']['film']!='classic_negative' or r['excluded']:continue
        z=np.load('research/paired-validation/cache/'+r['id']+'.npz')
        a=z['linear']*2**r['match']['reference_ev'];recipe=studio.StudioRecipe(**r['recipe'])
        studio.apply_official=apply_c
        b=studio.render(a,recipe)
        studio.apply_official=apply_official
        results.append({'id':r['id'],'split':r['split'],'flog2':r['candidate'],'flog2c':metrics(b,z['target'])})
    summary={s:{k:float(np.median([r[k]['de00_median'] for r in results if r['split']==s])) for k in ('flog2','flog2c')} for s in ('train','test')}
    (OUT/'gamut-paths.json').write_text(json.dumps({'summary':summary,'images':results,'limits':'Same FLog2 exposure anchor, output gamma22; recipes include DR/tone/chrome approximations, not an isolated film simulation test.'},indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
