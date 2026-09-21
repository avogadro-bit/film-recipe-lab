const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../fuji_recipe_lab/static/app.js'),'utf8');
function setup(){
 const menu={children:[],value:'',replaceChildren(){this.children=[];this.value='';},append(o){this.children.push(o);}};
 const context={$:()=>menu,element:(tag,text)=>({tag,text,disabled:false})};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('const films ='),source.indexOf('const wb ='))+source.slice(source.indexOf('function syncFilmChoices('),source.indexOf('function setupControls(')),context);
 return {menu,update:context.syncFilmChoices};
}
test('only ten official LUT simulations are selectable',()=>{
 const {menu,update}=setup();update('classic_negative');
 assert.equal(menu.children.length,10);
 assert.equal(menu.value,'classic_negative');
 for(const retired of ['pro_neg_hi','nostalgic_negative','monochrome','sepia'])assert.ok(!menu.children.some(o=>o.value===retired));
});
test('legacy recipes remain identifiable but cannot be selected again',()=>{
 const {menu,update}=setup();
 for(const retired of ['pro_neg_hi','nostalgic_negative','monochrome','sepia']){
  update(retired);assert.equal(menu.children.length,11);assert.equal(menu.value,retired);
  const legacy=menu.children.find(o=>o.value===retired);assert.equal(legacy.disabled,true);assert.match(legacy.text,/legacy recipe/);
 }
 update('provia');assert.equal(menu.children.length,10);assert.equal(menu.value,'provia');
});
