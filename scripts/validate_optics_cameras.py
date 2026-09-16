"""Exercise real local camera/lens inputs. Reports are private, not calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image,ImageDraw
from fuji_recipe_lab import studio
from fuji_recipe_lab.optics import inspect_optics,apply_corrections
from fuji_recipe_lab.raw import require_local


def checksum(path):
    require_local(path)
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('photos',type=Path,nargs='+')
    parser.add_argument('--output',type=Path,default=Path('outputs/camera-optics-validation'))
    parser.add_argument('--full-export',type=Path,action='append',default=[])
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=[];board=Image.new('RGB',(1000,len(args.photos)*365),'#202020');draw=ImageDraw.Draw(board)
    for i,p in enumerate(args.photos):
        before=checksum(p);started=time.monotonic();profile=inspect_optics(p)
        raw=studio.decode(p);corrected=apply_corrections(raw,profile,'auto','auto')
        assert np.isfinite(corrected).all() and raw.shape==corrected.shape
        raw_small=studio.resize_float(raw,600);small=studio.resize_float(corrected,600)
        for film in studio.OFFICIAL_FILMS:
            out=studio.render(small,studio.StudioRecipe(film=film))
            assert np.isfinite(out).all() and np.min(out)>=0 and np.max(out)<=1
        reference=studio.render(raw_small,studio.StudioRecipe())
        processed=studio.render(small,studio.StudioRecipe())
        for col,(label,a) in enumerate((('Sans correction',reference),('Correction disponible',processed))):
            image=Image.fromarray(np.uint8(np.clip(a,0,1)*255));image.thumbnail((496,310))
            board.paste(image,(col*500,i*365+50));draw.text((col*500+5,i*365+30),label,fill='white')
        metadata=profile.get('metadata',{})
        draw.text((5,i*365+5),f"{i+1}: {metadata.get('Model','?')} / {metadata.get('LensModel',metadata.get('LensID','objectif fixe'))}",fill='white')
        row={'file':str(p),'model':metadata.get('Model'),'lens':metadata.get('LensModel',metadata.get('LensID')),
             'optics':profile,'dimensions':[raw.shape[1],raw.shape[0]],'ten_films_finite':True,
             'optical_mae_display':float(abs(reference-processed).mean()),'source_sha256':before}
        if p in args.full_export:
            full=studio.decode(p,preview=False);full=apply_corrections(full,profile,'auto','auto')
            reduced=studio.resize_float(full,600)
            row['preview_vs_full_linear_mae']=float(abs(reduced-small).mean())
            rendered=studio.render(full,studio.StudioRecipe(lens_distortion='auto',lens_vignetting='auto'))
            payload,mime=studio.encode(rendered,studio.StudioRecipe())
            (args.output/f'{i+1}-full.jpg').write_bytes(payload)
            row['full_export_dimensions']=[rendered.shape[1],rendered.shape[0]]
            del full,rendered,payload
        assert checksum(p)==before,'Source file changed'
        row['source_unchanged']=True;row['seconds']=round(time.monotonic()-started,2);rows.append(row)
        print(i+1,metadata.get('Model'),profile['source'],round(row['optical_mae_display'],5),flush=True)
        (args.output/'report.json').write_text(json.dumps({'images':rows},indent=2))
    board.save(args.output/'comparison.jpg',quality=94)


if __name__=='__main__':main()
