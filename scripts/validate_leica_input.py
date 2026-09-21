"""Exercise the integrated Leica decoder on local real DNGs, read-only."""
import json
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from kora import studio
from kora.official_luts import FILMS

OUT=Path('outputs/leica-input')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('photos',type=Path,nargs='+')
    files=parser.parse_args().photos
    OUT.mkdir(parents=True,exist_ok=True)
    recipes=[('Classic Negative',studio.StudioRecipe()),
        ('H -2',studio.StudioRecipe(highlights=-2)),
        ('DR400',studio.StudioRecipe(dynamic_range=400)),
        ('WB R+4 B+4',studio.StudioRecipe(wb_red=4,wb_blue=4))]
    board=Image.new('RGB',(4*400,len(files)*296),'#202020');draw=ImageDraw.Draw(board)
    results=[]
    for i,path in enumerate(files):
        linear=studio.resize_float(studio.decode(path),600)
        info=studio.source_details(path)
        base=studio.render(linear,recipes[0][1])
        row={'file':str(path),'exposure':info,'linear_min':float(linear.min()),'linear_max':float(linear.max()),'effects':{}}
        for j,(name,r) in enumerate(recipes):
            a=studio.render(linear,r)
            assert np.isfinite(a).all()
            row['effects'][name]={'rgb_mae_from_default':float(abs(a-base).mean())}
            im=Image.fromarray(np.uint8(a*255));im.thumbnail((400,266))
            board.paste(im,(j*400,i*296+25));draw.text((j*400+5,i*296+7),path.name+' '+name,fill='white')
        row['films_finite']={f:bool(np.isfinite(studio.render(linear,studio.StudioRecipe(film=f))).all()) for f in FILMS}
        assert all(row['films_finite'].values())
        results.append(row)
        print(path.name,round(info['ev'],3),'linear',row['linear_min'],row['linear_max'],flush=True)
        if i==0:np.save(OUT/'preview-linear.npy',linear)
    board.save(OUT/'controls.jpg',quality=92)
    # Full export and preview must use exactly the same source gain. Demosaic
    # resolution differs, so compare smoothed/downsampled values, not identity.
    full=studio.resize_float(studio.decode(files[0],preview=False),600)
    preview=np.load(OUT/'preview-linear.npy')
    report={'images':results,'preview_full_linear_mae':float(abs(full-preview).mean()),
            'preview_full_shape_equal':full.shape==preview.shape,'full_finite':bool(np.isfinite(full).all())}
    (OUT/'validation.json').write_text(json.dumps(report,indent=2))
    print('Preview/full MAE',report['preview_full_linear_mae'],flush=True)


if __name__=='__main__':main()
