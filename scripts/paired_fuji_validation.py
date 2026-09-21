"""Read-only paired RAF/JPEG audit; split by capture day before measuring errors.
Outputs are local research artifacts, never a native Fuji calibration claim.
"""
from pathlib import Path
import json,hashlib,argparse
import numpy as np
from PIL import Image,ImageOps,ImageDraw
import cv2
from scipy.ndimage import gaussian_filter
from skimage.color import rgb2lab,deltaE_ciede2000
from kora.raw import require_local
from kora.studio import decode,source_details,render,StudioRecipe,shooting_settings,resize_float
ROOT=Path('research/paired-validation')
OUT=Path('outputs/paired-fuji-validation')


def metrics(a,b):
    # Reduced resolution + slight blur: assess tone/color, not grain/JPEG noise.
    a=np.clip(gaussian_filter(a,(.7,.7,0)),0,1)[8:-8,8:-8]
    b=np.clip(gaussian_filter(b,(.7,.7,0)),0,1)[8:-8,8:-8]
    de=deltaE_ciede2000(rgb2lab(a),rgb2lab(b))
    y=lambda x:np.sum(x*[.2126,.7152,.0722],-1)
    visible=(y(b)>.03)&(y(b)<.97)
    if not np.any(visible):visible=np.ones(b.shape[:2],bool)
    de=de[visible]
    return {'visible_fraction':float(visible.mean()),'de00_median':float(np.median(de)),'de00_p90':float(np.quantile(de,.9)),
            'rgb_mae':float(abs(a-b)[visible].mean()),'luma_rmse':float(np.sqrt(np.mean((y(a)[visible]-y(b)[visible])**2)))}


def select():
    inv=json.loads((ROOT/'inventory.json').read_text())
    meta={x['SourceFile']:x for x in json.loads((ROOT/'metadata.json').read_text())}
    selected=[];excluded=[];seen=set();groups={}
    # Whole days held out; nearby burst frames cannot cross this boundary.
    test_days={'2025:06:29','2025:07:12','2025:07:16','2025:07:19','2025:07:27','2025:08:01','2025:08:07','2025:08:22'}
    for pair in sorted(inv['pairs'],key=lambda x:x['raf']):
        r=meta[pair['raf']];j=meta[pair['jpegs'][0]]
        diff=[k for k in ['WhiteBalance','WhiteBalanceFineTune','ColorTemperature'] if r.get(k)!=j.get(k)]
        reason=None
        if diff:reason='Different source/target WB: '+','.join(diff)
        elif j.get('DevelopmentDynamicRange') not in (100,200,400):reason='DR metadata incomplete'
        elif r.get('DateTimeOriginal')!=j.get('DateTimeOriginal') or r.get('ExposureTime')!=j.get('ExposureTime'):reason='Capture mismatch'
        settings=shooting_settings(j);recipe=StudioRecipe(**settings)
        identity=(r.get('DateTimeOriginal'),r.get('SubSecTimeOriginal'),json.dumps(settings,sort_keys=True))
        day=r.get('DateTimeOriginal','')[:10]
        # Cap repeated same-day recipe samples before seeing their error.
        group=(day,json.dumps(settings,sort_keys=True))
        if identity in seen:reason=reason or 'Duplicate capture and recipe'
        if groups.get(group,0)>=2:reason=reason or 'Repeated day/recipe; capped at two before evaluation'
        if reason:excluded.append({**pair,'reason':reason});continue
        seen.add(identity);groups[group]=groups.get(group,0)+1
        uid=hashlib.sha256((pair['raf']+pair['jpegs'][0]).encode()).hexdigest()[:12]
        selected.append({**pair,'id':uid,'recipe':recipe.model_dump(),'source_meta':r,'jpeg_meta':j,
                         'split':'test' if day in test_days else 'train','day':day})
    report={'selected':selected,'excluded':excluded,'split_policy':'Whole capture days, fixed in code; max two per day/recipe before measuring',
            'acceptance':{'per_film_test_median_de00_max':3,'per_film_test_median_p90_de00_max':6,'per_film_test_luma_rmse_max':.03},
            'scope':'tone/color at 384px, not detail, no claim for unrepresented films or WB changes'}
    (ROOT/'selection.json').write_text(json.dumps(report,indent=2));print('Selected',len(selected),'train',sum(x['split']=='train' for x in selected),'test',sum(x['split']=='test' for x in selected),flush=True)
    return report


def prepare():
    OUT.mkdir(exist_ok=True);(ROOT/'cache').mkdir(exist_ok=True)
    selection=select();results=[]
    for i,item in enumerate(selection['selected']):
        cache=ROOT/'cache'/(item['id']+'.npz');reportfile=cache.with_suffix('.json')
        if cache.exists() and reportfile.exists():
            result=json.loads(reportfile.read_text());z=np.load(cache)
            result['gui_reference_guided']=metrics(z['gui'],z['target'])
            result['metadata_only']=metrics(render(z['linear'],StudioRecipe(**result['recipe'])),z['target'])
            results.append(result);continue
        p=Path(item['raf']);jp=Path(item['jpegs'][0]);require_local(p);require_local(jp)
        gui=decode(p);info=source_details(p);sensor=gui/2**info['reference_ev']
        target=ImageOps.exif_transpose(Image.open(jp)).convert('RGB');target.thumbnail((384,384),Image.Resampling.LANCZOS)
        target=np.asarray(target,dtype=np.float32)/255;h,w=target.shape[:2]
        sensor=cv2.resize(sensor,(w,h),interpolation=cv2.INTER_AREA)
        recipe=StudioRecipe(**item['recipe']);base=render(sensor*2**info['reference_ev'],recipe)
        gray=lambda a:cv2.cvtColor(a.astype(np.float32),cv2.COLOR_RGB2GRAY)
        warp=np.eye(2,3,dtype=np.float32)
        try:
            corr,warp=cv2.findTransformECC(gray(target),gray(base),warp,cv2.MOTION_AFFINE,(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,80,1e-5),None,5)
        except cv2.error:corr=None;warp=np.eye(2,3,dtype=np.float32)
        # Do not allow large transforms to conceal a mismatched scene.
        sane=bool(np.max(abs(warp[:,:2]-np.eye(2)))<.12 and np.max(abs(warp[:,2]))<30)
        if not sane:warp=np.eye(2,3,dtype=np.float32)
        aligned=cv2.warpAffine(sensor,warp,(w,h),flags=cv2.INTER_LINEAR|cv2.WARP_INVERSE_MAP,borderMode=cv2.BORDER_REFLECT)
        base=render(aligned*2**info['reference_ev'],recipe)
        blind=render(aligned,recipe)
        result={k:item[k] for k in ('id','raf','jpegs','recipe','split','day')}
        result.update({'exposure':info,'alignment':{'correlation':corr,'warp':warp.tolist(),'sane':sane},
                       'gui_reference_guided':metrics(base,target),'metadata_only':metrics(blind,target)})
        np.savez_compressed(cache,linear=aligned,target=target,gui=base)
        reportfile.write_text(json.dumps(result,indent=2));results.append(result)
        print(i+1,'/',len(selection['selected']),p.name,item['split'],recipe.film,'DE00',round(result['gui_reference_guided']['de00_median'],2),flush=True)
    (OUT/'baseline.json').write_text(json.dumps(results,indent=2))
    print('Finished',len(results),flush=True)

if __name__=='__main__':prepare()
