"""Common RAW input contract and camera-scoped normalization profiles.

A recognized extension is only an import candidate; LibRaw must decode the
actual camera/compression. None of these profiles claims Fuji colour matching.
"""
from dataclasses import dataclass
import numpy as np

RAW_EXTENSIONS=frozenset({'.raf','.dng','.cr2','.cr3','.crw','.nef','.nrw',
    '.arw','.sr2','.srf','.rw2','.orf','.ori','.pef','.ptx','.srw',
    '.3fr','.fff','.iiq','.rwl','.mos','.mrw','.kdc','.dcr','.erf','.mef','.raw'})

@dataclass(frozen=True)
class CameraInputProfile:
    key: str
    exposure_offset_ev: float
    floating_camera_rgb: bool
    label: str

# Fixed brightness only, learned on 20 files and checked on 10 other files.
# Keep corrections tied to an exact model; never inherit by camera brand.
LEICA_Q343=CameraInputProfile('leica-q3-43-v2',.8421820334636739,True,
                            'Leica Q3 43 · adjusted exposure')

def camera_profile(metadata):
    make=str(metadata.get('Make','')).strip().upper()
    model=str(metadata.get('Model','')).strip().upper()
    if make.startswith('LEICA') and model=='LEICA Q3 43':return LEICA_Q343
    return None


def validate_linear_input(pixels):
    """Enforce the shared representation without clipping RAW headroom."""
    a=np.asarray(pixels,dtype=np.float32)
    if a.ndim!=3 or a.shape[-1]!=3 or min(a.shape[:2])==0 or not np.isfinite(a).all():
        raise ValueError('Invalid RAW input: finite three-channel linear RGB is required.')
    return a


def normalization_details(metadata,suffix,exposure):
    profile=camera_profile(metadata) if suffix.lower()=='.dng' else None
    is_fuji=suffix.lower()=='.raf'
    matched=exposure.get('reference_matched',False)
    return {'version':1,'working_space':'linear sRGB','white_point':'D65',
        'dtype':'float32','display_clipping':False,'white_balance':'camera at decode',
        'color_conversion':'LibRaw camera conversion',
        'profile':profile.key if profile else 'fuji-reference' if is_fuji else 'generic-libraw',
        'label':profile.label if profile else 'Fuji · source recipe' if is_fuji else 'Generic input · uncalibrated',
        'exposure_method':'fixed camera offset + metadata' if profile else
            'embedded preview luminance estimate + metadata' if matched else 'metadata only',
        'exposure_is_absolute_calibration':False,'fuji_color_calibrated':False,
        'embedded_pixels_used_in_output':False,
        'signed_camera_conversion':bool(profile and profile.floating_camera_rgb),
        'make':str(metadata.get('Make','')),'model':str(metadata.get('Model',''))}
