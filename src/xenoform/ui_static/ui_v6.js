// Xenoform UI v6: synth macro strip (4 knobs + an Advanced drawer of per-stem sliders). Values persist in localStorage
// ("xeno-macros") and ride on the job payload as `macros`; the server maps them onto beat FX intensity and wobble.
(function(){
  const KEY="xeno-macros";
  const KNOBS=[["intensity","Intensity"],["speed","Speed"],["chaos","Chaos"],["glow","Glow"]];
  const LANES=[["drums","Drums","var(--st-drums)"],["bass","Bass","var(--st-bass)"],["vocals","Vocals","var(--st-vocals)"],["other","Other","var(--st-other)"]];
  const DEF={intensity:.5,speed:.5,chaos:.3,glow:.4,drums:.7,bass:.7,vocals:.5,other:.4};
  const load=()=>{try{return Object.assign({},DEF,JSON.parse(localStorage.getItem(KEY)||"{}"))}catch(e){return Object.assign({},DEF)}};
  let M=load(); window.XENO_MACROS=()=>Object.assign({},M);
  const save=()=>{localStorage.setItem(KEY,JSON.stringify(M));};
  const pct=v=>Math.round(v*100);
  const ARC=(v)=>{const a0=-135,a1=a0+270*v,r=25,c=27,p=a=>[c+r*Math.sin(a*Math.PI/180),c-r*Math.cos(a*Math.PI/180)];
    const [x0,y0]=p(a0),[x1,y1]=p(a1),[xe,ye]=p(135);
    return `<path d="M${x0} ${y0} A${r} ${r} 0 1 1 ${xe} ${ye}" stroke="rgba(28,28,30,.1)" stroke-width="3" fill="none" stroke-linecap="round"/>`+
      (v>0.001?`<path d="M${x0} ${y0} A${r} ${r} 0 ${270*v>180?1:0} 1 ${x1} ${y1}" stroke="url(#xfg)" stroke-width="3" fill="none" stroke-linecap="round"/>`:"");};
  const knob=([k,l])=>`<div class="xf-knob" data-k="${k}" role="slider" tabindex="0" aria-label="${l}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct(M[k])}">
      <div class="dial"><svg viewBox="0 0 54 54"><defs><linearGradient id="xfg" x1="0" x2="1"><stop offset="0" stop-color="#8f74ff"/><stop offset="1" stop-color="#4b33e6"/></linearGradient></defs>${ARC(M[k])}</svg>
      <div class="cap"><i style="transform:rotate(${-135+270*M[k]}deg)"></i></div></div><b>${l}</b><small>${pct(M[k])}</small></div>`;
  const lane=([k,l,c])=>`<label class="xf-lane"><span><i style="background:${c}"></i>${l}</span>
      <input type="range" min="0" max="100" value="${pct(M[k])}" data-k="${k}" style="--c:${c};--p:${pct(M[k])}%" aria-label="${l} reaction"><output>${pct(M[k])}</output></label>`;
  const html=()=>`<section class="xf-macros" data-tour="easy-macros"><div class="xf-macros-head"><span>Macros</span><button type="button" class="ghost" data-xf-reset>Reset</button></div>
      <div class="xf-knobs">${KNOBS.map(knob).join("")}</div>
      <details class="xf-adv"><summary>Stem reactions</summary><div class="xf-lanes">${LANES.map(lane).join("")}</div></details></section>`;
  function paint(el,k){const v=M[k];el.setAttribute("aria-valuenow",pct(v));el.querySelector("svg").innerHTML=el.querySelector("svg defs").outerHTML+ARC(v);
    el.querySelector(".cap i").style.transform=`rotate(${-135+270*v}deg)`;el.querySelector("small").textContent=pct(v);}
  function mount(){const host=document.querySelector(".simple-opts"); if(!host||host.querySelector(".xf-macros"))return;
    const box=document.createElement("div");box.innerHTML=html();const s=box.firstElementChild;
    const morph=host.querySelector(".morph-count"); morph?morph.after(s):host.prepend(s);}
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
