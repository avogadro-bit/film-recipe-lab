"""Unmodified Fujifilm video LUTs with an explicit photographic input adapter.

F-Log2 formula and F-Gamut primaries: Fujifilm data sheet v1.1.
Output viewing: Rec.709 / D65 / gamma 2.2, per GFX ETERNA 55 White Paper
v1.01 page 13, converted to sRGB for browser/ICC exports. Not a photo ISP.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import os
import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).with_name('luts')
MANIFEST = json.loads((ROOT/'manifest.json').read_text())
FILMS = tuple(MANIFEST['files'])
LUT_DISPLAY_GAMMA = 2.2


def user_lut_directory():
    return Path(os.environ.get('FUJI_RECIPE_LUT_DIR', Path.home()/'.local/share/fuji-recipe-lab/luts')).expanduser()


def lut_path(film):
    name=MANIFEST['files'][film]['file']
    user_path=user_lut_directory()/name
    # An explicit override is isolated (useful for portable installations/tests).
    if 'FUJI_RECIPE_LUT_DIR' in os.environ or user_path.is_file():
        return user_path
    return ROOT/name  # Existing development installations remain compatible.


def missing_luts():
    return [film for film in FILMS if not lut_path(film).is_file()]
# Linear sRGB / BT.709 D65 to F-Gamut (BT.2020 primaries), row vectors.
TO_F_GAMUT = np.array([[.627403896,.069097289,.016391439],
                      [.329283038,.919540395,.088013308],
                      [.043313066,.011362316,.895595253]],np.float32)


def flog2_encode(reflection):
    x=np.maximum(reflection,0)
    return np.where(x < .000889,8.799461*x+.092864,
                    .245281*np.log10(5.555556*x+.064829)+.384316)


@lru_cache(maxsize=10)
def load_lut(film):
    info=MANIFEST['files'][film]
    path=lut_path(film)
    if not path.is_file():
        raise ValueError('Fuji LUT missing. Download the GFX ETERNA 55 v1.10 ZIP from Fuji, then run: python -m fuji_recipe_lab.lut_install path/archive.zip')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=info['sha256']:
        raise ValueError(f'Official LUT has been modified: {film}')
    lines=raw.decode().splitlines()
    if 'LUT_3D_SIZE 65' not in lines:
        raise ValueError('Grille LUT inattendue')
    values=np.loadtxt([s for s in lines if s.strip() and not s.startswith(('#','LUT_'))],dtype=np.float32)
    if values.shape!=(65**3,3) or not np.isfinite(values).all():
        raise ValueError('Invalid official LUT')
    # .cube enumerates red fastest, then green, then blue.
    table=values.reshape(65,65,65,3)
    table.setflags(write=False)
    return table


def interpolate(table,rgb):
    coords=np.moveaxis(np.clip(rgb,0,1)*64,-1,0)[::-1]
    return np.stack([map_coordinates(table[...,c],coords,order=1,
                     mode='nearest',prefilter=False) for c in range(3)],axis=-1)


def apply_official(linear_srgb,film):
    table=load_lut(film)
    result=np.empty_like(linear_srgb,dtype=np.float32)
    # Bound temporary memory on full-resolution RAW exports.
    for start in range(0,len(result),128):
        linear=np.einsum('...i,ij->...j',linear_srgb[start:start+128],TO_F_GAMUT)
        video=interpolate(table,flog2_encode(linear))
        display=np.maximum(video,0)**LUT_DISPLAY_GAMMA
        result[start:start+128]=np.where(display<=.0031308,display*12.92,
                                         1.055*display**(1/2.4)-.055)
    return np.clip(result,0,1)
