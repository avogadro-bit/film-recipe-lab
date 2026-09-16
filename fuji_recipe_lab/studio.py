"""Independent photographic renderer. No Fuji firmware or calibrated Fuji model."""
from io import BytesIO
from functools import lru_cache
from pathlib import Path
from typing import Literal
import json
import numpy as np
from PIL import Image, ImageCms
from pydantic import Field
import rawpy
from scipy.ndimage import gaussian_filter
import tifffile
from .input_profiles import RAW_EXTENSIONS, validate_linear_input, normalization_details
from .recipe import Recipe
from .raw import require_local, exif
from .source_exposure import source_exposure, estimate_reference_ev
from .official_luts import FILMS as OFFICIAL_FILMS, apply_official
from .recipe_effects import wb_shift_gains, chrome_effect, dynamic_range_compress, linear_tone_curve, selective_tone_detail, preserve_film_hue


class StudioRecipe(Recipe):
    target_model: Literal['X-T4', 'X100VI'] = 'X100VI'
    firmware_version: str = ''
    wb: Literal['camera','auto','auto_white','auto_ambience','daylight','shade','tungsten','fluorescent1','fluorescent2','fluorescent3','underwater','kelvin'] = 'camera'
    dr_priority: Literal['off','weak','strong','auto'] = 'off'
    mono_warm: int = Field(default=0, ge=-18, le=18)
    mono_green: int = Field(default=0, ge=-18, le=18)
    smooth_skin: Literal['off','weak','strong'] = 'off'
    file_type: Literal['jpeg','tiff8','tiff16'] = 'jpeg'
    image_size: Literal['L','M','S'] = 'L'
    aspect: Literal['original','3:2','16:9','1:1','4:3'] = 'original'
    image_quality: Literal['fine','normal'] = 'fine'
    color_space: Literal['srgb','adobe_rgb'] = 'srgb'
    digital_crop: Literal[1,1.4,2] = 1
    lens_optimizer: Literal['off'] = 'off'
    lens_distortion: Literal['off','auto'] = 'off'
    lens_vignetting: Literal['off','auto'] = 'off'
    hdr: Literal['off'] = 'off'


def studio_status():
    from .official_luts import missing_luts
    return {'engine':'official-lut-photo-adapter-v1','available':True,'exact_fuji_render':False,
            'missing_luts':missing_luts(),
            'calibrated_against_fuji':False,'default_film':'provia',
            'official_lut_films':list(OFFICIAL_FILMS),
            'lut_source':'FUJIFILM GFX ETERNA 55 v1.10',
            'photo_adapter_calibrated':False,'recipe_response_revision':13,
            'lut_display_gamma':2.2,'raw_extensions':sorted(RAW_EXTENSIONS),
            'input_working_space':'linear sRGB / D65 / float32',
            'wb_shift_source':'X-T4 2.12 DAT; adapted RGB application',
            'chrome_reference':'public Fuji STRONG pairs + second-scene check'}


def resize_float(a, edge):
    h,w=a.shape[:2]
    if max(h,w)<=edge:return a
    size=(max(1,round(w*edge/max(h,w))),max(1,round(h*edge/max(h,w))))
    return np.stack([np.asarray(Image.fromarray(a[:,:,c]).resize(size,Image.Resampling.LANCZOS)) for c in range(3)],axis=-1)


