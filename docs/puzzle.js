/* 오늘의 퍼즐: 내가 실제로 틀린 국면에서 좋은 수 찾기. shared.js 다음에 module 로 로드된다.
   상태는 모두 이 기기의 localStorage 에 있다.
   puzzle-day      오늘 낼 문제 묶음과 진행 {date, ids[], pz{id:퍼즐}, rv{id:true}, res{id:'ok'|'ng'}, idx, daily, cont}
                   하루 중 새 게임이 들어와 puzzles.json 이 바뀌어도 오늘의 문제는 그대로다.
   puzzle-review   틀린 문제의 복습 일정 {id:{due, step, pz}}  1일 → 3일 → 7일 뒤에 다시. 틀리면 처음부터.
   puzzle-seen     풀어 본 문제 {id:날짜}  새 문제를 고를 때 안 푼 것부터 낸다.
   puzzle-history  날짜별 기록 {date:{ok,n}}  연속 일수와 최근 7일 막대. */
try{ document.body.insertAdjacentHTML('afterbegin', await fetch('pieces.svg').then(r=>{ if(!r.ok) throw new Error(`pieces.svg ${r.status}`); return r.text(); })); }catch(e){ loadError(e); throw e; }
const ALL = await fetch('puzzles.json',{cache:'no-cache'}).then(r=>r.ok?r.json():[]).catch(()=>[]);
$('#tpanel-slot').innerHTML=themePanel(); applyMode(); $('#pnav').innerHTML=practiceNav('puzzle');

const DAY=864e5, DAILY=10, STEPS=[1,3,7], MAX_REVIEW=80, MAX_SEEN=600;
const dkey=kstDay;   // KST 날짜, off 일 뒤 (shared.js)
const TODAY=dkey(0);
/* 설치형 앱을 자정 너머 켜 둔 채 돌아오면 어제 묶음에 오늘 기록이 붙는다. 날짜가 바뀌었으면 다시 불러온다 */
const dayCheck=()=>{ if(document.visibilityState==='visible'&&dkey(0)!==TODAY) location.reload(); };
document.addEventListener('visibilitychange',dayCheck); window.addEventListener('pageshow',dayCheck);
const HIST=load('puzzle-history',{}), REVIEW=load('puzzle-review',{}), SEEN=load('puzzle-seen',{});
const BYID=Object.fromEntries(ALL.map(p=>[p.id,p]));
const colorName=c=>c==='w'?'백':'흑';
/* 유형 연습: puzzle.html?cat=<실수 유형> 이면 그 유형의 퍼즐만 낸다. 오늘의 묶음(puzzle-day)은 건드리지 않고
   진행은 이 탭(sessionStorage)에만 둔다. 채점 기록·복습 일정·연속 일수에는 평소처럼 반영된다. */
const CAT=new URLSearchParams(location.search).get('cat');
const WIN=CAT==='win';     // 굳히기: 유리하던(+3 이상) 국면에서 무너진 수만 모은 묶음. 가장 큰 약점(유리한 판 마무리)을 겨냥한다
/* 국면·시간 묶음: phase:opening|middlegame|endgame, clock (남은 시간 1분 아래). 통계가 지적하는 약점을 바로 연습한다 */
const SETS={'phase:opening':{n:'오프닝 국면',rule:'오프닝에서는 전개와 킹 안전을 먼저 보고, 상대의 위협을 매 수 확인한다',f:p=>p.phase==='opening'},
  'phase:middlegame':{n:'중반전 국면',rule:'중반전에서는 두기 전에 상대의 체크·잡는 수·위협을 한 번 훑는다',f:p=>p.phase==='middlegame'},
  'phase:endgame':{n:'엔드게임 국면',rule:'엔드게임에서는 킹을 활동시키고 폰의 통과 가능성을 먼저 센다',f:p=>p.phase==='endgame'},
  clock:{n:'시간 압박 (1분 아래)',rule:'시간이 적을수록 단순한 수를 고르고, 상대의 체크와 잡는 수만은 꼭 본다',f:p=>p.clock!=null&&p.clock<60}};
