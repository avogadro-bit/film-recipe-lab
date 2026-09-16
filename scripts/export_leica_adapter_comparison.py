"""Controlled v8/v9 comparisons, original official cubes unchanged."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageCms,ImageDraw
from fuji_recipe_lab import studio,official_luts
from scripts.paired_fuji_validation import metrics
OUT=Path('outputs/classic-negative-adapter')
OLD_EV=1.0115000581063707
NEW_EV=.8421820334636739

def main():
    sources=json.loads(Path('outputs/leica-input/validation.json').read_text())['images']
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    board=Image.new('RGB',(1200,4*296),'#202020');draw=ImageDraw.Draw(board);rows=[]
    for index,r in enumerate(sources):
        p=Path(r['file']);a=studio.decode(p)
        np.save(OUT/(p.stem+'-linear-v9.npy'),studio.resize_float(a,600))
        official_luts.LUT_DISPLAY_GAMMA=2.4
        before=studio.render(a*2**(OLD_EV-NEW_EV),studio.StudioRecipe())
        official_luts.LUT_DISPLAY_GAMMA=2.2
        after=studio.render(a,studio.StudioRecipe())
        base=studio.render(a,studio.StudioRecipe(),neutral=True)
        for col,(name,pixels) in enumerate([('base-sans-film',base),('avant-v8',before),('classic-negative-v9',after)]):
            im=Image.fromarray(np.uint8(np.clip(pixels,0,1)*255))
            im.save(OUT/(p.stem+'-'+name+'.jpg'),quality=97,subsampling=0,icc_profile=profile)
            im.thumbnail((400,266));board.paste(im,(col*400,index*296+29))
            draw.text((col*400+5,index*296+5),p.stem+' '+name,fill='white')
        # Inspect tone/DR/WB pipeline stability on real signed RAW values.
        changes={}
        for name,options in {'H-2':{'highlights':-2},'S-2':{'shadows':-2},'DR400':{'dynamic_range':400},'WB4-4':{'wb_red':4,'wb_blue':4}}.items():
            v=studio.render(a,studio.StudioRecipe(**options))
            changes[name]={'finite':bool(np.isfinite(v).all()),'mean_change_8bit':float(abs(v-after).mean()*255)}
        rows.append({'file':str(p),'dimensions':[after.shape[1],after.shape[0]],'v8_v9_difference':metrics(after,before),'controls':changes})
        print(p.name,rows[-1]['v8_v9_difference']['de00_median'],flush=True)
    board.save(OUT/'comparatif-leica.jpg',quality=96,icc_profile=profile)
    (OUT/'leica-comparison.json').write_text(json.dumps({'images':rows,'limits':'Before/after difference, not Fuji matching accuracy. 1600px previews; original RAWs unchanged.'},indent=2))

if __name__=='__main__':main()
