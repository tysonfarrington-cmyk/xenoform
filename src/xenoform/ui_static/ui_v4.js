// Xenoform UI v4: animated vibe previews (hover + selected) and gallery hover-play. Pure progressive enhancement.
(function(){
  const clipFor = card => `/static/library/${card.dataset.vibe}/wide.mp4`;
  function ensure(card){
    const th = card.querySelector('.vibe-thumb'); if(!th) return null;
    let v = th.querySelector('video.vibe-anim');
    if(!v){ v=document.createElement('video'); v.className='vibe-anim'; v.muted=true; v.loop=true; v.playsInline=true; v.preload='none';
      v.src=(window.XENO_BASE||'')+clipFor(card); v.addEventListener('playing',()=>v.classList.add('live')); th.appendChild(v); }
    return v;
  }
  function play(card){const v=ensure(card); if(v) v.play().catch(()=>{});}
  function stop(card){const v=card.querySelector('video.vibe-anim'); if(v && !card.classList.contains('on')){v.pause(); v.classList.remove('live');}}
  document.addEventListener('mouseover',e=>{const c=e.target.closest&&e.target.closest('.vibe-card:not(.is-mini)'); if(c) play(c);
    const g=e.target.closest&&e.target.closest('.gallery-card'); if(g){const v=g.querySelector('video'); v&&v.play().catch(()=>{});}});
  document.addEventListener('mouseout',e=>{const c=e.target.closest&&e.target.closest('.vibe-card'); if(c&&!c.contains(e.relatedTarget)) stop(c);
    const g=e.target.closest&&e.target.closest('.gallery-card'); if(g&&!g.contains(e.relatedTarget)){const v=g.querySelector('video'); v&&v.pause();}});
  function sync(){document.querySelectorAll('.vibe-card.on:not(.is-mini)').forEach(play);}
  new MutationObserver(()=>requestAnimationFrame(sync)).observe(document.getElementById('app')||document.body,{childList:true,subtree:true});
  window.addEventListener('load',sync);
})();