const SET=CAT&&SETS[CAT]?CAT:null;
const PRACTICE=WIN||!!SET||!!(CAT&&CATS[CAT]);
const catInfo=()=>WIN?{n:'굳히기 (유리할 때)',rule:'유리하면 기물을 교환해 단순화하고, 매 수 상대의 체크와 잡는 수부터 확인한다'}:SET?SETS[SET]:catOf(CAT);
const inSet=(p)=>WIN?p.win:SET?SETS[SET].f(p):p.cat===CAT;
const COACH=await fetch('coach.json',{cache:'no-cache'}).then(r=>r.ok?r.json():null).catch(()=>null);
const NCAT={}; for(const p of ALL) if(p.cat) NCAT[p.cat]=(NCAT[p.cat]||0)+1;

function seeded(str){ let h=1779033703^str.length; for(let i=0;i<str.length;i++){ h=Math.imul(h^str.charCodeAt(i),3432918353); h=h<<13|h>>>19; } return ()=>{ h=Math.imul(h^h>>>16,2246822507); h=Math.imul(h^h>>>13,3266489909); return ((h^=h>>>16)>>>0)/4294967296; }; }
function shuffled(arr,seed){ const r=seeded(seed), a=arr.slice(); for(let i=a.length-1;i>0;i--){ const j=Math.floor(r()*(i+1)); [a[i],a[j]]=[a[j],a[i]]; } return a; }
/* 새 문제 후보: 복습 중이 아닌 것. 안 풀어 본 것이 먼저, 그다음 푼 지 오래된 것 */
function candidates(exclude,seed){
  const pool=shuffled(ALL.filter(p=>!REVIEW[p.id]&&!exclude.has(p.id)),seed);
  return [...pool.filter(p=>!SEEN[p.id]), ...pool.filter(p=>SEEN[p.id]).sort((a,b)=>SEEN[a.id].localeCompare(SEEN[b.id]))];
}
function buildDay(){
  const due=Object.entries(REVIEW).filter(([,r])=>r.due<=TODAY).sort((a,b)=>a[1].due.localeCompare(b[1].due)).slice(0,5).map(([id])=>id);
  const fresh=candidates(new Set(due),TODAY).slice(0,DAILY-due.length).map(p=>p.id);
  const d={date:TODAY, ids:[], pz:{}, rv:{}, res:{}, idx:0, daily:0, cont:false};
  for(const id of [...due,...fresh]){ const p=BYID[id]||(REVIEW[id]&&REVIEW[id].pz); if(!p) continue; d.ids.push(id); d.pz[id]=p; if(REVIEW[id]) d.rv[id]=true; }
  d.daily=d.ids.length;
  return d;
}
function buildPractice(){
  const pool=shuffled(ALL.filter(inSet),TODAY+CAT);
  const d={date:TODAY, ids:[], pz:{}, rv:{}, res:{}, idx:0, daily:0, cont:false, practice:CAT};
  for(const p of [...pool.filter(p=>!SEEN[p.id]), ...pool.filter(p=>SEEN[p.id]).sort((a,b)=>SEEN[a.id].localeCompare(SEEN[b.id]))]){ d.ids.push(p.id); d.pz[p.id]=p; if(REVIEW[p.id]) d.rv[p.id]=true; }
  d.daily=d.ids.length;
  return d;
}
const saveDay=()=>{ if(!PRACTICE) return save('puzzle-day',TD); try{ sessionStorage.setItem('puzzle-practice',JSON.stringify(TD)); }catch(e){} };
let TD;
if(PRACTICE){
  try{ TD=JSON.parse(sessionStorage.getItem('puzzle-practice')||'null'); }catch(e){ TD=null; }
  if(!TD||TD.date!==TODAY||TD.practice!==CAT||!Array.isArray(TD.ids)){ TD=buildPractice(); saveDay(); }
} else {
  TD=load('puzzle-day',null);
  if(!TD||TD.date!==TODAY||!Array.isArray(TD.ids)){ TD=buildDay(); saveDay(); }
}
const cur=()=>TD.pz[TD.ids[TD.idx]];
const answered=()=>{ const w=cur(); return w?TD.res[w.id]:null; };
/* 오늘의 묶음을 다 풀었으면 추가 문제를 하나 붙인다. 더 없으면 false */
function ensureCurrent(){
  if(TD.idx<TD.ids.length) return true;
  if(PRACTICE) return false;
  const nx=candidates(new Set(TD.ids),TODAY+'+')[0]; if(!nx) return false;
  TD.ids.push(nx.id); TD.pz[nx.id]=nx; saveDay(); return true;
}