def _decode_sensor(path, preview=True, floating_camera_rgb=False):
    require_local(path)
    with rawpy.imread(str(path)) as raw:
        black=min(raw.black_level_per_channel)
        highlight_mask=None
        if floating_camera_rgb:
            # Multiple clipped samples in a Bayer cell no longer provide a
            # reliable colour. Neutralize only those sensor-clipped regions,
            # not all bright scene-linear RGB. No invented highlight detail.
            sensor=raw.raw_image_visible
            if sensor.ndim!=2 or raw.raw_pattern.shape!=(2,2):
                raise ValueError('Unsupported Leica sensor layout.')
            h,w=sensor.shape;h-=h%2;w-=w%2
            count=np.zeros((h//2,w//2),np.uint8)
            for yy in (0,1):
                for xx in (0,1):
                    count+=(sensor[yy:h:2,xx:w:2]>=raw.white_level-32)
            highlight_mask=(count>=2).astype(np.float32)
            flip=raw.sizes.flip
            if flip in (3,5,6):highlight_mask=np.rot90(highlight_mask,{3:2,5:1,6:3}[flip])
        # Reserve 3 stops inside LibRaw's integer processing BEFORE WB/RGB
        # conversion. Restore the scale in float, with no clip to display white.
        white=black+8*(raw.white_level-black)
        a=raw.postprocess(use_camera_wb=True,use_auto_wb=False,no_auto_bright=True,
            adjust_maximum_thr=0,user_sat=int(white),output_bps=16,gamma=(1,1),
            output_color=rawpy.ColorSpace.raw if floating_camera_rgb else rawpy.ColorSpace.sRGB,half_size=preview)
        if floating_camera_rgb:
            # LibRaw has already decoded the sensor, applied its black/white
            # levels and camera WB. Apply its DNG-derived camera matrix in
            # float instead of its uint16 RGB conversion, retaining signed
            # out-of-sRGB colours and the reserved three stops of headroom.
            matrix=np.asarray(raw.color_matrix,dtype=np.float32)
            if (a.shape[-1]!=3 or matrix.shape!=(3,4) or not np.isfinite(matrix).all()
                    or np.max(np.abs(matrix[:,:3]))<.01 or np.any(matrix[:,3]!=0)):
                raise ValueError('Unsupported Leica color matrix; conversion stopped.')
            a=np.einsum('...j,ij->...i',a.astype(np.float32),matrix[:,:3])
            mask=np.asarray(Image.fromarray(highlight_mask).resize((a.shape[1],a.shape[0]),Image.Resampling.BILINEAR))
            # Feather the mask boundary; keep the luminance/RAW headroom.
            mask=gaussian_filter(mask,.6 if preview else 1.2)[:,:,None]
            y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),-1,keepdims=True)
            a=a*(1-mask)+y*mask
        reference=None
        if preview:
            try:
                thumb=raw.extract_thumb()
                im=Image.open(BytesIO(thumb.data)) if thumb.format==rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
                im=im.convert('RGB');im.thumbnail((256,256),Image.Resampling.LANCZOS)
                reference=np.asarray(im,dtype=np.float32)/255
            except (rawpy.LibRawNoThumbnailError,rawpy.LibRawUnsupportedThumbnailError,OSError,ValueError):
                pass
    a=a.astype(np.float32)*(8/65535)
    # A responsive whole-image proxy. Source pixels are requested separately
    # as viewport tiles at 100%+, so edits never rebuild a giant browser JPEG.
    a=resize_float(a,1800) if preview else a
    return (a if floating_camera_rgb else np.maximum(a,0)),reference


@lru_cache(maxsize=2)
def _preview_source(path,mtime,size):
    metadata=exif(path)
    info=source_exposure(metadata,path.suffix)
    if info.get('floating_camera_rgb'):
        linear,reference=_decode_sensor(path,True,floating_camera_rgb=True)
    else:
        linear,reference=_decode_sensor(path,True)
    linear*=info['gain']
    match={'reference_ev':0.,'reference_matched':False,'reason':'No readable embedded preview'}
    if info.get('fixed_camera_exposure'):
        match={'reference_ev':0.,'reference_matched':False,
               'reason':'Fixed Leica model normalization; embedded preview not used'}
    elif reference is not None:
        # A fixed reference film per source, independent of the selected recipe.
        # For other cameras PROVIA is only a neutral-ish adapter, not their JPEG engine.
        # The embedded JPEG includes the capture's tone/color recipe. Omitting
        # those settings makes the exposure estimate compensate for the wrong
        # rendering. WB is already in decoded RGB; shooting_settings keeps its
        # shifts at zero. This stays independent of the recipe being edited.
        settings={'film':'provia'}
        if path.suffix.lower()=='.raf':settings.update(shooting_settings(metadata))
        ref_recipe=StudioRecipe(**settings)
        match=estimate_reference_ev(resize_float(linear,256),reference,lambda a:render(a,ref_recipe))
    info={**info,**match,'metadata_ev':info.get('baseline_ev',info['ev'])}
    info['ev']+=match['reference_ev'];info['gain']=2**info['ev']
    linear*=2**match['reference_ev']
    linear=validate_linear_input(linear)
    info['normalization']=normalization_details(metadata,path.suffix,info)
    linear.setflags(write=False)
    return linear,info


def source_details(path):
    path=Path(path);require_local(path);st=path.stat()
    return dict(_preview_source(path,st.st_mtime_ns,st.st_size)[1])


def decode(path, preview=True):
    path=Path(path);require_local(path);st=path.stat()
    linear,info=_preview_source(path,st.st_mtime_ns,st.st_size)
    if preview:return linear.copy()
    if info.get('floating_camera_rgb'):
        a,_=_decode_sensor(path,False,floating_camera_rgb=True)
    else:
        a,_=_decode_sensor(path,False)
    return validate_linear_input(a*info['gain'])


