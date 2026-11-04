// Xenoform MIDI map: the controller on the same screen as the controls (UI_REVIEW 6.5; C7, V3, A5). midi.js is the
// mapping layer; this is its face, the same on the desk (the Knobs panel's "MIDI controller" row) and on /vj (a docked
// panel, never a modal):
//  - the panel: the controller and its map in plain words, an activity light, Map (the controller drawn from its
//    profile with what every control does) or the list of rows, Learn, and under More: Reset to default, Export,
//    Import, Start from, Save as the shipped preset;
//  - a badge (K1, A2, F3) on every control of the page that a controller can drive ([data-midi], [data-midi-slot], the
//    desk's knobs and stem lanes), shown while a controller is connected or Learn is on;
//  - Learn as a popover anchored to the control: click a badge, a control in Learn mode or a drawn control, then move a
//    knob or hit a pad; the mode and range are there, Done keeps it, Clear removes it (with Undo), Esc puts it back.
// window.XenoMidiMap = {mount(host, {page}), dock({page}), toggle(open), refresh(), domTargets(), learnAt(el, target)}.
(function(){
"use strict";
const X=window.XenoMidi,C=window.XenoMidiCore;
if(!X||!C||window.XenoMidiMap)return;
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const UIKEY="xeno-midi-ui";
const ui=(()=>{try{return JSON.parse(localStorage.getItem(UIKEY)||"{}")||{}}catch(e){return{}}})();
const keepUi=()=>{try{localStorage.setItem(UIKEY,JSON.stringify(ui))}catch(e){}};
const views=[];let pop=null,undo=null,layer=null,badges=new Map(),queued=0,dockEl=null;
const rowKey=e=>C.srcKey(e.source)+">"+e.target;
const sameSrc=(s,c)=>s.type===c.type&&+s.num===+c.num&&(!+s.ch||!+c.ch||+s.ch===+c.ch);
const rowForControl=c=>X.mappings.find(e=>sameSrc(e.source,c))||null;
const shortOf=s=>C.shortName(X.profile,s);
const pct=(row,v)=>Math.round(100*(v-(+row.min||0))/((row.max==null?1:+row.max)-(+row.min||0)||1));
function catchHTML(row){const a=row&&X.away(row);if(!a)return"";
 return`<em class="xm-catch" title="${esc(`The control is at ${pct(row,a.hw)}, the screen at ${pct(row,a.screen)}: turn it ${a.dir>0?"up":"down"} past ${pct(row,a.screen)} to take over`)}">${a.dir>0?"▲":"▼"}</em>`}

// ---------------------------------------------------------------- the page's controls
const SEL='[data-midi],[data-midi-slot],.xf-knob[data-k],.xf-lane input[data-k]';
const inFace=el=>!!(el&&el.closest&&el.closest(".xm,.xm-pop,.xm-badges,[data-xm-ui]"));
function targetOf(el){if(!el||!el.closest||inFace(el))return null;const m=el.closest("[data-midi],[data-midi-slot]");
 if(m)return m.getAttribute("data-midi")||m.getAttribute("data-midi-slot");
 const k=el.closest(".xf-knob[data-k]");if(k)return"macro:"+k.dataset.k;
 const l=el.closest(".xf-lane");if(l){const i=l.querySelector("input[data-k]");if(i)return i.dataset.k}
 const map=X._opts.elements||{},e=el.closest("[id]");return e&&map[e.id]||null}
function mappables(){const out=[...document.querySelectorAll(SEL)],map=X._opts.elements||{};
 for(const id of Object.keys(map)){const e=document.getElementById(id);if(e&&!out.includes(e))out.push(e)}
 return out.filter(e=>!inFace(e))}

// ---------------------------------------------------------------- the panel
function stateLine(){const dev=X.device,d=X.devices.find(o=>C.sameDevice(o.name,dev)),on=!!d;
 const map=X.personal?"your map":X.choice?X.choice.label+(X.choice.kind==="preset"?" (shipped preset)":"")+" map":"";
 return{on,name:on?dev:"No controller",sub:on?[d.via==="bridge"?"via the bridge":"Web MIDI",map].filter(Boolean).join(" · "):"plug one in and allow MIDI"}}
function cellHTML(c,kind){const row=rowForControl(c),t=row?X.name(row.target):"nothing";
 return`<button type="button" class="xm-ctl xm-${kind}${row?"":" is-free"}" data-ctl="${esc(c.id)}" data-type="${c.type}" data-num="${c.num}" data-ch="${+c.ch||0}"${row?` data-key="${esc(rowKey(row))}"`:""}
  aria-label="${esc(c.short+", "+c.label+": "+t+". Change it")}"><i class="xm-light" aria-hidden="true"></i><b>${esc(c.short)}</b><span>${esc(row?t:"—")}</span>${catchHTML(row)}</button>`}
// the controller drawn from its profile's layout (UI_REVIEW 6.5's "Map"): each control with its badge name, what it does
// here in plain words, a light and the catch-up arrow; a zone with nothing on this page folds into one line
function boardHTML(){const p=C.PROFILES[X.profile]||C.PROFILES.generic,L=p.layout||{},byId=id=>p.controls.find(c=>c.id===id),idle=[];
 const zone=(name,ids,kind,cols,label)=>{const cs=(ids||[]).map(byId).filter(Boolean);if(!cs.length)return"";
  if(!cs.some(rowForControl)){idle.push(label||name);return""}
  return`<div class="xm-zone">${name?`<span class="xm-zone-name">${esc(name)}</span>`:""}<div class="xm-grid xm-grid-${kind}" style="--xm-cols:${cols||cs.length}">${cs.map(c=>cellHTML(c,kind)).join("")}</div></div>`};
 const known=new Set(p.controls.map(c=>c.type+":"+c.num)),others=X.mappings.filter(e=>!known.has(e.source.type+":"+e.source.num));
 const mini=p===C.PROFILES.minilab3,pads=(L.pads||[]).map((ids,i)=>{const n=mini?"Pads "+"AB"[i]:i?"Pads 9-16":"Pads 1-8";return zone(n,ids,"pad",8)}).join("");
 const knobs=(L.knobs||[]).map((ids,i)=>zone(i?"":"Knobs",ids,"knob",4,"Knobs")).join("");
 const body=knobs+zone(mini?"Faders":"Sliders",L.faders,"fader",4)+pads+zone("Strips and encoder",L.extra,"extra",2)+
  (others.length?`<div class="xm-zone"><span class="xm-zone-name">Other controls</span><div class="xm-grid xm-grid-pad" style="--xm-cols:4">${others.map(e=>cellHTML({id:rowKey(e),short:shortOf(e.source),label:C.srcName(e.source),type:e.source.type,num:e.source.num,ch:e.source.ch},"pad")).join("")}</div></div>`:"");
 return`<div class="xm-board" data-profile="${esc(X.profile)}">${body||`<p class="xm-note">Nothing on this controller drives this page yet.</p>`}
  ${idle.length?`<p class="xm-note">Not used on this page: ${esc([...new Set(idle)].join(", "))}. Learn puts anything on them.</p>`:""}
  ${L.note&&mini&&pads?`<p class="xm-note">${esc(L.note)}</p>`:""}</div>`}
function rowsHTML(){if(!X.mappings.length)return`<p class="xm-note">Nothing is mapped. Press Learn, click a control, then move a knob or hit a pad.</p>`;
 return`<ul class="xm-rows">${X.mappings.map(e=>{const n=X.name(e.target),s=shortOf(e.source);
  return`<li class="xm-row" data-key="${esc(rowKey(e))}" data-type="${e.source.type}" data-num="${e.source.num}" data-ch="${+e.source.ch||0}">
   <i class="xm-light" aria-hidden="true"></i><b class="xm-short">${esc(s)}</b><span class="xm-what"><span>${esc(n)}</span><small>${esc((e.label||C.srcName(e.source))+" · "+(C.MODE_NAMES[e.mode]||e.mode))}</small></span>${catchHTML(e)}
   <button type="button" class="text xm-relearn" aria-label="${esc("Learn "+n+" again")}">Learn</button>
   <button type="button" class="text xm-remove" aria-label="${esc("Remove "+s+" from "+n)}">Remove</button></li>`}).join("")}</ul>`}
function panelHTML(v){const st=stateLine(),mapOn=ui.map!==false,many=X.devices.length>1;
 return`<section class="xm${v.dock?" xm-in-dock":""}" data-tour="midi" aria-label="MIDI map">
  <header class="xm-head">
   <span class="xm-state${st.on?" is-on":""}" role="status"><i class="xm-light" data-xm-any aria-hidden="true"></i><b>${esc(st.name)}</b><small>${esc(st.sub)}</small></span>
   ${many?`<select class="xm-pick" aria-label="Controller to show">${X.devices.map(d=>`<option value="${esc(d.name)}"${C.sameDevice(d.name,X.device)?" selected":""}>${esc(d.name)}</option>`).join("")}</select>`:""}
   <span class="xm-acts toggle" role="group" aria-label="MIDI map view">
    <button type="button" class="xm-map${mapOn?" on":""}" aria-pressed="${mapOn}">Map</button><button type="button" class="xm-list${mapOn?"":" on"}" aria-pressed="${!mapOn}">List</button></span>
   <button type="button" class="ghost xm-learn${X.learnMode?" on":""}" aria-pressed="${X.learnMode}" title="Learn: click a control on the page, then move a knob or hit a pad (L on /vj)">Learn</button>
   ${v.dock?`<button type="button" class="text xm-close" aria-label="Close the MIDI map">Close</button>`:""}
  </header>
  ${st.on?"":`<p class="xm-note">No controller yet. Plug one in and allow MIDI (Chrome, Edge, Opera). Firefox or Safari: run <code>xenoform midi serve</code>.</p>`}
  ${X.learnMode?`<p class="xm-hint" role="status">Learn is on: click a control on the page, then move a knob or hit a pad. Esc stops.</p>`:""}
  ${mapOn?boardHTML():rowsHTML()}
  <p class="xm-undo" role="status" hidden></p>
  <details class="xm-more"><summary>More</summary><div class="xm-more-body">
   <button type="button" class="text xm-reset">Reset to default</button>
   <button type="button" class="text xm-export">Export</button>
   <label class="text xm-import">Import<input type="file" accept="application/json,.json" hidden></label>
   <label class="xm-from">Start from <select class="xm-profile">${Object.keys(C.PROFILES).map(k=>`<option value="${k}"${k===X.profile?" selected":""}>${esc(C.PROFILES[k].label)}</option>`).join("")}</select></label>
   <button type="button" class="text xm-ship" title="Write this controller's map, every page, into configs/midi_presets for the repository">Save as the shipped preset</button>
   <p class="xm-note">Saved for each controller on this desk${X.mapsFile?` (<code>${esc(X.mapsFile)}</code>)`:""} and in this browser${X.saved==="this browser only"?": the desk did not answer, so only in this browser for now":""}.</p>
  </div></details></section>`}
function wire(v){const el=v.el,q=s=>el.querySelector(s);
 q(".xm-map").onclick=()=>{ui.map=true;keepUi();refresh()};q(".xm-list").onclick=()=>{ui.map=false;keepUi();refresh()};
 q(".xm-learn").onclick=()=>X.setLearnMode(!X.learnMode);
 const pick=q(".xm-pick");if(pick)pick.onchange=e=>X.setDevice(e.target.value);
 const close=q(".xm-close");if(close)close.onclick=()=>toggle(false);
 q(".xm-reset").onclick=()=>X.reset();
 q(".xm-export").onclick=()=>{const t=X.exportJSON(),a=document.createElement("a");a.href=URL.createObjectURL(new Blob([t],{type:"application/json"}));
  a.download=`xenoform-midi-${(C.bare(X.device)||"controller").replace(/[^A-Za-z0-9]+/g,"-")}.json`;document.body.appendChild(a);a.click();a.remove();X.toast("MIDI map exported")};
 q(".xm-import input").onchange=e=>{const f=e.target.files&&e.target.files[0];if(!f)return;f.text().then(t=>{const n=X.importJSON(t);X.toast(n+" mappings imported for "+(X.device||"this controller"))})
  .catch(err=>X.toast("Import failed: "+err.message));e.target.value=""};
 q(".xm-profile").onchange=e=>X.setProfile(e.target.value);
 q(".xm-ship").onclick=()=>X.shipPreset().then(j=>X.toast("Shipped preset written: "+j.path)).catch(err=>X.toast("Not saved: "+err.message));
 el.querySelectorAll(".xm-ctl").forEach(b=>b.onclick=()=>openPop(b,{kind:"source",source:{type:b.dataset.type,num:+b.dataset.num,ch:+b.dataset.ch},id:b.dataset.ctl}));
 el.querySelectorAll(".xm-row").forEach(li=>{const row=X.mappings.find(e=>rowKey(e)===li.dataset.key);if(!row)return;
  li.querySelector(".xm-relearn").onclick=ev=>openPop(ev.currentTarget,{kind:"target",target:row.target});
  li.querySelector(".xm-remove").onclick=()=>{const gone=X.removeRows(e=>rowKey(e)===rowKey(row));offerUndo(gone,shortOf(row.source)+" → "+X.name(row.target))}})}
function render(v){const more=v.el.querySelector(".xm-more"),open=more&&more.open,a=document.activeElement,mine=a&&v.el.contains(a);
 const ctl=mine&&a.dataset&&a.dataset.ctl,focus=mine&&!ctl?[...a.classList].find(c=>/^xm-/.test(c)):null;
 v.el.innerHTML=panelHTML(v);wire(v);if(open)v.el.querySelector(".xm-more").open=true;
 const f=ctl?v.el.querySelector(`.xm-ctl[data-ctl="${CSS.escape(ctl)}"]`):focus?v.el.querySelector("."+focus):null;if(f)f.focus({preventScroll:true});
 if(undo)paintUndo();if(pop&&!pop.anchor.isConnected)place()}
function refresh(){if(queued)return;queued=1;const go=()=>{queued=0;views.forEach(v=>{if(v.el.isConnected)render(v)});paintState();paintBadges()};
 (window.requestAnimationFrame&&document.visibilityState==="visible"?requestAnimationFrame:setTimeout)(go,0);setTimeout(()=>{if(queued)go()},60)}
// the desk's row title and /vj's MIDI button say whether a controller is there
function paintState(){const st=stateLine();document.querySelectorAll("[data-xm-state]").forEach(e=>{e.classList.toggle("xm-on",st.on);
 if(e.getAttribute("data-xm-state")==="name")e.textContent=st.on?st.name:""})}

// ---------------------------------------------------------------- Remove, with Undo
function offerUndo(gone,what){if(!gone||!gone.length)return;clearTimeout(undo&&undo.t);undo={gone,what,t:setTimeout(()=>{undo=null;paintUndo()},8000)};paintUndo()}
function paintUndo(){views.forEach(v=>{const p=v.el.querySelector(".xm-undo");if(!p)return;p.hidden=!undo;if(!undo){p.innerHTML="";return}
 p.innerHTML=`Removed ${esc(undo.what)}. <button type="button" class="text xm-undo-go">Undo</button>`;
 p.querySelector(".xm-undo-go").onclick=()=>{const u=undo;clearTimeout(u.t);undo=null;X.putBack(u.gone);X.toast("Put back: "+u.what)}})}

// ---------------------------------------------------------------- the Learn popover
function modeOptions(type,cur){const list=type==="note"?["hold","toggle","trigger","abs"]:["abs","rel","hold","toggle","trigger"];
 return list.map(m=>`<option value="${m}"${m===cur?" selected":""}>${esc(C.MODE_NAMES[m])}</option>`).join("")}
function rangeHTML(row){if(!row||row.mode==="rel"&&row.target==="fx:step")return"";
 return`<div class="xm-pop-row"><label>From <input type="number" class="xm-min" step="0.05" value="${+row.min||0}"></label><label>to <input type="number" class="xm-max" step="0.05" value="${row.max==null?1:+row.max}"></label></div>`}
function popHTML(spec){const target=spec.kind==="target"?X.canonical(spec.target):null;
 if(spec.kind==="target"){const row=X.rowsOf(spec.target)[0]||null,n=X.name(spec.target);
  return`<div class="xm-pop-head"><b>${esc(n)}</b><button type="button" class="text xm-x" aria-label="Cancel: put the map back as it was">Cancel</button></div>
   <p class="xm-listen"><i class="xm-light is-listening" aria-hidden="true"></i>Move a knob or hit a pad…</p>
   <p class="xm-heard">${row?`Heard: <b>${esc(C.srcName(row.source))}</b> <small>(${esc(shortOf(row.source))}${row.label&&row.label!==C.srcName(row.source)?", "+esc(row.label):""})</small>`:"Nothing yet."}</p>
   ${row?`<div class="xm-pop-row"><label>Mode <select class="xm-mode">${modeOptions(row.source.type,row.mode)}</select></label></div>${rangeHTML(row)}`:""}
   <div class="xm-pop-foot"><button type="button" class="generate xm-done">Done</button><button type="button" class="ghost xm-clear"${row?"":" disabled"}>Clear</button></div>`}
 const row=rowForControl(spec.source),c=C.controlOf(X.profile,spec.source),title=(c?c.short+" · "+c.label:shortOf(spec.source));
 const T=X.targets();if(row&&!T.includes(row.target))T.push(row.target);
 return`<div class="xm-pop-head"><b>${esc(title)}</b><button type="button" class="text xm-x" aria-label="Cancel: put the map back as it was">Cancel</button></div>
  <p class="xm-heard"><i class="xm-light" data-xm-src aria-hidden="true"></i>${esc(C.srcName(spec.source))} <small>moves light this up</small></p>
  <div class="xm-pop-row"><label>Does <select class="xm-target"><option value="">Nothing</option>${T.map(t=>`<option value="${esc(t)}"${row&&row.target===t?" selected":""}>${esc(X.name(t))}</option>`).join("")}</select></label></div>
  ${row?`<div class="xm-pop-row"><label>Mode <select class="xm-mode">${modeOptions(spec.source.type,row.mode)}</select></label></div>${rangeHTML(row)}`:""}
  <div class="xm-pop-foot"><button type="button" class="generate xm-done">Done</button><button type="button" class="ghost xm-clear"${row?"":" disabled"}>Clear</button></div>`}
// the anchor re-rendered under the popover (a binding changed the panel, the desk redrew its knobs): find its successor,
// the drawn control with the same id or the page control with the same target; else stay where it was
function reanchor(){if(!pop||pop.anchor.isConnected)return;const s=pop.spec;let n=null;
 if(s.kind==="source"&&s.id)n=document.querySelector(`.xm-ctl[data-ctl="${CSS.escape(s.id)}"]`);
 else if(s.kind==="target"){const c=X.canonical(s.target);n=mappables().find(e=>{const t=targetOf(e);return t&&X.canonical(t)===c})||null}
 if(n)pop.anchor=n}
function place(){if(!pop)return;reanchor();const live=pop.anchor.isConnected,r=live?pop.anchor.getBoundingClientRect():pop.rect;if(!r)return;if(live)pop.rect=r;
 const w=Math.min(300,innerWidth-16),el=pop.el;el.style.width=w+"px";
 const h=el.offsetHeight||200,below=r.bottom+8+h<=innerHeight||r.top<h+16;
 el.style.left=Math.max(8,Math.min(innerWidth-w-8,r.left+r.width/2-w/2))+"px";el.style.top=Math.max(8,below?r.bottom+8:r.top-h-8)+"px"}
function paintPop(){if(!pop)return;const p=pop,el=p.el;el.innerHTML=popHTML(p.spec);const q=s=>el.querySelector(s);
 const row=()=>p.spec.kind==="target"?X.rowsOf(p.spec.target)[0]||null:rowForControl(p.spec.source);
 q(".xm-x").onclick=()=>closePop(false);q(".xm-done").onclick=()=>closePop(true);
 q(".xm-clear").onclick=()=>{const r=row();if(!r)return;const gone=X.removeRows(e=>rowKey(e)===rowKey(r));offerUndo(gone,shortOf(r.source)+" → "+X.name(r.target));closePop(true)};
 const m=q(".xm-mode");if(m)m.onchange=()=>{const r=row();if(r){X.updateRow(r,{mode:m.value});paintPop()}};
 const lo=q(".xm-min"),hi=q(".xm-max");[lo,hi].forEach(i=>{if(i)i.onchange=()=>{const r=row(),a=parseFloat(lo.value),b=parseFloat(hi.value);if(r&&isFinite(a)&&isFinite(b))X.updateRow(r,{min:a,max:b})}});
 const t=q(".xm-target");if(t)t.onchange=()=>{const r=row();if(!t.value){if(r)X.removeRows(e=>rowKey(e)===rowKey(r))}else X.setRow(Object.assign({},r?r.source:p.spec.source),t.value);paintPop()};
 place()}
function openPop(anchor,spec){closePop(true);const el=document.createElement("div");el.className="xm-pop";el.setAttribute("role","dialog");
 el.setAttribute("aria-label",spec.kind==="target"?"Learn: "+X.name(spec.target):"Change "+shortOf(spec.source));document.body.appendChild(el);
 pop={el,anchor,spec,snap:X.mappings.map(e=>Object.assign({},e,{source:Object.assign({},e.source)}))};
 if(spec.kind==="target"){X.learn(X.canonical(spec.target),true);pop.off=X.on("learned",r=>{if(!pop)return;paintPop();X.learn(X.canonical(spec.target),true)})}
 paintPop();const f=el.querySelector(".xm-target,.xm-done");if(f)f.focus()}
// Done (or a click outside) keeps what was heard; Esc and the corner button put the map back as it was
function closePop(keep){if(!pop)return;const p=pop;pop=null;if(p.off)p.off();if(X.learnTarget)X.learn(null,true);
 if(!keep){X.mappings=p.snap;X.save();X.render()}p.el.remove();if(p.anchor&&p.anchor.isConnected&&p.anchor.focus)try{p.anchor.focus({preventScroll:true})}catch(e){}}

// ---------------------------------------------------------------- badges on the page's controls
function badgeFor(el){let b=badges.get(el);if(b)return b;b=document.createElement("button");b.type="button";b.className="xm-badge";
 b.onclick=e=>{e.preventDefault();e.stopPropagation();const t=targetOf(el);if(t)openPop(el,{kind:"target",target:t})};layer.appendChild(b);badges.set(el,b);return b}
function paintBadges(){if(!layer){layer=document.createElement("div");layer.className="xm-badges";layer.setAttribute("data-xm-ui","");document.body.appendChild(layer)}
 const show=X.devices.length>0||X.learnMode,seen=new Set();layer.hidden=!show;
 if(show)for(const el of mappables()){const t=targetOf(el);if(!t)continue;const rows=X.rowsOf(t),label=rows.length?shortOf(rows[0].source):X.learnMode?"+":"";
  const r=el.getBoundingClientRect();if(!label||!r.width||!r.height||r.bottom<0||r.top>innerHeight||el.closest("[hidden],.hide"))continue;
  const cx=Math.min(innerWidth-1,Math.max(0,r.left+r.width/2)),cy=Math.min(innerHeight-1,Math.max(0,r.top+r.height/2)),hit=document.elementFromPoint(cx,cy);
  if(hit&&!(el===hit||el.contains(hit)||hit.contains(el)))continue;  // under a dialog, a menu or a sticky header
  const b=badgeFor(el);seen.add(el);b.textContent=label;b.classList.toggle("is-free",!rows.length);b.dataset.target=X.canonical(t);
  b.setAttribute("aria-label",rows.length?label+" drives "+X.name(t)+": change":"Learn "+X.name(t));
  b.style.left=Math.round(Math.min(innerWidth-24,r.right-12))+"px";b.style.top=Math.round(Math.max(2,r.top-9))+"px";b.hidden=false}
 for(const [el,b] of badges)if(!seen.has(el)){if(!el.isConnected){b.remove();badges.delete(el)}else b.hidden=true}}
let moved=0;const onMove=()=>{if(moved)return;moved=1;setTimeout(()=>{moved=0;paintBadges();place()},40)};
addEventListener("scroll",onMove,{capture:true,passive:true});addEventListener("resize",onMove);
// the page moved something (a re-render, a drawer opening): place the badges again; their own moves, the map's lights
// and a canvas resizing every frame do not count
new MutationObserver(recs=>{if(recs.some(r=>{const t=r.target;return t&&t.nodeType===1&&t.tagName!=="CANVAS"&&!inFace(t)}))onMove()})
 .observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:["class","hidden","open","style"]});