let SEL=null, T0=0;   // T0: 지금 문제를 보여 준 시각 (푸는 데 걸린 시간)
function headHTML(){
  let n=0, off=HIST[dkey(0)]?0:-1; while(HIST[dkey(off)]){ n++; off--; }
  const tot=Object.values(HIST).reduce((a,h)=>[a[0]+h.ok,a[1]+h.n,a[2]+(h.s||0),a[3]+(h.sn||0)],[0,0,0,0]);
  const mx=Math.max(1,...[0,1,2,3,4,5,6].map(i=>(HIST[dkey(-i)]||{}).n||0));
  const week=[6,5,4,3,2,1,0].map(i=>{ const k=dkey(-i), h=HIST[k]; return `<div><i class="${h?'has':''}" style="height:${h?Math.max(8,Math.round(h.n/mx*36)):4}px"></i>${'일월화수목금토'[new Date(k+'T00:00:00Z').getUTCDay()]}</div>`; }).join('');
  const waiting=Object.keys(REVIEW).length;
  let h=`<div class="card streakcard"><div><div class="sub">연속 풀이</div><div class="n">${n}<small>일</small></div><div class="sub">누적 정답 ${tot[0]} / ${tot[1]}${tot[1]?` (${Math.round(tot[0]/tot[1]*100)}%)`:''}${tot[3]?` · 평균 ${Math.round(tot[2]/tot[3])}초`:''}${waiting?` · 복습 대기 ${waiting}개`:''}</div></div><div class="week">${week}</div></div>`;
  const focus=(COACH&&COACH.focus)||[];
  const keys=Object.keys(NCAT).filter(k=>CATS[k]).sort((a,b)=>(focus.includes(b)-focus.includes(a))||NCAT[b]-NCAT[a]);
  if(keys.length) h+=`<div class="pzmodes"><a class="${PRACTICE?'':'on'}" href="puzzle.html">오늘의 10문제</a><a class="win ${WIN?'on':''}" href="puzzle.html?cat=win">굳히기 ${ALL.filter(p=>p.win).length}</a>${Object.entries(SETS).map(([k,s])=>{ const n=ALL.filter(s.f).length; return n?`<a class="set ${k===SET?'on':''}" href="puzzle.html?cat=${k}">${s.n.replace(/ \(.*\)| 국면/,'')} ${n}</a>`:''; }).join('')}${keys.map(k=>`<a class="${k===CAT?'on':''}" href="puzzle.html?cat=${k}">${esc(catOf(k).n)} ${NCAT[k]}</a>`).join('')}</div>`;
  const inDaily=TD.idx<TD.daily, vals=Object.values(TD.res);
  if(PRACTICE) return h+`<div class="rule" style="margin-top:12px"><span>두기 전에</span>${esc(catInfo().rule)}</div><div class="prog"><div><b>${esc(catInfo().n)}</b> <span class="sub">유형 연습 ${Math.min(TD.idx+1,TD.daily)} / ${TD.daily} · 정답 ${vals.filter(x=>x==='ok').length} / ${vals.length}</span></div></div>`;
  h+=`<div class="prog"><div><b>${inDaily?'오늘의 퍼즐':'추가 퍼즐'}</b> <span class="sub">${inDaily?`${TD.idx+1} / ${TD.daily}`:`오늘 정답 ${vals.filter(x=>x==='ok').length} / ${vals.length}`}</span></div>`;
  if(inDaily) h+=`<div class="dots">${TD.ids.slice(0,TD.daily).map((id,i)=>`<i class="${TD.res[id]||''} ${i===TD.idx?'cur':''}"></i>`).join('')}</div>`;
  return h+`</div>`;
}
function render(){
  if(!ALL.length&&!TD.ids.length){ $('#main').innerHTML='<div class="empty">퍼즐이 아직 없습니다. 게임이 분석되면 생깁니다.</div>'; return; }
  if(PRACTICE&&TD.idx>=TD.daily){   // 유형 연습 끝 (또는 이 유형의 퍼즐이 없음)
    const ok=Object.values(TD.res).filter(x=>x==='ok').length;
    $('#main').innerHTML=`<div id="pzhead">${headHTML()}</div><div class="card done"><div class="sub">${TD.daily?`${esc(catInfo().n)} 연습 끝`:'이 유형의 퍼즐이 아직 없습니다'}</div>${TD.daily?`<div class="big">${ok} / ${TD.daily}</div><div class="sub">틀린 문제는 오늘의 퍼즐에 복습으로 다시 나옵니다.</div>`:''}<div class="acts"><a class="btn" href="${WIN?'index.html#stats':`index.html?cat=${CAT}#mistakes`}">${WIN?'대시보드':'이 유형 사례'}</a><a class="btn on" href="puzzle.html">오늘의 퍼즐 ›</a></div></div>`;
    return;
  }
  if(TD.daily&&TD.idx===TD.daily&&!TD.cont){   // 오늘의 묶음 끝
    const ok=TD.ids.slice(0,TD.daily).filter(id=>TD.res[id]==='ok').length;
    $('#main').innerHTML=`<div id="pzhead">${headHTML()}</div><div class="card done"><div class="sub">오늘의 퍼즐 끝</div><div class="big">${ok} / ${TD.daily}</div><div class="sub">틀린 문제는 내일부터 복습으로 다시 나옵니다.</div><div class="acts"><a class="btn" href="index.html">대시보드</a><span class="btn on" id="more">더 풀기 ›</span></div></div>`;
    return;
  }
  if(!ensureCurrent()){ $('#main').innerHTML=`<div id="pzhead">${headHTML()}</div><div class="card done"><div class="sub">지금 낼 수 있는 문제를 모두 풀었습니다</div><div class="sub" style="margin-top:6px">새 게임이 분석되면 문제가 추가됩니다.</div></div>`; return; }
  const w=cur();
  let h=`<div id="pzhead">${headHTML()}</div>`;
  h+=`<div class="task">${TD.rv[w.id]?'<span class="rv">복습</span>':''}${colorName(w.color)} 차례 · 가장 좋은 수를 찾으세요<div class="sub">${esc(w.date)} · vs ${esc(w.opp)} · ${w.move}수 · ${PH[w.phase]||''}</div></div>`;
  h+=`<div class="boardwrap">${evalBarHTML('pzeval')}<div class="pzboard" id="pzboard"></div></div><div class="toast" id="pztoast"></div><div id="pzresult"></div><div class="acts" id="pzacts"></div>`;
  $('#main').innerHTML=h;
  pzBar(w.cp_before);
  if(answered()) showAnswer((TD.mv||{})[w.id],true);
  else { $('#pzacts').innerHTML=`<span class="btn" id="giveup">모르겠어요</span>`; drawBoard(); T0=Date.now(); }
}
/* 판 왼쪽 평가 막대. cp 는 둘 쪽(나) 기준이라 백 기준으로 바꿔 넣는다 */
function pzBar(cp){ const w=cur(); setEvalBar($('#pzeval'), cp==null?null:(w.mover==='w'?cp:-cp), w.color==='b'); }
/* 둔 수 뒤의 평가(둘 쪽 기준). 최선·실전의 수는 깊은 분석값, 비슷한 정답은 수순 계산값, 나머지는 모든 수 평가(moves, 얕은 깊이라 최선보다 높게는 잡지 않는다).
   모르는 수(예전 퍼즐)는 null */
