"""Research-only display response fit; NOT a RAW rendering implementation.

Fit four strengths on the official isolated pairs, then evaluate untouched
X-E4 examples. Tests the existing rational curve family, with fixed .5 pivot.
This cannot describe highlight detail already clipped in a JPEG reference.
"""
import json
import numpy as np
from scipy.optimize import least_squares
from scripts.audit_online_references import read, align, luma, OUT


def curve(y, h, s, p):
    def half(t, setting, strength):
        return t/(t+(1-t)*np.exp(strength*setting*(1-t)))
    dark = .5*half(np.minimum(2*y, 1), s, p[2 if s < 0 else 3])
    light = 1-.5*half(np.minimum(2*(1-y), 1), h, p[0 if h < 0 else 1])
    return np.where(y < .5, dark, light)


def samples(first, second, crop=None):
    a=read(first, crop); b, valid, registration=align(a, read(second, crop))
    if not registration['sane']:
        raise ValueError('Unreliable registration: '+first)
    y=luma(a); z=luma(b)
    valid &= (np.hypot(*np.gradient(y)) < .035) & (y > .02) & (y < .98)
    # Spatial split not used as validation: entire other scenes are held out.
    return y[valid], z[valid]


def main():
    training=[]
    for control in ('highlight', 'shadow'):
        for name, setting in [('minus2', -2), ('plus4', 4)]:
            y,z=samples(control+'-0.png', control+'-'+name+'.png', (540,8,865,274))
            h,s=(setting,0) if control=='highlight' else (0,setting)
            # Equal influence per supported luminance bin, not per pixel.
            for low in np.arange(.02,.98,.02):
                mask=(y>=low)&(y<low+.02)
                if mask.sum()>=50:
                    training.append((float(np.median(y[mask])),float(np.median(z[mask])),h,s))
    def residual(p):
        return np.array([curve(np.array(y),h,s,p)-z for y,z,h,s in training])
    fit=least_squares(residual, [.8]*4, bounds=(0,3))
    report={'production_changed':False,'parameters_hneg_hpos_sneg_spos':fit.x.tolist(),
        'training_bin_rmse_8bit':float(np.sqrt(np.mean(residual(fit.x)**2))*255),
        'limitations':['Display response only; not RAW latitude',
            'X-E4 reference files have Lightroom export metadata',
            'Two PROVIA scenes do not establish other films or X100VI accuracy'], 'validation':[]}
    for name, first, second, h,s in [('soft','17b','17c',-1,-1.5),('hard','26a','26b',2.5,1)]:
        y,z=samples('impress-'+first+'.jpg','impress-'+second+'.jpg')
        pred=curve(y,h,s,fit.x)
        report['validation'].append({'scene':name,'pixels':len(y),
            'identity_luma_rmse_8bit':float(np.sqrt(np.mean((y-z)**2))*255),
            'candidate_luma_rmse_8bit':float(np.sqrt(np.mean((pred-z)**2))*255),
            'candidate_luma_p90_abs_8bit':float(np.percentile(np.abs(pred-z),90)*255),
            'old_display_v4_rmse_8bit':float(np.sqrt(np.mean((curve(y,h,s,[.8]*4)-z)**2))*255)})
    (OUT/'tone-fit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
