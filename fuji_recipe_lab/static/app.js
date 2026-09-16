"use strict";
const $ = s => document.querySelector(s);
const session = new URLSearchParams(location.hash.slice(1)).get("session") || sessionStorage.getItem("film-session") || sessionStorage.getItem("fuji-session") || "";
sessionStorage.setItem("film-session", session); history.replaceState(null, "", "/");
let files = [], selected = null, filter = "all", defaults, recipe, selectionVersion = 0, toastTimer;
const selectedIds = new Set(), recipesById = new Map();
let rawExtensions = new Set([".raf", ".dng"]);
const pictures = new Map();
const embeddedPictures = new Map();
const thumbnailPictures = new Map(), thumbnailRequests = new Set();
let thumbnailQueue=[],thumbnailWorkers=0,thumbnailTimer;
let shootingSettings=null, opticsInfo=null;
let engineState=null;
let undoStack=[],future=[],copiedSettings=null;
let renderRevision=0, renderTimer, renderBusy=false, renderAgain=false, renderURL, beforeURL, comparing=false, currentRenderQuality=null, renderController=null;
let fullWidth=0,fullHeight=0,tileTimer,tileGeneration=0,tileLoading=0;
const tileControllers=new Set(),tileURLs=new Map();
const films = [
 ["provia","PROVIA / Standard","Balanced color for everyday photography."], ["velvia","Velvia / Vivid","A vivid palette with deep color."],
 ["astia","ASTIA / Soft","Delicate color and soft tonality."], ["classic_chrome","Classic Chrome","A restrained palette with a documentary character."],
 ["classic_negative","Classic Negative","Official Classic Negative LUT · GFX ETERNA 55."], ["pro_neg_std","PRO Neg. Std","Measured contrast for portraits."],
 ["pro_neg_hi","PRO Neg. Hi","Higher-contrast portrait color."], ["eterna","ETERNA / Cinema","A soft palette inspired by cinema."],
 ["eterna_bleach","ETERNA Bleach Bypass","Strong contrast and muted color."], ["nostalgic_negative","Nostalgic Negative","Warm tones with a nostalgic character."],
 ["reala_ace","REALA ACE","Natural color with clear tonal separation."], ["acros","ACROS","Silver-halide-inspired black and white tonality."],
 ["monochrome","Monochrome","A classic black and white rendering."], ["sepia","Sepia","Brown-toned monochrome."]
];
const officialFilms = new Set(["provia","velvia","astia","classic_chrome","classic_negative","pro_neg_std","eterna","eterna_bleach","reala_ace","acros"]);
const wb = [["camera","As Shot"],["auto","Auto"],["auto_white","Auto White Priority"],["auto_ambience","Auto Ambience Priority"],["daylight","Daylight"],["shade","Shade"],["tungsten","Tungsten"],["fluorescent1","Fluorescent 1"],["fluorescent2","Fluorescent 2"],["fluorescent3","Fluorescent 3"],["underwater","Underwater"],["kelvin","Color Temperature"]];
const effect = [["off","Off"],["weak","Weak"],["strong","Strong"]];
function element(tag, text, className) { const e = document.createElement(tag); if(text !== undefined) e.textContent = text; if(className)e.className=className; return e; }
function toast(text) { clearTimeout(toastTimer); $("#toast").textContent=text; $("#toast").hidden=false; toastTimer=setTimeout(()=>$("#toast").hidden=true,4500); }
let activityRequests=0,activityShowTimer,activityHideTimer,activityVisibleAt=0;
function beginActivity(){
 activityRequests++;clearTimeout(activityHideTimer);if(activityRequests!==1)return;clearTimeout(activityShowTimer);activityShowTimer=setTimeout(()=>{if(!activityRequests)return;const bar=$("#activity-bar");bar.hidden=false;bar.setAttribute("aria-valuetext","Processing");activityVisibleAt=performance.now();},90);
}
function endActivity(){
 activityRequests=Math.max(0,activityRequests-1);if(activityRequests)return;clearTimeout(activityShowTimer);const bar=$("#activity-bar");if(bar.hidden)return;const wait=Math.max(0,180-(performance.now()-activityVisibleAt));activityHideTimer=setTimeout(()=>{if(activityRequests)return;bar.hidden=true;bar.setAttribute("aria-valuetext","Idle");},wait);
}
async function api(path, options={}) {
 beginActivity();
 try{const response = await fetch(path, {...options, headers:{"X-Fuji-Session":session,...options.headers}});
  if(!response.ok){const value=await response.json();throw new Error(value.error||"Request failed");}
  const type=response.headers.get("content-type")||"";
  return type.startsWith("image/")||type.startsWith("application/zip") ? response.blob() : response.json();
 }finally{endActivity();}
}
function section(name) { const e=element("section",undefined,"control-section");e.append(element("h3",name));$("#controls").append(e);return e; }
function select(parent, label, key, choices) {const l=element("label",label),s=element("select");s.dataset.key=key;for(const [v,t] of choices){const o=element("option",t);o.value=v;s.append(o);}l.append(s);parent.append(l);}
function slider(parent,label,key,min,max,step=1) {const row=element("div",undefined,"range-row"),l=element("label",label),o=element("output"),i=element("input");i.type="range";i.min=min;i.max=max;i.step=step;i.dataset.key=key;i.id="control-"+key;l.htmlFor=i.id;o.dataset.output=key;l.append(o);row.append(l,i);parent.append(row);}
function setupWBGrid(parent){
 const wrap=element("div",undefined,"wb-grid-wrap"),title=element("div","WHITE BALANCE SHIFT","wb-grid-title");
 const canvas=element("canvas");canvas.id="wb-grid";canvas.width=380;canvas.height=380;canvas.tabIndex=0;canvas.setAttribute("role","group");canvas.setAttribute("aria-label","White balance grid. Left and right arrows adjust red. Up and down arrows adjust blue. Home centers the marker.");
 const readout=element("output");readout.id="wb-grid-value";readout.setAttribute("aria-live","polite");
 const reset=element("button","Center R/B");reset.type="button";reset.id="wb-grid-reset";
 const foot=element("div",undefined,"wb-grid-footer");foot.append(readout,reset);
 wrap.append(title,element("small","Blue + ↑ · Red + → · range −9 to +9"),canvas,foot,element("small","Click or drag the marker. Use the arrow keys for precise adjustment."));parent.append(wrap);
 let dragging=false,saved=false;
 function setShift(red,blue,record=true){
  if(!recipe)return;
  red=Math.max(-9,Math.min(9,Math.round(red)));blue=Math.max(-9,Math.min(9,Math.round(blue)));
  if(red===recipe.wb_red&&blue===recipe.wb_blue)return;
  if(record)recordUndo();
  applyPatchToSelection({wb_red:red,wb_blue:blue});populate();persist();scheduleRender();
 }
 function move(e){const box=canvas.getBoundingClientRect();const x=(e.clientX-box.left)/box.width,y=(e.clientY-box.top)/box.height;
  const red=Math.max(-9,Math.min(9,Math.round((x*380-20)/340*18-9))),blue=Math.max(-9,Math.min(9,Math.round(9-(y*380-20)/340*18)));
  if(red!==recipe?.wb_red||blue!==recipe?.wb_blue){setShift(red,blue,!saved);saved=true;}}
 canvas.onpointerdown=e=>{if(e.button!==0||!recipe)return;e.preventDefault();canvas.focus();dragging=true;saved=false;canvas.setPointerCapture(e.pointerId);move(e);};
 canvas.onpointermove=e=>{if(dragging)move(e);};
 canvas.onpointerup=e=>{if(dragging)move(e);dragging=false;};canvas.onpointercancel=()=>{dragging=false;};canvas.onlostpointercapture=()=>{dragging=false;};
 canvas.onkeydown=e=>{const steps={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]};if(e.key==="Home"){e.preventDefault();e.stopPropagation();setShift(0,0);}else if(steps[e.key]&&recipe){e.preventDefault();e.stopPropagation();const [r,b]=steps[e.key];setShift(recipe.wb_red+r,recipe.wb_blue+b);}};
 reset.onclick=()=>setShift(0,0);
}
function drawWBGrid(){
 const canvas=$("#wb-grid");if(!canvas||!recipe)return;const ctx=canvas.getContext("2d");ctx.fillStyle="#161b1c";ctx.fillRect(0,0,380,380);
 for(let b=-9;b<=9;b++)for(let r=-9;r<=9;r++){ctx.fillStyle=`rgb(${145+r*9},145,${145+b*9})`;ctx.beginPath();ctx.arc(20+(r+9)/18*340,20+(9-b)/18*340,3.1,0,Math.PI*2);ctx.fill();}
 ctx.strokeStyle="#ffffff70";ctx.lineWidth=1;ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(190,10);ctx.lineTo(190,370);ctx.moveTo(10,190);ctx.lineTo(370,190);ctx.stroke();ctx.setLineDash([]);
 const x=20+(recipe.wb_red+9)/18*340,y=20+(9-recipe.wb_blue)/18*340;
 ctx.strokeStyle="#000";ctx.lineWidth=7;ctx.strokeRect(x-7,y-7,14,14);ctx.strokeStyle="#fff";ctx.lineWidth=3;ctx.strokeRect(x-7,y-7,14,14);
 const sign=n=>n>0?"+"+n:String(n);$("#wb-grid-value").textContent=`R : ${sign(recipe.wb_red)}   B : ${sign(recipe.wb_blue)}`;
 canvas.setAttribute("aria-description",`Red ${recipe.wb_red}, Blue ${recipe.wb_blue}`);
}
function setupControls(){
 for(const [v,t] of films){const o=element("option",t+(officialFilms.has(v)?" · Fuji LUT":" · interpretation"));o.value=v;$("#film").append(o);}
 let s=section("LIGHT & CONTRAST");select(s,"Dynamic Range","dynamic_range",[[100,"DR100"],[200,"DR200"],[400,"DR400"]]);select(s,"D Range Priority","dr_priority",[["off","Off"],["auto","Auto"],["weak","Weak"],["strong","Strong"]]);select(s,"Push / Pull · EV","exposure",Array.from({length:19},(_,i)=>{const v=Number(((i-9)/3).toFixed(6));return [v,(v>0?"+":"")+v.toFixed(2)];}));slider(s,"Highlights","highlights",-100,100);slider(s,"Whites","whites",-100,100);slider(s,"Shadows","shadows",-100,100);slider(s,"Blacks","blacks",-100,100);
 s=section("WHITE BALANCE");select(s,"Mode","wb",wb);slider(s,"Color Temperature · K","kelvin",2500,10000,10);slider(s,"Red Shift","wb_red",-9,9);slider(s,"Blue Shift","wb_blue",-9,9);setupWBGrid(s);
 s=section("COLOR & DETAIL");slider(s,"Color","color",-4,4);slider(s,"Sharpness","sharpness",-4,4);slider(s,"Clarity","clarity",-5,5);slider(s,"Noise Reduction","noise_reduction",-4,4);
 s=section("TEXTURE & EFFECTS");const grid=element("div",undefined,"select-grid");s.append(grid);select(grid,"Grain Effect","grain",effect);select(grid,"Grain Size","grain_size",[["small","Small"],["large","Large"]]);select(grid,"Color Chrome Effect","color_chrome",effect);select(grid,"Color Chrome FX Blue","fx_blue",effect);select(s,"Monochromatic Filter","mono_filter",[["none","None"],["yellow","Yellow"],["red","Red"],["green","Green"]]);
 slider(s,"Monochromatic Color · warm / cool","mono_warm",-18,18);slider(s,"Monochromatic Color · green / magenta","mono_green",-18,18);
 select(s,"Smooth Skin Effect","smooth_skin",effect);
 s=section("LENS CORRECTIONS");select(s,"Lens Distortion","lens_distortion",[["off","Off"],["auto","Automatic Profile"]]);select(s,"Lens Vignetting","lens_vignetting",[["off","Off"],["auto","Automatic Profile"]]);const opticalNote=element("p","Choose a photo to identify its lens.");opticalNote.id="optics-status";opticalNote.setAttribute("role","status");s.append(opticalNote);
 s=section("CROP & OUTPUT");select(s,"File Type","file_type",[["jpeg","JPEG"],["tiff8","TIFF · 8-bit"],["tiff16","TIFF · 16-bit"]]);
 select(s,"Image Size","image_size",[["L","L · full developed resolution"],["M","M · 50% of the pixels"],["S","S · 25% of the pixels"]]);
 select(s,"Image Aspect","aspect",[["original","Original"],["3:2","3:2"],["16:9","16:9"],["1:1","1:1"],["4:3","4:3"]]);
 select(s,"JPEG Quality","image_quality",[["fine","Fine"],["normal","Normal"]]);
 select(s,"Export Color Space","color_space",[["srgb","sRGB"],["adobe_rgb","Adobe RGB (1998)"]]);
 select(s,"Digital Teleconverter · crop without super-resolution","digital_crop",[[1,"Off"],[1.4,"1.4×"],[2,"2×"]]);
 select(s,"Fuji Lens Modulation Optimizer · unavailable","lens_optimizer",[["off","Off"]]);
 select(s,"Multi-exposure HDR · unavailable","hdr",[["off","Off"]]);
 for(const key of ["lens_optimizer","hdr"])document.querySelector(`[data-key="${key}"]`).disabled=true;

}
function populate(){
 drawWBGrid();updateOpticsStatus();
 for(const input of document.querySelectorAll("[data-key]")){input.value=recipe[input.dataset.key] ?? defaults[input.dataset.key];const out=document.querySelector(`[data-output="${input.dataset.key}"]`);if(out)out.textContent=Number(input.value)>0&&input.dataset.key!=="kelvin"?"+"+input.value:input.value;}
 $("#film-description").textContent=officialFilms.has(recipe.film)?"Official Fujifilm LUT · GFX ETERNA 55 · uncalibrated photo adaptation.":"Independent interpretation · this film has no LUT in the official pack.";
 const unsupported=recipe.target_model==="X-T4"&&["reala_ace","nostalgic_negative"].includes(recipe.film);
 $("#validation-note").textContent=unsupported?"This simulation is unavailable on the X-T4.":"";
 $("#control-kelvin").disabled=recipe.wb!=="kelvin";
 const mono=["acros","monochrome","sepia"].includes(recipe.film);
 for(const key of ["mono_filter","mono_warm","mono_green"])document.querySelector(`[data-key="${key}"]`).disabled=!mono;
 document.querySelector('[data-key="image_quality"]').disabled=recipe.file_type!=="jpeg";
 for(const key of ["dynamic_range","highlights","whites","shadows","blacks"])document.querySelector(`[data-key="${key}"]`).disabled=recipe.dr_priority!=="off";
}
function selectedTargets(){return selectedIds.size?[...selectedIds]:(selected?[selected.id]:[]);}
function syncActiveRecipe(){if(selected&&recipe)recipesById.set(selected.id,structuredClone(recipe));}
function ensureRecipe(id,seed=recipe||defaults){if(!recipesById.has(id))recipesById.set(id,structuredClone(seed));return recipesById.get(id);}
function snapshotRecipes(ids=selectedTargets()){return ids.map(id=>[id,structuredClone(ensureRecipe(id))]);}
function recordUndo(){undoStack.push(snapshotRecipes());if(undoStack.length>100)undoStack.shift();future=[];}
function restoreSnapshot(snapshot){const current=snapshotRecipes(snapshot.map(([id])=>id));for(const [id,value] of snapshot)recipesById.set(id,structuredClone(value));if(selected)recipe=structuredClone(ensureRecipe(selected.id));return current;}
function applyPatchToSelection(patch){for(const id of selectedTargets())recipesById.set(id,{...ensureRecipe(id),...structuredClone(patch)});if(selected)recipe=structuredClone(ensureRecipe(selected.id));}
function applyFullToSelection(value){const next={...defaults,...structuredClone(value)};for(const id of selectedTargets())recipesById.set(id,structuredClone(next));if(selected)recipe=structuredClone(ensureRecipe(selected.id));else recipe=next;}
function exportLabel(){const count=selectedIds.size;return count>1?`Export ${count} JPEGs`:"Export Image";}
function updateSelectionState(){
 const count=selectedIds.size,label=count?`${count} photo${count===1?"":"s"} selected`:"No photo selected";
 $("#selection-state").textContent=count>1?label+" · adjustments are linked":count===1?"1 photo selected · individual editing":label;
 $("#selection-clear").disabled=count<=1;
 if(!$("#export-image").disabled)$("#export-image").textContent=exportLabel();
}
function persist(){syncActiveRecipe();$("#recipe-state").textContent=selectedIds.size>1?`Recipe updated on ${selectedIds.size} photos`:"Recipe updated";updateSelectionState();}
function visibleFiles(){const term=$("#search").value.toLowerCase();return files.filter(f=>(filter==="all"||f.format===filter||(filter==="OTHER"&&!["RAF","DNG"].includes(f.format)))&&f.name.toLowerCase().includes(term));}
function queueThumbnail(f){
 if(!f.local||pictures.has(f.id)||thumbnailPictures.has(f.id)||thumbnailRequests.has(f.id))return;
 thumbnailRequests.add(f.id);thumbnailQueue.push(f);clearTimeout(thumbnailTimer);thumbnailTimer=setTimeout(drainThumbnailQueue,180);
}
function drainThumbnailQueue(){
 while(thumbnailWorkers<2&&thumbnailQueue.length){const f=thumbnailQueue.shift();thumbnailWorkers++;
  api("/api/thumbnail/"+f.id).then(blob=>{const url=URL.createObjectURL(blob);thumbnailPictures.set(f.id,url);while(thumbnailPictures.size>96){const key=thumbnailPictures.keys().next().value;URL.revokeObjectURL(thumbnailPictures.get(key));thumbnailPictures.delete(key);}for(const image of document.querySelectorAll(`img[data-photo-id="${f.id}"]`)){image.src=url;image.hidden=false;image.previousElementSibling.hidden=true;}}).catch(()=>{}).finally(()=>{thumbnailRequests.delete(f.id);thumbnailWorkers--;drainThumbnailQueue();});
 }
}
function drawLibrary(){
 const visible=visibleFiles();$("#count").textContent=files.length;$("#file-list").replaceChildren();$("#filmstrip").replaceChildren();
 if(!visible.length)$("#file-list").append(element("p",files.length?"No files match this filter.":"Choose a photo folder.","no-files"));
 for(const f of visible){const b=element("button",undefined,"file-row"+(f.id===selected?.id?" selected":"")+(selectedIds.has(f.id)?" batch-selected":""));b.title=f.path;b.setAttribute("aria-label","Open "+f.name);const icon=element("span",f.format,"file-icon"),t=element("span",undefined,"file-text");t.append(element("strong",f.name),element("small",f.local?`${(f.bytes/1048576).toFixed(1)} MB · ${f.group}`:"iCloud · download required"));b.append(icon,t);b.onclick=()=>openPhoto(f);$("#file-list").append(b);}
 const index=Math.max(0,visible.findIndex(f=>f.id===selected?.id));for(const f of visible.slice(Math.max(0,index-8),Math.max(0,index-8)+24)){
  const entry=element("div",undefined,"strip-entry"+(selectedIds.has(f.id)?" batch-selected":""));
  const b=element("button",undefined,"strip-item"+(f.id===selected?.id?" selected":""));b.title=f.name;b.setAttribute("aria-label", "Open "+f.name);
  const visual=element("span",undefined,"strip-visual"),placeholder=element("span",f.format,"strip-placeholder"),im=element("img");im.alt="Thumbnail of "+f.name;im.dataset.photoId=f.id;const source=pictures.get(f.id)||thumbnailPictures.get(f.id);if(source){im.src=source;placeholder.hidden=true;}else{im.hidden=true;queueThumbnail(f);}visual.append(placeholder,im);if(f.id===selected?.id)visual.append(element("span","VIEWING","strip-active-badge"));
  const caption=element("span",undefined,"strip-caption");caption.append(element("strong",f.name),element("small",f.format));b.append(visual,caption);
  b.onclick=()=>openPhoto(f,selectedIds.size>1&&selectedIds.has(f.id));
  const check=element("button",selectedIds.has(f.id)?"✓":"","strip-select");check.type="button";check.title=selectedIds.has(f.id)?"Remove from editing group":"Include in editing group";check.setAttribute("aria-label",check.title+": "+f.name);check.setAttribute("aria-pressed",String(selectedIds.has(f.id)));check.onclick=e=>{e.stopPropagation();toggleSelected(f);};
  entry.append(b,check);$("#filmstrip").append(entry);
 }
 updateSelectionState();
}
function toggleSelected(f){
 syncActiveRecipe();undoStack=[];future=[];
 if(selectedIds.has(f.id)){
  if(selectedIds.size===1)return toast("Keep at least one photo selected.");
  selectedIds.delete(f.id);
  if(selected?.id===f.id){const next=files.find(item=>selectedIds.has(item.id));return openPhoto(next,true);}
 }else{selectedIds.add(f.id);ensureRecipe(f.id,recipe);}
 drawLibrary();toast(selectedIds.size>1?`${selectedIds.size} photos selected. New adjustments will apply to the group.`:"Individual editing restored.");
}
$("#selection-clear").onclick=()=>{if(!selected)return;selectedIds.clear();selectedIds.add(selected.id);undoStack=[];future=[];drawLibrary();toast("Group cleared. Adjustments now apply only to the photo being viewed.");};
async function openPhoto(f,preserveSelection=false){
 syncActiveRecipe();
 if(!preserveSelection){selectedIds.clear();selectedIds.add(f.id);undoStack=[];future=[];}else if(!selectedIds.has(f.id)){selectedIds.add(f.id);}
 ensureRecipe(f.id,recipe||defaults);recipe=structuredClone(ensureRecipe(f.id));
 opticsInfo=null;shootingSettings=null;currentRenderQuality=null;fullWidth=fullHeight=0;clearDetailTiles(true);$("#shooting").disabled=true;const version=++selectionVersion;renderRevision++;comparing=false;beforeURL && URL.revokeObjectURL(beforeURL);beforeURL=null;selected=f;$("#export-image").disabled=true;$("#compare").disabled=true;populate();drawLibrary();$("#filename").textContent=f.name;$("#file-subtitle").textContent=f.format+" · "+f.group;$("#preview").hidden=true;$("#empty").hidden=true;$("#loading").hidden=false;$("#zoom").disabled=true;resetView();$("#recipe-state").textContent=selectedIds.size>1?`Editing ${selectedIds.size} selected photos`:"Photo recipe restored";$("#preview-kind").textContent="Opening…";
 try{
  const info=await api("/api/photo/"+f.id);if(version!==selectionVersion)return;
  fullWidth=info.developed_size?.width||info.sizes.width;fullHeight=info.developed_size?.height||info.sizes.height;opticsInfo=info.optics;updateOpticsStatus();shootingSettings=info.shooting_settings;$("#shooting").disabled=!shootingSettings;const x=info.exif;$("#file-subtitle").textContent=[x.Model||f.format, `Developed ${fullWidth} × ${fullHeight}`, info.source_exposure?.ev ? `Base${info.source_exposure.reference_matched?" estimated":""} ${info.source_exposure.ev>0?"+":""}${info.source_exposure.ev.toFixed(2)} EV` : null].filter(Boolean).join(" · ");
  $("#photo-info").textContent=[x.Model,info.input_normalization?.label,x.FNumber?"ƒ/"+x.FNumber:null,x.ExposureTime?x.ExposureTime+" s":null,x.ISO?"ISO "+x.ISO:null].filter(Boolean).join("   ·   ")||"File metadata";
  if(info.preview_available){if(!embeddedPictures.has(f.id)){const blob=await api("/api/preview/"+f.id);if(version!==selectionVersion)return;embeddedPictures.set(f.id,URL.createObjectURL(blob));while(embeddedPictures.size>32){const key=embeddedPictures.keys().next().value;URL.revokeObjectURL(embeddedPictures.get(key));embeddedPictures.delete(key);}}if(version!==selectionVersion)return;$("#preview").src=embeddedPictures.get(f.id);$("#preview").hidden=false;$("#zoom").disabled=false;$("#preview-kind").textContent="EMBEDDED PREVIEW · recipe not applied";drawLibrary();}
  else{$("#preview-kind").textContent="Developing RAW…";}
  scheduleRender(0);
 }catch(e){if(version===selectionVersion){toast(e.message);$("#preview-kind").textContent=e.message;$("#photo-info").textContent="This file could not be opened.";}}
 finally{if(version===selectionVersion)$("#loading").hidden=true;}
}
function applySettings(value){recordUndo();applyFullToSelection(value);populate();persist();scheduleRender(0);}
$("#shooting").onclick=()=>{if(shootingSettings){applySettings(shootingSettings);toast("Recognized EXIF settings applied. White balance was already included during decoding; import is partial.");}};
$("#undo").onclick=()=>{if(!undoStack.length)return;future.push(restoreSnapshot(undoStack.pop()));populate();persist();scheduleRender(0);};
$("#redo").onclick=()=>{if(!future.length)return;undoStack.push(restoreSnapshot(future.pop()));populate();persist();scheduleRender(0);};
$("#copy-settings").onclick=()=>{copiedSettings=structuredClone(recipe);toast("Settings copied.");};
$("#paste-settings").onclick=()=>{if(copiedSettings)applySettings(copiedSettings);else toast("Copy settings first.");};
$("#store-preset").onclick=()=>{try{localStorage.setItem("film-studio-"+$("#preset-slot").value,JSON.stringify(recipe));toast("Recipe saved to "+$("#preset-slot").value);}catch(e){toast("Local storage is unavailable. Save the recipe as JSON instead.");}};
$("#recall-preset").onclick=async()=>{try{const slot=$("#preset-slot").value,body=localStorage.getItem("film-studio-"+slot)||localStorage.getItem("fuji-studio-"+slot);if(!body)return toast("This slot is empty.");const result=await api("/api/recipe",{method:"POST",headers:{"Content-Type":"application/json"},body});applySettings(result.recipe);}catch(e){toast(e.message);}};
function scheduleRender(delay=70){
 if(beforeURL)URL.revokeObjectURL(beforeURL);beforeURL=null;
 renderRevision++;currentRenderQuality=null;comparing=false;clearDetailTiles(true); $("#compare").textContent="View Without Film";
 $("#export-image").disabled=true;$("#compare").disabled=true;$("#recipe-state").textContent="Settings pending…";
 clearTimeout(renderTimer);
 renderTimer=setTimeout(queueRender,delay);
}
function queueRender(){
 if(!selected)return;
 if(renderBusy){
  renderAgain=true;renderController?.abort();
  return;
 }
 updateRender();
}
async function updateRender(){
 if(!selected)return;
 renderBusy=true;renderAgain=false;
 const controller=new AbortController();renderController=controller;
 const revision=renderRevision,id=selected.id,settings=structuredClone(recipe);
 const showOverlay=photo.hidden;$("#loading").hidden=!showOverlay;$("#loading").textContent="Updating preview…";
 $("#recipe-state").textContent="Updating screen preview…";
 try{
  const blob=await api("/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,recipe:settings,quality:"interactive"}),signal:controller.signal});
  if(revision!==renderRevision||id!==selected?.id)return;
  if(renderURL)URL.revokeObjectURL(renderURL);renderURL=URL.createObjectURL(blob);
  $("#preview").src=renderURL;$("#preview").hidden=false;$("#zoom").disabled=false;
 currentRenderQuality="interactive";
 $("#preview-kind").textContent="SCREEN-QUALITY PREVIEW · "+(officialFilms.has(settings.film)?"FUJIFILM LUT · ":"INTERPRETATION · ")+(films.find(f=>f[0]===settings.film)?.[1]||settings.film);
  $("#recipe-state").textContent="Recipe applied";
  if(pictures.has(id))URL.revokeObjectURL(pictures.get(id));pictures.set(id,URL.createObjectURL(blob));while(pictures.size>32){const key=pictures.keys().next().value;URL.revokeObjectURL(pictures.get(key));pictures.delete(key);}drawLibrary();
  $("#export-image").disabled=false;$("#compare").disabled=false;updateSelectionState();
  scheduleTileRefresh(0);
 }catch(e){if(e.name!=="AbortError"&&revision===renderRevision){toast(e.message);$("#recipe-state").textContent="Render failed · previous preview";}}
 finally{if(renderController===controller)renderController=null;renderBusy=false;$("#loading").hidden=true;if(renderAgain||revision!==renderRevision){renderAgain=false;queueRender();}}
}
$("#compare").onclick=async()=>{
 if(!selected||!renderURL)return;
 const id=selected.id,rev=renderRevision;
 try{
  if(!beforeURL){const b=await api("/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,recipe:{...defaults,lens_distortion:recipe.lens_distortion,lens_vignetting:recipe.lens_vignetting},neutral:true,quality:currentRenderQuality||"interactive"})});if(id!==selected?.id||rev!==renderRevision)return;beforeURL=URL.createObjectURL(b);}
  comparing=!comparing;$("#preview").src=comparing?beforeURL:renderURL;
  if(comparing)clearDetailTiles(false);else scheduleTileRefresh(0);
  $("#compare").textContent=comparing?"View Recipe":"View Without Film";
  $("#preview-kind").textContent=comparing?"RAW BASE · no film simulation or recipe settings":(officialFilms.has(recipe.film)?"AFTER · official Fujifilm LUT":"AFTER · independent interpretation");
 }catch(e){toast(e.message);}
};
$("#export-image").onclick=async()=>{
 if(!selected)return;syncActiveRecipe();const targets=files.filter(file=>selectedIds.has(file.id));
 $("#export-image").disabled=true;$("#export-image").textContent=targets.length>1?`Exporting ${targets.length} full-resolution JPEGs…`:"Exporting full-resolution image…";
 try{let blob,download,message;if(targets.length>1){const items=targets.map(file=>({id:file.id,recipe:structuredClone(ensureRecipe(file.id))}));if(items.some(item=>item.recipe.file_type!=="jpeg"))throw new Error("Batch export supports JPEG only. Select JPEG in Crop & Output.");blob=await api("/api/export-batch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items})});download=`film-recipe-lab-${targets.length}-photos.zip`;message=`${targets.length} JPEGs exported with their current recipes.`;}else{const settings=structuredClone(recipe);blob=await api("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:selected.id,recipe:settings})});download=selected.name.replace(/\.[^.]+$/,"-")+settings.film+(settings.file_type==="jpeg"?".jpg":".tif");message="Image exported with its current recipe.";}
 const url=URL.createObjectURL(blob),a=element("a");a.href=url;a.download=download;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);toast(message);
 }catch(e){toast(e.message);}finally{$("#export-image").disabled=false;$("#export-image").textContent=exportLabel();}
};

