"""Study DNG dual-illuminant input adaptation; not a Fuji sensor profile."""
import numpy as np
# CIE 1960 isotemperature data, Wyszecki & Stiles, Color Science 2nd ed p228.
# Only 150..350 mired needed for the D65 / A calibration interval.
TABLE=np.array([[150,.19962,.30921,-.70471],[175,.20525,.31647,-.84901],
 [200,.21142,.32312,-1.0182],[225,.21807,.32909,-1.2168],
 [250,.22511,.33439,-1.4512],[275,.23247,.33904,-1.7298],
 [300,.24010,.34308,-2.0637],[325,.24702,.34655,-2.4681],
 [350,.25591,.34951,-2.9641]])
BRADFORD=np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])
SRGB_XYZ=np.array([[.4123907993,.3575843394,.1804807884],[.2126390059,.7151686788,.0721923154],[.0193308187,.1191947798,.9505321522]])
D65=SRGB_XYZ@np.ones(3)


def cct(xy):
    x,y=xy;uv=np.array([2*x,3*y])/(1.5-x+6*y)
    dist=((uv[1]-TABLE[:,2])-(uv[0]-TABLE[:,1])*TABLE[:,3])/np.sqrt(1+TABLE[:,3]**2)
    if dist[0]<=0:return 1e6/TABLE[0,0]
    if dist[-1]>=0:return 1e6/TABLE[-1,0]
    i=np.flatnonzero(dist<=0)[0]
    f=dist[i-1]/(dist[i-1]-dist[i])
    return 1e6/(TABLE[i-1,0]*(1-f)+TABLE[i,0]*f)


def matrix(meta):
    cm=[np.fromstring(meta['ColorMatrix'+str(i)],sep=' ').reshape(3,3) for i in (1,2)]
    n=np.fromstring(meta['AsShotNeutral'],sep=' ');n/=n.max()
    xy=np.array([.3457,.3585])
    for _ in range(50):
        t=cct(xy);weight=np.clip((1/t-1/6504)/(1/2856-1/6504),0,1)
        m=cm[0]*weight+cm[1]*(1-weight)
        white=np.linalg.solve(m,n);nextxy=white[:2]/white.sum()
        if np.max(abs(nextxy-xy))<1e-9:break
        xy=nextxy
    white=np.linalg.solve(m,n);white/=white[1]
    adapt=np.linalg.solve(BRADFORD,np.diag((BRADFORD@D65)/(BRADFORD@white))@BRADFORD)
    # Input already white-balanced to equal camera RGB: undo gains with n.
    result=np.linalg.solve(SRGB_XYZ,adapt@np.linalg.inv(m)@np.diag(n))
    result/= (result@np.ones(3))[1]
    return result,{'cct_kelvin':float(t),'illuminant1_weight':float(weight),'white_xy':xy.tolist()}


def main():
    import json,rawpy
    from pathlib import Path
    from fuji_recipe_lab.raw import exif
    from fuji_recipe_lab.studio import resize_float,render,StudioRecipe
    from fuji_recipe_lab.source_exposure import estimate_reference_ev
    from scripts.paired_fuji_validation import metrics
    rows=json.loads(Path('research/leica-input/selection.json').read_text());out=[]
    for r in rows:
        p=Path(r['SourceFile']);meta=exif(p)
        new,info=matrix(meta)
        with rawpy.imread(str(p)) as raw:old=raw.color_matrix[:,:3].copy()
        z=np.load('research/leica-input/'+p.stem+'.npz');a=resize_float(z['linear'],256);ref=z['reference']
        ref=resize_float(ref,256)
        # Compare luma-aligned renderings to the Leica Standard JPEG; it is not
        # a colorimetric target, so even lower deltaE cannot establish accuracy.
        b=np.einsum('...i,ji->...j',a,new@np.linalg.inv(old))
        rec=StudioRecipe(film='provia')
        vals={}
        for name,x in [('old',a),('dng',b)]:
            fit=estimate_reference_ev(x,ref,lambda v:render(v,rec))
            im=render(x*2**fit['reference_ev'],rec)
            if im.shape!=ref.shape:
                from PIL import Image
                ref=np.asarray(Image.fromarray(np.uint8(ref*255)).resize((im.shape[1],im.shape[0])),np.float32)/255
            vals[name]={**fit,**metrics(im,ref)}
        out.append({'file':str(p),'split':r['split'],**info,**vals})
        print(p.name,round(info['cct_kelvin']),*[round(vals[k]['de00_median'],2) for k in vals],flush=True)
    Path('outputs/classic-negative-adapter/dng-matrix-audit.json').write_text(json.dumps(out,indent=2))
    for split in ('train','test'):
        print(split,{k:float(np.median([r[k]['de00_median'] for r in out if r['split']==split])) for k in ('old','dng')})

if __name__=='__main__':main()
