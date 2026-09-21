"""Audit published Fuji Log/Classic Negative example, levels and gamut paths."""
from pathlib import Path
import json,hashlib
from zipfile import ZipFile
import numpy as np
from PIL import Image
from kora.official_luts import interpolate,apply_official,flog2_encode,TO_F_GAMUT
from kora.studio import srgb_encode
from scripts.paired_fuji_validation import metrics

ROOT=Path('research/classic-negative-adapter')
OUT=Path('outputs/classic-negative-adapter')


def primaries_matrix(points):
    rgb=np.array([[x/y,1,(1-x-y)/y] for x,y in points]).T
    x,y=.3127,.3290
    white=np.array([x/y,1,(1-x-y)/y])
    return rgb*np.linalg.solve(rgb,white)


def main():
    with ZipFile(ROOT/'luts-v110.zip') as z:
        name=next(n for n in z.namelist() if '/65Grid/F-Log2C/FLog2C_to_CLASSIC-Neg._' in n and not n.startswith('__MACOSX'))
        raw=z.read(name)
    (ROOT/'classic-negative-flog2c.cube').write_bytes(raw)
    lines=raw.decode().splitlines()
    values=np.loadtxt([s for s in lines if s.strip() and not s.startswith(('#','LUT_'))],dtype=np.float32).reshape(65,65,65,3)
    a=np.asarray(Image.open(ROOT/'figure-003.jpg').convert('RGB'),np.float32)/255
    target=np.asarray(Image.open(ROOT/'figure-011.jpg').convert('RGB'),np.float32)/255
    results=[]
    for level,x in [('unchanged',a),('full_to_video',(a*876+64)/1023),('video_to_full',(a*1023-64)/876)]:
        video=interpolate(values,x)
        for mode,b in [('published_codes',video),('gamma22_to_srgb',srgb_encode(np.maximum(video,0)**2.2)),('gamma24_to_srgb',srgb_encode(np.maximum(video,0)**2.4))]:
            results.append({'input_levels':level,'output':mode,**metrics(b,target)})
            Image.fromarray(np.uint8(np.clip(b,0,1)*255)).save(OUT/('official-'+level+'-'+mode+'.jpg'),quality=95)
    # F-Log2 C uses the same transfer curve, different primaries (whitepaper
    # pp.10-12). Compare equivalent colourimetric input through both LUTs.
    srgb=primaries_matrix([(.64,.33),(.30,.60),(.15,.06)])
    fg=primaries_matrix([(.708,.292),(.170,.797),(.131,.046)])
    fgc=primaries_matrix([(.7347,.2653),(.0263,.9737),(.1173,-.0224)])
    matrix=np.linalg.solve(fgc,srgb).T
    fg_error=float(np.max(abs(np.linalg.solve(fg,srgb).T-TO_F_GAMUT)))
    rng=np.random.default_rng(91);samples=rng.uniform(0,1,(10000,1,3)).astype(np.float32)
    c=srgb_encode(np.maximum(interpolate(values,flog2_encode(np.einsum('...i,ij->...j',samples,matrix))),0)**2.2)
    b=apply_official(samples,'classic_negative')
    report={'source':'https://dl.fujifilm-x.com/support/lut/GFX_ETERNA_WhitePaper_260206_v101.pdf',
        'pdf_sha256':hashlib.sha256((ROOT/'whitepaper.pdf').read_bytes()).hexdigest(),
        'lut_archive_member':name,'lut_sha256':hashlib.sha256(raw).hexdigest(),
        'published_pair_results':results,'fgamut_matrix_max_error':fg_error,
        'flog2_vs_flog2c_equivalent_inputs_rgb_mae':float(abs(c-b).mean()),
        'fgamutc_matrix_rows':matrix.tolist(),
        'limits':['PDF illustrations are JPEG recompressed 8-bit samples, not master Log footage',
                  'Published code comparison does not establish display EOTF; gamma22 comes from text on page13',
                  'Different official LUT paths; difference cause not established, not a sensor-matching calibration']}
    (OUT/'official-audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
