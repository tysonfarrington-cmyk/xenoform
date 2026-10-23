// Xenoform UI v6: synth macro strip (4 knobs + an Advanced drawer of per-stem sliders). Values persist in localStorage
// ("xeno-macros") and ride on the job payload as `macros`; the server maps them onto beat FX intensity and wobble.
(function(){
  const KEY="xeno-macros";
  const KNOBS=[["intensity","Intensity","beat pulse and flash"],["speed","Speed","cut density and trail length"],["chaos","Chaos","punches, stutters and orbit swing"],["glow","Glow","bloom and halation"]];
  // Per-stem reaction lanes: the default four, or one lane per stem the song actually has (up to MAX_STEMS),
  // set with window.XENO_SET_STEMS(["Kick","Snare","Sub bass",...]) once stems are split or uploaded.
  const MAX_STEMS=32;
  const ROLE=n=>{n=String(n).toLowerCase();return /drum|kick|snare|hat|perc|beat|cymbal|tom|clap/.test(n)?"drums":/bass|sub|808/.test(n)?"bass":/vocal|vox|voice|choir|sing/.test(n)?"vocals":"other"};
  const lanesFor=names=>names.slice(0,MAX_STEMS).map(n=>["stem:"+n,n,`var(--st-${ROLE(n)})`]);
  let LANES=[["drums","Drums","var(--st-drums)"],["bass","Bass","var(--st-bass)"],["vocals","Vocals","var(--st-vocals)"],["other","Other","var(--st-other)"]];
  const DEF={intensity:.5,speed:.5,chaos:.3,glow:.4,drums:.7,bass:.7,vocals:.5,other:.4};
  const load=()=>{try{return Object.assign({},DEF,JSON.parse(localStorage.getItem(KEY)||"{}"))}catch(e){return Object.assign({},DEF)}};
  let M=load();
  // payload: the four knobs/role lanes as before, plus macros.stems = {name: 0..1} for per-stem lanes
  window.XENO_MACROS=()=>{const o={},st={};for(const k in M){if(k.startsWith("stem:"))st[k.slice(5)]=M[k];else o[k]=M[k];}
    if(Object.keys(st).length)o.stems=st;if(STEMS.id)o.stems_id=STEMS.id;return o;};
  // Stems on demand: opening "Stem reactions" asks the desk to split the current song (POST /api/stems, cached by
  // song hash), then the lanes become one per real stem. The song id comes from app.js: window.XENO_STATE().audioId
  // (set by /api/analyze or "demo"), or window.XENO_CURRENT_SONG(), or #easy-file[data-song]; else the bundled demo.
  const STEMS={id:"",song:"",status:"",engine:"",names:[]};
  const songId=()=>{try{const s=window.XENO_STATE&&window.XENO_STATE();if(s&&s.audioId)return s.audioId;}catch(e){}
    try{const c=window.XENO_CURRENT_SONG&&window.XENO_CURRENT_SONG();if(c)return typeof c==="string"?c:c.audioId||c.id||"demo";}catch(e){}
    const f=document.querySelector("#easy-file");return (f&&f.dataset.song)||"demo";};
  const stemsStatus=t=>{const el=document.querySelector(".xf-stems-status");if(el)el.textContent=t;};
  async function requestStems(){const id=songId();if(STEMS.song===id&&STEMS.status==="running")return;
    if(STEMS.song===id&&STEMS.status==="done"){stemsStatus(`${STEMS.names.length} stems (${STEMS.engine})`);return;}
    STEMS.song=id;STEMS.status="running";stemsStatus("splitting stems…");
    try{const api=p=>(window.XENO_BASE||"")+p;let r=await fetch(api("/api/stems"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({audio_id:id})});
      let j=await r.json();if(!r.ok)throw new Error(j.detail||"stems failed");
      while(j.status==="running"){await new Promise(res=>setTimeout(res,1500));if(STEMS.song!==id)return;stemsStatus(`splitting stems… (${j.engine||"auto"})`);
        r=await fetch(api("/api/stems/"+j.id));j=await r.json();}
      if(j.status!=="done")throw new Error(j.error||"stems failed");
      Object.assign(STEMS,{id:j.id,status:"done",engine:j.engine,names:j.stems||[]});
      if(STEMS.names.length)window.XENO_SET_STEMS(STEMS.names);stemsStatus(`${STEMS.names.length} stems (${STEMS.engine})`);}
    catch(e){STEMS.status="error";stemsStatus("stems: "+e.message);}}
  window.XENO_STEMS=()=>Object.assign({},STEMS);window.XENO_REQUEST_STEMS=requestStems;
  document.addEventListener("toggle",e=>{const d=e.target;if(d&&d.classList&&d.classList.contains("xf-adv")&&d.open)requestStems();},true);
  window.XENO_SET_STEMS=names=>{LANES=(names&&names.length)?lanesFor(names):LANES;
    for(const [k] of LANES)if(M[k]==null)M[k]=0.7;const s=document.querySelector(".xf-macros");s&&s.remove();mount();};
  // XENO_MACRO_SET(k, v): drive a knob ("intensity"...), a role lane ("drums") or a stem lane ("stem:Kick") from
  // MIDI or a script; repaints the control and persists like a hand move would.
  window.XENO_MACRO_SET=(k,v)=>{if(typeof v!=="number"||isNaN(v))return;M[k]=Math.max(0,Math.min(1,v));
    const kn=document.querySelector(`.xf-knob[data-k="${CSS.escape(k)}"]`);if(kn)paint(kn,k);
    const r=document.querySelector(`.xf-lane input[data-k="${CSS.escape(k)}"]`);if(r){r.value=pct(M[k]);r.style.setProperty("--p",r.value+"%");r.nextElementSibling.textContent=r.value;}
    clearTimeout(window.XENO_MACRO_SET.t);window.XENO_MACRO_SET.t=setTimeout(save,150);};
  const save=()=>{localStorage.setItem(KEY,JSON.stringify(M));};
  const pct=v=>Math.round(v*100);
  const ARC=(v)=>{const a0=-135,a1=a0+270*v,r=25,c=27,p=a=>[c+r*Math.sin(a*Math.PI/180),c-r*Math.cos(a*Math.PI/180)];
    const [x0,y0]=p(a0),[x1,y1]=p(a1),[xe,ye]=p(135);
    return `<path d="M${x0} ${y0} A${r} ${r} 0 1 1 ${xe} ${ye}" stroke="rgba(28,28,30,.1)" stroke-width="3" fill="none" stroke-linecap="round"/>`+
      (v>0.001?`<path d="M${x0} ${y0} A${r} ${r} 0 ${270*v>180?1:0} 1 ${x1} ${y1}" stroke="url(#xfg)" stroke-width="3" fill="none" stroke-linecap="round"/>`:"");};
  const knob=([k,l,hint])=>`<div class="xf-knob" data-k="${k}" role="slider" tabindex="0" aria-label="${l}" title="${hint||l}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct(M[k])}">
      <div class="dial"><svg viewBox="0 0 54 54"><defs><linearGradient id="xfg" x1="0" x2="1"><stop offset="0" stop-color="#8f74ff"/><stop offset="1" stop-color="#4b33e6"/></linearGradient></defs>${ARC(M[k])}</svg>
      <div class="cap"><i style="transform:rotate(${-135+270*M[k]}deg)"></i></div></div><b>${l}</b><small>${pct(M[k])}</small></div>`;
  const lane=([k,l,c])=>`<label class="xf-lane" title="${l}"><span><i style="background:${c}"></i>${l}</span>
      <input type="range" min="0" max="100" value="${pct(M[k])}" data-k="${k}" style="--c:${c};--p:${pct(M[k])}%" aria-label="${l} reaction"><output>${pct(M[k])}</output></label>`;
  const html=()=>`<section class="xf-macros" data-tour="easy-macros"><div class="xf-macros-head"><span>Knobs</span><button type="button" class="ghost" data-xf-reset>Reset</button></div>
      <div class="xf-knobs">${KNOBS.map(knob).join("")}</div>
      <details class="xf-adv"${STEMS.status?" open":""}><summary>Stem reactions <small class="xf-stems-status">${STEMS.status==="done"?`${STEMS.names.length} stems (${STEMS.engine})`:STEMS.status==="running"?"splitting stems…":""}</small></summary><div class="xf-lanes${LANES.length>8?" xf-many":""}" data-count="${LANES.length}">${LANES.map(lane).join("")}</div></details>
      <details class="xf-adv xf-midi"><summary>MIDI controller</summary><div class="xf-midi-panel"></div></details></section>`;
  function paint(el,k){const v=M[k];el.setAttribute("aria-valuenow",pct(v));el.querySelector("svg").innerHTML=el.querySelector("svg defs").outerHTML+ARC(v);
    el.querySelector(".cap i").style.transform=`rotate(${-135+270*v}deg)`;el.querySelector("small").textContent=pct(v);}
  function mount(){const host=document.querySelector(".simple-knobs")||document.querySelector(".simple-opts"); if(!host||host.querySelector(".xf-macros"))return;
    try{const box=document.createElement("div");box.innerHTML=html();const s=box.firstElementChild;
      const morph=host.querySelector(".morph-count"); morph?morph.after(s):host.prepend(s);midiMount();}
    catch(e){console.error("xenoform macros",e);}}
  // MIDI on the desk: midi.js (shared with /vj) drives the knobs and lanes; MiniLab 3 knobs 1-4 = the four macros,
  // knobs 5-8 = stem lanes 1-4, faders = drums/bass/other/vocals. "stem:N" means the Nth lane of this song.
  function midiInit(){const X=window.XenoMidi;if(!X||X._desk)return;X._desk=true;
    const laneName=n=>/^\d+$/.test(n)?(LANES[+n-1]||[])[0]||null:("stem:"+n);
    X.init({page:"desk",toast:t=>{const el=document.querySelector(".xf-stems-status");if(el){el.textContent=t;clearTimeout(midiInit.t);midiInit.t=setTimeout(()=>{if(el.textContent===t)el.textContent="";},1800);}},
      targets:{"macro:*":(k,v)=>window.XENO_MACRO_SET(k,v),drums:v=>window.XENO_MACRO_SET("drums",v),bass:v=>window.XENO_MACRO_SET("bass",v),
        other:v=>window.XENO_MACRO_SET("other",v),vocals:v=>window.XENO_MACRO_SET("vocals",v),
        "stem:*":(n,v)=>{const k=laneName(n);if(k&&M[k]!=null)window.XENO_MACRO_SET(k,v);}}});midiMount();}
  function midiMount(){const X=window.XenoMidi,el=document.querySelector(".xf-midi-panel");if(X&&X._desk&&el&&!el.firstChild)X.panel(el);}
  if(!window.XenoMidi){const sc=document.createElement("script");sc.src=(window.XENO_BASE||"")+"/static/midi.js";sc.onload=midiInit;document.head.appendChild(sc);}else midiInit();
  let drag=null;
  document.addEventListener("pointerdown",e=>{const k=e.target.closest&&e.target.closest(".xf-knob");if(!k)return;
    drag={el:k,k:k.dataset.k,y:e.clientY,v:M[k.dataset.k]};k.setPointerCapture(e.pointerId);e.preventDefault();});
  document.addEventListener("pointermove",e=>{if(!drag)return;const v=Math.max(0,Math.min(1,drag.v+(drag.y-e.clientY)/160));M[drag.k]=v;paint(drag.el,drag.k);});
  document.addEventListener("pointerup",()=>{if(drag){save();drag=null;}});
  document.addEventListener("dblclick",e=>{const k=e.target.closest&&e.target.closest(".xf-knob");if(!k)return;M[k.dataset.k]=DEF[k.dataset.k];paint(k,k.dataset.k);save();});
  document.addEventListener("keydown",e=>{const k=e.target.closest&&e.target.closest(".xf-knob");if(!k)return;
    const d={ArrowUp:.05,ArrowRight:.05,ArrowDown:-.05,ArrowLeft:-.05}[e.key];if(d==null)return;e.preventDefault();
    M[k.dataset.k]=Math.max(0,Math.min(1,M[k.dataset.k]+d));paint(k,k.dataset.k);save();});
  document.addEventListener("input",e=>{const r=e.target.closest&&e.target.closest(".xf-lane input");if(!r)return;
    M[r.dataset.k]=r.value/100;r.style.setProperty("--p",r.value+"%");r.nextElementSibling.textContent=r.value;save();});
  document.addEventListener("click",e=>{if(e.target.closest&&e.target.closest("[data-xf-reset]")){M=Object.assign({},DEF);save();
    const s=document.querySelector(".xf-macros");s&&s.remove();mount();}});
  // Hide shot-strip tiles whose library still is missing (new vibes ship a hero thumbnail, not a 4-shot strip).
  function strips(){document.querySelectorAll(".strip-shot:not([data-xf])").forEach(s=>{s.dataset.xf="1";
    const m=/url\(["']?([^"')]+)/.exec(s.style.backgroundImage||"");if(!m)return;const im=new Image();
    im.onerror=()=>{s.classList.add("xf-missing");const p=s.parentElement;if(p&&![...p.children].some(c=>!c.classList.contains("xf-missing")))p.classList.add("xf-strip-empty");};im.src=m[1];});}
  new MutationObserver(()=>requestAnimationFrame(strips)).observe(document.getElementById("app")||document.body,{childList:true,subtree:true});
  new MutationObserver(()=>requestAnimationFrame(mount)).observe(document.getElementById("app")||document.body,{childList:true,subtree:true});
  window.addEventListener("load",mount);
})();
