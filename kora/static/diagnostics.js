/* Loaded before app.js so startup/script errors are captured too. Local only. */
(()=>{
 "use strict";
 const storageKey="film-pending-errors",seen=new WeakSet();
 let token="",queue=[],sending=false,budget=0,budgetStart=Date.now();
 try{token=new URLSearchParams(location.hash.slice(1)).get("session")||sessionStorage.getItem("film-session")||"";}catch(_){}
 function clean(value,limit=2000){
  let s=String(value||"");if(token)s=s.split(token).join("[session]");
  return s.replace(/https?:\/\/[^/\s]+\/(app|diagnostics)\.js/g,"$1.js")
   .replace(/https?:\/\/[^\s"'<>]+/g,"[url]")
   .replace(/(?:[A-Za-z]:[\\/]|\/)[^\n\r"'<>]*/g,"[path]").slice(0,limit);
 }
 const keys=new Set(["photo_id","film","grain","grain_size","zoom","pan_x","pan_y","x","y","size","level","generation","revision","request_id","status","width","height","online","source","client_time","client_version"]);
 function context(value){return Object.fromEntries(Object.entries(value||{}).filter(([k,v])=>keys.has(k)&&["string","number","boolean"].includes(typeof v)).map(([k,v])=>[k,typeof v==="string"?clean(v,160):v]));}
 function persist(){try{localStorage.setItem(storageKey,JSON.stringify(queue));}catch(_){} }
 try{const saved=JSON.parse(localStorage.getItem(storageKey)||"[]");if(Array.isArray(saved))queue=saved.slice(-40).filter(e=>e&&typeof e.message==="string").map(e=>({operation:clean(e.operation,80),message:clean(e.message),stack:clean(e.stack,4000),context:context(e.context)}));}catch(_){}
 async function flush(){
  if(sending||!token||!queue.length)return;sending=true;
  try{
   while(queue.length){
    const response=await fetch("/api/diagnostics",{method:"POST",headers:{"X-Fuji-Session":token,"Content-Type":"application/json"},body:JSON.stringify(queue[0]),signal:AbortSignal.timeout(5000)});
    if(!response.ok)break;
    queue.shift();persist();
   }
  }catch(_){}finally{sending=false;}
 }
 window.reportError=(error,operation="interface",extra={})=>{
  if(error?.name==="AbortError")return; // Superseded views are normal cancellations.
  if(error&&typeof error==="object"){if(seen.has(error))return;seen.add(error);}
  if(Date.now()-budgetStart>60000){budget=0;budgetStart=Date.now();}
  if(++budget>60)return;
  let details={};try{details=window.filmDiagnosticContext?.()||{};}catch(_){}
  const entry={operation:clean(operation,80),message:clean(error?.message||error),stack:clean(error?.stack,4000),context:context({...details,...extra,online:navigator.onLine,client_time:new Date().toISOString()})};
  if(queue.length>=40)queue.shift();queue.push(entry);persist();void flush();
 };
 addEventListener("error",event=>{
  if(event.error)reportError(event.error,"uncaught-js");
  else reportError(new Error(event.message||"Resource failed to load"),"resource",{source:event.target?.tagName||"script"});
 },true);
 addEventListener("unhandledrejection",event=>reportError(event.reason,"unhandled-promise"));
 addEventListener("online",flush);setInterval(flush,10000);void flush();
})();
