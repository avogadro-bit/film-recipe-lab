"""Compare identical controls on real RAF/Leica DNG, including matched colours.

No render tuning: reports scene-wide and equal-colour-cell weighted responses.
"""
import json
from pathlib import Path
import numpy as np
from fuji_recipe_lab import studio

OUT=Path('outputs/format-response')
W=np.array([.2126,.7152,.0722],np.float32)
CHANGES={'H-2':{'highlights':-2},'H+4':{'highlights':4},
 'S-2':{'shadows':-2},'S+4':{'shadows':4},'DR400':{'dynamic_range':400},
 'WB R4 B4':{'wb_red':4,'wb_blue':4},'Chrome strong':{'color_chrome':'strong'},
 'Blue strong':{'fx_blue':'strong'},'Color +4':{'color':4}}


def main(films=False):
    from fuji_recipe_lab.official_luts import FILMS
    from PIL import Image,ImageDraw
    changes={f:{'film':f} for f in FILMS if f!='provia'} if films else CHANGES
    recipe=studio.StudioRecipe(film='provia') if films else studio.StudioRecipe()
    OUT.mkdir(parents=True,exist_ok=True)
    leica=json.loads(Path('outputs/leica-input/validation.json').read_text())['images']
    raf=json.loads(Path('outputs/paired-fuji-validation/baseline.json').read_text())
    raf=[r for r in raf if r['id'] in ['d33607bd1ac0','60bb9a2bd04a','ba350d1b6da1','4d1adba56fde','c924f2d07be5']]
    sources=[('DNG',Path(r['file'])) for r in leica]+[('RAF',Path(r['raf'])) for r in raf]
    result=[];accum={kind:{k:[] for k in changes} for kind in ['DNG','RAF']}
    shown=['provia','classic_negative','velvia','classic_chrome','eterna']
    board=Image.new('RGB',(5*400,len(sources)*292),'#202020') if films else None
    for kind,path in sources:
        cache=OUT/(path.stem+'-linear.npy')
        if cache.exists():a=np.load(cache)
        else:
            a=studio.resize_float(studio.decode(path),400);np.save(cache,a)
        base=studio.render(a,recipe)
        if films:
            for col,film in enumerate(shown):
                im=Image.fromarray(np.uint8(studio.render(a,recipe.model_copy(update={'film':film}))*255));im.thumbnail((400,264))
                top=len(result)*292
                board.paste(im,(col*400,top+26))
                ImageDraw.Draw(board).text((col*400+5,top+5),kind+' '+path.name+' '+film,fill='white')
        # RGB cube cells condition simultaneously on brightness and colour.
        cells=np.minimum((base*12).astype(int),11)
        labels=(cells[...,0]*144+cells[...,1]*12+cells[...,2]).ravel()
        row={'file':str(path),'format':kind,'linear_y_quantiles':np.quantile(np.sum(a*W,-1),[.1,.5,.9,.99]).tolist(),'effects':{}}
        for name,change in changes.items():
            image=studio.render(a,recipe.model_copy(update=change))
            delta=abs(image-base).mean(-1).ravel()*255
            row['effects'][name]={'mean_rgb_delta_8bit':float(delta.mean()),'p90_rgb_delta_8bit':float(np.quantile(delta,.9))}
            accum[kind][name].append((labels,delta))
        result.append(row);print(kind,path.name,flush=True)
    matched={}
    for name in changes:
        stats={}
        for kind in accum:
            labels=np.concatenate([p[0] for p in accum[kind][name]])
            delta=np.concatenate([p[1] for p in accum[kind][name]])
            counts=np.bincount(labels,minlength=1728)
            avg=np.bincount(labels,weights=delta,minlength=1728)/np.maximum(counts,1)
            stats[kind]=(counts,avg)
        valid=(stats['DNG'][0]>=100)&(stats['RAF'][0]>=100)
        matched[name]={'shared_cells':int(valid.sum()),**{kind:float(stats[kind][1][valid].mean()) for kind in stats}}
    summary={kind:{name:float(np.median([r['effects'][name]['mean_rgb_delta_8bit'] for r in result if r['format']==kind])) for name in changes} for kind in accum}
    report={'recipe':recipe.model_dump(),'scene_median_effect_8bit':summary,'matched_rgb_cells_effect_8bit':matched,'images':result,
       'limits':['Different scenes, no causal sensor comparison', 'Coarse display RGB bins, not matched RAW pixels',
                 'All comparisons start at DR100 and the same default recipe; saved GUI drafts may differ']}
    (OUT/('films-report.json' if films else 'report.json')).write_text(json.dumps(report,indent=2))
    if films:board.save(OUT/'films-comparison.jpg',quality=93)
    print(json.dumps({'scene':summary,'matched':matched},indent=2))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--films',action='store_true')
    main(parser.parse_args().films)