def srgb_encode(a):
    a=np.maximum(a,0)
    return np.where(a<=.0031308,a*12.92,1.055*a**(1/2.4)-.055)


def srgb_decode(a):
    return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)


def blur(a, radius):
    return gaussian_filter(a,sigma=(radius,radius,0),mode='reflect')


def _coordinate_noise(shape, origin=(0,0)):
    """Deterministic normal noise addressed by absolute image coordinates."""
    y=np.arange(origin[0],origin[0]+shape[0],dtype=np.uint64)[:,None]
    x=np.arange(origin[1],origin[1]+shape[1],dtype=np.uint64)[None,:]
    def uniform(seed):
        value=x*np.uint64(0x9E3779B185EBCA87)^y*np.uint64(0xC2B2AE3D27D4EB4F)^np.uint64(seed)
        value^=value>>np.uint64(30);value*=np.uint64(0xBF58476D1CE4E5B9)
        value^=value>>np.uint64(27);value*=np.uint64(0x94D049BB133111EB)
        value^=value>>np.uint64(31)
        return ((value>>np.uint64(11)).astype(np.float64)+.5)*(1/2**53)
    u=np.maximum(uniform(71821),1e-12);v=uniform(99173)
    return (np.sqrt(-2*np.log(u))*np.cos(2*np.pi*v)).astype(np.float32)


@lru_cache(maxsize=32)
def _grain_deviation(size, scale):
    noise=_coordinate_noise((768,768))
    fine,coarse=((.35*scale,1.2*scale) if size=='large' else (.2*scale,.8*scale))
    fine_field=noise if fine<.3 else gaussian_filter(noise,fine,mode='reflect')
    return max(float((fine_field-gaussian_filter(noise,max(.35,coarse),mode='reflect')).std()),1e-5)


def film_grain(shape, size, scale=1, origin=(0,0)):
    """Deterministic monochrome band-pass texture in display-pixel units.

    Fujifilm describes Roughness and Size as separate controls. The public
    with/without example is dominated by luminance noise with slightly
    negative adjacent-pixel correlation, so a blurred Gaussian field is the
    wrong texture. This field removes a broader low-frequency component while
    preserving a stable apparent scale across preview and full-size output.
    """
    noise=_coordinate_noise(shape,origin)
    if size=='large':
        fine=.35*scale;coarse=1.2*scale
    else:
        fine=.2*scale;coarse=.8*scale
    fine_field=noise if fine<.3 else gaussian_filter(noise,fine,mode='reflect')
    field=fine_field-gaussian_filter(noise,max(.35,coarse),mode='reflect')
    # A fixed normalization keeps adjacent independently rendered tiles equal.
    return field/_grain_deviation(size,round(float(scale),4))


