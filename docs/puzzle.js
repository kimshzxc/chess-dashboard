/* 오늘의 퍼즐: 내가 실제로 틀린 국면에서 최선 수 찾기. shared.js 다음에 module 로 로드된다. */
document.body.insertAdjacentHTML('afterbegin', await fetch('pieces.svg').then(r=>r.text()));
const ALL = await fetch('puzzles.json',{cache:'no-cache'}).then(r=>r.json());
$('#tpanel-slot').innerHTML=themePanel(); applyMode();

const TODAY=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);   // KST 날짜
const DAILY=10;
function seeded(str){ let h=1779033703^str.length; for(let i=0;i<str.length;i++){ h=Math.imul(h^str.charCodeAt(i),3432918353); h=h<<13|h>>>19; } return ()=>{ h=Math.imul(h^h>>>16,2246822507); h=Math.imul(h^h>>>13,3266489909); return ((h^=h>>>16)>>>0)/4294967296; }; }
function shuffled(arr,seed){ const r=seeded(seed), a=arr.slice(); for(let i=a.length-1;i>0;i--){ const j=Math.floor(r()*(i+1)); [a[i],a[j]]=[a[j],a[i]]; } return a; }
const ORDER=shuffled(ALL,TODAY);
const KEY='puzzle-'+TODAY;
let ST={idx:0,res:[]};
try{ const s=JSON.parse(localStorage.getItem(KEY)||'null'); if(s&&s.res) ST=s; }catch(e){}
const save=()=>{ try{localStorage.setItem(KEY,JSON.stringify(ST))}catch(e){} };

/* 날짜별 기록 → 연속 일수와 최근 7일 */
let HIST={}; try{ HIST=JSON.parse(localStorage.getItem('puzzle-history')||'{}')||{}; }catch(e){}
function record(ok){ const h=HIST[TODAY]||{ok:0,n:0}; h.n++; if(ok) h.ok++; HIST[TODAY]=h; try{localStorage.setItem('puzzle-history',JSON.stringify(HIST))}catch(e){} }
const dkey=(off)=>new Date(Date.now()+9*3600*1000-off*864e5).toISOString().slice(0,10);
function streakCard(){
  let n=0, off=HIST[dkey(0)]?0:1; while(HIST[dkey(off)]){ n++; off++; }
  const tot=Object.values(HIST).reduce((a,h)=>[a[0]+h.ok,a[1]+h.n],[0,0]);
  const mx=Math.max(1,...Array.from({length:7},(_,i)=>(HIST[dkey(i)]||{}).n||0));
  const days='일월화수목금토';
  const week=Array.from({length:7},(_,i)=>{ const k=dkey(6-i), h=HIST[k]; const d=days[new Date(k+'T00:00:00Z').getUTCDay()];
    return `<div><i class="${h?'has':''}" style="height:${h?Math.max(8,Math.round(h.n/mx*36)):4}px" title="${k}"></i>${d}</div>`; }).join('');
  return `<div class="card streakcard"><div><div class="sub">연속 풀이</div><div class="n">${n}<small>일</small></div><div class="sub">누적 정답 ${tot[0]} / ${tot[1]}${tot[1]?` (${Math.round(tot[0]/tot[1]*100)}%)`:''}</div></div><div class="week">${week}</div></div>`;
}
let SEL=null, ANSWERED=false;
const cur=()=>ORDER[ST.idx];
const colorName=c=>c==='w'?'백':'흑';