function moveCp(w,uci){
  if(uci==null) return w.cp_before;
  const u=uci.slice(0,4);
  if(u===w.best_uci.slice(0,4)) return w.cp_before;
  if(u===w.uci.slice(0,4)) return w.cp_after;
  const alt=(w.alts||[]).find(a=>a.uci.slice(0,4)===u); if(alt) return alt.cp!=null?Math.min(alt.cp,w.cp_before):w.cp_before;
  const m=w.moves&&w.moves[u]; return m==null?null:Math.min(m,w.cp_before);
}
const legalOf=(w)=>w.legal?w.legal.split(' '):null;   // 예전 형식의 퍼즐에는 없을 수 있다
function drawBoard(extra={}){
  const w=cur(), flip=w.color==='b';
  $('#pzboard').innerHTML=boardSVG(w.fen,{flip,last:SEL?[SEL]:[],arrows:extra.arrows||[]});
  const legal=legalOf(w);
  if(SEL&&legal&&!extra.arrows){   // 고른 기물이 갈 수 있는 칸: 빈 칸은 점, 잡는 칸은 고리
    const occ=new Set(parseFen(w.fen).map(x=>x.sq)); let d='';
    for(const m of legal) if(m.slice(0,2)===SEL){ const to=m.slice(2,4), [x,y]=sqXY(to,flip);
      d+=occ.has(to)?`<circle cx="${x+50}" cy="${y+50}" r="44" fill="none" stroke="rgba(0,0,0,.26)" stroke-width="9"/>`:`<circle cx="${x+50}" cy="${y+50}" r="15" fill="rgba(0,0,0,.26)"/>`; }
    $('#pzboard svg').insertAdjacentHTML('beforeend',d);
  }
  applyTheme();
}
function toast(t){ const el=$('#pztoast'); if(!el) return; el.textContent=t; el.classList.add('on'); clearTimeout(toast.t); toast.t=setTimeout(()=>el.classList.remove('on'),1500); }
function mine(sq){ const w=cur(); const p=parseFen(w.fen).find(x=>x.sq===sq); return p&&p.p[0]===w.color; }
/* uci: 둔 수(예 'e2e4'), null 이면 '모르겠어요' */
function answer(uci){
  const w=cur();
  const accepted=new Set([w.best_uci.slice(0,4), ...(w.alts||[]).map(a=>a.uci.slice(0,4))]);   // 최선 수와, 승률 차이가 작아 같이 인정하는 수
  const ok=uci!==null&&accepted.has(uci.slice(0,4));
  const sec=T0?Math.min(600,Math.round((Date.now()-T0)/1000)):null;
  TD.res[w.id]=ok?'ok':'ng'; (TD.mv=TD.mv||{})[w.id]=uci; if(sec!=null) (TD.sec=TD.sec||{})[w.id]=sec; saveDay();
  const h=HIST[TODAY]||{ok:0,n:0}; h.n++; if(ok) h.ok++; if(sec!=null){ h.s=(h.s||0)+sec; h.sn=(h.sn||0)+1; } HIST[TODAY]=h; save('puzzle-history',HIST);
  if(WIN){ const pw=load('puzzle-win',null); const d=pw&&pw.date===TODAY?pw:{date:TODAY,n:0,ok:0}; d.n++; if(ok) d.ok++; save('puzzle-win',d); }   // 홈의 '오늘' 줄이 센다
  SEEN[w.id]=TODAY; const sk=Object.keys(SEEN); if(sk.length>MAX_SEEN) sk.sort((a,b)=>SEEN[a].localeCompare(SEEN[b])).slice(0,sk.length-MAX_SEEN).forEach(k=>delete SEEN[k]); save('puzzle-seen',SEEN);
  const r=REVIEW[w.id];
  if(!ok) REVIEW[w.id]={due:dkey(STEPS[0]),step:0,pz:w};
  else if(r){ const st=r.step+1; if(st>=STEPS.length) delete REVIEW[w.id]; else REVIEW[w.id]={due:dkey(STEPS[st]),step:st,pz:w}; }
  const rk=Object.keys(REVIEW); if(rk.length>MAX_REVIEW) rk.sort((a,b)=>REVIEW[a].due.localeCompare(REVIEW[b].due)).slice(MAX_REVIEW).forEach(k=>delete REVIEW[k]);
  save('puzzle-review',REVIEW);
  showAnswer(uci,false);
}
/* 채점 결과 화면. restored=true 는 이미 푼 문제를 다시 열었을 때(새로고침 등): 기록을 다시 남기지 않는다 */
function showAnswer(uci,restored){
  const w=cur(), ok=TD.res[w.id]==='ok';
  const alt=uci?(w.alts||[]).find(a=>a.uci.slice(0,4)===uci.slice(0,4)):null;
  const arrows=[]; if(uci) arrows.push([uci, ok?GREEN:RED]); if(!ok||alt||!uci) arrows.push([w.best_uci, alt?BLUE:GREEN]);
  SEL=null; drawBoard({arrows});
  const mcp=uci===undefined?w.cp_before:moveCp(w,uci); if(mcp!=null) pzBar(mcp);
  const tk=$('#pztoast'); if(tk) tk.classList.remove('on');
  if(!restored) $('#pzboard').classList.add(ok?'ok':'ng');
  const lost=`실전에서는 <span class="mono">${esc(w.san)}</span> 을 두어 승률을 ${w.wp_loss}%p 잃었습니다`;
  let msg;
  if(restored) msg=`<span class="ic">${ok?'정답':'오답'}</span>이미 푼 문제입니다. 가장 좋은 수는 <b>${esc(w.best)}</b> 입니다. ${lost}.`;
  else if(uci===null) msg=`<span class="ic">정답 공개</span>가장 좋은 수는 <b>${esc(w.best)}</b> 입니다. ${lost} (${ev(w.cp_before)} → ${ev(w.cp_after)}).`;
  else if(alt) msg=`<span class="ic">정답</span><b>${esc(alt.san)}</b> 도 좋은 수입니다. 엔진의 첫째 선택은 <b>${esc(w.best)}</b> 이지만 차이가 작습니다. ${lost}.`;
  else if(ok) msg=`<span class="ic">정답</span><b>${esc(w.best)}</b> 가 가장 좋은 수입니다. ${lost}.`;
  else msg=`<span class="ic">오답</span>가장 좋은 수는 <b>${esc(w.best)}</b> 입니다. ${lost} (${ev(w.cp_before)} → ${ev(w.cp_after)}).`;
  if(uci) msg+=`<div style="margin-top:4px">내가 둔 <span class="mono">${esc(uciSan(w,uci))}</span> 뒤 ${wpChange(w.cp_before,mcp)||'<span class="sub">승률 계산 없음</span>'}${(TD.sec||{})[w.id]!=null&&!restored?` <span class="sub">· ${TD.sec[w.id]}초</span>`:''}</div>`;
  msg+=otherMoves(w,uci);
  const others=(w.alts||[]).filter(a=>a!==alt).map(a=>esc(a.san));
  if(others.length) msg+=`<div class="sub" style="margin-top:6px">${alt?'그 밖에':'같이'} 정답으로 인정되는 수: ${others.join(', ')}</div>`;
  if(w.cat) msg+=`<div class="sub" style="margin-top:8px">${catTag(w.cat,COACH&&COACH.focus&&COACH.focus.includes(w.cat)?'rep':'')} 두기 전에: ${esc(catOf(w.cat).rule)}</div>`;
  const rv=REVIEW[w.id];
  if(rv) msg+=`<div class="sub" style="margin-top:6px">${Math.max(1,Math.round((Date.parse(rv.due)-Date.parse(TODAY))/DAY))}일 뒤 복습으로 다시 나옵니다.</div>`;
  else if(TD.rv[w.id]&&ok) msg+=`<div class="sub" style="margin-top:6px">복습을 마쳤습니다.</div>`;
  $('#pzresult').innerHTML=`<div class="result ${ok?'ok':'ng'}">${msg}</div>`+(w.best_line&&w.best_line.length?blunderViewer(w):'');
  drawAll($('#pzresult')); applyTheme();
  $('#pzacts').innerHTML=`<a class="btn" href="game.html?id=${gameId(w.url)}&ply=${w.ply}">게임에서 보기</a><span class="btn on" id="next">다음 퍼즐 ›</span>`;
  $('#pzhead').innerHTML=headHTML();
  if(!restored) $('#next').scrollIntoView({behavior:'smooth',block:'nearest'});
}
/* 후보 수들의 평가표: 최선·같이 좋은 수·실전 수·내가 둔 수와, 모든 수 평가(moves)에서 그다음으로 좋은 수들. 아깝게 틀린 수가 왜 아까운지 보인다 */
function otherMoves(w,uci){
  if(!w.moves) return '';
  const rows=new Map(); const add=(u,cp,tag)=>{ u=u.slice(0,4); if(!rows.has(u)) rows.set(u,{u,cp,tags:[]}); if(tag) rows.get(u).tags.push(tag); };
  add(w.best_uci,w.cp_before,'최선'); (w.alts||[]).forEach(a=>add(a.uci,a.cp!=null?Math.min(a.cp,w.cp_before):w.cp_before,'같이 정답')); add(w.uci,w.cp_after,'실전'); if(uci) add(uci,moveCp(w,uci),'내 답');
  Object.entries(w.moves).sort((a,b)=>b[1]-a[1]).slice(0,6).forEach(([u,cp])=>add(u,Math.min(cp,w.cp_before)));
  const list=[...rows.values()].filter(r=>r.cp!=null||r.tags.includes('내 답')).sort((a,b)=>(b.cp??-1e9)-(a.cp??-1e9)).slice(0,7);   // 내 답은 평가가 없어도(얕은 평가에 빠진 수) 보여 준다
  if(list.length<2) return '';
  return `<details class="omoves"><summary>다른 수들은 어땠나 (엔진 평가)</summary><table>${list.map(r=>`<tr class="${r.tags.includes('내 답')?'me':''}"><td class="mono">${esc(uciSan(w,r.u))}</td><td>${r.cp==null?'<span class="sub">평가 없음</span>':ev(r.cp)}</td><td class="sub">${r.cp==null?'':(wpChange(w.cp_before,r.cp)||'')}</td><td class="sub">${r.tags.join(' · ')}</td></tr>`).join('')}</table></details>`;
}
/* 둔 수의 표기: 최선·실전·비슷한 정답은 저장된 SAN, 나머지는 기물 글자+칸으로 간단히 */
function uciSan(w,uci){
  const u=uci.slice(0,4);
  if(u===w.best_uci.slice(0,4)) return w.best; if(u===w.uci.slice(0,4)) return w.san;
  const alt=(w.alts||[]).find(a=>a.uci.slice(0,4)===u); if(alt) return alt.san;
  const pc=parseFen(w.fen).find(x=>x.sq===u.slice(0,2)), cap=parseFen(w.fen).some(x=>x.sq===u.slice(2,4));
  return (pc&&pc.p[1]!=='P'?pc.p[1]:'')+(cap?(pc&&pc.p[1]==='P'?u[0]+'x':'x'):'')+u.slice(2,4);
}
document.addEventListener('pointerdown',(e)=>{
  const svg=e.target.closest('#pzboard svg.board'); if(!svg||answered()) return;
  const w=cur(), sq=squareAt(svg,e,w.color==='b'); if(!sq) return;
  if(SEL&&sq!==SEL){
    if(mine(sq)){ SEL=sq; drawBoard(); return; }
    const legal=legalOf(w);
    if(legal&&!legal.includes(SEL+sq)){ toast('그 수는 둘 수 없습니다'); return; }   // 잘못 누른 칸은 채점하지 않고 선택을 유지한다
    const u=SEL+sq; SEL=null; answer(u); return;
  }
  if(mine(sq)){ SEL=(SEL===sq?null:sq); drawBoard(); }
});
document.addEventListener('click',(e)=>{
  if(e.target.closest('#giveup')){ if(!answered()) answer(null); return; }
  if(e.target.closest('#next')){ TD.idx++; SEL=null; saveDay(); render(); window.scrollTo(0,0); return; }
  if(e.target.closest('#more')){ TD.cont=true; saveDay(); render(); window.scrollTo(0,0); }
});
render();
