// Xenoform MIDI: one mapping layer shared by the VJ page (vj.html) and the desk (ui_v6.js).
// Events arrive from Web MIDI (Chrome/Edge/Opera) and from the desk's /ws/midi websocket, fed by
// `xenoform midi serve` (so Firefox, Safari and headless renders see the controller too). Every event
// is the same shape everywhere: {type:"cc"|"note"|"pitch"|"prog"|"touch", ch:1..16, num, value:0..127, t}.
// A mapping row is {source:{type,ch,num}, target, mode:"abs"|"toggle"|"trigger"|"rel", min, max}; the
// table lives in localStorage "xeno-midi" as {profile, mappings:{vj:[...], desk:[...]}}.
(function(){
const KEY="xeno-midi";
// Arturia MiniLab 3 factory map (Arturia-mode template, checked against Arturia's MIDI Control Center manual):
// knobs 1-8 CC 74 71 76 77 93 18 19 16 · faders 1-4 CC 82 83 85 17 · mod strip CC 1 · pads bank A notes 36-43,
// bank B 44-51 on channel 10 · keys and knobs on channel 1.
// UNCERTAIN: the clickable main encoder. We assume relative CC 28 (Arturia mode; DAW mode sends MCU instead).
// If yours is different, Learn mode rebinds it in one twist.
const knobs=[74,71,76,77,93,18,19,16],faders=[82,83,85,17];
const PROFILES={
 minilab3:{label:"Arturia MiniLab 3 (factory map)",controls:[
   ...knobs.map((n,i)=>({id:"knob"+(i+1),label:"Knob "+(i+1),type:"cc",ch:1,num:n,mode:"abs"})),
   ...faders.map((n,i)=>({id:"fader"+(i+1),label:"Fader "+(i+1),type:"cc",ch:1,num:n,mode:"abs"})),
   {id:"mod",label:"Mod strip",type:"cc",ch:1,num:1,mode:"abs"},
   {id:"encoder",label:"Main encoder (relative, uncertain)",type:"cc",ch:1,num:28,mode:"rel"},
   ...[...Array(8)].map((_,i)=>({id:"padA"+(i+1),label:"Pad A"+(i+1),type:"note",ch:10,num:36+i,mode:"trigger"})),
   ...[...Array(8)].map((_,i)=>({id:"padB"+(i+1),label:"Pad B"+(i+1),type:"note",ch:10,num:44+i,mode:"trigger"}))],
  vj:{knob1:"intensity",knob2:"every",knob3:"drums",knob4:"bass",knob5:"other",knob6:"vocals",knob7:"stem:1",knob8:"stem:2",
      fader1:"stem:3",fader2:"stem:4",fader3:"stem:5",fader4:"stem:6",mod:"intensity",encoder:"fx:step",
      padA1:"fx:1",padA2:"fx:2",padA3:"fx:3",padA4:"fx:4",padA5:"fx:5",padA6:"fx:6",padA7:"fx:7",padA8:"fx:8",
      padB1:"dance:1",padB2:"dance:2",padB3:"dance:3",padB4:"dance:4",padB5:"dance:5",padB6:"dance:6",padB7:"strobe",padB8:"record"},
  desk:{knob1:"macro:intensity",knob2:"macro:speed",knob3:"macro:chaos",knob4:"macro:glow",knob5:"stem:1",knob6:"stem:2",knob7:"stem:3",knob8:"stem:4",
      fader1:"drums",fader2:"bass",fader3:"other",fader4:"vocals"}},
 generic:{label:"Generic controller (CC 1-8, notes 36-51)",controls:[
   ...[...Array(8)].map((_,i)=>({id:"knob"+(i+1),label:"CC "+(i+1),type:"cc",ch:0,num:i+1,mode:"abs"})),
   ...[...Array(16)].map((_,i)=>({id:"pad"+(i+1),label:"Note "+(36+i),type:"note",ch:0,num:36+i,mode:"trigger"}))],
  vj:{knob1:"intensity",knob2:"every",knob3:"drums",knob4:"bass",knob5:"other",knob6:"vocals",
      pad1:"fx:1",pad2:"fx:2",pad3:"fx:3",pad4:"fx:4",pad5:"fx:5",pad6:"fx:6",pad7:"fx:7",pad8:"fx:8",
      pad9:"dance:1",pad10:"dance:2",pad11:"dance:3",pad12:"dance:4",pad13:"dance:5",pad14:"dance:6",pad15:"strobe",pad16:"record"},
  desk:{knob1:"macro:intensity",knob2:"macro:speed",knob3:"macro:chaos",knob4:"macro:glow",knob5:"drums",knob6:"bass",knob7:"other",knob8:"vocals"}}};
const TOGGLES=["strobe","mirror","hud","kaleido","record"];
const VJ_TARGETS=["intensity","every","fx:next","fx:prev","fx:step","fx:auto","fx:1","fx:2","fx:3","fx:4","fx:5","fx:6","fx:7","fx:8",
 "dance:1","dance:2","dance:3","dance:4","dance:5","dance:6","mirror","strobe","kaleido","record","tap","hud","drums","bass","other","vocals",
 "stem:1","stem:2","stem:3","stem:4","stem:5","stem:6","stem:7","stem:8"];
const DESK_TARGETS=["macro:intensity","macro:speed","macro:chaos","macro:glow","drums","bass","other","vocals",
 "stem:1","stem:2","stem:3","stem:4","stem:5","stem:6","stem:7","stem:8"];
const range=t=>t==="intensity"?[0,2]:[0,1];
function modeFor(target,type,profileMode){if(profileMode==="rel")return"rel";if(type!=="note")return"abs";
 if(TOGGLES.includes(target))return"toggle";if(/^(fx:|dance:|tap$|record$)/.test(target))return"trigger";return"abs"}
function profileMapping(profile,page){const p=PROFILES[profile]||PROFILES.generic,T=p[page]||{};const out=[];
 for(const c of p.controls){const t=T[c.id];if(!t)continue;const[lo,hi]=range(t);
  out.push({source:{type:c.type,ch:c.ch,num:c.num},target:t,mode:modeFor(t,c.type,c.mode),min:lo,max:hi,label:c.label})}return out}
function normalise(data,t){const b=data;if(!b||b.length<1||b[0]<0x80)return null;const st=b[0]&0xf0,ch=(b[0]&15)+1,d1=b[1]|0,d2=b[2]|0,tt=t!=null?t:Date.now()/1000;
 if(st===0x90)return{type:"note",ch,num:d1,value:d2,t:tt};if(st===0x80)return{type:"note",ch,num:d1,value:0,t:tt};
 if(st===0xB0)return{type:"cc",ch,num:d1,value:d2,t:tt};if(st===0xE0)return{type:"pitch",ch,num:0,value:(d1|(d2<<7))>>7,t:tt};
 if(st===0xC0)return{type:"prog",ch,num:d1,value:d1,t:tt};if(st===0xD0)return{type:"touch",ch,num:0,value:d1,t:tt};
 if(st===0xA0)return{type:"touch",ch,num:d1,value:d2,t:tt};return null}
const matches=(e,ev)=>e.source&&e.source.type===ev.type&&+e.source.num===+ev.num&&(!+e.source.ch||+e.source.ch===+ev.ch);
const relDelta=v=>v>=64?v-64:v>0?-(64-v):0;
const srcName=s=>(s.type==="note"?"note ":s.type==="cc"?"CC ":s.type+" ")+s.num+(s.ch?" ch"+s.ch:"");
function load(){try{const j=JSON.parse(localStorage.getItem(KEY)||"{}");return{profile:j.profile||"minilab3",mappings:j.mappings||{}}}catch(e){return{profile:"minilab3",mappings:{}}}}

const X={
 page:"vj",profile:"minilab3",mappings:[],handlers:{},state:{},inputs:[],ws:null,es:null,wsState:"off",learnTarget:null,learnMode:false,
 share:false,last:null,count:0,log:[],_opts:{},_el:null,_timer:null,
 init(opts){opts=opts||{};this._opts=opts;this.page=opts.page||"vj";const st=load();this.profile=st.profile;
  const stored=st.mappings[this.page];this.mappings=Array.isArray(stored)&&stored.length?stored:profileMapping(this.profile,this.page);
  Object.assign(this.handlers,opts.targets||{});
  if(navigator.requestMIDIAccess&&opts.webmidi!==false)navigator.requestMIDIAccess().then(acc=>{const bind=()=>{this.inputs=[];acc.inputs.forEach(inp=>{this.inputs.push(inp.name||"MIDI input");
     inp.onmidimessage=ev=>{const e=normalise(ev.data);if(e)this.handle(e,"webmidi")}});this._status()};bind();acc.onstatechange=bind}).catch(()=>{this._status()});
  if(opts.bridge!==false)this.connect();this._status();return this},
 // ---- events
 handle(ev,origin){this.last=ev;this.count++;this.log.push(ev);this.log.length>12&&this.log.shift();
  if(this.learnTarget&&(ev.type==="cc"||ev.type==="note")&&ev.value>0){this.bind(this.learnTarget,ev);return}
  if(this.share&&origin==="webmidi"&&this.ws&&this.ws.readyState===1)this.ws.send(JSON.stringify(ev));
  let hit=false;for(const e of this.mappings){if(!matches(e,ev))continue;const r=this.apply(e,ev);if(r){hit=true;this.fire(r[0],r[1],ev,e)}}
  if(this._opts.onEvent)this._opts.onEvent(ev,hit,origin);this._status(true)},
 apply(e,ev){const t=e.target,mode=e.mode||"abs",lo=+e.min||0,hi=e.max==null?1:+e.max,v=ev.value|0;let val;
  if(mode==="abs")val=lo+(hi-lo)*v/127;
  else if(mode==="rel"){val=Math.max(lo,Math.min(hi,(this.state[t]==null?lo:this.state[t])+(hi-lo)*relDelta(v)/100));if(t==="fx:step"){if(!relDelta(v))return null;val=relDelta(v)}}
  else if(mode==="toggle"){if(ev.type==="note"&&v===0)return null;val=(this.state[t]==null?lo:this.state[t])<=lo?hi:lo}
  else{if(v===0)return null;val=hi}
  this.state[t]=val;return[t,val]},
 fire(target,val,ev,entry){const h=this.handlers;const m=/^([a-z]+):(.+)$/.exec(target);
  if(h[target])return h[target](val,ev,entry);
  if(m&&h[m[1]+":*"])return h[m[1]+":*"](m[2],val,ev,entry);
  if(h["*"])h["*"](target,val,ev,entry)},
 // ---- mapping edits
 bind(target,ev){const type=ev.type,prof=PROFILES[this.profile]||PROFILES.generic;
  const pc=prof.controls.find(c=>c.type===type&&c.num===ev.num&&(!c.ch||c.ch===ev.ch));const[lo,hi]=range(target);
  this.mappings=this.mappings.filter(e=>e.target!==target&&!(matches(e,ev)));
  this.mappings.push({source:{type,ch:ev.ch,num:ev.num},target,mode:modeFor(target,type,pc&&pc.mode),min:lo,max:hi,label:pc?pc.label:srcName({type,num:ev.num,ch:ev.ch})});
  this.learnTarget=null;this.save();this.toast("MIDI: "+srcName({type,num:ev.num,ch:ev.ch})+" → "+target);this.render()},
 learn(target){this.learnTarget=target||null;if(target)this.toast("Move a knob or hit a pad for "+target+"…");this.render()},
 setLearnMode(on){this.learnMode=!!on;document.body.classList.toggle("midi-learn",this.learnMode);if(!on)this.learnTarget=null;
  this.toast(this.learnMode?"Learn: click a control, then move a knob":"Learn off");this.render()},
 unmap(i){this.mappings.splice(i,1);this.save();this.render()},
 add(target,source,mode,min,max){const[lo,hi]=range(target);this.mappings.push({source,target,mode:mode||modeFor(target,source.type),min:min==null?lo:min,max:max==null?hi:max});this.save();this.render()},
 setProfile(name){if(!PROFILES[name])return;this.profile=name;this.mappings=profileMapping(name,this.page);this.save();this.render()},
 reset(){this.mappings=profileMapping(this.profile,this.page);this.save();this.render()},
 save(){const st=load();st.profile=this.profile;st.mappings[this.page]=this.mappings;try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}},
 exportJSON(){return JSON.stringify({kind:"xenoform-midi-map",version:1,profile:this.profile,page:this.page,mappings:this.mappings},null,1)},
 importJSON(text){const j=typeof text==="string"?JSON.parse(text):text;const rows=Array.isArray(j)?j:j.mappings||(j.pages&&j.pages[this.page]);
  if(!Array.isArray(rows))throw new Error("not a mapping file");this.mappings=rows.filter(r=>r&&r.source&&r.target).map(r=>({source:{type:r.source.type,ch:+r.source.ch||0,num:+r.source.num},target:String(r.target),mode:r.mode||"abs",min:+r.min||0,max:r.max==null?1:+r.max,label:r.label}));
  if(j.profile&&PROFILES[j.profile])this.profile=j.profile;this.save();this.render();return this.mappings.length},
 // ---- the desk websocket (Python bridge fan-out), SSE when there is no websocket
 connect(){const base=(window.XENO_BASE||"");if(this.ws||this.es)return;let url;
  try{url=(location.protocol==="https:"?"wss://":"ws://")+location.host+base+"/ws/midi?name="+encodeURIComponent(this.page)}catch(e){return}
  let opened=false;const ws=new WebSocket(url);this.ws=ws;this.wsState="connecting";
  ws.onopen=()=>{opened=true;this.wsState="bridge";this._retry=0;this._status()};
  ws.onmessage=m=>{try{const ev=JSON.parse(m.data);if(ev&&ev.type&&ev.type!=="hello")this.handle(ev,"bridge")}catch(e){}};
  ws.onclose=ws.onerror=()=>{if(this.ws!==ws)return;this.ws=null;this.wsState="off";this._status();
   if(!opened&&(this._retry=(this._retry||0)+1)>=2)return this.sse(base);clearTimeout(this._timer);this._timer=setTimeout(()=>this.connect(),2500*Math.min(6,this._retry||1))}},
 sse(base){if(this.es||!window.EventSource)return;const es=new EventSource(base+"/api/midi/stream");this.es=es;this.wsState="sse";
  es.onmessage=m=>{try{const ev=JSON.parse(m.data);if(ev&&ev.type)this.handle(ev,"bridge")}catch(e){}};
  es.onerror=()=>{this.wsState="sse (reconnecting)";this._status()};this._status()},
 status(){return{inputs:this.inputs.slice(),bridge:this.wsState,profile:this.profile,mappings:this.mappings.length,events:this.count,last:this.last,learn:this.learnMode||!!this.learnTarget}},
 _status(light){const s=this.status();if(this._opts.onStatus)this._opts.onStatus(s);if(!light||this.count%8===0)this._paintStatus()},
 toast(t){if(this._opts.toast)this._opts.toast(t)},
 // ---- learn mode: a click on any control picks the target, the next knob/pad binds it
 _clickTarget(el){const m=el.closest&&el.closest("[data-midi]");if(m)return m.dataset.midi;
  const k=el.closest&&el.closest(".xf-knob[data-k]");if(k)return"macro:"+k.dataset.k;
  const l=el.closest&&el.closest(".xf-lane input[data-k],.xf-lane");if(l){const i=l.matches("input")?l:l.querySelector("input[data-k]");if(i)return i.dataset.k}
  const map=this._opts.elements||{};const e=el.closest&&el.closest("[id]");return e&&map[e.id]||null},
 // ---- panel (inputs, profile, mappings, learn, export/import)
 panel(el){this._el=el;if(!document.getElementById("xeno-midi-css")){const s=document.createElement("style");s.id="xeno-midi-css";s.textContent=`
  #xeno-midi-panel{font:12px/1.5 inherit;color:inherit}#xeno-midi-panel h3{margin:10px 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.7}
  #xeno-midi-panel .mrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0}#xeno-midi-panel table{width:100%;border-collapse:collapse;max-height:240px}
  #xeno-midi-panel td{padding:2px 6px;border-bottom:1px solid rgba(128,128,128,.18);vertical-align:middle}#xeno-midi-panel select,#xeno-midi-panel button,#xeno-midi-panel input{font:inherit;padding:2px 8px;border-radius:999px;border:1px solid rgba(128,128,128,.35);background:rgba(128,128,128,.08);color:inherit;cursor:pointer}
  #xeno-midi-panel .wrap{max-height:230px;overflow:auto}#xeno-midi-panel .on{background:#f4f3fb;color:#0a0a10}#xeno-midi-panel textarea{width:100%;height:70px;font:11px/1.3 monospace;background:rgba(0,0,0,.25);color:inherit;border:1px solid rgba(128,128,128,.3);border-radius:8px}
  #xeno-midi-panel .pulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:#7b84ff;opacity:.3;margin-right:6px}#xeno-midi-panel .pulse.hot{opacity:1;box-shadow:0 0 12px #7b84ff}
  body.midi-learn [data-midi],body.midi-learn .xf-knob,body.midi-learn .xf-lane{outline:2px dashed #7b84ff;outline-offset:2px;cursor:crosshair}`;document.head.appendChild(s)}
  this.render();return this},
 _paintStatus(){const el=this._el&&this._el.querySelector("#xm-status");if(!el)return;const s=this.status();
  el.innerHTML=`<span class="pulse${Date.now()/1000-((s.last&&s.last.t)||0)<.4?" hot":""}"></span>${s.inputs.length?s.inputs.join(", "):"no Web MIDI input"} · bridge: ${s.bridge} · ${s.events} events`+
   (s.last?` · last ${srcName(s.last)} = ${s.last.value}`:"")},
 render(){const el=this._el;if(!el)return;const T=(this.page==="desk"?DESK_TARGETS:VJ_TARGETS).concat((this._opts.extraTargets||[]));
  const opts=T.map(t=>`<option value="${t}">${t}</option>`).join("");
  el.innerHTML=`<div id="xeno-midi-panel" data-tour="midi">
   <div class="mrow"><b>MIDI</b><span id="xm-status"></span></div>
   <div class="mrow"><label>Profile <select id="xm-prof">${Object.keys(PROFILES).map(k=>`<option value="${k}"${k===this.profile?" selected":""}>${PROFILES[k].label}</option>`).join("")}</select></label>
    <button id="xm-learn" class="${this.learnMode?"on":""}">${this.learnMode?"Learn: click a control…":"Learn mode (L)"}</button>
    <button id="xm-reset">Factory map</button><button id="xm-export">Export JSON</button><label><input type="checkbox" id="xm-share"${this.share?" checked":""}> share with other pages</label></div>
   ${this.learnTarget?`<div class="mrow">Waiting for a knob or pad for <b>${this.learnTarget}</b> · <button id="xm-cancel">cancel</button></div>`:""}
   <div class="wrap"><table><tbody>${this.mappings.map((m,i)=>`<tr><td>${m.label||srcName(m.source)}</td><td><small>${srcName(m.source)}</small></td><td><b>${m.target}</b></td><td>${m.mode}</td>
    <td><button data-learn="${m.target}">learn</button> <button data-del="${i}" title="remove">×</button></td></tr>`).join("")}</tbody></table></div>
   <div class="mrow"><select id="xm-new">${opts}</select><button id="xm-add">+ map (then move a knob)</button></div>
   <div class="mrow"><textarea id="xm-json" placeholder="Paste a mapping JSON here and press Import"></textarea></div>
   <div class="mrow"><button id="xm-import">Import JSON</button><small>Saved in this browser (localStorage "xeno-midi"). The Python bridge: <code>xenoform midi serve</code>.</small></div></div>`;
  const $=s=>el.querySelector(s);$("#xm-prof").onchange=e=>this.setProfile(e.target.value);$("#xm-learn").onclick=()=>this.setLearnMode(!this.learnMode);
  $("#xm-reset").onclick=()=>this.reset();$("#xm-share").onchange=e=>{this.share=e.target.checked};
  $("#xm-export").onclick=()=>{const t=this.exportJSON();$("#xm-json").value=t;const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([t],{type:"application/json"}));a.download=`xenoform-midi-${this.page}.json`;a.click();this.toast("Mapping exported")};
  $("#xm-import").onclick=()=>{try{const n=this.importJSON($("#xm-json").value);this.toast(n+" mappings imported")}catch(e){this.toast("Import failed: "+e.message)}};
  $("#xm-add").onclick=()=>this.learn($("#xm-new").value);const c=$("#xm-cancel");if(c)c.onclick=()=>this.learn(null);
  el.querySelectorAll("[data-learn]").forEach(b=>b.onclick=()=>this.learn(b.dataset.learn));el.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>this.unmap(+b.dataset.del));
  el.addEventListener("click",e=>e.stopPropagation());this._paintStatus()},
 PROFILES,profileMapping,normalise,srcName,VJ_TARGETS,DESK_TARGETS};
// learn-mode click capture (before the page's own handlers)
document.addEventListener("click",e=>{if(!X.learnMode||!e.target||(e.target.closest&&e.target.closest("#xeno-midi-panel")))return;
 const t=X._clickTarget(e.target);if(!t)return;e.preventDefault();e.stopPropagation();X.learn(t)},true);
document.addEventListener("pointerdown",e=>{if(!X.learnMode||!e.target||(e.target.closest&&e.target.closest("#xeno-midi-panel")))return;
 if(X._clickTarget(e.target)){e.preventDefault();e.stopPropagation()}},true);
window.XenoMidi=X;
})();
