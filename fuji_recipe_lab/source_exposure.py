"""Source exposure normalization, independent of the user's recipe exposure.

LibRaw's dcraw processing with no_auto_bright does not apply DNG
BaselineExposure or restore Fujifilm's DR capture underexposure.
This is not a camera-specific middle-gray calibration.
"""
import math
from .input_profiles import camera_profile
import numpy as np
from scipy.optimize import minimize_scalar


def source_exposure(metadata, suffix):
    ev = 0.
    basis = 'No exposure compensation specified'
    if suffix.lower() == '.dng':
        # BaselineExposureOffset belongs to a selected DNG camera profile.
        # We do not apply that profile, so do not add its offset here.
        try:
            value = float(metadata.get('BaselineExposure', 0))
        except (TypeError, ValueError):
            value = 0.
        if math.isfinite(value) and -10 <= value <= 10:
            ev = value
            basis = 'Exposition de base DNG'
        # Fixed camera input offset from 20 Standard Q3 43 previews, checked
        # on 10 images in withheld folders. Brightness adaptation only: not a
        # Fuji colour calibration. No per-image JPEG tone/style matching.
        profile=camera_profile(metadata)
        if profile is not None:
            # Recomputed with signed float decode and Fuji's gamma-2.2
            # viewing recommendation; see CLASSIC_NEGATIVE_LEICA_V9.md.
            offset=profile.exposure_offset_ev
            return {'ev':ev+offset,'basis':'Leica Q3 43 input: DNG baseline + fixed normalization',
                    'gain':2**(ev+offset),'baseline_ev':ev,'camera_offset_ev':offset,
                    'input_profile':profile.key,'fixed_camera_exposure':True,
                    'floating_camera_rgb':profile.floating_camera_rgb,'calibrated_fuji_color':False}
    elif suffix.lower() == '.raf':
        try:
            dr = int(metadata.get('DevelopmentDynamicRange', 100))
        except (TypeError, ValueError):
            dr = 100
        if dr in (100, 200, 400):
            ev = math.log2(dr / 100)
            basis = f'Compensation de prise de vue Fuji DR{dr}'
    return {'ev': ev, 'basis': basis, 'gain': 2**ev}


def estimate_reference_ev(linear, reference, develop):
    """Fit one global exposure to embedded-preview luminance quantiles.

    No reference pixels enter the output. Film/tone differences make this
    an estimate, not an exposure measurement or a Fuji calibration.
    """
    weights=np.array([.2126,.7152,.0722],np.float32)
    ranks=np.linspace(.02,.98,49)
    target=np.quantile(np.sum(reference*weights,-1),ranks)
    valid=(target>.06)&(target<.9)
    if np.count_nonzero(valid)<5:
        return {'reference_ev':0.,'reference_matched':False,'reason':'Preview has too few usable tones'}
    def loss(ev):
        candidate=develop(linear*2**ev)
        values=np.quantile(np.sum(candidate*weights,-1),ranks)
        return float(np.mean((values[valid]-target[valid])**2))
    before=loss(0)
    fit=minimize_scalar(loss,bounds=(-3,3),method='bounded',options={'xatol':.015,'maxiter':24})
    ev=float(fit.x) if fit.success and fit.fun<before else 0.
    return {'reference_ev':ev,'reference_matched':True,'reference_rmse_before':math.sqrt(before),
            'reference_rmse_after':math.sqrt(loss(ev)), 'reference_limit_reached':abs(ev)>2.97}
