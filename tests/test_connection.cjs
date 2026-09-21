// Run with node tests/test_connection.cjs. No browser or network required.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('kora/static/app.js','utf8');
const nodes=new Map();
let now=0,response=()=>Promise.reject(new Error('busy'));
const context=vm.createContext({
 $:key=>{if(!nodes.has(key))nodes.set(key,{hidden:true,textContent:''});return nodes.get(key);},
 Date:{now:()=>now},document:{hidden:false,addEventListener(){}},window:{addEventListener(){}},
 session:'test',fetch:()=>response(),AbortSignal:{timeout:()=>null},setInterval(){}
});
vm.runInContext(source.slice(source.indexOf('let healthCheckBusy='),source.indexOf('function section(')),context);
const run=code=>vm.runInContext(code,context);
(async()=>{
 await run('checkConnection()');assert.equal(nodes.get('#connection-status')?.hidden??true,true);
 now=15000;await run('checkConnection()');assert.match(nodes.get('#connection-message').textContent,/slowly/);
 now=31000;await run('checkConnection()');assert.match(nodes.get('#connection-message').textContent,/not responding/);
 response=()=>Promise.resolve({ok:true,status:200});await run('checkConnection()');assert.equal(nodes.get('#connection-status').hidden,true);
 response=()=>Promise.resolve({ok:false,status:403});await run('checkConnection()');assert.match(nodes.get('#connection-message').textContent,/expired/);
 run('connectionHealthy()');
 let reject;response=()=>new Promise((_,r)=>reject=r);
 const pending=run('checkConnection()');now+=1;run('connectionHealthy()');reject(new Error('late timeout'));await pending;
 assert.equal(run('healthFailures'),0);assert.equal(nodes.get('#connection-status').hidden,true);
 assert.equal(typeof nodes.get('#connection-retry').onclick,'function');
 console.log('Connection checks: isolated delay, slow response, repeated failure, recovery, expired session, late timeout passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
