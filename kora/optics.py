"""Optional, explicit optical corrections before film rendering.

Native Leica mosaic DNG: geometric WarpRectilinear from OpcodeList3 (green
plane for all RGB channels; no claim of chromatic aberration correction).
Other supported cameras: uniquely identified Lensfun profiles. No guessing
from a similar camera/lens; no second automatic correction of linear DNGs.
"""
from functools import lru_cache
import json
from pathlib import Path
import struct
import subprocess
import numpy as np
from scipy.ndimage import map_coordinates
from .official_luts import run_parallel_rows
from .raw import require_local
from .external_tools import find_exiftool


def parse_warp(data):
    if len(data)<24:raise ValueError('Truncated DNG opcode')
    count,opcode,version,flags,length,planes=struct.unpack('>6I',data[:24])
    if count!=1 or opcode!=1 or version>0x01070100 or flags & ~3:
        raise ValueError('Unsupported OpcodeList3 sequence')
    if planes not in (1,3) or length!=4+planes*48+16 or len(data)!=20+length:
        raise ValueError('Invalid WarpRectilinear size')
    values=np.frombuffer(data[24:],dtype='>f8').astype(np.float64)
    if not np.isfinite(values).all():raise ValueError('Coefficients DNG non finis')
    center=values[-2:];coeff=values[:-2].reshape(planes,6)[1 if planes==3 else 0]
    if np.any((center<0)|(center>1)) or np.max(np.abs(coeff))>10:
        raise ValueError('Coefficients DNG hors limites')
    # This first implementation supports radial correction only. Never silently
    # ignore tangential terms or a non-invertible radial polynomial.
    if np.any(coeff[4:]!=0):raise ValueError('Unsupported DNG tangential distortion')
    r2=np.linspace(0,1,1025)
    derivative=coeff[0]+3*coeff[1]*r2+5*coeff[2]*r2**2+7*coeff[3]*r2**3
    if np.min(derivative)<=0:raise ValueError('Distorsion DNG non inversible')
    return {'coefficients':coeff.tolist(),'center':center.tolist()}


def warp_coordinates(width,height,start,rows,warp,scale=1.):
    cx,cy=np.asarray(warp['center'])*[width-1,height-1]
    radius=np.hypot(max(cx,width-1-cx),max(cy,height-1-cy))
    yy,xx=np.mgrid[start:start+rows,0:width].astype(np.float32)
    dx=(xx-cx)/(radius*scale);dy=(yy-cy)/(radius*scale);r2=dx*dx+dy*dy
    k=warp['coefficients'];f=k[0]+r2*(k[1]+r2*(k[2]+r2*k[3]))
    return np.stack([cx+radius*dx*f,cy+radius*dy*f],axis=-1).astype(np.float32)


def remap(linear,coordinates):
    result=np.empty_like(linear)
    def process(start,stop):
        rows=stop-start
        xy=coordinates(start,rows)
        if xy.shape!=(rows,linear.shape[1],2) or not np.isfinite(xy).all():
            raise ValueError('Invalid lens correction map')
        coords=np.moveaxis(xy[...,::-1],-1,0)
        for c in range(3):
            result[start:stop,:,c]=map_coordinates(linear[...,c],coords,order=1,mode='nearest',prefilter=False)
    run_parallel_rows(len(linear),process)
    return result


@lru_cache(maxsize=64)
def _warp_scale(w,h,coefficients,center):
    warp={'coefficients':coefficients,'center':center}
    def bounds(scale):
        edge=np.concatenate([warp_coordinates(w,h,0,1,warp,scale).reshape(-1,2),
            warp_coordinates(w,h,h-1,1,warp,scale).reshape(-1,2)])
        return np.all((edge>=0)&(edge<=np.array([w-1,h-1])))
    if bounds(1.):return 1.
    lo,hi=1.,2.
    if not bounds(hi):raise ValueError('Recadrage DNG hors limites')
    for _ in range(20):
        mid=(lo+hi)/2
        if bounds(mid):hi=mid
        else:lo=mid
    return hi


def dng_corrected_region(linear,profile,box,step=1):
    """Sample only requested output pixels; coordinates match full correction.

    The sparse step is for global tone statistics, not tile downsampling.
    Source rotations are views, avoiding an extra full-resolution allocation.
    """
    rotation={1:0,3:2,6:3,8:1}[profile['orientation']]
    source=np.rot90(linear,-rotation)
    h,w=source.shape[:2];warp=profile['warp']
    scale=_warp_scale(w,h,tuple(warp['coefficients']),tuple(warp['center']))
    cx,cy=np.asarray(warp['center'])*[w-1,h-1]
    radius=np.hypot(max(cx,w-1-cx),max(cy,h-1-cy))
    x0,y0,x1,y1=box
    xs=np.arange(x0,x1,step,dtype=np.float32)
    ys=np.arange(y0,y1,step,dtype=np.float32)
    result=np.empty((len(ys),len(xs),3),np.float32)
    for start in range(0,len(ys),128):
        xx,yy=np.meshgrid(xs,ys[start:start+128])
        if rotation==1:xx,yy=w-1-yy,xx
        elif rotation==2:xx,yy=w-1-xx,h-1-yy
        elif rotation==3:xx,yy=yy,h-1-xx
        dx=(xx-cx)/(radius*scale);dy=(yy-cy)/(radius*scale);r2=dx*dx+dy*dy
        k=warp['coefficients'];f=k[0]+r2*(k[1]+r2*(k[2]+r2*k[3]))
        coords=np.stack([cy+radius*dy*f,cx+radius*dx*f]).astype(np.float32)
        for channel in range(3):
            result[start:start+len(yy),:,channel]=map_coordinates(source[...,channel],coords,order=1,mode='nearest',prefilter=False)
    return result