// ---------------------------------------------------------------- activity: a light a row, a drawn control, a badge
function flash(el){el.classList.add("hot");clearTimeout(el._xmT);el._xmT=setTimeout(()=>el.classList.remove("hot"),160)}
X.on("event",ev=>{const hits=X.rowsFor(ev.dev).filter(e=>C.matches(e,ev)),targets=new Set(hits.map(e=>e.target));
 const mine=d=>d.type===ev.type&&+d.num===+ev.num&&(!+d.ch||+d.ch===+ev.ch);
 views.forEach(v=>{const a=v.el.querySelector("[data-xm-any]");if(a)flash(a);v.el.querySelectorAll(".xm-ctl,.xm-row").forEach(e=>{if(mine(e.dataset))flash(e)})});
 if(pop){const s=pop.el.querySelector("[data-xm-src]");if(s&&pop.spec.kind==="source"&&mine({type:pop.spec.source.type,num:pop.spec.source.num,ch:pop.spec.source.ch}))flash(s)}
 for(const [,b] of badges)if(!b.hidden&&targets.has(b.dataset.target))flash(b)});
X.on("away",()=>views.forEach(v=>v.el.querySelectorAll("[data-key]").forEach(e=>{const row=X.mappings.find(r=>rowKey(r)===e.dataset.key);
 const old=e.querySelector(".xm-catch"),html=catchHTML(row);if(old)old.remove();if(html)e.insertAdjacentHTML("beforeend",html)})));
