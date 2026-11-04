// Xenoform MIDI: one mapping layer shared by the VJ page (vj.html) and the desk (ui_v6.js).
// Events arrive from Web MIDI (Chrome/Edge/Opera) and from the desk's /ws/midi websocket, fed by
// `xenoform midi serve` (so Firefox, Safari and headless renders see the controller too). Every event
// is the same shape everywhere: {type:"cc"|"note"|"pitch"|"prog"|"touch", ch:1..16, num, value:0..127, t}
// (+ dev, the input's name, when Web MIDI read it). A mapping row is {source:{type,ch,num}, target,
// mode:"abs"|"toggle"|"trigger"|"rel"|"hold", min, max}; the table lives in localStorage "xeno-midi" as
// {profile, mappings:{vj:[...], desk:[...]}}.
// Two halves in one file: the pure core (profiles, normalise, resolve, the hold stack, plain names) loads under node
// too (module.exports, for tests/js/midi_test.js), and the browser runtime (window.XenoMidi) runs only in a page, so a
// page that loads /static/midi.js alone gets both.
(function(root){
"use strict";
// Arturia MiniLab 3 factory map (Arturia-mode template, checked against Arturia's MIDI Control Center manual):
// knobs 1-8 CC 74 71 76 77 93 18 19 16 · faders 1-4 CC 82 83 85 17 · mod strip CC 1 · pads bank A notes 36-43,
// bank B 44-51 on channel 10 · keys and knobs on channel 1.
// UNCERTAIN: the clickable main encoder. We assume relative CC 28 (Arturia mode; DAW mode sends MCU instead).
// If yours is different, Learn mode rebinds it in one twist.
const knobs=[74,71,76,77,93,18,19,16],faders=[82,83,85,17];
const n8=[...Array(8)].map((_,i)=>i+1);
const PROFILES={
 minilab3:{label:"Arturia MiniLab 3",match:"mini\\s*lab\\s*3",controls:[
   ...knobs.map((n,i)=>({id:"knob"+(i+1),short:"K"+(i+1),label:"Knob "+(i+1),type:"cc",ch:1,num:n,mode:"abs"})),
   ...faders.map((n,i)=>({id:"fader"+(i+1),short:"F"+(i+1),label:"Fader "+(i+1),type:"cc",ch:1,num:n,mode:"abs"})),
   {id:"mod",short:"Mod",label:"Mod strip",type:"cc",ch:1,num:1,mode:"abs"},
   {id:"encoder",short:"Enc",label:"Main encoder (relative, uncertain)",type:"cc",ch:1,num:28,mode:"rel"},
   ...[...Array(8)].map((_,i)=>({id:"padA"+(i+1),short:"A"+(i+1),label:"Pad A"+(i+1),type:"note",ch:10,num:36+i,mode:"trigger"})),
   ...[...Array(8)].map((_,i)=>({id:"padB"+(i+1),short:"B"+(i+1),label:"Pad B"+(i+1),type:"note",ch:10,num:44+i,mode:"trigger"}))],
  // how the controller is drawn (UI_REVIEW 6.5): two rows of four knobs, four faders, the pads in their two banks
  layout:{knobs:[["knob1","knob2","knob3","knob4"],["knob5","knob6","knob7","knob8"]],faders:["fader1","fader2","fader3","fader4"],
   pads:[n8.map(i=>"padA"+i),n8.map(i=>"padB"+i)],extra:["mod","encoder"],note:"Pads A and B are the two banks of the eight pads."},
  // pads A1-A8 hold a scene (pad:N, T2's perform pads): shown while held, the song's own picture again on release
  vj:{knob1:"intensity",knob2:"every",knob3:"drums",knob4:"bass",knob5:"other",knob6:"vocals",knob7:"stem:1",knob8:"stem:2",
      fader1:"stem:3",fader2:"stem:4",fader3:"stem:5",fader4:"stem:6",mod:"intensity",encoder:"fx:step",
      ...Object.fromEntries(n8.map(i=>["padA"+i,"pad:"+i])),
      padB1:"dance:1",padB2:"dance:2",padB3:"dance:3",padB4:"dance:4",padB5:"dance:5",padB6:"dance:6",padB7:"strobe",padB8:"record"},
  desk:{knob1:"macro:intensity",knob2:"macro:speed",knob3:"macro:chaos",knob4:"macro:glow",knob5:"stem:1",knob6:"stem:2",knob7:"stem:3",knob8:"stem:4",
      fader1:"drums",fader2:"bass",fader3:"other",fader4:"vocals"}},
 // an unknown controller: knobs in CC order (1-8) to the main parameters and the stem gains, sliders (CC 9-12) to the
 // master levels, pads in note order (36-51) to the scenes, then the dance presets as on the MiniLab's bank B
 generic:{label:"Any controller (CC 1-12, notes 36-51)",controls:[
   ...[...Array(8)].map((_,i)=>({id:"knob"+(i+1),short:"K"+(i+1),label:"Knob "+(i+1)+" (CC "+(i+1)+")",type:"cc",ch:0,num:i+1,mode:"abs"})),
   ...[...Array(4)].map((_,i)=>({id:"slider"+(i+1),short:"S"+(i+1),label:"Slider "+(i+1)+" (CC "+(i+9)+")",type:"cc",ch:0,num:i+9,mode:"abs"})),
   ...[...Array(16)].map((_,i)=>({id:"pad"+(i+1),short:"P"+(i+1),label:"Pad "+(i+1)+" (note "+(36+i)+")",type:"note",ch:0,num:36+i,mode:"trigger"}))],
  layout:{knobs:[n8.map(i=>"knob"+i)],faders:["slider1","slider2","slider3","slider4"],pads:[n8.map(i=>"pad"+i),n8.map(i=>"pad"+(i+8))],extra:[],
   note:"An unknown controller: knobs on CC 1-8, sliders on CC 9-12, pads on notes 36-51. Learn moves any of them."},
  vj:{knob1:"intensity",knob2:"every",knob3:"stem:1",knob4:"stem:2",knob5:"stem:3",knob6:"stem:4",knob7:"stem:5",knob8:"stem:6",
      slider1:"drums",slider2:"bass",slider3:"other",slider4:"vocals",...Object.fromEntries(n8.map(i=>["pad"+i,"pad:"+i])),
      pad9:"dance:1",pad10:"dance:2",pad11:"dance:3",pad12:"dance:4",pad13:"dance:5",pad14:"dance:6",pad15:"strobe",pad16:"record"},
  desk:{knob1:"macro:intensity",knob2:"macro:speed",knob3:"macro:chaos",knob4:"macro:glow",knob5:"stem:1",knob6:"stem:2",knob7:"stem:3",knob8:"stem:4",
      slider1:"drums",slider2:"bass",slider3:"other",slider4:"vocals"}}};
const TOGGLES=["strobe","mirror","hud","kaleido","record"];
const HOLDS=/^(pad|scene):|^blackout$/,TRIGGERS=/^(fx:|dance:|cue:|tap$|play$)/;
const VJ_TARGETS=["intensity","every",...n8.map(i=>"pad:"+i),"fx:next","fx:prev","fx:step","fx:auto","fx:1","fx:2","fx:3","fx:4","fx:5","fx:6","fx:7","fx:8",
 "dance:1","dance:2","dance:3","dance:4","dance:5","dance:6","mirror","strobe","kaleido","record","tap","hud","drums","bass","other","vocals",
 "stem:1","stem:2","stem:3","stem:4","stem:5","stem:6","stem:7","stem:8"];
const DESK_TARGETS=["macro:intensity","macro:speed","macro:chaos","macro:glow","drums","bass","other","vocals",
 "stem:1","stem:2","stem:3","stem:4","stem:5","stem:6","stem:7","stem:8"];
const range=t=>t==="intensity"?[0,2]:[0,1];
// the mode a new binding gets: a pad target holds, a switch toggles and an action fires once (on a note or a CC button
// alike), an encoder steps, anything else follows the control
function modeFor(target,type,profileMode){if(profileMode==="rel")return"rel";if(HOLDS.test(target))return"hold";
 if(TOGGLES.includes(target))return"toggle";if(TRIGGERS.test(target))return"trigger";return"abs"}
// a CC press: the value comes up through 64, or a button that only ever sends 127 sends it again (a knob never repeats
// a value), so a knob on Tap or Record fires once a turn past half, not on every tick
function ccPress(e,ev,state){const k="~"+e.target+">"+srcKey(ev),was=state[k]==null?0:state[k],v=ev.value|0;state[k]=v;return v>=64&&(was<64||was===v)}
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
const srcKey=s=>s.type+":"+(+s.ch||0)+":"+s.num;
// a press lets go when the control comes back up: note-off (or a note-on at velocity 0), a CC button below 64
const isRelease=ev=>ev.type==="note"?(ev.value|0)===0:(ev.value|0)<64;
// One event through one row: {target, value, kind} where kind is "set", or "press"/"release" for a hold row; null for
// an event the row ignores (a toggle's or a trigger's release). `state` keeps toggles and encoders between events.
function resolve(e,ev,state){const t=e.target,mode=e.mode||"abs",lo=+e.min||0,hi=e.max==null?1:+e.max,v=ev.value|0;let val,kind="set";
 if(mode==="abs")val=lo+(hi-lo)*v/127;
 else if(mode==="rel"){const d=relDelta(v);if(t==="fx:step"){if(!d)return null;val=d}else val=Math.max(lo,Math.min(hi,(state[t]==null?lo:state[t])+(hi-lo)*d/100))}
 else if(mode==="toggle"){if(ev.type==="note"?v===0:!ccPress(e,ev,state))return null;val=(state[t]==null?lo:state[t])<=lo?hi:lo}
 else if(mode==="hold"){const on=!isRelease(ev);kind=on?"press":"release";val=on?hi:lo}
 else{if(ev.type==="note"?v===0:!ccPress(e,ev,state))return null;val=hi}
 state[t]=val;return{target:t,value:val,kind}}
// The hold stack: pads are temporary overriders. press(id) puts a pad on top (last in wins), release(id) takes it off
// wherever it is, top() is what shows now (optionally the top one of a family: top("pad:")), clear() lets go of all,
// on(fn) hears every change as fn(id, on, top, stack) and returns its unsubscribe.
function HoldStack(){this.stack=[];this.subs=[]}
HoldStack.prototype={
 press(id){if(!id)return;const i=this.stack.indexOf(id);if(i>=0)this.stack.splice(i,1);this.stack.push(id);this._tell(id,true)},
 release(id){const i=this.stack.indexOf(id);if(i<0)return false;this.stack.splice(i,1);this._tell(id,false);return true},
 top(prefix){for(let i=this.stack.length-1;i>=0;i--){const id=this.stack[i];if(!prefix||id.indexOf(prefix)===0)return id}return null},
 held(id){return this.stack.includes(id)},list(){return this.stack.slice()},
 clear(){while(this.stack.length)this.release(this.stack[this.stack.length-1])},
 on(fn){this.subs.push(fn);return()=>{this.subs=this.subs.filter(f=>f!==fn)}},
 _tell(id,on){const top=this.top(),stack=this.stack.slice();for(const fn of this.subs.slice()){try{fn(id,on,top,stack)}catch(e){if(typeof console!=="undefined")console.error("midi hold",e)}}}};
// Soft takeover for absolute knobs and faders: the value moves only once the hardware passes the on-screen value (or
// comes within a small window of it), so a knob left somewhere else by a song change, a page change, a reset or a
// mouse drag never makes the picture jump. One state per (control, target) pair. decide(key, c, s, lo, hi): c is the
// value the hardware asks for, s the value on screen now (null: no takeover for this target, apply at once).
// Returns {apply, picked, dir}; dir is the way to move the hardware to catch the value (+1 up, -1 down).
function Takeover(windowFrac){this.w=windowFrac==null?0.03:windowFrac;this.rows={}}
Takeover.prototype={
 decide(key,c,s,lo,hi){const st=this.rows[key]||(this.rows[key]={picked:false,hw:null,applied:null,screen:null});
  if(s==null||!isFinite(s)){st.picked=true;st.hw=st.applied=c;st.screen=null;return{apply:true,picked:true,dir:0}}
  const tol=this.w*(Math.abs((+hi||0)-(+lo||0))||1);
  if(st.picked&&st.applied!=null&&Math.abs(s-st.applied)>tol)st.picked=false;  // the value was moved by something else
  if(!st.picked&&(Math.abs(c-s)<=tol||(st.hw!=null&&(st.hw-s)*(c-s)<=0)))st.picked=true;  // within reach, or passed it
  st.hw=c;st.screen=s;if(st.picked){st.applied=c;return{apply:true,picked:true,dir:0}}
  return{apply:false,picked:false,dir:c<s?1:-1}},
 // {hw, screen, dir} when the hardware is known to be away from the value, else null
 away(key){const st=this.rows[key];return st&&!st.picked&&st.hw!=null&&st.screen!=null?{hw:st.hw,screen:st.screen,dir:st.hw<st.screen?1:-1}:null},
 reset(key){if(key)delete this.rows[key];else this.rows={}}};
// plain words for targets (C7: "Intensity", "Drums level", not macro:intensity)
const FX_NAMES=["Clean cut","Match-cut","Flow carry","Liquid flow","Depth parallax","Lens breath","Chrome refraction","Echo trail"];
const DANCE_NAMES=["Clean","Mirror","Strobe","Mirror + strobe","Echo trail","Chrome mirror"];
const NAMES={intensity:"Intensity",every:"Switch rate",speed:"Speed",chaos:"Chaos",glow:"Glow",master:"Master fade",blackout:"Blackout",
 play:"Play / pause","cue:drop":"Cue the drop","fx:next":"Next scene","fx:prev":"Previous scene","fx:step":"Step the transition","fx:auto":"Auto transitions",
 mirror:"Mirror",strobe:"Strobe",kaleido:"Kaleido",record:"Record",tap:"Tap tempo",hud:"HUD",drums:"Drums level",bass:"Bass level",
 other:"Other level",vocals:"Vocals level",feel:"Feel",look:"Look"};
function targetName(t){t=String(t||"");if(NAMES[t])return NAMES[t];let m;
 if((m=/^macro:(.+)$/.exec(t)))return NAMES[m[1]]||m[1].charAt(0).toUpperCase()+m[1].slice(1);
 if((m=/^fx:(\d+)$/.exec(t)))return"Transition "+m[1]+(FX_NAMES[+m[1]-1]?" · "+FX_NAMES[+m[1]-1]:"");
 if((m=/^dance:(\d+)$/.exec(t)))return"Dance "+m[1]+(DANCE_NAMES[+m[1]-1]?" · "+DANCE_NAMES[+m[1]-1]:"");
 if((m=/^(pad|scene):(\d+)$/.exec(t)))return(m[1]==="pad"?"Pad ":"Scene ")+m[2];
 if((m=/^stem:(\d+)$/.exec(t)))return"Stem "+m[1];if((m=/^stem:(.+)$/.exec(t)))return m[1]+" stem";
 return t.replace(/[:_-]+/g," ")}
const MODE_NAMES={abs:"Follows the control",rel:"Steps (endless encoder)",toggle:"Press on, press off",hold:"On while held",trigger:"Fires on press"};
// the profile control behind a source, and its short name for a badge (K1, F2, A3, Mod); a learned control the profile
// does not know is named by its message (CC74, N36)
function controlOf(profile,s){const p=PROFILES[profile]||PROFILES.generic;if(!s)return null;
 return p.controls.find(c=>c.type===s.type&&+c.num===+s.num&&(!+c.ch||!+s.ch||+c.ch===+s.ch))||null}
function shortName(profile,s){const c=controlOf(profile,s);return c?c.short:s?(s.type==="note"?"N":s.type==="cc"?"CC":s.type.charAt(0).toUpperCase())+s.num:""}
// ---- maps by device name: the port's name picks the map. bare() drops the port number some backends append (rtmidi
// on Windows lists the MiniLab 3 as "Minilab3 0" where Web MIDI says "Minilab3"); midi_maps.py has the same rule.
const bare=n=>String(n||"").trim().replace(/\s+\d+$/,"");
const sameDevice=(a,b)=>{a=String(a||"").trim();b=String(b||"").trim();return!!(a&&b)&&(a===b||bare(a)===b||a===bare(b))};
const reTest=(src,name)=>{try{return!!src&&new RegExp(src,"i").test(name)}catch(e){return false}};
// The default map for a port name: the first shipped preset (configs/midi_presets) whose match or device fits, else the
// built-in profile whose name pattern fits (the MiniLab 3), else the generic map. No name at all (an old bridge, a
// script) keeps the MiniLab 3's map, the default before maps had names.
function pickDefault(name,presets){name=String(name||"");
 if(name)for(const p of presets||[])if(reTest(p.match,name)||(p.device&&sameDevice(p.device,name)))
  return{kind:"preset",id:p.id,label:p.label||p.device||p.id,profile:PROFILES[p.profile]?p.profile:"generic",pages:p.pages||{}};
 if(!name)return{kind:"profile",id:"minilab3",label:PROFILES.minilab3.label,profile:"minilab3"};
 for(const id of Object.keys(PROFILES))if(reTest(PROFILES[id].match,name))return{kind:"profile",id,label:PROFILES[id].label,profile:id};
 return{kind:"profile",id:"generic",label:PROFILES.generic.label,profile:"generic"}}
const cloneRows=rows=>(rows||[]).map(r=>Object.assign({},r,{source:Object.assign({},r.source)}));
function defaultRows(choice,page){if(choice&&choice.kind==="preset"&&Array.isArray(choice.pages[page]))return cloneRows(choice.pages[page]);
 return profileMapping(choice?choice.profile:"minilab3",page)}
// which of several inputs the map shows: a known controller first, and never a side port ("MIDIIN2 (Minilab3)") while
// the main one is there
function primaryDevice(names,presets){const main=names.filter(n=>!/^MIDIIN\d/i.test(n)),pool=main.length?main:names;
 return pool.find(n=>pickDefault(n,presets).id!=="generic")||pool[0]||""}
// A table the first midi.js stored (one map a page, no device names) is the user's own work only when it differs from
// the factory map it was made from (before 4 Nov 2026 pads A were the transitions) and from today's.
const sig=rows=>(rows||[]).map(r=>srcKey(r.source)+">"+r.target).sort().join("|");
function legacyFactory(profile,page){const rows=profileMapping(profile,page);
 if(profile!=="generic"){if(page==="vj")rows.forEach(r=>{const m=/^pad:(\d+)$/.exec(r.target);if(m)r.target="fx:"+m[1]});return rows}
 const T=page==="vj"?["intensity","every","drums","bass","other","vocals"]:["macro:intensity","macro:speed","macro:chaos","macro:glow","drums","bass","other","vocals"];
 const out=T.map((t,i)=>({source:{type:"cc",ch:0,num:i+1},target:t}));
 if(page==="vj")for(let i=0;i<16;i++)out.push({source:{type:"note",ch:0,num:36+i},target:i<8?"fx:"+(i+1):i<14?"dance:"+(i-7):i===14?"strobe":"record"});
 return out}
const isOwnLegacy=(rows,profile,page)=>Array.isArray(rows)&&rows.length>0&&sig(rows)!==sig(legacyFactory(profile,page))&&sig(rows)!==sig(profileMapping(profile,page));

const core={PROFILES,VJ_TARGETS,DESK_TARGETS,MODE_NAMES,range,modeFor,profileMapping,normalise,matches,relDelta,srcName,srcKey,
 isRelease,resolve,HoldStack,Takeover,targetName,controlOf,shortName,bare,sameDevice,pickDefault,defaultRows,cloneRows,primaryDevice,
 legacyFactory,isOwnLegacy};
if(typeof module==="object"&&module.exports){module.exports=core;return}

// ---------------------------------------------------------------- the browser runtime
// The maps live per device name: localStorage["xeno-midi"] = {version:2, devices:{name:{device, profile, pages:{vj:[rows],
// desk:[rows]}, updated}}, active} mirrors the desk's ~/.xenoform/midi_map.json (GET/PUT /api/midi/maps/{device}); the
// newer copy of a device wins. The first midi.js kept {profile, mappings:{vj, desk}}; a table of the user's own in it is
// taken over by the first controller of that profile that connects.
const KEY="xeno-midi";
function loadStore(){try{const j=JSON.parse(localStorage.getItem(KEY)||"{}");return j&&typeof j==="object"?j:{}}catch(e){return{}}}
function saveStore(j){try{localStorage.setItem(KEY,JSON.stringify(j))}catch(e){}}
const api=p=>(window.XENO_BASE||"")+p;
const holds=new HoldStack(),takeover=new Takeover();
const rowKey=e=>srcKey(e.source)+">"+e.target;

const X={
 page:"vj",profile:"minilab3",mappings:[],handlers:{},state:{},inputs:[],ws:null,es:null,wsState:"off",learnTarget:null,learnMode:false,
 share:false,last:null,count:0,log:[],bridgeDevices:{},holds,takeover,_held:{},_opts:{},_el:null,_timer:null,
 devices:[],device:"",maps:{},presets:[],choice:null,personal:false,saved:"",mapsFile:"",_rows:{},_push_t:{},_subs:{},
 init(opts){opts=opts||{};this._opts=opts;this.page=opts.page||"vj";
  // ?webmidi=0: the bridge only. Web MIDI opens every input it binds, and on Windows an open input is exclusive, so a
  // second window (or a test page) that must not take the controller from another app asks for the bridge alone.
  if(/[?&]webmidi=0(&|$)/.test(location.search||""))opts.webmidi=false;
  const st=loadStore();this.maps=st.devices&&typeof st.devices==="object"?st.devices:{};this.device=String(st.active||"");
  this._legacy=st.version>=2||!st.mappings?null:{profile:PROFILES[st.profile]?st.profile:"minilab3",mappings:st.mappings};
  Object.assign(this.handlers,opts.targets||{});
  // onHold(target, on, {top, stack}): the page applies a pad (shows its scene or look) and lets go of it (back to what
  // the song holds now); several holds stack, last in wins
  if(opts.onHold)holds.on((id,on,top,stack)=>opts.onHold(id,on,{top,stack}));
  this._apply();this._sync();
  if(navigator.requestMIDIAccess&&opts.webmidi!==false)navigator.requestMIDIAccess().then(acc=>{const bind=()=>{this.inputs=[];const names=[];
     acc.inputs.forEach(inp=>{const name=inp.name||"MIDI input";this.inputs.push(name);names.push(name);
      inp.onmidimessage=ev=>{const e=normalise(ev.data);if(e){e.dev=name;this.handle(e,"webmidi")}}});
     this._gone(names);this._setDevices(names.map(n=>({name:n,via:"Web MIDI"})),"webmidi")};bind();acc.onstatechange=bind}).catch(()=>{this._status()});
  if(opts.bridge!==false)this.connect();this._status();return this},
 // ---- a tiny event hub for the map's face (midi_map.js): "event", "fire", "map", "devices", "status"
 on(type,fn){(this._subs[type]||(this._subs[type]=[])).push(fn);return()=>{this._subs[type]=(this._subs[type]||[]).filter(f=>f!==fn)}},
 emit(type,a,b,c){for(const fn of (this._subs[type]||[]).slice()){try{fn(a,b,c)}catch(e){console.error("midi "+type,e)}}},
 // ---- devices: Web MIDI's inputs and the bridge's ports, the active one's map shown and edited
 _setDevices(list,via){const before=this.devices.map(d=>d.name);
  this.devices=this.devices.filter(d=>d.via!==(via==="webmidi"?"Web MIDI":"bridge")).concat(list).filter((d,i,a)=>a.findIndex(o=>sameDevice(o.name,d.name))===i);
  const names=this.devices.map(d=>d.name);
  const side=n=>/^MIDIIN\d/i.test(n);  // the MiniLab's extra ports come and go with it: one toast is enough
  for(const n of names)if(!side(n)&&!before.some(b=>sameDevice(b,n)))this.toast(n+" connected · "+pickDefault(n,this.presets).label+(this._own(n)?" (your map)":""));
  for(const b of before)if(!side(b)&&!names.some(n=>sameDevice(n,b)))this.toast(b+" unplugged");
  if(!names.some(n=>sameDevice(n,this.device))&&names.length)this.setDevice(primaryDevice(names,this.presets),true);
  this.emit("devices",this.devices);this._status()},
 _bridgeSeen(dev){if(dev&&!this.devices.some(d=>sameDevice(d.name,dev)))this._setDevices(this.devices.filter(d=>d.via==="bridge").concat([{name:dev,via:"bridge"}]),"bridge")},
 setDevice(name,quiet){name=String(name||"");if(name===this.device&&this.choice)return;this.releaseAll();this.device=name;
  const st=loadStore();st.version=2;st.devices=this.maps;st.active=name;saveStore(st);this._adoptLegacy();this._apply();
  if(!quiet)this.toast("MIDI map: "+(name||"no controller")+" · "+this.choice.label)},
 _ownKey(name){if(!name)return this.maps["*"]?"*":null;if(this.maps[name])return name;return Object.keys(this.maps).find(k=>sameDevice(k,name))||null},
 _own(name){const k=this._ownKey(name);return k?this.maps[k]:null},
 // the rows the active device plays on this page: its own map if it has one, else its default (preset, profile, generic)
 _apply(){const name=this.device;this.choice=pickDefault(name,this.presets);const own=this._own(name);
  this.personal=!!(own&&own.pages&&Array.isArray(own.pages[this.page]));
  this.profile=this.personal&&PROFILES[own.profile]?own.profile:this.choice.profile;
  this.mappings=this.personal?cloneRows(own.pages[this.page]):defaultRows(this.choice,this.page);this._rows={};
  this.emit("map",this.mappings);this.render()},
 // rows for an event from another connected controller (each controller plays its own map)
 rowsFor(name){if(!name||sameDevice(name,this.device))return this.mappings;if(this._rows[name])return this._rows[name];
  const own=this._own(name);return this._rows[name]=own&&own.pages&&Array.isArray(own.pages[this.page])?own.pages[this.page]:defaultRows(pickDefault(name,this.presets),this.page)},
 _adoptLegacy(){const L=this._legacy,name=this.device;if(!L||!name)return;const rows=L.mappings[this.page];
  if(this._own(name)||pickDefault(name,this.presets).profile!==L.profile||!isOwnLegacy(rows,L.profile,this.page))return;
  this.maps[name]={device:name,profile:L.profile,pages:{[this.page]:cloneRows(rows)},updated:Date.now()/1000};
  delete L.mappings[this.page];const st=loadStore();st.mappings=L.mappings;st.version=2;st.devices=this.maps;saveStore(st);
  this._push(name,{[this.page]:rows})},
 // the desk's copy: fetch every saved map and the shipped presets; the newer copy of a device wins, a local one that
 // is newer (saved while the desk was away) goes up
 _sync(){if(!window.fetch)return;fetch(api("/api/midi/maps")).then(r=>r.ok?r.json():null).then(j=>{if(!j)return;
   this.presets=Array.isArray(j.presets)?j.presets:[];this.mapsFile=j.file||"";const server=j.devices||{};
   for(const [k,e] of Object.entries(server)){const lk=this._ownKey(k),local=lk?this.maps[lk]:null;
    if(!local||(+e.updated||0)>=(+local.updated||0)){if(lk&&lk!==k)delete this.maps[lk];this.maps[k]=e}}
   for(const [k,e] of Object.entries(this.maps)){if(k==="*")continue;const sk=Object.keys(server).find(s=>sameDevice(s,k));
    if(!sk||(+server[sk].updated||0)<(+e.updated||0))this._push(k,e.pages,e.updated)}
   const st=loadStore();st.version=2;st.devices=this.maps;saveStore(st);this.saved="server";this._adoptLegacy();this._apply();this._status()})
  .catch(()=>{this.saved="this browser only";this._status()})},
 _push(name,pages,updated){if(!name||name==="*"||!window.fetch)return;clearTimeout(this._push_t[name]);
  const body={pages,profile:this.profile,updated:updated||Date.now()/1000};
  this._push_t[name]=setTimeout(()=>fetch(api("/api/midi/maps/"+encodeURIComponent(name)),{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
   .then(r=>{this.saved=r.ok?"server":"this browser only";this._status()}).catch(()=>{this.saved="this browser only";this._status()}),250)},
 // ---- events
 handle(ev,origin){this.last=ev;this.count++;this.log.push(ev);this.log.length>12&&this.log.shift();
  if(origin==="bridge"&&ev.dev)this._bridgeSeen(ev.dev);
  if(this.learnTarget&&(ev.type==="cc"||ev.type==="note")&&ev.value>0){this.bind(this.learnTarget,ev);return}
  if(this.share&&origin==="webmidi"&&this.ws&&this.ws.readyState===1)this.ws.send(JSON.stringify(ev));
  let hit=false;const sk=(ev.dev?bare(ev.dev)+"/":"")+srcKey(ev),off=isRelease(ev),rows=this.rowsFor(ev.dev);
  // a release lets go of whatever this control pressed, even if the map changed while it was held
  if(off&&this._held[sk]){const was=this._held[sk];delete this._held[sk];for(const h of was)if(holds.release(h.t)){hit=true;this.fire(h.t,h.lo,ev,h.row)}}
  for(const e of rows){if(!matches(e,ev))continue;if(e.mode==="hold"&&off)continue;
   const mode=e.mode||"abs",screen=(mode==="abs"&&ev.type!=="note")||mode==="rel"?this.read(e.target):null;
   if(mode==="rel"&&screen!=null)this.state[e.target]=screen;  // an encoder steps from the value on screen
   const r=resolve(e,ev,this.state);if(!r)continue;hit=true;
   if(mode==="abs"&&ev.type!=="note"){const k=rowKey(e),d=takeover.decide(k,r.value,screen,e.min==null?0:e.min,e.max==null?1:e.max);
    if(!d.apply){this._awayChanged(k);continue}this._awayChanged(k)}
   if(r.kind==="press"){const was=this._held[sk]||(this._held[sk]=[]);if(was.some(h=>h.t===r.target))continue;
    was.push({t:r.target,lo:+e.min||0,dev:ev.dev||"",via:origin,row:e});holds.press(r.target)}
   this.fire(r.target,r.value,ev,e)}
  if(this._opts.onEvent)this._opts.onEvent(ev,hit,origin);this.emit("event",ev,hit,origin);this._status(true)},
 // the value a target shows now, from the page (init({read})), for soft takeover; null when the page does not say
 read(target){const f=this._opts.read;if(!f)return null;try{const v=f(target);return typeof v==="number"&&isFinite(v)?v:null}catch(e){return null}},
 // {hw, screen, dir} when this row's hardware is away from the value it drives (the row's catch-up indicator)
 away(row){return takeover.away(rowKey(row))},
 _awayChanged(k){const a=takeover.away(k),sig=a?Math.round(a.hw*1000)+":"+Math.round(a.screen*1000):"";this._aways=this._aways||{};
  if(this._aways[k]===sig)return;this._aways[k]=sig;this._paintAway()},
 // a Web MIDI input went away (unplugged mid-hold): let go of what its pads held, the page snaps back (a pad held
 // through the bridge is not Web MIDI's to let go)
 _gone(names){for(const k of Object.keys(this._held)){const keep=this._held[k].filter(h=>h.via!=="webmidi"||!h.dev||names.includes(h.dev));
   for(const h of this._held[k])if(!keep.includes(h))holds.release(h.t);if(keep.length)this._held[k]=keep;else delete this._held[k]}},
 releaseAll(){this._held={};holds.clear()},
 fire(target,val,ev,entry){const h=this.handlers;const m=/^([a-z]+):(.+)$/.exec(target);
  if(h[target])return h[target](val,ev,entry);
  if(m&&h[m[1]+":*"])return h[m[1]+":*"](m[2],val,ev,entry);
  if(h["*"])h["*"](target,val,ev,entry)},
 // ---- mapping edits
 // one control drives one target and a target hears one control: binding a source to a target drops both old rows
 setRow(source,target,patch){const s={type:source.type,ch:+source.ch||0,num:+source.num},pc=controlOf(this.profile,s),[lo,hi]=range(target);
  this.mappings=this.mappings.filter(e=>e.target!==target&&srcKey(e.source)!==srcKey(s));
  const row=Object.assign({source:s,target,mode:modeFor(target,s.type,pc&&pc.mode),min:lo,max:hi,label:pc?pc.label:srcName(s)},patch||{});
  this.mappings.push(row);this.save();this.render();return row},
 bind(target,ev){const row=this.setRow({type:ev.type,ch:ev.ch,num:ev.num},target);this.learnTarget=null;
  if(!this._quiet)this.toast("MIDI: "+srcName(row.source)+" → "+this.name(target));this.emit("learned",row,ev);this.render()},
 learn(target,quiet){this.learnTarget=target||null;this._quiet=!!quiet;if(target&&!quiet)this.toast("Move a knob or hit a pad for "+this.name(target)+"…");
  this.emit("learn",this.learnTarget);this.render()},
 setLearnMode(on){this.learnMode=!!on;document.body.classList.toggle("midi-learn",this.learnMode);if(!on)this.learnTarget=null;
  this.toast(this.learnMode?"Learn: click a control on the page, then move a knob or hit a pad":"Learn off");this.emit("learn",this.learnTarget);this.render()},
 // plain words for a target, the page's own first (a pad's scene, a stem's name), then the shared ones
 name(t){const f=this._opts.targetName;let n=null;try{n=f&&f(t)}catch(e){}return n||targetName(t)},
 // the target a page control learns (the desk's "stem:Kick" lane learns as stem:3, so the map works on every song)
 canonical(t){const f=this._opts.canonical;let c=null;try{c=f&&f(t)}catch(e){}return c||t},
 rowsOf(t){const a=[t,this.canonical(t)];return this.mappings.filter(e=>a.includes(e.target))},
 rowOf(source){const k=srcKey(source);return this.mappings.find(e=>srcKey(e.source)===k)||null},
 updateRow(row,patch){const i=this.mappings.findIndex(e=>rowKey(e)===rowKey(row));if(i<0)return null;
  if(patch&&patch.target&&patch.target!==row.target)this.mappings=this.mappings.filter((e,j)=>j===i||e.target!==patch.target);
  const at=this.mappings.findIndex(e=>rowKey(e)===rowKey(row)),next=Object.assign({},this.mappings[at],patch||{});
  this.mappings[at]=next;this.save();this.render();return next},
 // Remove (with the map's Undo): the rows taken out, each with where it was
 removeRows(pred){const out=[];this.mappings.forEach((e,i)=>{if(pred(e))out.push({row:e,i})});if(!out.length)return out;
  this.mappings=this.mappings.filter(e=>!pred(e));this.save();this.render();return out},
 putBack(list){for(const {row,i} of (list||[]).slice().sort((a,b)=>a.i-b.i)){this.mappings=this.mappings.filter(e=>rowKey(e)!==rowKey(row)&&e.target!==row.target&&srcKey(e.source)!==srcKey(row.source));
   this.mappings.splice(Math.min(i,this.mappings.length),0,row)}this.save();this.render()},
 // the targets this page can drive: its own list, the page's extras, and every control on it that wears data-midi
 targets(){const base=this.page==="desk"?DESK_TARGETS:VJ_TARGETS,dom=window.XenoMidiMap?window.XenoMidiMap.domTargets():[];
  return[...new Set(base.concat(this._opts.extraTargets||[],dom))]},
 unmap(i){const gone=this.mappings.splice(i,1)[0];this.save();this.render();return gone},
 // put back a row Remove took out (the map's Undo)
 restore(row,i){if(!row)return;this.mappings=this.mappings.filter(e=>rowKey(e)!==rowKey(row));this.mappings.splice(i==null?this.mappings.length:Math.min(i,this.mappings.length),0,row);this.save();this.render()},
 add(target,source,mode,min,max){const[lo,hi]=range(target);this.mappings.push({source,target,mode:mode||modeFor(target,source.type),min:min==null?lo:min,max:max==null?hi:max});this.save();this.render()},
 // "Start from": the active controller takes a built-in profile's map as its own (when its name was not recognised)
 setProfile(name){if(!PROFILES[name])return;this.profile=name;this.releaseAll();this.mappings=profileMapping(name,this.page);this.save();this.render()},
 // Reset to default: the active controller's own rows for this page go; its preset, profile or generic map is back
 reset(){this.releaseAll();const name=this.device,k=this._ownKey(name),e=k?this.maps[k]:null;
  if(e&&e.pages){delete e.pages[this.page];e.updated=Date.now()/1000;if(!Object.keys(e.pages).length)delete this.maps[k]}
  const st=loadStore();st.version=2;st.devices=this.maps;saveStore(st);
  if(name&&window.fetch)fetch(api("/api/midi/maps/"+encodeURIComponent(name)+"?page="+encodeURIComponent(this.page)),{method:"DELETE"}).catch(()=>{});
  this._apply();this.toast("MIDI: "+(name||"this controller")+" is back on "+this.choice.label)},
 // the active controller's rows for this page become its own map: localStorage now, the desk's file a moment later
 save(more){const name=this.device||"*",k=this._ownKey(name)||name,e=this.maps[k]||(this.maps[k]={device:name,pages:{}});
  e.pages=e.pages||{};e.pages[this.page]=cloneRows(this.mappings);Object.assign(e.pages,more||{});e.profile=this.profile;e.updated=Date.now()/1000;
  this.personal=true;this._rows={};const st=loadStore();st.version=2;st.devices=this.maps;st.active=this.device;saveStore(st);
  this._push(k,Object.assign({[this.page]:e.pages[this.page]},more||{}),e.updated);this.emit("map",this.mappings)},
 exportJSON(){const e=this._own(this.device),pages=Object.assign({},(e&&e.pages)||{},{[this.page]:this.mappings});
  return JSON.stringify({kind:"xenoform-midi-map",version:2,device:this.device,profile:this.profile,page:this.page,mappings:this.mappings,pages},null,1)},
 // a file from Export (this page's rows in "mappings", every page in "pages"), or a bare list of rows; a shared layout's
 // other pages are kept for this controller too
 importJSON(text){const j=typeof text==="string"?JSON.parse(text):text;const rows=Array.isArray(j)?j:j.mappings||(j.pages&&j.pages[this.page]);
  if(!Array.isArray(rows))throw new Error("not a mapping file");
  const clean=rs=>rs.filter(r=>r&&r.source&&r.target).map(r=>({source:{type:r.source.type,ch:+r.source.ch||0,num:+r.source.num},target:String(r.target),mode:r.mode||"abs",min:+r.min||0,max:r.max==null?1:+r.max,label:r.label}));
  this.mappings=clean(rows);if(j.profile&&PROFILES[j.profile])this.profile=j.profile;const more={};
  if(j.pages&&typeof j.pages==="object")for(const [p,rs] of Object.entries(j.pages))if(p!==this.page&&Array.isArray(rs))more[p]=clean(rs);
  this.releaseAll();this.save(more);this.render();return this.mappings.length},
 // "Save as the shipped preset": the active controller's map for every page, written by the desk into
 // configs/midi_presets/<device>.json for the repository (the next clean install with it plugged in starts from it)
 shipPreset(label){const name=this.device;if(!name)return Promise.reject(new Error("Plug the controller in first: the preset is named after its port"));
  const e=this._own(name),pages={};for(const p of ["vj","desk"])pages[p]=p===this.page?this.mappings:(e&&e.pages&&e.pages[p])||defaultRows(this.choice,p);
  const prof=PROFILES[this.profile],match=prof&&reTest(prof.match,name)?prof.match:"";
  return fetch(api("/api/midi/presets"),{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({device:name,port:name,label:label||bare(name),profile:this.profile,match,pages})})
   .then(r=>r.json().then(j=>{if(!r.ok)throw new Error(j.detail||"the preset was not saved");this._sync();return j}))},
 // ---- the desk websocket (Python bridge fan-out), SSE when there is no websocket. The desk says first whether it can
 // upgrade one (/api/midi/status "websocket": the [midi] extra brings the websockets package); if not, straight to SSE,
 // so a desk without the extra no longer logs a failed /ws/midi on every page load.
 connect(){const base=(window.XENO_BASE||"");if(this.ws||this.es||this._asking)return;
  if(this._canWs==null&&window.fetch){this._asking=true;fetch(base+"/api/midi/status").then(r=>r.ok?r.json():{}).catch(()=>({})).then(j=>{
    this._asking=false;this._canWs=j.websocket!==false;this._bridgeNames(j.devices);this.connect()});return}
  if(this._canWs===false)return this.sse(base);let url;
  try{url=(location.protocol==="https:"?"wss://":"ws://")+location.host+base+"/ws/midi?name="+encodeURIComponent(this.page)}catch(e){return}
  let opened=false;const ws=new WebSocket(url);this.ws=ws;this.wsState="connecting";
  ws.onopen=()=>{opened=true;this.wsState="bridge";this._retry=0;this._status()};
  ws.onmessage=m=>{try{const ev=JSON.parse(m.data);if(ev&&ev.type==="hello")this._bridgeNames(ev.devices);else if(ev&&ev.type)this.handle(ev,"bridge")}catch(e){}};
  ws.onclose=ws.onerror=()=>{if(this.ws!==ws)return;this.ws=null;this.wsState="off";this._status();
   if(!opened&&(this._retry=(this._retry||0)+1)>=2)return this.sse(base);clearTimeout(this._timer);this._timer=setTimeout(()=>this.connect(),2500*Math.min(6,this._retry||1))}},
 // the ports the desk's bridge reads ({source: port}), from the status and the websocket's hello
 _bridgeNames(devs){this.bridgeDevices=devs&&typeof devs==="object"?devs:{};for(const n of Object.values(this.bridgeDevices))this._bridgeSeen(String(n||""))},
 sse(base){if(this.es||!window.EventSource)return;const es=new EventSource(base+"/api/midi/stream");this.es=es;this.wsState="sse";
  es.onmessage=m=>{try{const ev=JSON.parse(m.data);if(ev&&ev.type)this.handle(ev,"bridge")}catch(e){}};
  es.onerror=()=>{this.wsState="sse (reconnecting)";this._status()};this._status()},
 status(){return{inputs:this.inputs.slice(),bridge:this.wsState,profile:this.profile,mappings:this.mappings.length,events:this.count,last:this.last,
  learn:this.learnMode||!!this.learnTarget,held:holds.list(),devices:this.devices.slice(),device:this.device,
  map:this.personal?"your map":this.choice?this.choice.label:"",saved:this.saved}},
 _status(light){const s=this.status();if(this._opts.onStatus)this._opts.onStatus(s);this.emit("status",s,light);if(!light||this.count%8===0)this._paintStatus()},
 toast(t){if(this._opts.toast)this._opts.toast(t)},
 // ---- the map's face lives in midi_map.js (+ midi_map.css): the panel in a host (the desk's Knobs panel), the docked
 // panel on /vj, the badges on the page's controls and the Learn popover. panel()/dock() load it once, on demand, so a
 // page that loads /static/midi.js alone can still show the map.
 _face(){if(window.XenoMidiMap)return Promise.resolve(window.XenoMidiMap);if(this._loading)return this._loading;
  return this._loading=new Promise((ok,no)=>{if(!document.querySelector('link[data-xm-css]')){const l=document.createElement("link");l.rel="stylesheet";
    l.href=api("/static/midi_map.css");l.setAttribute("data-xm-css","");document.head.appendChild(l)}
   const s=document.createElement("script");s.src=api("/static/midi_map.js");s.onload=()=>window.XenoMidiMap?ok(window.XenoMidiMap):no(new Error("midi_map.js did not load"));
   s.onerror=()=>no(new Error("midi_map.js did not load"));document.head.appendChild(s)})},
 panel(el,o){this._el=el;this._face().then(F=>F.mount(el,Object.assign({page:this.page},o||{}))).catch(e=>console.error("midi map",e));return this},
 dock(o){this._face().then(F=>F.dock(Object.assign({page:this.page},o||{}))).catch(e=>console.error("midi map",e));return this},
 toggleDock(open){return this._face().then(F=>F.toggle(open)).catch(e=>console.error("midi map",e))},
 render(){if(window.XenoMidiMap)window.XenoMidiMap.refresh()},
 _paintStatus(){},
 // the catch-up arrow a row (the map paints it): the knob is away from the value it drives
 _paintAway(){if(this._opts.onAway)this._opts.onAway();this.emit("away")},
 ...core};
root.XenoMidiCore=core;root.XenoMidi=X;
})(typeof window!=="undefined"?window:this);