def render(linear, r, neutral=False, *, output_transform=True, context=None, origin=(0,0)):
    """float32 display sRGB; recipe effects are deterministic artistic approximations."""
    a=linear.astype(np.float32,copy=True)
    context=context or {}
    statistics=np.asarray(context.get('sample',a[::8,::8]),dtype=np.float32)
    if not neutral:
        if r.wb.startswith('auto'):
            means=np.mean(statistics,axis=(0,1))+1e-5
            strength={'auto':.65,'auto_white':1.,'auto_ambience':.3}[r.wb]
            gains=np.clip((means.mean()/means)**strength,.5,2)
        else:
            # Relative temperature adaptation of camera-balanced RGB; not sensor-space WB.
            temp={'daylight':5500,'shade':7500,'tungsten':3200,'fluorescent1':6500,'fluorescent2':5000,'fluorescent3':4000,'underwater':8500}.get(r.wb,r.kelvin if r.wb=='kelvin' else 5500)
            t=np.log(temp/5500)
            gains=np.array([np.exp(.5*t),1,np.exp(-.65*t)],np.float32)
        gains=gains*wb_shift_gains(r.wb_red,r.wb_blue)*2**r.exposure
        a*=gains
        adjusted_statistics=statistics*gains
        dr=r.dynamic_range
        if r.dr_priority!='off':
            # D-range priority takes over both DR and manual tone controls.
            dr={'weak':200,'strong':400,'auto':400 if np.percentile(adjusted_statistics,99)>.8 else 200}[r.dr_priority]
        if r.dr_priority=='off':
            highlights,whites,shadows,blacks=r.highlights,r.whites,r.shadows,r.blacks
        else:
            # Priority owns the complete four-way tone group.
            highlights,whites,shadows,blacks=((-35,-12,20,5) if dr==200
                                               else (-55,-28,38,12))
        color_input=a
        stabilize_color=any((highlights,whites,shadows,blacks)) or dr!=100
        a=linear_tone_curve(a,highlights=highlights,whites=whites,
                            shadows=shadows,blacks=blacks)
        a=dynamic_range_compress(a,dr)
    if neutral:return np.clip(srgb_encode(a),0,1)
    official=r.film in OFFICIAL_FILMS
    if official:
        if r.film=='acros' and r.mono_filter!='none':
            # Artistic prefilter; the official pack only supplies plain ACROS.
            gains={'red':[1.5,.8,.4],'yellow':[1.2,1.1,.5],
                   'green':[.7,1.25,.7]}[r.mono_filter]
            a=a*np.array(gains,np.float32)
            color_input=color_input*np.array(gains,np.float32)
        a=apply_official(a,r.film)
        if stabilize_color:
            # Tone changes can move hue inside a 3D film LUT. Keep the film's
            # original hue while taking gradation from the adjusted RAW branch.
            a=preserve_film_hue(apply_official(color_input,r.film),a)
        sat=1.
    else:
        # Legacy artistic looks are explicitly identified in the GUI.
        a=np.clip(srgb_encode(a),0,1)
        contrast,sat={'pro_neg_hi':(1.1,.94),'nostalgic_negative':(1.06,.93)}.get(r.film,(1.,1.))
        if r.film=='nostalgic_negative':
            y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=2)
            a+=y[:,:,None]**2*np.array([.035,.012,-.025],np.float32)
        a=a+(contrast-1)*4*(a-.5)*a*(1-a)
    if highlights<0 or whites<0 or shadows>0 or blacks>0:
        # Restore surviving RAW texture after the film/display transform, where
        # a LUT shoulder would otherwise flatten it again.
        a=selective_tone_detail(color_input,a,highlights=highlights,whites=whites,
                                shadows=shadows,blacks=blacks)
    y=np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=2)
    a=y[:,:,None]+(a-y[:,:,None])*(sat*(1+r.color*.085))
    a=chrome_effect(a,r.color_chrome)
    a=chrome_effect(a,r.fx_blue,blue_only=True)
    if r.film in ['acros','monochrome','sepia']:
        weights={'none':[.2126,.7152,.0722],'red':[.55,.4,.05],'yellow':[.35,.6,.05],'green':[.12,.82,.06]}[r.mono_filter]
        y=np.sum(a*np.array(weights,np.float32),axis=2)
        if r.film=='acros' and not official:y=y+.25*(y-.5)*y*(1-y)
        a=np.repeat(y[:,:,None],3,axis=2)
        if r.film=='sepia':a*=np.array([1.08,.96,.80],np.float32)
        a+=y[:,:,None]*(1-y[:,:,None])*np.array([r.mono_warm*.004-r.mono_green*.002,r.mono_green*.003,-r.mono_warm*.004-r.mono_green*.002],np.float32)
    scale=max(context.get('full_shape',a.shape)[:2])/1600
    if r.noise_reduction>-4:
        amount=(r.noise_reduction+4)/16
        a=a*(1-amount)+blur(a,max(.45,.65*scale))*amount
    if r.smooth_skin!='off':
        mask=np.clip((a[:,:,0]-a[:,:,2])*5,0,1)*np.clip((a[:,:,1]-a[:,:,2])*5,0,1)
        mix=mask[:,:,None]*({'weak':.25,'strong':.5}[r.smooth_skin])
        a=a*(1-mix)+blur(a,max(.6,1.5*scale))*mix
    if r.clarity:a+=(a-blur(a,max(1,12*scale)))*r.clarity*.10
    if r.sharpness:a+=(a-blur(a,max(.5,.75*scale)))*r.sharpness*.12
    if r.grain!='off':
        noise=film_grain(a.shape[:2],r.grain_size,scale,origin)
        amount=.022 if r.grain=='weak' else .040
        luminance=np.clip(np.sum(a*np.array([.2126,.7152,.0722],np.float32),axis=2),0,1)
        # Fujifilm's public pair is close to constant-amplitude display noise,
        # with only a modest reduction at the tonal extremes.
        visibility=.72+.28*np.power(np.clip(4*luminance*(1-luminance),0,1),.3)
        a+=noise[:,:,None]*amount*visibility[:,:,None]
    a=np.clip(a,0,1)
    if not output_transform:return a
    h,w=a.shape[:2]
    cw,ch=int(w/r.digital_crop),int(h/r.digital_crop)
    if r.aspect!='original':
        rw,rh=map(int,r.aspect.split(':'));ratio=rw/rh
        if h>w:ratio=1/ratio
        if cw/ch>ratio:cw=round(ch*ratio)
        else:ch=round(cw/ratio)
    a=a[(h-ch)//2:(h-ch)//2+ch,(w-cw)//2:(w-cw)//2+cw]
    if r.image_size!='L':a=resize_float(a,round(max(a.shape[:2])*{'M':.7071,'S':.5}[r.image_size]))
    return a


def encode(a,r,preview=False):
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    if r.color_space=='adobe_rgb' and not preview:
        profile=Path('/System/Library/ColorSync/Profiles/AdobeRGB1998.icc')
        if not profile.is_file():raise ValueError('Adobe RGB 1998 profile is missing from this computer.')
        # sRGB linear to Adobe RGB (1998), both D65; encode gamma 563/256.
        linear=srgb_decode(a)
        a=np.clip(np.einsum("...i,ij->...j",linear,np.array([[.7151626,0,0],[.2848374,1,.0411705],[0,0,.9588295]],np.float32)),0,1)**(256/563)
        icc=profile.read_bytes()
    buf=BytesIO()
    if preview or r.file_type=='jpeg':
        im=Image.fromarray(np.round(a*255).astype(np.uint8))
        im.save(buf,'JPEG',quality=90 if preview else (96 if r.image_quality=='fine' else 82),icc_profile=icc,
            comment=('Film Recipe Lab: '+('official GFX ETERNA 55 LUT; uncalibrated photo adapter' if r.film in OFFICIAL_FILMS else 'independent artistic look')).encode())
        return buf.getvalue(),'image/jpeg'
    dtype=np.uint16 if r.file_type=='tiff16' else np.uint8
    maximum=65535 if r.file_type=='tiff16' else 255
    tifffile.imwrite(buf,np.round(a*maximum).astype(dtype),photometric='rgb',metadata=None,
        description=json.dumps({'renderer':'official-lut-photo-adapter-v1','recipe_response_revision':13,'official_lut':r.film if r.film in OFFICIAL_FILMS else None,'exact_fuji_render':False,'recipe':r.model_dump()}),
        extratags=[(34675,'B',len(icc),icc,False)])
    return buf.getvalue(),'image/tiff'


def shooting_settings(meta):
    """Import only unambiguous EXIF settings; WB is already applied by LibRaw."""
    import re
    values={'name':'File Settings (Partial)','wb':'camera','wb_red':0,'wb_blue':0}
    films={'classic negative':'classic_negative','classic chrome':'classic_chrome','provia':'provia','velvia':'velvia','astia':'astia','eterna':'eterna','eterna bleach bypass':'eterna_bleach','reala ace':'reala_ace','nostalgic neg.':'nostalgic_negative','pro neg. std':'pro_neg_std','pro neg. hi':'pro_neg_hi'}
    film=str(meta.get('FilmMode','')).lower()
    if film in films:values['film']=films[film]
    # ACROS/monochrome and its filter are encoded in Saturation, not FilmMode.
    mono=str(meta.get('Saturation','')).lower()
    if mono.startswith('acros') or mono.startswith('b&w') or mono=='none (b&w)':
        values['film']='acros' if mono.startswith('acros') else 'sepia' if 'sepia' in mono else 'monochrome'
        values['mono_filter']=next((c for c in ['red','yellow','green'] if c in mono),'none')
    for tag,key in [('HighlightTone','highlights'),('ShadowTone','shadows'),('Saturation','color'),('Sharpness','sharpness'),('NoiseReduction','noise_reduction'),('Clarity','clarity')]:
        text=str(meta.get(tag,''));match=re.match(r'^([+-]?\d+(?:\.\d+)?)',text)
        if match:
            v=float(match[1])
            if key=='highlights':v=round(v*25)
            elif key=='shadows':v=round(v*-25)
            candidate={**values,key:v}
            try:StudioRecipe(**candidate)
            except ValueError:continue
            values[key]=v
        elif text.lower()=='normal':values[key]=0
    for tag,key in [('GrainEffectRoughness','grain'),('ColorChromeEffect','color_chrome'),('ColorChromeFXBlue','fx_blue')]:
        val=str(meta.get(tag,'')).lower()
        if val in ['off','weak','strong']:values[key]=val
    size=str(meta.get('GrainEffectSize','')).lower()
    if size in ['small','large']:values['grain_size']=size
    dr=meta.get('DevelopmentDynamicRange')
    if dr in [100,200,400]:values['dynamic_range']=dr
    return values