X.on("map",refresh);X.on("devices",refresh);X.on("learn",refresh);X.on("status",(s,light)=>{if(!light)refresh()});

// ---------------------------------------------------------------- Learn mode: a click on any control opens its popover
document.addEventListener("click",e=>{if(!X.learnMode||inFace(e.target))return;const el=e.target.closest&&e.target.closest(SEL+(Object.keys(X._opts.elements||{}).map(id=>",#"+CSS.escape(id)).join("")));
 const t=el&&targetOf(el);if(!t)return;e.preventDefault();e.stopPropagation();openPop(el,{kind:"target",target:t})},true);
document.addEventListener("pointerdown",e=>{if(pop&&!pop.el.contains(e.target)&&!(pop.anchor&&pop.anchor.contains(e.target))&&!(e.target.closest&&e.target.closest(".xm-badge")))closePop(true);
 if(X.learnMode&&!inFace(e.target)&&targetOf(e.target)){e.preventDefault();e.stopPropagation()}},true);
// Esc closes the popover (putting the map back) or ends Learn, and goes no further: on the desk Esc also means Stop
document.addEventListener("keydown",e=>{if(e.key!=="Escape")return;if(pop){e.preventDefault();e.stopPropagation();closePop(false)}
 else if(X.learnMode){e.preventDefault();e.stopPropagation();X.setLearnMode(false)}},true);
