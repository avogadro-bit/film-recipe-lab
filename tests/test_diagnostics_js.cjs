const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../kora/static/diagnostics.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(available=true){
 const store=new Map(),events={},sent=[];
 const state={available};
 const sandbox={URLSearchParams,AbortSignal,location:{hash:'#session=private-key'},navigator:{onLine:true},
  sessionStorage:{getItem:()=>null},localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},
  addEventListener:(k,v)=>events[k]=v,setInterval:()=>0,
  fetch:async(url,options)=>{if(!state.available)throw new Error('offline');sent.push(JSON.parse(options.body));return {ok:true};}};
 sandbox.window=sandbox;vm.runInNewContext(source,sandbox);
 return {sandbox,events,sent,store,state};
}
test('reports errors, removes secrets and ignores normal cancellation',async()=>{
 const s=setup();s.sandbox.reportError(new Error('private-key /private/diagnostic-fixture/image.DNG'),'zoom',{zoom:4,recipe:{secret:true}});
 await tick();assert.equal(s.sent.length,1);assert.equal(s.sent[0].context.zoom,4);
 assert.ok(s.sent[0].context.client_time);assert.ok(!JSON.stringify(s.sent).includes('private-key'));
 assert.ok(!JSON.stringify(s.sent).includes('image.DNG'));assert.ok(!JSON.stringify(s.sent).includes('recipe'));
 s.sandbox.reportError({name:'AbortError',message:'obsolete'});await tick();assert.equal(s.sent.length,1);
});
test('offline queue persists and is retried on reconnection',async()=>{
 const s=setup(false);s.events.unhandledrejection({reason:new Error('offline test')});await tick();
 assert.equal(JSON.parse(s.store.get('film-pending-errors')).length,1);
 s.state.available=true;await s.events.online();assert.equal(s.sent.length,1);
 assert.deepEqual(JSON.parse(s.store.get('film-pending-errors')),[]);
});
test('duplicate error objects are sent once and pending queue is bounded',async()=>{
 const s=setup(false),error=new Error('one');s.sandbox.reportError(error);s.sandbox.reportError(error);await tick();
 assert.equal(JSON.parse(s.store.get('film-pending-errors')).length,1);
 for(let i=0;i<100;i++)s.sandbox.reportError(new Error(String(i)));
 assert.equal(JSON.parse(s.store.get('film-pending-errors')).length,40);
});
