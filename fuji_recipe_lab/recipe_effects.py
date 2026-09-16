"""Reference-backed approximations, not Fujifilm's complete photo processing.

WB: X-T4 2.12 DAT coefficients; RGB application is an adaptation.
Chrome STRONG: fit to official public pairs, checked on a second X100V scene.
WEAK: half the STRONG response, not measured independently.
See docs/PARAMETER_AUDIT.md and research/reference-effects/chrome-fit.json.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter

WB_TABLE=json.loads((Path(__file__).with_name('luts')/'wb-shifts-xt4.json').read_text())


def wb_shift_gains(red,blue):
    return np.array([WB_TABLE['red_q10'][red+9],1024,
                     WB_TABLE['blue_q10'][blue+9]],np.float32)/1024


def chrome_effect(a,setting,blue_only=False):
    if setting=='off':return a
    strength={'weak':.5,'strong':1.}[setting]
    high=a.max(-1);low=a.min(-1);chroma=high-low
    sat=np.clip(chroma/np.maximum(high,1e-6),0,1)
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=-1)
    if blue_only:
        hue=np.clip((a[...,2]-np.maximum(a[...,0],a[...,1]))/np.maximum(chroma,1e-6),0,1)
        mask=sat**1.32407230501026*hue**.3702288353626123
        out=a-strength*.6912800902142242*(mask*y)[...,None]
    else:
        hue=np.clip((np.maximum(a[...,0],a[...,1])-a[...,2])/np.maximum(chroma,1e-6),0,1)
        mask=sat**1.09437228*hue
        density=.15368655*mask
        target=y*(1-density)
        # Refit with bounded chroma: taper extra saturation near the gamut
        # boundary, instead of exaggerating already saturated colors and
        # independently clipping their channels (revision 2).
        gain=1-density+mask*(1-sat)
        gain=np.minimum(gain,target/np.maximum(y-low,1e-6))
        gain=np.minimum(gain,(1-target)/np.maximum(high-y,1e-6))
        strong=target[...,None]+gain[...,None]*(a-y[...,None])
        out=a+strength*(strong-a)
    return np.clip(out,0,1)


def dynamic_range_compress(a,level):
    """Shoulder preserving middle gray, mapping 1/2 stops of headroom to white.

    Does not recover sensor highlights absent from the decoded input.
    """
    if level==100:return a
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=-1)
    excess=np.maximum(y-.18,0)
    white=level/100
    # f(.18)=.18, f'(.18)=1, f(white)=1. The previous coefficients
    # mapped white to .825 (DR200) / .622 (DR400), needlessly darkening it.
    k=(white-1)/((white-.18)*(1-.18))
    target=np.minimum(y,.18)+excess/(1+k*excess)
    # Signed camera-to-working-space conversion can yield negative out-of-gamut
    # values. Dividing those by a positive epsilon inverted them into enormous
    # positive values, which appeared as isolated white preview pixels after a
    # DR change. DR compression is undefined below zero luminance; leave those
    # samples signed for the film transform to handle instead of inverting them.
    scale=np.ones_like(y)
    np.divide(target,y,out=scale,where=y>1e-8)
    return a*scale[...,None]


def tone_curve(a, highlights=0, shadows=0):
    """Independent, stronger photo tone controls; not a measured Fuji curve.

    Positive shadow values darken; positive highlights brighten. The two
    halves join at display luminance .5 with unit slope. The rational curves
    remain monotonic throughout the recipe's -2..4 range, unlike simply
    multiplying the former additive correction until it folds or clips.
    """
    if highlights == 0 and shadows == 0:
        return a
    a=np.clip(a,0,1)
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=-1)
    def half(t,setting):
        return t/(t+(1-t)*np.exp(.8*setting*(1-t)))
    dark=.5*half(np.minimum(2*y,1),shadows)
    light=1-.5*half(np.minimum(2*(1-y),1),highlights)
    target=np.where(y<.5,dark,light)
    # Keep chroma where possible, reduce it only at the display gamut boundary.
    low=a.min(-1);high=a.max(-1)
    gain=np.minimum(1,target/np.maximum(y-low,1e-6))
    gain=np.minimum(gain,(1-target)/np.maximum(high-y,1e-6))
    return np.clip(target[...,None]+gain[...,None]*(a-y[...,None]),0,1)


def _tone_tail(ev, pivot, strength, high):
    """Monotonic log-luminance tail with a fixed point and unit pivot slope."""
    distance=np.maximum(ev-pivot,0) if high else np.maximum(pivot-ev,0)
    # The bounded exponent approaches a constant contrast away from the
    # pivot. It cannot fold the curve over in the supported strength range.
    mapped=distance*np.exp2(strength*distance/(1+distance))
    return np.where(distance>0,pivot+mapped if high else pivot-mapped,ev)


def linear_tone_curve(a, highlights=0, shadows=0, whites=0, blacks=0):
    """Four-way, exposure-domain tonal adjustment before film clipping.

    Values follow common photo-editor directions on a -100..100 scale:
    negative Highlights/Whites recover bright tones, while positive
    Shadows/Blacks open dark tones. The four monotonic log-luminance tails
    overlap smoothly without clipping HDR values or changing RGB ratios.
    This is an independent Capture One-like model, not Capture One code.
    """
    if highlights == 0 and whites == 0 and shadows == 0 and blacks == 0:
        return a
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=-1)
    valid=y>1e-12
    ev=np.log2(np.maximum(y,1e-12)/.18)
    # Narrow endpoint controls first, then the broader tonal controls. Every
    # stage is monotonic, so even four extreme settings preserve ordering.
    ev=_tone_tail(ev,-2.5,-1.55*blacks/100,False)
    ev=_tone_tail(ev,0,-1.35*shadows/100,False)
    ev=_tone_tail(ev,0,1.25*highlights/100,True)
    ev=_tone_tail(ev,2,1.85*whites/100,True)
    target=.18*np.exp2(np.clip(ev,-60,60))
    scale=np.ones_like(y)
    np.divide(target,y,out=scale,where=valid)
    return a*scale[...,None]


def _resize_plane(a, size):
    """Resize one float32 plane without quantizing it to an image format."""
    return np.asarray(Image.fromarray(a.astype(np.float32), mode='F').resize(
        size, Image.Resampling.BILINEAR), dtype=np.float32)


def _guided_base(a, radius, epsilon=.16):
    """Edge-aware base layer for log-luminance local-contrast separation."""
    size=2*radius+1
    mean=uniform_filter(a,size=size,mode='reflect')
    correlation=uniform_filter(a*a,size=size,mode='reflect')
    variance=np.maximum(correlation-mean*mean,0)
    coefficient=variance/(variance+epsilon)
    offset=mean-coefficient*mean
    return (uniform_filter(coefficient,size=size,mode='reflect')*a
            +uniform_filter(offset,size=size,mode='reflect'))


def selective_tone_detail(original, adjusted, highlights=0, shadows=0, whites=0, blacks=0):
    """Restore existing RAW texture after four-way tonal compression.

    Recovery directions are negative Highlights/Whites and positive
    Shadows/Blacks. Only detail already present in the RAW luminance is used;
    clipped sensor samples are never invented.
    """
    highlight_strength=np.clip(-highlights/100,0,1)
    white_strength=np.clip(-whites/100,0,1)
    shadow_strength=np.clip(shadows/100,0,1)
    black_strength=np.clip(blacks/100,0,1)
    if max(highlight_strength,white_strength,shadow_strength,black_strength)==0:
        return adjusted

    weights=np.array([.2126,.7152,.0722],np.float32)
    source_y=np.sum(original*weights,-1)
    adjusted_y=np.sum(adjusted*weights,-1)
    h,w=source_y.shape
    edge=min(1200,max(h,w))
    small_size=(max(1,round(w*edge/max(h,w))),max(1,round(h*edge/max(h,w))))
    source_small=_resize_plane(source_y,small_size) if small_size!=(w,h) else source_y
    adjusted_small=_resize_plane(adjusted_y,small_size) if small_size!=(w,h) else adjusted_y

    source_log=np.log2(np.maximum(source_small,2**-16))
    adjusted_log=np.log2(np.maximum(adjusted_small,2**-16))
    radius=max(6,round(min(small_size)/16))
    source_base=_guided_base(source_log,radius)
    adjusted_base=_guided_base(adjusted_log,radius)
    source_detail=source_log-source_base
    # Restore what the global curve removed, then strengthen surviving RAW
    # structure modestly. The second term is essential for broad cloud texture:
    # a point curve can preserve ordering while still looking perceptually flat.
    recovered_detail=(source_detail-(adjusted_log-adjusted_base))+.65*source_detail

    base_y=np.exp2(source_base)
    highlight_mask=np.clip((base_y-.35)/(.95-.35),0,1)
    highlight_mask=highlight_mask*highlight_mask*(3-2*highlight_mask)
    white_mask=np.clip((base_y-.72)/(1.35-.72),0,1)
    white_mask=white_mask*white_mask*(3-2*white_mask)
    shadow_mask=1-np.clip((base_y-.06)/(.30-.06),0,1)
    shadow_mask=shadow_mask*shadow_mask*(3-2*shadow_mask)
    black_mask=1-np.clip((base_y-.015)/(.085-.015),0,1)
    black_mask=black_mask*black_mask*(3-2*black_mask)
    strength=np.maximum.reduce((.95*highlight_strength*highlight_mask,
                                .85*white_strength*white_mask,
                                .75*shadow_strength*shadow_mask,
                                .65*black_strength*black_mask))
    # Restore at most 0.85 stop locally. This is enough to keep cloud and
    # foliage structure after compression without producing edge halos.
    gain_small=np.exp2(np.clip(recovered_detail*strength,-.85,.85)).astype(np.float32)
    gain=_resize_plane(gain_small,(w,h)) if small_size!=(w,h) else gain_small
    gain=np.where((source_y>2**-14)&(adjusted_y>2**-14),gain,1)
    # Scaling preserves hue only while no display channel clips. Let bright
    # detail recover mainly by locally darkening valleys near the white limit.
    gain=np.minimum(gain,1/np.maximum(adjusted.max(-1),1e-8))
    return adjusted*gain[...,None]


def preserve_film_hue(reference, adjusted):
    """Use RAW-adjusted luminance with the reference film's RGB hue direction.

    The second rendering retains recovered RAW gradation. Chroma is scaled
    with luminance and reduced at the gamut boundary, never channel-clipped.
    This is an independent color-stability policy, not Fuji's algorithm.
    """
    weights=np.array([.2126,.7152,.0722],np.float32)
    y=np.sum(reference*weights,-1)
    target=np.clip(np.sum(adjusted*weights,-1),0,1)
    chroma=reference-y[...,None]
    gain=target/np.maximum(y,1e-8)
    gain=np.minimum(gain,target/np.maximum(y-reference.min(-1),1e-8))
    gain=np.minimum(gain,(1-target)/np.maximum(reference.max(-1)-y,1e-8))
    return np.clip(target[...,None]+gain[...,None]*chroma,0,1)
