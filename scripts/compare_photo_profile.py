"""Research-only photographic Classic Negative profile comparison.

Aaron Buchler / abpy, CC BY-NC-SA 4.0. No production integration.
The third-party LUT expects sRGB-encoded, linear-contrast input, not F-Log2.
"""
from pathlib import Path
from functools import lru_cache
import hashlib,json
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import brentq
from PIL import Image,ImageDraw
from kora import studio
from kora.recipe_effects import preserve_film_hue
from scripts.paired_fuji_validation import metrics

ROOT=Path('research/photo-profile-candidate')
OUT=Path('outputs/photo-profile-candidate')
ORIGINAL=studio.apply_official
W=np.array([.2126,.7152,.0722],np.float32)


@lru_cache
def table():
    path=ROOT/'classic-negative.cube'
    lines=path.read_text().splitlines()
    size=int(next(s.split()[1] for s in lines if s.startswith('LUT_3D_SIZE')))
    values=np.loadtxt([s for s in lines if s.strip() and s[0] not in '#LTD'])
    assert values.shape==(size**3,3) and np.isfinite(values).all()
    return values.reshape(size,size,size,3).astype(np.float32)


def photo(a,ev):
    cube=table();n=cube.shape[0]
    coords=np.moveaxis(np.clip(studio.srgb_encode(a*2**ev),0,1)*(n-1),-1,0)[::-1]
    return np.stack([map_coordinates(cube[...,c],coords,order=1,mode='nearest',prefilter=False) for c in range(3)],-1)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    gray=np.full((1,1,3),.18,np.float32)
    target=float(np.sum(ORIGINAL(gray,'classic_negative')*W))
    offset=brentq(lambda ev:float(np.sum(photo(gray,ev)*W))-target,-4,4)
    def candidate(a,film):
        official=ORIGINAL(a,film)
        if film!='classic_negative':return official
        # Borrow photographic chroma only. Keep the full floating RAW tonal
        # branch, including highlight recovery. Not a native Fuji operation.
        return preserve_film_hue(photo(a,offset),official)
    def render(a,r):
        studio.apply_official=candidate
        try:return studio.render(a,r)
        finally:studio.apply_official=ORIGINAL
    files=['20260621_0001','L1006259','L1004777','L1003163']
    board=Image.new('RGB',(1200,len(files)*292),'#202020');draw=ImageDraw.Draw(board)
    for i,name in enumerate(files):
        a=np.load(Path('outputs/format-response')/(name+'-linear.npy'))
        images=[studio.render(a,studio.StudioRecipe()),photo(a,offset),render(a,studio.StudioRecipe())]
        for j,(label,image) in enumerate(zip(['Actuel','Profil photo direct','Chroma photo / tons actuels'],images)):
            assert np.isfinite(image).all()
            im=Image.fromarray(np.uint8(np.clip(image,0,1)*255));im.thumbnail((400,264))
            board.paste(im,(j*400,i*292+26));draw.text((j*400+5,i*292+5),name+' '+label,fill='white')
            im.save(OUT/(name+'-'+str(j)+'.jpg'),quality=95)
    board.save(OUT/'leica-comparison.jpg',quality=94)
    rows=json.loads(Path('outputs/paired-fuji-validation/baseline.json').read_text())
    gains={r['id']:r['match']['reference_ev'] for r in json.loads(Path('outputs/recipe-exposure-candidate/report.json').read_text())['images']}
    results=[]
    for row in rows:
        if row['recipe']['film']!='classic_negative':continue
        z=np.load(Path('research/paired-validation/cache')/(row['id']+'.npz'))
        a=z['linear']*2**gains[row['id']];r=studio.StudioRecipe(**row['recipe'])
        original=studio.render(a,r);image=render(a,r)
        results.append({'id':row['id'],'split':row['split'],
            'excluded':not row['alignment']['sane'] or (row['alignment']['correlation'] or 0)<.6,
            'baseline':metrics(original,z['target']),'candidate':metrics(image,z['target'])})
    group=[r for r in results if r['split']=='test' and not r['excluded']]
    summary={v:{k:float(np.median([r[v][k] for r in group])) for k in ('de00_median','de00_p90','luma_rmse')} for v in ('baseline','candidate')}
    report={'source':'https://github.com/abpy/FujifilmCameraProfiles','author':'Aaron Buchler (abpy)',
        'license':'CC BY-NC-SA 4.0','lut_sha256':hashlib.sha256((ROOT/'classic-negative.cube').read_bytes()).hexdigest(),
        'neutral_axis_offset_ev':offset,'fit_to_user_images':False,'production_changed':False,
        'test_images':len(group),'summary':summary,'images':results,
        'limits':['Not the full Adobe camera profile pipeline', 'Direct LUT clips its input above one: not suitable for full RAW latitude',
                  'Hybrid retains official tonal branch but uses an experimental chroma combination',
                  'No paired Leica/Fuji same-scene ground truth', 'Existing evaluation set, not a new blind test']}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'offset_ev':offset,'summary':summary},indent=2))


if __name__=='__main__':main()
