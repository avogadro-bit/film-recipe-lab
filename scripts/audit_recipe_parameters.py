"""Operational coverage of image/output controls; not a camera-fidelity test."""
from pathlib import Path
import json
import argparse
import numpy as np
from kora.studio import StudioRecipe,decode,render,resize_float,encode
changes={
'exposure':{'exposure':1},'wb':{'wb':'auto'},'kelvin':{'wb':'kelvin','kelvin':3200},
'wb_red':{'wb_red':9},'wb_blue':{'wb_blue':-9},'dynamic_range':{'dynamic_range':400},
'dr_priority':{'dr_priority':'strong'},'highlights':{'highlights':4},'shadows':{'shadows':4},
'color':{'color':4},'sharpness':{'sharpness':4},'clarity':{'clarity':-5},'noise_reduction':{'noise_reduction':4},
'grain':{'grain':'strong'},'grain_size':{'grain':'strong','grain_size':'large'},
'color_chrome':{'color_chrome':'strong'},'fx_blue':{'fx_blue':'strong'},
'mono_filter':{'film':'acros','mono_filter':'red'},'mono_warm':{'film':'acros','mono_warm':18},'mono_green':{'film':'acros','mono_green':18},
'smooth_skin':{'smooth_skin':'strong'},'image_size':{'image_size':'S'},'aspect':{'aspect':'1:1'},'digital_crop':{'digital_crop':2}}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('photos',type=Path,nargs='+')
paths=parser.parse_args().photos
rows=[]
for source in paths:
 a=resize_float(decode(Path(source)),600)
 for key,setting in changes.items():
  base={'film':'acros'} if key.startswith('mono_') else {'grain':'strong'} if key=='grain_size' else {}
  before=render(a,StudioRecipe(**base));after=render(a,StudioRecipe(**setting))
  difference=float(abs(after-before).mean()) if before.shape==after.shape else None
  rows.append({'source':Path(source).name,'control':key,'setting':setting,'mean_absolute_change':difference,'shape':list(after.shape),'changes_pixels_or_size':difference>1e-8 if difference is not None else True})
 for key,setting in {'file_type':{'file_type':'tiff16'},'image_quality':{'image_quality':'normal'},'color_space':{'color_space':'adobe_rgb'}}.items():
  base=render(a,StudioRecipe());original=encode(base,StudioRecipe())[0];data,mime=encode(base,StudioRecipe(**setting))
  rows.append({'source':Path(source).name,'control':key,'changes_export_bytes':data!=original,'mime':mime})
p=Path('outputs/parameter-audit');p.mkdir(exist_ok=True);(p/'operational-coverage.json').write_text(json.dumps(rows,indent=2))
print(len(rows),'checks; no-response:',[r for r in rows if r.get('changes_pixels_or_size') is False or r.get('changes_export_bytes') is False])
