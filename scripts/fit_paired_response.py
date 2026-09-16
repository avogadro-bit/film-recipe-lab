"""Research-only fit: six shared parameters, train days only; no GUI mutation."""
import json
import argparse
from pathlib import Path
import numpy as np
import cv2
from scipy.optimize import least_squares
from scipy.ndimage import gaussian_filter
from fuji_recipe_lab import studio
from scripts.paired_fuji_validation import ROOT,OUT,metrics
ORIGINAL_CHROME=studio.chrome_effect


def candidate(linear,recipe,p):
    r=recipe.model_copy(update={'highlights':recipe.highlights*p[1],'shadows':recipe.shadows*p[2],
                                'color':recipe.color*p[3]})
    def chrome(a,setting,blue_only=False):
        out=ORIGINAL_CHROME(a,setting,blue_only)
        return np.clip(a+(out-a)*p[5 if blue_only else 4],0,1)
    studio.chrome_effect=chrome
    try:return studio.render(linear*2**p[0],r)
    finally:studio.chrome_effect=ORIGINAL_CHROME


def main(per_film=False):
    rows=json.loads((OUT/'baseline.json').read_text());training=[]
    for row in rows:
        if row['split']!='train':continue
        z=np.load(ROOT/'cache'/(row['id']+'.npz'))
        # Tone/color fit at low resolution; do not synthesize grain or sharpen
        # a tiny image and mistake its spatial response for a color error.
        linear=cv2.resize(z['linear'],(48,48),interpolation=cv2.INTER_AREA)
        target=cv2.resize(z['target'],(48,48),interpolation=cv2.INTER_AREA)
        recipe=studio.StudioRecipe(**row['recipe']).model_copy(update={'grain':'off','sharpness':0,'noise_reduction':-4,'clarity':0})
        y=np.sum(target*[.2126,.7152,.0722],-1);mask=(y>.03)&(y<.97)
        training.append((linear,target,recipe,mask))
    def residual(p,film=None):
        result=[]
        for a,b,r,mask in training:
            if film is not None and r.film!=film:continue
            diff=(candidate(a,r,p)-b)[mask]
            result.append(diff.ravel()/np.sqrt(max(len(diff),1)))
        return np.concatenate(result)
    fits={}
    for film in (['classic_negative','classic_chrome','acros'] if per_film else [None]):
        fit=least_squares(lambda p:residual(p,film),[1,.5,.5,.7,.5,.5],bounds=([-1,0,0,0,0,0],[3,2,2,2,1.5,1.5]),
                          loss='linear',max_nfev=80,diff_step=.015,ftol=1e-6)
        fits[film]=fit.x
        print('Parameters',film,fit.x,'training loss',float(np.mean(residual(fit.x,film)**2)),flush=True)
    result=[]
    for row in rows:
        z=np.load(ROOT/'cache'/(row['id']+'.npz'))
        params=fits[row['recipe']['film'] if per_film else None]
        out=candidate(z['linear'],studio.StudioRecipe(**row['recipe']),params)
        m=metrics(out,z['target']);row={**row,'candidate':m}
        if not row['alignment']['sane'] or row['alignment']['correlation'] is None or row['alignment']['correlation']<.6:
            row['excluded_from_color_summary']='Alignment unresolved; inspect crop separately'
        np.save(OUT/(row['id']+('-candidate-per-film.npy' if per_film else '-candidate.npy')),out)
        result.append(row)
    summary={}
    for film in ['classic_negative','classic_chrome','acros']:
        group=[r for r in result if r['split']=='test' and r['recipe']['film']==film and 'excluded_from_color_summary' not in r]
        summarize=lambda key:{k:float(np.median([r[key][k] for r in group])) for k in ['de00_median','de00_p90','luma_rmse']}
        summary[film]={'test_images':len(group),'current_gui_reference_guided':summarize('gui_reference_guided'),'candidate_no_reference':summarize('candidate')}
    report={'parameters':{str(k):dict(zip(['exposure_ev','highlight_scale','shadow_scale','color_scale','chrome_scale','fx_blue_scale'],v.tolist())) for k,v in fits.items()},
        'training_only':True,'per_image_reference_used_by_candidate':False,'summary':summary,'images':result,
        'limitations':['Six shared factors do not identify individual controls from one recipe per source',
                       'Only three represented films; Classic Chrome holdout has only one scene',
                       'One digital-teleconverter pair has unresolved alignment']}
    (OUT/('candidate-fit-per-film.json' if per_film else 'candidate-fit.json')).write_text(json.dumps(report,indent=2));print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--per-film',action='store_true');args=parser.parse_args();main(args.per_film)
