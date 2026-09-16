"""Full-resolution, separate JPEGs of the three research comparison variants."""
import gc
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED
import numpy as np
from PIL import Image, ImageCms
from fuji_recipe_lab import studio
from fuji_recipe_lab.recipe_effects import preserve_film_hue
from scripts.compare_photo_profile import photo

OUT=Path('outputs/photo-profile-candidate/HD')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report=json.loads(Path('outputs/photo-profile-candidate/report.json').read_text())
    offset=report['neutral_axis_offset_ev']
    source_rows=json.loads(Path('outputs/leica-input/validation.json').read_text())['images']
    labels=['1-actuel','2-profil-photo','3-couleurs-photo-tons-actuels']
    recipe=studio.StudioRecipe()
    assert recipe.wb=='camera' and recipe.grain=='off' and recipe.sharpness==0 and recipe.clarity==0 and recipe.noise_reduction==-4
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    results=[]
    for row in source_rows:
        source=Path(row['file'])
        print('Décodage pleine définition :',source.name,flush=True)
        linear=studio.decode(source,preview=False)
        h,w=linear.shape[:2]
        buffers=[np.empty((h,w,3),np.uint8) for _ in labels]
        # Default recipe has no spatial effects: strip rendering is identical
        # to a single full-image render while bounding temporary float memory.
        for start in range(0,h,64):
            a=linear[start:start+64]
            current=studio.render(a,recipe)
            direct=photo(a,offset)
            hybrid=preserve_film_hue(direct,current)
            for buf,image in zip(buffers,[current,direct,hybrid]):
                if not np.isfinite(image).all():raise ValueError('Nonfinite output')
                buf[start:start+64]=np.round(np.clip(image,0,1)*255).astype(np.uint8)
        del linear
        for label,buf in zip(labels,buffers):
            path=OUT/(source.stem+'-'+label+'.jpg')
            Image.fromarray(buf).save(path,'JPEG',quality=98,subsampling=0,icc_profile=icc,
                comment=('Classic Negative comparison; '+label+'; independent rendering, not native Fuji').encode())
            with Image.open(path) as im:
                im.load()
                assert im.size==(w,h) and im.info.get('icc_profile')
            results.append({'file':path.name,'source':str(source),'variant':label,'width':w,'height':h,
                'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            print('Export vérifié :',path.name,w,'x',h,flush=True)
        del buffers,buf
        gc.collect()
    manifest={'format':'JPEG quality 98, 4:4:4, embedded sRGB','full_resolution':True,
              'source_profile':report['source'],'lut_sha256':report['lut_sha256'],
              'neutral_axis_offset_ev':offset,'images':results}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (OUT/'LIRE-MOI.txt').write_text('Comparaison Classic Negative — pleine définition\n\n1-actuel : rendu actuel du GUI.\n2-profil-photo : profil photo abpy direct (expérimental).\n3-couleurs-photo-tons-actuels : couleurs photo et tonalités actuelles (expérimental).\n\nJPEG qualité 98, sans sous-échantillonnage couleur, profil sRGB incorporé.\nNouveaux développements des DNG originaux, pas agrandissements du comparatif.\nLes variantes 2 et 3 utilisent les couleurs du profil Aaron Buchler / abpy.\nhttps://github.com/abpy/FujifilmCameraProfiles\nAucune modification du moteur du GUI ni des fichiers originaux.\n')
    archive=OUT.parent/'comparatifs-leica-HD.zip'
    with ZipFile(archive,'w',compression=ZIP_STORED) as z:
        for path in sorted(OUT.iterdir()):
            if path.is_file():z.write(path,'comparatifs-leica-HD/'+path.name)
    print('Archive :',archive,archive.stat().st_size,'octets',flush=True)


if __name__=='__main__':main()