async function importFiles(items){
 const raws=[...items].filter(f=>rawExtensions.has("."+f.name.split(".").pop().toLowerCase()));if(!raws.length)return toast("Choose a compatible RAW file (RAF, DNG, CR3, NEF, ARW…).");let first;
 $("#import").disabled=true;
 for(let i=0;i<raws.length;i++){
  const f=raws[i];$("#import").textContent=`Import ${i+1}/${raws.length}…`;
  try{const added=await api("/api/import?name="+encodeURIComponent(f.name),{method:"POST",body:f,headers:{"Content-Type":"application/octet-stream"}});files.push(added);first ||= added;}catch(e){toast(f.name+" : "+e.message);}
 }
 $("#import").disabled=false;$("#import").textContent="Import Files";drawLibrary();if(first)await openPhoto(first);$("#file-input").value="";
}
$("#import").onclick=()=>$("#file-input").click();$("#file-input").onchange=e=>importFiles(e.target.files);
$("#recipe-form").addEventListener("submit",e=>e.preventDefault());
$("#recipe-form").addEventListener("input",e=>{const key=e.target.dataset.key;if(!key||!recipe)return;recordUndo();applyPatchToSelection({[key]:typeof defaults[key]==="number"?Number(e.target.value):e.target.value});populate();persist();scheduleRender();});
$("#reset").onclick=()=>{applySettings(defaults);toast("Recipe reset to PROVIA defaults.");};
$("#save-recipe").onclick=async()=>{try{const result=await api("/api/recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(recipe)});const url=URL.createObjectURL(new Blob([JSON.stringify(result.recipe,null,2)+"\n"],{type:"application/json"}));const a=element("a");a.href=url;a.download=(recipe.name.replace(/[^\p{L}\p{N}_-]+/gu,"-")||"recipe")+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast("Recipe JSON saved.");}catch(e){toast(e.message);}};
$("#load-recipe").onclick=()=>$("#recipe-input").click();$("#recipe-input").onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>65536)throw new Error("The recipe exceeds 64 KB.");const result=await api("/api/recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:await file.text()});applySettings(result.recipe);toast("Recipe loaded.");}catch(err){toast(err.message);}e.target.value="";};
$("#search").oninput=drawLibrary;for(const b of document.querySelectorAll("[data-filter]"))b.onclick=()=>{filter=b.dataset.filter;for(const x of document.querySelectorAll("[data-filter]"))x.classList.toggle("active",x===b);drawLibrary();};

$("#about").onclick=()=>$("#engine-dialog").showModal();$("#close-dialog").onclick=()=>$("#engine-dialog").close();
function updateLutSetup(engine){
 engineState=engine;const missing=engine?.missing_luts||[],status=$("#lut-status");
 status.classList.toggle("ready",!missing.length);
 status.textContent=missing.length?`${missing.length} of 10 official LUTs are missing.`:"All 10 official LUTs are installed and verified.";
 $("#choose-lut-archive").textContent=missing.length?"2. Choose Downloaded ZIP":"Reinstall from ZIP";
}
$("#setup").onclick=()=>$("#setup-dialog").showModal();
$("#setup-close").onclick=()=>$("#setup-dialog").close();
$("#choose-lut-archive").onclick=()=>$("#lut-input").click();
$("#lut-input").onchange=async()=>{
 const input=$("#lut-input"),archive=input.files[0];if(!archive)return;
 const button=$("#choose-lut-archive"),progress=$("#lut-progress"),error=$("#lut-error");
 button.disabled=true;progress.hidden=false;error.textContent="";$("#lut-status").textContent="Verifying and installing the LUTs…";
 try{
  const result=await api("/api/luts/install?name="+encodeURIComponent(archive.name),{method:"POST",headers:{"Content-Type":"application/zip"},body:archive});
  updateLutSetup(result.engine);toast("Official LUTs installed and verified.");
  if(selected)scheduleRender(0);
 }catch(e){error.textContent=e.message;updateLutSetup(engineState);}
 finally{button.disabled=false;progress.hidden=true;input.value="";}
};
document.addEventListener("keydown",e=>{if(["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName)||$("#engine-dialog").open||$("#folder-dialog").open)return;const list=visibleFiles(),i=list.findIndex(f=>f.id===selected?.id),j=i+(e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0);if(j!==i&&list[j]){e.preventDefault();openPhoto(list[j]);}});
let drags=0;document.addEventListener("dragenter",e=>{if(e.dataTransfer.types.includes("Files")){e.preventDefault();drags++;$("#drop-overlay").hidden=false;}});document.addEventListener("dragleave",()=>{if(--drags<=0)$("#drop-overlay").hidden=true;});document.addEventListener("dragover",e=>e.preventDefault());document.addEventListener("drop",e=>{e.preventDefault();drags=0;$("#drop-overlay").hidden=true;importFiles(e.dataTransfer.files);});
setupControls();
(async()=>{try{const data=await api("/api/library");rawExtensions=new Set(data.engine.raw_extensions||[".raf",".dng"]);$("#file-input").accept=[...rawExtensions].join(",");files=[];defaults=data.recipe;recipe=structuredClone(defaults);populate();drawLibrary();updateLutSetup(data.engine);$("#input-folder").textContent="Choose a folder to begin";if(data.engine.missing_luts?.length)$("#setup-dialog").showModal();}catch(e){toast(e.message);$("#file-subtitle").textContent="Reopen the full link displayed in the terminal.";}})();

// Viewer: a responsive whole-image proxy stays underneath source-resolution
// RAW tiles. At 100% one output pixel equals one screen pixel.
let zoomMode="fit",viewScale=1,panX=0,panY=0,panGesture=null;
const viewport=$("#canvas"),photo=$("#preview"),detailLayer=$("#detail-layer"),TILE_SIZE=512;
function outputGeometry(){
 let w=fullWidth||photo.naturalWidth,h=fullHeight||photo.naturalHeight;if(!w||!h)return {width:0,height:0};
 let cw=Math.floor(w/Number(recipe?.digital_crop||1)),ch=Math.floor(h/Number(recipe?.digital_crop||1));
 if(recipe?.aspect&&recipe.aspect!=="original"){let [rw,rh]=recipe.aspect.split(":").map(Number),ratio=rw/rh;if(h>w)ratio=1/ratio;if(cw/ch>ratio)cw=Math.round(ch*ratio);else ch=Math.round(cw/ratio);}
 const factor={L:1,M:.7071,S:.5}[recipe?.image_size]||1,edge=Math.round(Math.max(cw,ch)*factor);
 if(edge<Math.max(cw,ch)){const maximum=Math.max(cw,ch);cw=Math.max(1,Math.round(cw*edge/maximum));ch=Math.max(1,Math.round(ch*edge/maximum));}
 return {width:cw,height:ch};
}
function fitScale(){const geometry=outputGeometry();return Math.min(viewport.clientWidth/geometry.width,viewport.clientHeight/geometry.height,1);}
function clearDetailTiles(dropCache=false){
 clearTimeout(tileTimer);tileGeneration++;for(const controller of tileControllers)controller.abort();tileControllers.clear();tileLoading=0;detailLayer.replaceChildren();detailLayer.hidden=true;
 if(dropCache){for(const url of tileURLs.values())URL.revokeObjectURL(url);tileURLs.clear();}
}
function addDetailTile(key,x,y,width,height){
 const url=tileURLs.get(key);if(!url)return;const image=element("img");image.src=url;image.alt="";image.dataset.x=x;image.dataset.y=y;image.dataset.width=width;image.dataset.height=height;detailLayer.append(image);layoutDetailTiles(image);
}
function layoutDetailTiles(only){
 const images=only?[only]:detailLayer.querySelectorAll("img");
 for(const image of images){image.style.left=Number(image.dataset.x)*viewScale+"px";image.style.top=Number(image.dataset.y)*viewScale+"px";image.style.width=Number(image.dataset.width)*viewScale+"px";image.style.height=Number(image.dataset.height)*viewScale+"px";}
}
function scheduleTileRefresh(delay=120){
 clearTimeout(tileTimer);
 if(!selected||comparing||zoomMode==="fit"||!fullWidth||!fullHeight){detailLayer.hidden=true;return;}
 if(delay<=0){refreshVisibleTiles();return;}
 tileTimer=setTimeout(refreshVisibleTiles,delay);
}
function detailLevel(){
 const maximum=Math.max(1,Math.min(8,1/viewScale));return 2**Math.floor(Math.log2(maximum));
}
async function refreshVisibleTiles(){
 if(!selected||comparing||zoomMode==="fit")return;
 const geometry=outputGeometry(),displayWidth=geometry.width*viewScale,displayHeight=geometry.height*viewScale;
 const imageLeft=(viewport.clientWidth-displayWidth)/2+panX,imageTop=(viewport.clientHeight-displayHeight)/2+panY;
 const x0=Math.max(0,Math.floor((-imageLeft)/viewScale)),y0=Math.max(0,Math.floor((-imageTop)/viewScale));
 const x1=Math.min(geometry.width,Math.ceil((viewport.clientWidth-imageLeft)/viewScale)),y1=Math.min(geometry.height,Math.ceil((viewport.clientHeight-imageTop)/viewScale));
 const tileLevel=detailLevel(),tileSpan=TILE_SIZE*tileLevel;
 const startX=Math.max(0,Math.floor(x0/tileSpan)-1)*tileSpan,startY=Math.max(0,Math.floor(y0/tileSpan)-1)*tileSpan;
 const endX=Math.min(geometry.width,(Math.ceil(x1/tileSpan)+1)*tileSpan),endY=Math.min(geometry.height,(Math.ceil(y1/tileSpan)+1)*tileSpan);
 const generation=++tileGeneration,id=selected.id,revision=renderRevision,settings=structuredClone(recipe),missing=[];
 for(const controller of tileControllers)controller.abort();tileControllers.clear();detailLayer.replaceChildren();detailLayer.hidden=false;
 for(let y=startY;y<endY;y+=tileSpan)for(let x=startX;x<endX;x+=tileSpan){const width=Math.min(tileSpan,geometry.width-x),height=Math.min(tileSpan,geometry.height-y),key=`${id}:${revision}:${tileLevel}:${x}:${y}`;if(tileURLs.has(key))addDetailTile(key,x,y,width,height);else missing.push({x,y,width,height,key});}
 if(!missing.length){$("#preview-kind").textContent="SOURCE-RESOLUTION DETAIL · "+(officialFilms.has(recipe.film)?"FUJIFILM LUT":"INTERPRETATION");return;}
 tileLoading=missing.length;$("#recipe-state").textContent="Loading source detail…";
 async function worker(){
  while(missing.length&&generation===tileGeneration){const tile=missing.shift(),controller=new AbortController();tileControllers.add(controller);
   try{const blob=await api("/api/tile",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id,recipe:settings,x:tile.x,y:tile.y,size:TILE_SIZE,level:tileLevel}),signal:controller.signal});
    if(generation!==tileGeneration||id!==selected?.id){continue;}const url=URL.createObjectURL(blob);tileURLs.set(tile.key,url);while(tileURLs.size>128){const oldest=tileURLs.keys().next().value;URL.revokeObjectURL(tileURLs.get(oldest));tileURLs.delete(oldest);}addDetailTile(tile.key,tile.x,tile.y,tile.width,tile.height);
   }catch(error){if(error.name!=="AbortError"&&generation===tileGeneration)$("#recipe-state").textContent="Source detail unavailable · proxy retained";}
   finally{tileControllers.delete(controller);tileLoading--;}
  }
 }
 await Promise.all(Array.from({length:Math.min(2,missing.length)},worker));
 if(generation===tileGeneration){$("#preview-kind").textContent="SOURCE-RESOLUTION DETAIL · "+(officialFilms.has(recipe.film)?"FUJIFILM LUT":"INTERPRETATION");$("#recipe-state").textContent="Recipe applied · source detail ready";}
}
function updateView(tileDelay=120){
 const ready=!photo.hidden&&photo.naturalWidth>0;
 for(const id of ["zoom","zoom-in","zoom-out"])$("#"+id).disabled=!ready;
 if(!ready)return;
 viewScale=zoomMode==="fit"?fitScale():Number(zoomMode);
 const geometry=outputGeometry(),displayWidth=geometry.width*viewScale,displayHeight=geometry.height*viewScale;
 const maxX=Math.max(0,(displayWidth-viewport.clientWidth)/2),maxY=Math.max(0,(displayHeight-viewport.clientHeight)/2);
 panX=Math.max(-maxX,Math.min(maxX,panX));panY=Math.max(-maxY,Math.min(maxY,panY));
 // Size the bitmap directly instead of transforming its full 60 MP surface.
 // WebKit can rasterize very large transformed JPEGs with a non-uniform
 // backing surface, making a correct 3:2 DNG look vertically compressed.
 photo.style.width=displayWidth+"px";photo.style.height=displayHeight+"px";
 photo.style.transform=`translate(-50%,-50%) translate(${panX}px,${panY}px)`;
 detailLayer.style.width=displayWidth+"px";detailLayer.style.height=displayHeight+"px";detailLayer.style.transform=photo.style.transform;
 layoutDetailTiles();
 viewport.classList.toggle("pannable",maxX>0||maxY>0);
 const select=$("#zoom");select.querySelector('[data-custom]')?.remove();
 const val=zoomMode==="fit"?"fit":String(viewScale);
 if(![...select.options].some(o=>o.value===val)){const o=element("option",Math.round(viewScale*100)+" %");o.value=val;o.dataset.custom="1";select.append(o);}
 select.value=val;
 scheduleTileRefresh(tileDelay);
}
function resetView(){zoomMode="fit";panX=panY=0;updateView(0);}
function changeZoom(value,point){
 if(photo.hidden||!photo.naturalWidth)return;
 if(value==="fit"){resetView();return;}
 const next=Math.max(.1,Math.min(4,Number(value))),box=viewport.getBoundingClientRect();
 const x=point?point.clientX-box.left-viewport.clientWidth/2:0,y=point?point.clientY-box.top-viewport.clientHeight/2:0;
 panX=x-(x-panX)*next/viewScale;panY=y-(y-panY)*next/viewScale;zoomMode=next;updateView(0);
}
photo.addEventListener("load",()=>updateView(0));photo.draggable=false;
$("#zoom").title="At 100%, visible tiles are rendered from the full-resolution RAW.";
$("#zoom").onchange=e=>changeZoom(e.target.value);
$("#zoom-in").onclick=()=>changeZoom(viewScale*1.25);$("#zoom-out").onclick=()=>changeZoom(viewScale/1.25);
viewport.addEventListener("wheel",e=>{if(photo.hidden)return;e.preventDefault();changeZoom(viewScale*Math.exp(-e.deltaY*(e.deltaMode===1?.04:.002)),e);},{passive:false});
viewport.addEventListener("dblclick",e=>{if(!photo.hidden)changeZoom(zoomMode==="fit"?1:"fit",e);});
viewport.addEventListener("pointerdown",e=>{if(e.button!==0||photo.hidden||!viewport.classList.contains("pannable"))return;panGesture={x:e.clientX,y:e.clientY,px:panX,py:panY};viewport.setPointerCapture(e.pointerId);viewport.classList.add("dragging");e.preventDefault();});
viewport.addEventListener("pointermove",e=>{if(!panGesture)return;panX=panGesture.px+e.clientX-panGesture.x;panY=panGesture.py+e.clientY-panGesture.y;updateView();});
for(const event of ["pointerup","pointercancel","lostpointercapture"])viewport.addEventListener(event,()=>{panGesture=null;viewport.classList.remove("dragging");scheduleTileRefresh(0);});
new ResizeObserver(()=>updateView()).observe(viewport);

// Resizable framing around the photograph. Values are local UI preferences;
// double-clicking any separator restores that edge to its default size.
const frameDefaults={left:224,right:326,top:62,bottom:214},workspace=$(".workspace");
let frameLayout={...frameDefaults};
try{const saved=JSON.parse(localStorage.getItem("film-view-layout")||"null");if(saved)for(const key of Object.keys(frameDefaults))if(Number.isFinite(saved[key]))frameLayout[key]=saved[key];}catch(_){}
function frameLimits(key){
 const viewerHeight=$(".viewer").clientHeight||innerHeight;
 if(key==="left")return [120,Math.max(120,Math.min(480,innerWidth-frameLayout.right-340))];
 if(key==="right")return [240,Math.max(240,Math.min(520,innerWidth-frameLayout.left-340))];
 if(key==="top")return [42,Math.max(42,Math.min(140,viewerHeight-frameLayout.bottom-120))];
 return [112,Math.max(112,Math.min(360,viewerHeight-frameLayout.top-120))];
}
function setFrameSize(key,value,save=false){const [minimum,maximum]=frameLimits(key);frameLayout[key]=Math.round(Math.max(minimum,Math.min(maximum,value)));applyFrameLayout();if(save)persistFrameLayout();}
function applyFrameLayout(){
 const desktop=innerWidth>800;
 if(desktop)for(const key of Object.keys(frameDefaults)){const [minimum,maximum]=frameLimits(key);frameLayout[key]=Math.round(Math.max(minimum,Math.min(maximum,frameLayout[key])));}
 for(const key of ["left","right"]){const property="--"+key;if(desktop)workspace.style.setProperty(property,frameLayout[key]+"px");else workspace.style.removeProperty(property);}
 for(const [key,property] of [["top","--viewer-head"],["bottom","--viewer-bottom"]]){if(desktop)workspace.style.setProperty(property,frameLayout[key]+"px");else workspace.style.removeProperty(property);}
 for(const handle of document.querySelectorAll("[data-resize]")){const key=handle.dataset.resize,[minimum,maximum]=frameLimits(key);handle.setAttribute("aria-valuemin",minimum);handle.setAttribute("aria-valuemax",maximum);handle.setAttribute("aria-valuenow",frameLayout[key]);handle.title="Drag to resize · double-click to reset";}
}
function persistFrameLayout(){try{localStorage.setItem("film-view-layout",JSON.stringify(frameLayout));}catch(_){}}
for(const handle of document.querySelectorAll("[data-resize]")){
 const key=handle.dataset.resize;let gesture=null;
 handle.onpointerdown=e=>{if(e.button!==0||innerWidth<=800)return;gesture={x:e.clientX,y:e.clientY,value:frameLayout[key]};handle.setPointerCapture(e.pointerId);handle.classList.add("resizing");document.body.classList.add("layout-resizing");document.body.classList.toggle("vertical",key==="top"||key==="bottom");e.preventDefault();};
 handle.onpointermove=e=>{if(!gesture)return;const dx=e.clientX-gesture.x,dy=e.clientY-gesture.y;setFrameSize(key,gesture.value+(key==="left"?dx:key==="right"?-dx:key==="top"?dy:-dy));};
 const finish=()=>{if(!gesture)return;gesture=null;handle.classList.remove("resizing");document.body.classList.remove("layout-resizing","vertical");persistFrameLayout();scheduleTileRefresh(0);};
 handle.onpointerup=finish;handle.onpointercancel=finish;handle.onlostpointercapture=finish;
 handle.ondblclick=()=>setFrameSize(key,frameDefaults[key],true);
 handle.onkeydown=e=>{const step=e.shiftKey?25:8;let delta=0;if(key==="left")delta=e.key==="ArrowRight"?step:e.key==="ArrowLeft"?-step:0;else if(key==="right")delta=e.key==="ArrowLeft"?step:e.key==="ArrowRight"?-step:0;else if(key==="top")delta=e.key==="ArrowDown"?step:e.key==="ArrowUp"?-step:0;else delta=e.key==="ArrowUp"?step:e.key==="ArrowDown"?-step:0;if(e.key==="Home"){e.preventDefault();setFrameSize(key,frameDefaults[key],true);}else if(delta){e.preventDefault();setFrameSize(key,frameLayout[key]+delta,true);}};
}
addEventListener("resize",applyFrameLayout);applyFrameLayout();
let panels={library:true,editor:true};
try{const saved=JSON.parse(localStorage.getItem("film-view-panels")||localStorage.getItem("fuji-view-panels"));if(saved&&typeof saved.library==="boolean"&&typeof saved.editor==="boolean")panels=saved;}catch(_){}
function updatePanels(){
 for(const side of ["library","editor"]){$("."+side).hidden=!panels[side];$(".workspace").classList.toggle("hide-"+side,!panels[side]);$("#toggle-"+side).setAttribute("aria-pressed",String(panels[side]));}
 $("#focus-view").textContent=!panels.library&&!panels.editor?"Show Panels":"Photo View";
 try{localStorage.setItem("film-view-panels",JSON.stringify(panels));}catch(_){}
}
for(const side of ["library","editor"])$("#toggle-"+side).onclick=()=>{panels[side]=!panels[side];updatePanels();};
$("#focus-view").onclick=()=>{const show=!panels.library&&!panels.editor;panels={library:show,editor:show};updatePanels();};updatePanels();
document.addEventListener("keydown",e=>{if(["INPUT","SELECT","TEXTAREA","BUTTON"].includes(document.activeElement.tagName)||document.activeElement.id==="wb-grid"||$("#folder-dialog").open||$("#engine-dialog").open||$("#setup-dialog").open)return;
 if(e.key==="Tab"){e.preventDefault();$("#focus-view").click();}else if(["+","="].includes(e.key)){e.preventDefault();changeZoom(viewScale*1.25);}else if(e.key==="-"){e.preventDefault();changeZoom(viewScale/1.25);}else if(e.key==="0")resetView();else if(e.key==="1")changeZoom(1);
});
// Local folder browser: no copying of RAW files and no upload of a directory.
let folderPath=null,folderParent=null,folderRevision=0;
async function browseFolder(path){
 const revision=++folderRevision;$("#folder-error").textContent="";$("#folder-select").disabled=true;
 try{const data=await api("/api/folders"+(path?"?path="+encodeURIComponent(path):""));if(revision!==folderRevision)return;
 folderPath=data.path;folderParent=data.parent;$("#folder-path").value=data.path||"";$("#folder-up").disabled=!data.parent;
 $("#folder-shortcuts").replaceChildren();
 for(const item of data.shortcuts||[]){const b=element("button",item.name,"folder-shortcut"+(item.path===data.path?" active":""));b.type="button";b.title=item.path;b.onclick=()=>browseFolder(item.path);$("#folder-shortcuts").append(b);}
 $("#folder-breadcrumbs").replaceChildren();
 for(const [index,item] of (data.breadcrumbs||[]).entries()){if(index)$("#folder-breadcrumbs").append(element("span","›","folder-separator"));const b=element("button",item.name,"folder-crumb");b.type="button";b.title=item.path;b.disabled=index===data.breadcrumbs.length-1;b.onclick=()=>browseFolder(item.path);$("#folder-breadcrumbs").append(b);}
 $("#folder-list").replaceChildren();
 for(const f of data.folders){const b=element("button",undefined,"folder-row");b.type="button";b.title=f.path;b.append(element("span","▰","folder-icon"),element("span",f.name,"folder-name"),element("span","›","folder-open"));b.onclick=()=>browseFolder(f.path);$("#folder-list").append(b);}
 if(!data.folders.length)$("#folder-list").append(element("p","This folder has no subfolders.","no-files"));
 $("#folder-selection-name").textContent=data.name||"None";$("#folder-selection-name").title=data.path||"";
 $("#folder-selection-details").textContent=`${data.raw_count||0} compatible RAW file${data.raw_count===1?"":"s"} directly in this folder`;
 $("#folder-select").disabled=!data.path;
 }catch(e){if(revision===folderRevision)$("#folder-error").textContent=e.message;}
}
function openFolderPicker(){$("#folder-dialog").showModal();browseFolder(folderPath);}
$("#choose-folder").onclick=$("#empty-import").onclick=openFolderPicker;
$("#folder-close").onclick=()=>$("#folder-dialog").close();$("#folder-up").onclick=()=>browseFolder(folderParent);
$("#folder-path-form").onsubmit=e=>{e.preventDefault();browseFolder($("#folder-path").value.trim());};
$("#folder-select").onclick=async()=>{
 if(!folderPath)return;const button=$("#folder-select");button.disabled=true;button.textContent="Reading Folder…";
 try{const data=await api("/api/folder",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:folderPath,recursive:$("#folder-recursive").checked})});
 selectionVersion++;renderRevision++;selected=null;fullWidth=fullHeight=0;clearDetailTiles(true);selectedIds.clear();recipesById.clear();undoStack=[];future=[];files=data.files;filter="all";$("#search").value="";for(const b of document.querySelectorAll("[data-filter]"))b.classList.toggle("active",b.dataset.filter==="all");
 photo.hidden=true;$("#empty").hidden=false;$("#loading").hidden=true;$("#filename").textContent="Choose a photo";$("#file-subtitle").textContent=files.length+" RAW file"+(files.length===1?"":"s")+" in this folder";$("#photo-info").textContent="";$("#preview-kind").textContent="No photo selected";$("#recipe-state").textContent="Recipe retained";
 $("#compare").disabled=$("#export-image").disabled=true;resetView();
 $("#input-folder").textContent=data.folder;$("#input-folder").title=data.folder;$("#folder-dialog").close();drawLibrary();
 if(data.limit_reached)toast("The library is limited to the first 5,000 RAW files in this folder.");
 const first=files.find(f=>f.local);if(first)await openPhoto(first);else if(!files.length)toast("This folder contains no compatible RAW files.");
 }catch(e){$("#folder-error").textContent=e.message;}finally{button.disabled=false;button.textContent="Choose This Folder";}
};

function updateOpticsStatus(){
 const note=$("#optics-status");if(!note)return;
 if(!opticsInfo){note.textContent="Choose a photo to identify its lens.";return;}
 const state=(key,available)=>recipe?.[key]==="auto"?(available?"enabled":"unavailable · not applied"):"off";
 note.textContent=opticsInfo.label+". Distortion: "+state("lens_distortion",opticsInfo.distortion)+". Vignetting: "+state("lens_vignetting",opticsInfo.vignetting)+".";
}
