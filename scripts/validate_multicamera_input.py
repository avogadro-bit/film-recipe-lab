"""Real-file smoke tests for the shared input contract; not colour calibration."""
import json
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageCms,ImageDraw
from kora import studio
from kora.raw import require_local
OUT=Path('outputs/multicamera-input')

def main():
    OUT.mkdir(exist_ok=True)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('photos',type=Path,nargs='+')
    paths=parser.parse_args().photos
    rows=[];board=Image.new('RGB',(800,len(paths)*290),'#202020');draw=ImageDraw.Draw(board)
    for i,p in enumerate(paths):
        require_local(p);a=studio.decode(p);info=studio.source_details(p)
        small=studio.resize_float(a,600)
        effects=[]
        for film in studio.OFFICIAL_FILMS:
            b=studio.render(small,studio.StudioRecipe(film=film));assert np.isfinite(b).all()
            effects.append(float(b.mean()))
        base=studio.render(a,studio.StudioRecipe(),neutral=True);film=studio.render(a,studio.StudioRecipe())
        icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        for col,(label,img) in enumerate([('sans film',base),('Classic Negative',film)]):
            im=Image.fromarray(np.uint8(np.clip(img,0,1)*255));im.save(OUT/(p.stem+('-classic-negative.jpg' if col else '-base.jpg')),quality=96,icc_profile=icc)
            im.thumbnail((400,262));board.paste(im,(col*400,i*290+26));draw.text((col*400+5,i*290+5),p.name+' '+label,fill='white')
        row={'file':str(p),'normalization':info['normalization'],'exposure_ev':info['ev'],
            'preview_dimensions':[a.shape[1],a.shape[0]],'linear_range':[float(a.min()),float(a.max())],
            'ten_films_finite':True,'film_vs_base_mean_delta_8bit':float(abs(base-film).mean()*255)}
        reference=Path('outputs/classic-negative-adapter')/(p.stem+'-linear-v9.npy')
        if reference.exists():
            previous=np.load(reference);error=float(abs(previous-small).max());row['v9_input_max_error']=error
            assert error<1e-6,'Unexpected change to approved Leica input'
        rows.append(row);print(p.name,info['normalization']['model'],round(info['ev'],3),flush=True)
    board.save(OUT/'comparatif.jpg',quality=95)
    (OUT/'validation.json').write_text(json.dumps({'images':rows,'scope':'Decode and render compatibility, not cross-camera colour matching'},indent=2))

if __name__=='__main__':main()
