// Canvas event/protocol checks without a browser or actual microphone.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../think_app/board/index.html'),'utf8');
const source=html.split('<script>')[1].split('</script>')[0];
const sent=[],listeners={},draw=[];
const context=new Proxy({}, {get:(obj,name)=>obj[name]||((...args)=>draw.push([name,...args]))});
const elements={};
for(const id of ['board','status','grid','color','size','pen','erase','undo','clear']){
  elements[id]={value:id==='size'?'3':'#153e40',checked:true,style:{},classList:{toggle(){}},setAttribute(){},
    addEventListener:(name,fn)=>{listeners[id+':'+name]=fn},setPointerCapture(){},
    getBoundingClientRect:()=>({left:10,top:20,width:500,height:310}),getContext:()=>context,
    toDataURL:()=> 'data:image/png;base64,c2ltdWxhdGVk'};
}
const parent={postMessage:msg=>sent.push(msg)},win={parent,addEventListener:(name,fn)=>{listeners[name]=fn}};
vm.runInNewContext(source,{document:{getElementById:id=>elements[id],body:{scrollHeight:600}},window:win,confirm:()=>true,Image:class{}});
assert(sent.some(m=>m.type==='streamlit:componentReady'&&m.apiVersion===1));
listeners.message({source:parent,data:{type:'streamlit:render',args:{}}});
const e={clientX:60,clientY:70,pointerId:1,preventDefault(){}};
listeners['board:pointerdown'](e);
listeners['board:pointermove']({...e,clientX:160,clientY:170});
listeners['board:pointerup']();
let value=sent.filter(m=>m.type==='streamlit:setComponentValue').at(-1);
assert(value.value.hasInk===true&&value.dataType==='json');
assert(draw.some(d=>d[0]==='moveTo'&&d[1]===100&&d[2]===100));
elements.undo.onclick();
assert(sent.filter(m=>m.type==='streamlit:setComponentValue').at(-1).value.hasInk===false);
listeners['board:pointerdown'](e);listeners['board:pointercancel']();
assert(sent.filter(m=>m.type==='streamlit:setComponentValue').at(-1).value.hasInk===true);
elements.clear.onclick();
assert(sent.filter(m=>m.type==='streamlit:setComponentValue').at(-1).value.hasInk===false);
console.log('Whiteboard protocol, scaled coordinates, stroke, undo, cancel, clear: passed (simulated DOM).');