function render(){
  const total=Math.min(DAILY,ORDER.length);
  if(!ORDER.length){ $('#main').innerHTML='<div class="empty">퍼즐이 아직 없습니다.</div>'; return; }
  const w=cur(); const inDaily=ST.idx<total;
  let h=streakCard()+`<div class="prog"><div><b>${inDaily?'오늘의 퍼즐':'추가 퍼즐'}</b> <span class="sub">${inDaily?`${ST.idx+1} / ${total}`:`${ST.idx+1}번째 · 오늘 정답 ${ST.res.filter(x=>x==='ok').length}/${ST.res.length}`}</span></div>`;
  if(inDaily) h+=`<div class="dots">${Array.from({length:total},(_,i)=>`<i class="${ST.res[i]||''} ${i===ST.idx?'cur':''}"></i>`).join('')}</div>`;
  h+=`</div>`;
  if(!w){ h+=summary(); $('#main').innerHTML=h; return; }
  h+=`<div class="task">${colorName(w.color)}차례 · 최선 수를 찾으세요<div class="sub">${w.date} · vs ${esc(w.opp)} · ${w.move}수 · ${PH[w.phase]||''}</div></div>`;
  h+=`<div class="pzboard" id="pzboard"></div>`;
  h+=`<div id="pzresult"></div>`;
  h+=`<div class="acts" id="pzacts"><span class="btn" id="giveup">모르겠어요</span></div>`;
  $('#main').innerHTML=h;
  drawBoard();
}
function summary(){
  const ok=ST.res.filter(x=>x==='ok').length;
  return `<div class="card done"><div class="sub">오늘의 퍼즐 끝</div><div class="big">${ok} / ${ST.res.length}</div><div class="sub">${ok>=ST.res.length*0.7?'좋습니다. 실전에서도 한 번 더 보고 두세요.':'틀린 국면은 게임 페이지에서 수순을 다시 보세요.'}</div></div>`;
}
function drawBoard(extra={}){
  const w=cur(); const flip=w.color==='b';
  $('#pzboard').innerHTML=boardSVG(w.fen,{flip,last:SEL?[SEL]:[],arrows:extra.arrows||[]});
  applyTheme();
}
function squareAt(svg,e){
  const r=svg.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*800, py=(e.clientY-r.top)/r.height*800;
  let fx=Math.floor(px/100), ry=Math.floor(py/100); if(fx<0||fx>7||ry<0||ry>7) return null;
  if(cur().color==='b'){ fx=7-fx; ry=7-ry; }
  return FILES[fx]+(8-ry);
}
function mine(sq){ const w=cur(); const p=parseFen(w.fen).find(x=>x.sq===sq); return p&&p.p[0]===w.color; }
function answer(uci){
  const w=cur(); ANSWERED=true;
  const ok=uci.slice(0,4)===(w.best_uci||'').slice(0,4);
  ST.res[ST.idx]=ok?'ok':'ng'; save(); record(ok);
  $('#pzboard').classList.add(ok?'ok':'ng');
  const gave=uci==='----';
  drawBoard({arrows:[...(gave?[]:[[uci,ok?GREEN:RED]]),...(ok?[]:[[w.best_uci,GREEN]])]});
  if(gave) ST.res[ST.idx]='ng';
  let msg=gave?`<span class="ic">정답 공개</span>최선은 <b>${esc(w.best)}</b> 입니다. 실전에서는 <span class="mono">${esc(w.san)}</span> 을 두어 승률을 ${w.wp_loss}%p 잃었습니다 (${ev(w.cp_before)} → ${ev(w.cp_after)}).`:ok?`<span class="ic">정답</span><b>${esc(w.best)}</b> 가 최선입니다. 실전에서는 <span class="mono">${esc(w.san)}</span> 을 두어 승률을 ${w.wp_loss}%p 잃었습니다.`
           :`<span class="ic">오답</span>정답은 <b>${esc(w.best)}</b> 입니다. 실전에서도 <span class="mono">${esc(w.san)}</span> 을 두어 승률을 ${w.wp_loss}%p 잃었습니다 (${ev(w.cp_before)} → ${ev(w.cp_after)}).`;
  $('#pzresult').innerHTML=`<div class="result ${ok?'ok':'ng'}">${msg}</div>`+(w.best_line&&w.best_line.length?blunderViewer(w):'');
  drawAll($('#pzresult')); applyTheme();
  $('#pzacts').innerHTML=`<a class="btn" href="game.html?id=${gameId(w.url)}&ply=${w.ply}">게임에서 보기</a><span class="btn on" id="next">다음 퍼즐 ›</span>`;
  $('#next').scrollIntoView({behavior:'smooth',block:'nearest'});
}
document.addEventListener('pointerdown',(e)=>{
  const svg=e.target.closest('#pzboard svg.board'); if(!svg||ANSWERED) return;
  const sq=squareAt(svg,e); if(!sq) return;
  if(SEL&&sq!==SEL&&!mine(sq)){ const u=SEL+sq; SEL=null; answer(u); return; }
  if(SEL&&sq!==SEL&&mine(sq)){ SEL=sq; drawBoard(); return; }
  if(mine(sq)){ SEL=(SEL===sq?null:sq); drawBoard(); }
});
document.addEventListener('click',(e)=>{
  if(e.target.closest('#giveup')){ if(!ANSWERED) answer('----'); return; }
  if(e.target.closest('#next')){ ST.idx++; SEL=null; ANSWERED=false; save(); render(); window.scrollTo(0,0); }
});
render();
if(new URLSearchParams(location.search).get('reveal')==='1'&&cur()) answer('----');   // ?reveal=1 → 정답 바로 보기
