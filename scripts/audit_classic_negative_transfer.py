"""Measure PROVIA -> Classic Negative on published same-scene renderings.

The inverse is an equivalent LUT input, NOT a recovered RAW. Reject clipped or
ill-conditioned inversions before interpreting colour differences.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image,ImageCms,ImageDraw
from fuji_recipe_lab.official_luts import load_lut,interpolate
from fuji_recipe_lab.studio import srgb_encode,srgb_decode
from scripts.paired_fuji_validation import metrics
OUT=Path('outputs/classic-negative-transfer')

def inverse_provia(rgb):
    table=load_lut('provia')
    b,g,r=np.meshgrid(*([np.arange(6,51)/64]*3),indexing='ij')
    grid=np.stack([r,g,b],-1).reshape(-1,3)
    values=interpolate(table,grid[:,None,:])[:,0]
    target=np.maximum(srgb_decode(rgb),0)**(1/2.2)
    tree=cKDTree(values);_,idx=tree.query(target.reshape(-1,3))
    x=grid[idx].reshape(rgb.shape).astype(np.float32)
    for _ in range(14):
        y=interpolate(table,x);jac=np.empty((*x.shape,3),np.float32)
        for c in range(3):
            d=np.zeros(3,np.float32);d[c]=.00025
            jac[...,c]=(interpolate(table,x+d)-interpolate(table,x-d))/.0005
        # Damped least-squares inverse, batched explicitly to avoid BLAS image @.
        jt=np.swapaxes(jac,-1,-2)
        lhs=np.einsum('...ij,...jk->...ik',jt,jac)+np.eye(3)*1e-5
        rhs=np.einsum('...ij,...j->...i',jt,y-target)
        step=np.linalg.solve(lhs,rhs[...,None])[...,0]
        x=np.clip(x-np.clip(step,-.02,.02),.092864,.80).astype(np.float32)
    rebuilt=srgb_encode(np.maximum(interpolate(table,x),0)**2.2)
    valid=(rgb.min(-1)>.025)&(rgb.max(-1)<.975)&(abs(rebuilt-rgb).max(-1)<1/255)
    singular=np.linalg.svd(jac,compute_uv=False)
    valid&=singular[...,-1]>.15
    prediction=srgb_encode(np.maximum(interpolate(load_lut('classic_negative'),x),0)**2.2)
    return prediction,rebuilt,valid,x

def read(path):
    im=Image.open(path);im.thumbnail((600,600),Image.Resampling.LANCZOS)
    return np.asarray(im.convert('RGB'),np.float32)/255

def main():
    OUT.mkdir(exist_ok=True)
    pairs=[('impress','research/reference-tones/impress-13b.jpg','research/reference-tones/impress-13c.jpg'),
           ('fuji-whitepaper','research/classic-negative-adapter/figure-005.jpg','research/classic-negative-adapter/figure-011.jpg')]
    results=[]
    for name,base_path,target_path in pairs:
        a=read(base_path);target=read(target_path)
        candidate,reconstruction,mask,log_input=inverse_provia(a)
        from skimage.color import rgb2lab,deltaE_ciede2000
        de=deltaE_ciede2000(rgb2lab(candidate),rgb2lab(target))
        results.append({'name':name,'valid_fraction':float(mask.mean()),'valid_deltaE_median':float(np.median(de[mask])),
            'valid_deltaE_p90':float(np.percentile(de[mask],90)),'whole_image':metrics(candidate,target),
            'inverse_reconstruction_max_valid_error':float(abs(reconstruction-a)[mask].max())})
        np.savez_compressed(OUT/(name+'.npz'),provia=a,target=target,prediction=candidate,valid=mask,log_input=log_input)
        w=a.shape[1];h=a.shape[0];board=Image.new('RGB',(w*3,h+28),'#202020');draw=ImageDraw.Draw(board)
        for i,(label,image) in enumerate([('PROVIA publie',a),('Classic Negative predit',candidate),('Classic Negative publie',target)]):
            board.paste(Image.fromarray(np.uint8(np.clip(image,0,1)*255)),(w*i,28));draw.text((w*i+6,5),label,fill='white')
        board.save(OUT/(name+'.jpg'),quality=96,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        print(results[-1],flush=True)
    (OUT/'audit.json').write_text(json.dumps({'pairs':results,'limits':['Equivalent LUT inputs, not reconstructed RAWs','Published JPEGs may contain additional processing','Pixel correspondence assumed for same-scene examples; visual check required']},indent=2))

if __name__=='__main__':main()