@lru_cache(maxsize=1)
def database():
    try:import lensfunpy
    except ImportError:return None
    return lensfunpy.Database(load_common=False)


def lensfun_match(metadata):
    db=database()
    if db is None:return None
    make=str(metadata.get('Make','')).strip();model=str(metadata.get('Model','')).strip()
    # LensID may be a numeric manufacturer ID: only use it when it is a name.
    name=metadata.get('LensModel') or metadata.get('LensID') or metadata.get('LensType')
    if not isinstance(name,str) or not make or not model:return None
    cameras=db.find_cameras(make,model,loose_search=False)
    if len(cameras)!=1:return None
    lenses=db.find_lenses(cameras[0],lens=name.strip(),loose_search=False)
    if len(lenses)!=1:return None
    return cameras[0],lenses[0]


def _number(value,default=0.):
    try:x=float(value)
    except (TypeError,ValueError):return default
    return x if np.isfinite(x) else default


@lru_cache(maxsize=64)
def _inspect(path,mtime,size):
    base={'distortion':False,'vignetting':False,'source':'none','label':'No lens profile identified','orientation':1}
    executable = find_exiftool()
    if not executable:return {**base,'label':'ExifTool missing: lens profile unavailable'}
    tags=['Make','Model','LensModel','LensID','LensType','FocalLength','FNumber','Orientation',
          'PhotometricInterpretation','Software','OpcodeList3','DefaultScale']
    result=subprocess.run([executable,'-j','-n',*['-'+t for t in tags],str(path)],capture_output=True,text=True,check=True,timeout=20)
    metadata=json.loads(result.stdout)[0];metadata.pop('SourceFile',None)
    orientation=int(_number(metadata.get('Orientation'),1))
    base.update(metadata=metadata,orientation=orientation)
    if orientation not in (1,3,6,8):return {**base,'label':'Mirrored orientation: lens correction unavailable'}
    if path.suffix.lower()=='.dng':
        # Conservative: only native, mosaiced Leica files with understood stage3
        # geometry. Linear/computational or externally converted DNGs can
        # already be warped; no Lensfun fallback on these files.
        native=(str(metadata.get('Make','')).upper().startswith('LEICA') and
                metadata.get('PhotometricInterpretation')==32803 and
                str(metadata.get('Software',''))[:1].isdigit())
        if not native:return {**base,'label':'Transformed or unvalidated DNG: automatic correction disabled'}
        if metadata.get('DefaultScale') not in (None,'1 1'):
            return {**base,'label':'Unsupported DNG scale'}
        blob=subprocess.run([executable,'-b','-OpcodeList3',str(path)],capture_output=True,check=True,timeout=20).stdout
        try:warp=parse_warp(blob)
        except ValueError as exc:return {**base,'label':str(exc)}
        return {**base,'distortion':True,'source':'dng-warp','warp':warp,
                'label':'Leica DNG · embedded distortion correction (without chromatic correction)'}
    match=lensfun_match(metadata)
    if match is None:
        return {**base,'label':'Lensfun missing: install .[optics]' if database() is None else base['label']}
    cam,lens=match;focal=_number(metadata.get('FocalLength'));aperture=_number(metadata.get('FNumber'))
    if focal<=0 or focal<lens.min_focal-.1 or focal>lens.max_focal+.1:
        return {**base,'label':'Focale absente ou hors du profil optique'}
    distortion=lens.interpolate_distortion(focal) is not None
    vignetting=aperture>0 and lens.interpolate_vignetting(focal,aperture,1000.) is not None
    return {**base,'source':'lensfun','label':'Lensfun · '+lens.model,
            'distortion':distortion,'vignetting':vignetting,'focal':focal,'aperture':aperture,
            'focus_distance_m':1000.,'focus_distance_estimated':True}


def inspect_optics(path):
    path=Path(path);require_local(path);st=path.stat()
    return _inspect(path,st.st_mtime_ns,st.st_size)


def apply_corrections(linear,profile,distortion='off',vignetting='off'):
    do_dist=distortion=='auto' and profile.get('distortion',False)
    do_vign=vignetting=='auto' and profile.get('vignetting',False)
    if not do_dist and not do_vign:return linear
    # The decoder has already oriented pixels. Work in original sensor axes.
    rotation={1:0,3:2,6:3,8:1}[profile['orientation']]
    a=np.ascontiguousarray(np.rot90(linear,-rotation))
    h,w=a.shape[:2]
    if profile['source']=='dng-warp':
        warp=profile['warp']
        scale=_warp_scale(w,h,tuple(warp['coefficients']),tuple(warp['center']))
        a=remap(a,lambda start,rows:warp_coordinates(w,h,start,rows,warp,scale))
    else:
        import lensfunpy
        match=lensfun_match(profile['metadata'])
        if match is None:raise ValueError('Lensfun profile is no longer available')
        cam,lens=match;flags=0
        if do_dist:flags|=lensfunpy.ModifyFlags.DISTORTION|lensfunpy.ModifyFlags.SCALE
        if do_vign:flags|=lensfunpy.ModifyFlags.VIGNETTING
        modifier=lensfunpy.Modifier(lens,cam.crop_factor,w,h)
        modifier.initialize(profile['focal'],profile['aperture'] or 8.,distance=1000.,
                            scale=0. if do_dist else 1.,pixel_format=np.float32,flags=flags)
        if do_vign:
            a=a.copy()
            if not modifier.apply_color_modification(a):raise ValueError('Vignetting correction unavailable')
        if do_dist:a=remap(a,lambda start,rows:modifier.apply_geometry_distortion(0,start,w,rows))
    if not np.isfinite(a).all():raise ValueError('Lens correction produced non-finite values')
    return np.ascontiguousarray(np.rot90(a,rotation))