// typing in the map's own fields (a range, the controller picker) never reaches a page's single-key shortcuts (/vj
// listens on window: 0-8 pick a transition, M mirror, R record...)
document.addEventListener("keydown",e=>{if(e.key!=="Escape"&&inFace(e.target)&&e.target.matches&&e.target.matches("input,select,textarea"))e.stopPropagation()});

// ---------------------------------------------------------------- a control the page marked but gave no handler
// [data-midi="feel"] on a row of chips: a knob picks along it, a pad steps to the next; a marked range or select follows
// the knob; a marked button presses. Only what a page marked: an unmarked control is never pressed by MIDI.
function drive(t,v,ev,row){let el=null;try{el=document.querySelector(`[data-midi="${CSS.escape(t)}"],[data-midi-slot="${CSS.escape(t)}"]`)}catch(e){}if(!el)return;
 const mode=(row&&row.mode)||"abs",lo=row?+row.min||0:0,hi=row&&row.max!=null?+row.max:1,f=Math.max(0,Math.min(1,(v-lo)/((hi-lo)||1)));
 if(el.matches('input[type="range"]')){const a=el.min===""?0:+el.min,b=el.max===""?100:+el.max;el.value=String(a+(b-a)*f);el.dispatchEvent(new Event("input",{bubbles:true}));return}
 if(el.matches("select")){const i=Math.min(el.options.length-1,Math.floor(f*el.options.length));if(i>=0&&el.selectedIndex!==i){el.selectedIndex=i;el.dispatchEvent(new Event("change",{bubbles:true}))}return}
 const kids=el.matches("button,a")?[]:[...el.querySelectorAll("button:not([disabled]),.chip:not([disabled])")];
 if(kids.length){if(mode==="abs"){const i=Math.min(kids.length-1,Math.floor(f*kids.length));if(el._xmIdx!==i){el._xmIdx=i;kids[i].click()}}
  else if(v>lo||mode==="toggle"){const cur=kids.findIndex(k=>k.classList.contains("on"));kids[(cur+1)%kids.length].click()}return}
 if(mode==="abs"){const up=f>=.5;if(up&&!el._xmUp)el.click();el._xmUp=up}else if(mode!=="hold"||v>lo)el.click()}
if(!X.handlers["*"])X.handlers["*"]=drive;

// ---------------------------------------------------------------- mounting
function mount(host,o){if(!host)return null;for(let i=views.length-1;i>=0;i--)if(!views[i].el.isConnected)views.splice(i,1);  // a desk re-render left it behind
 let v=views.find(w=>w.el===host);if(!v){v={el:host,page:(o&&o.page)||X.page,dock:!!(o&&o.dock)};views.push(v)}
 render(v);paintState();paintBadges();return v}
// /vj: a docked panel beside the picture (never the help modal); #midi-panel when the page has one, else a new <aside>
function dock(o){if(!dockEl){dockEl=document.getElementById("midi-panel")||document.createElement("aside");if(!dockEl.isConnected)document.body.appendChild(dockEl);
  dockEl.classList.add("xm-dock");dockEl.setAttribute("data-xm-ui","");dockEl.hidden=!ui.dock;mount(dockEl,Object.assign({},o,{dock:true}))}return dockEl}
function toggle(open){if(!dockEl)dock({page:X.page});const on=open==null?dockEl.hidden:!!open;dockEl.hidden=!on;ui.dock=on;keepUi();
 document.querySelectorAll("[data-xm-toggle]").forEach(b=>{b.classList.toggle("on",on);b.setAttribute("aria-expanded",String(on))});if(on)refresh();return on}
window.XenoMidiMap={mount,dock,toggle,refresh,learnAt:(el,t)=>openPop(el,{kind:"target",target:t||targetOf(el)}),
 domTargets:()=>[...new Set(mappables().map(targetOf).filter(Boolean).map(t=>X.canonical(t)))],views,get open(){return!!pop}};
})();
