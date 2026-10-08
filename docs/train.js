/* 오프닝 연습: train.html?o=<오프닝 id>[&l=<라인 번호>]. shared.js 다음에 module 로 로드된다.
   book.json 의 라인(내 15수째까지)을 직접 두어 본다. 내 수는 판에서 기물과 칸을 눌러 두고, 상대 수는 자동으로 놓인다.
   train-done (localStorage)  {오프닝 id: {라인 번호: {clean: 실수 없이 끝낸 횟수, n: 끝낸 횟수, last: 날짜}}} */
document.body.insertAdjacentHTML('afterbegin', await fetch('pieces.svg').then(r=>r.text()));
const BOOK = await fetch('book.json',{cache:'no-cache'}).then(r=>r.ok?r.json():null).catch(()=>null);
$('#tpanel-slot').innerHTML=themePanel(); applyMode();
$('#backbtn').innerHTML=icon('back')+'오프닝 성적';
const Q=new URLSearchParams(location.search);
const OPS=(BOOK&&BOOK.openings)||{};
const O=OPS[Q.get('o')];
const VERD={weak:['취약','critical'],weak_hint:['취약 조짐','serious'],strong:['강점','good'],strong_hint:['강점 조짐','good'],even:['평균 수준','']};
const SIDE={mine:'내가 고른 수순',opp:'상대가 고른 수순'};
const load=(k,d)=>{ try{ const v=JSON.parse(localStorage.getItem(k)||'null'); return v??d; }catch(e){ return d; } };
const save=(k,v)=>{ try{ localStorage.setItem(k,JSON.stringify(v)); }catch(e){} };
const DONE=load('train-done',{});
const today=()=>new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
const START='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const num=(p,first)=>p.mover==='w'?`${p.move}.`:(first?`${p.move}…`:'');
const cpTxt=(v)=>v==null?'-':Math.abs(v)>=9000?(v>0?'외통 승':'외통 패'):(v>0?'+':v<0?'−':'')+(Math.abs(v)/100).toFixed(1);

/* ---------- 목록 (o 가 없거나 모르는 id) ---------- */
function listHTML(){
  const all=Object.values(OPS); if(!all.length) return '<div class="empty">연습 라인이 아직 만들어지지 않았습니다. 게임이 분석되면 몇 분 안에 생깁니다.</div>';
  const rank=o=>o.verdict.startsWith('weak')?0:o.verdict==='even'?1:2;
  all.sort((a,b)=>rank(a)-rank(b)||b.n-a.n);
  let h=`<h1 class="tt">오프닝 연습</h1><div class="sub">취약한 오프닝부터 · 내 15수째까지 직접 두어 봅니다</div><div class="card" style="margin-top:12px">`;
  for(const o of all){ const v=VERD[o.verdict]||VERD.even, d=DONE[o.id]||{}, cl=o.lines.filter((_,i)=>d[i]&&d[i].clean).length;
    h+=`<a class="trow" href="train.html?o=${encodeURIComponent(o.id)}"><div><div class="ok"><span class="mono">${esc(o.key)}</span></div><div class="nm">${o.color==='w'?'백':'흑'} · ${SIDE[o.side]} · 주로 ${esc(o.name)} · ${o.n}판 ${o.score}%</div>
      <div class="nm">라인 ${o.lines.length}개${cl?` · 실수 없이 끝낸 라인 ${cl}개`:''}</div></div><span class="chip ${v[1]}">${v[0]}</span></a>`; }
  return h+'</div>';
}

/* ---------- 연습 ---------- */
let LI=Math.max(0,Math.min(O?O.lines.length-1:0,+(Q.get('l')||0)||0));
let ST=null;   // {i: 다음에 둘 수의 순번, wrong: 이 수에서 틀린 횟수, miss: 이 라인에서 틀린 수의 개수, shown: 정답을 본 수, msg, sel, busy, done}
const line=()=>O.lines[LI];
const fenAt=(i)=>i>0?line().plies[i-1].fen:START;
function reset(){ ST={i:0,wrong:0,miss:0,shown:0,msg:'',cls:'',sel:null,busy:false,done:false,arrows:[]}; autoOpp(true); }
/* 내 차례가 올 때까지 상대 수(와 첫 화면의 흐름)를 놓는다 */
function autoOpp(instant){
  const P=line().plies;
  if(ST.i>=P.length){ finish(); return; }
  if(P[ST.i].mine){ render(); return; }
  ST.busy=true; render();
  setTimeout(()=>{ if(!ST) return; ST.i++; ST.busy=false; ST.arrows=[]; autoOpp(false); }, instant?350:550);
}
function finish(){
  ST.done=true;
  const d=DONE[O.id]=DONE[O.id]||{}, e=d[LI]=d[LI]||{clean:0,n:0}; e.n++; if(!ST.miss&&!ST.shown) e.clean++; e.last=today(); save('train-done',DONE);
  render();
}
function headHTML(){
  const v=VERD[O.verdict]||VERD.even, d=DONE[O.id]||{};
  let h=`<div class="thead"><div><h1 class="tt"><span class="mono">${esc(O.key)}</span></h1><div class="sub">${O.color==='w'?'백':'흑'} · ${SIDE[O.side]} · 주로 ${esc(O.name)} · ${O.n}판 승률 ${O.score}%</div></div><span class="chip ${v[1]}">${v[0]}</span></div>`;
  h+=`<div class="pzmodes">${O.lines.map((l,i)=>`<a class="${i===LI?'on':''}" data-line="${i}" href="train.html?o=${encodeURIComponent(O.id)}&l=${i}">${d[i]&&d[i].clean?'<i class="ck"></i>':''}${esc(l.name)}</a>`).join('')}</div>`;
  return h+`<div class="sub lnote">${esc(line().note)}${line().fix?` · 평소 틀리던 자리 ${line().fix}곳`:''}</div>`;
}
function movesHTML(){
  const P=line().plies; let h='<div class="tmoves">';
  P.forEach((p,i)=>{ if(i>=ST.i) return; const n=num(p,i===0); h+=`${n?`<span class="num">${n}</span>`:''}<span class="m ${p.mine?'me':''} ${i===ST.i-1?'cur':''}">${esc(p.san)}</span>`; });
  return h+'</div>';
}
function render(){
  const P=line().plies, p=P[ST.i], last=ST.i>0?P[ST.i-1]:null, flip=O.color==='b';
  const myNo=P.slice(0,ST.i).filter(x=>x.mine).length, myTot=P.filter(x=>x.mine).length;
  let h=headHTML();
  h+=`<div class="prog"><div><b>${ST.done?'라인 끝':ST.busy?'상대 차례':'내 차례'}</b> <span class="sub">${ST.done?`${myTot}수 완료`:`내 ${Math.min(myNo+1,myTot)}수째 / ${myTot}`}</span></div><div class="pbar"><i style="width:${(myNo/myTot*100).toFixed(1)}%"></i></div></div>`;
  h+=`<div class="pzboard ${ST.cls}" id="tboard">${boardSVG(fenAt(ST.i),{flip,last:ST.sel?[ST.sel]:last?[last.uci.slice(0,2),last.uci.slice(2,4)]:[],arrows:ST.arrows})}</div>`;
  let msg=ST.msg;
  if(!msg&&!ST.done&&!ST.busy&&p){
    if(last&&!last.mine) msg=`상대 <b class="mono">${esc(last.san)}</b>${last.eng?' <span class="sub">(내 게임에 없는 국면: 엔진의 수)</span>':last.n?` <span class="sub">(내 게임 ${last.n}판)</span>`:''}. `;
    msg+=`${O.color==='w'?'백':'흑'} ${p.move}수째를 두세요.`;
    if(p.bad) msg+=`<div class="warn">자주 틀리던 자리입니다. 평소 두던 수는 정답이 아닙니다.</div>`;
  }
  if(ST.done){
    const clean=!ST.miss&&!ST.shown;
    msg=`<span class="ic">${clean?'완벽':'완료'}</span>${clean?'실수 없이 끝까지 뒀습니다.':`틀린 수 ${ST.miss}개${ST.shown?`, 정답을 본 수 ${ST.shown}개`:''}. 실수 없이 끝낼 때까지 다시 해 보세요.`} 이 진행의 끝 형세는 <b>${cpTxt(line().cp)}</b> (내 기준)입니다.`;
  }
  h+=`<div class="result ${ST.done?(ST.miss||ST.shown?'':'ok'):ST.cls==='ng'?'ng':ST.cls==='ok'?'ok':''}" id="tmsg">${msg||'&nbsp;'}</div>`;
  h+=movesHTML();
  if(ST.done){ const nx=(LI+1)%O.lines.length;
    h+=`<div class="acts"><span class="btn" id="again">다시 두기</span>${O.lines.length>1?`<a class="btn on" href="train.html?o=${encodeURIComponent(O.id)}&l=${nx}" data-line="${nx}">다음 라인 ›</a>`:`<a class="btn on" href="train.html">다른 오프닝 ›</a>`}</div>`;
  } else h+=`<div class="acts"><span class="btn" id="hint">힌트</span><span class="btn" id="show">정답 보기</span><span class="btn" id="again">처음부터</span></div>`;
  h+=`<details class="card allm"><summary>이 라인 전체 수순 보기</summary><div class="tmoves full">${P.map((x,i)=>`${num(x,i===0)?`<span class="num">${num(x,i===0)}</span>`:''}<span class="m ${x.mine?'me':''}">${esc(x.san)}</span>`).join('')}</div>
    ${P.filter(x=>x.bad).map(x=>`<div class="sub">${x.move}수: 평소 <span class="mono">${esc(x.bad.san)}</span> (${x.bad.n}번, 평균 −${x.bad.loss}%p) 대신 <b class="mono">${esc(x.san)}</b></div>`).join('')}</details>`;
  h+=`<div class="more"><a class="btn" href="train.html">다른 오프닝 연습</a></div>`;
  const keep=document.querySelector('details.allm'); const open=keep&&keep.open;
  $('#main').innerHTML=h; if(open) document.querySelector('details.allm').open=true;
  applyTheme();
}
function squareAt(svg,e){
  const r=svg.getBoundingClientRect(); let fx=Math.floor((e.clientX-r.left)/r.width*8), ry=Math.floor((e.clientY-r.top)/r.height*8);
  if(fx<0||fx>7||ry<0||ry>7) return null; if(O.color==='b'){ fx=7-fx; ry=7-ry; }
  return FILES[fx]+(8-ry);
}
const mineAt=(sq)=>{ const x=parseFen(fenAt(ST.i)).find(q=>q.sq===sq); return x&&x.p[0]===O.color; };
function play(uci){
  const p=line().plies[ST.i], u=uci.slice(0,4);
  if(u===p.uci.slice(0,4)){ advance(`<span class="ic">정답</span><b class="mono">${esc(p.san)}</b>${p.mineN?` <span class="sub">평소 두던 수 그대로입니다 (${p.mineN}번).</span>`:''}`); return; }
  const alt=(p.ok||[]).find(a=>a.uci.slice(0,4)===u);
  if(alt){ advance(`<span class="ic">정답</span><b class="mono">${esc(alt.san)}</b> 도 좋은 수입니다. 이 연습에서는 <b class="mono">${esc(p.san)}</b> 로 진행합니다.`); return; }
  ST.wrong++; if(ST.wrong===1) ST.miss++;
  ST.cls='ng'; ST.sel=null;
  const usual=p.bad&&p.bad.uci&&p.bad.uci.slice(0,4)===u;
  ST.msg=`<span class="ic">다시</span>${usual?`평소 두던 수입니다 (${p.bad.n}번, 평균 −${p.bad.loss}%p). 여기가 고칠 자리입니다.`:'이 라인의 수가 아닙니다.'} ${ST.wrong>=2?'움직일 기물을 표시했습니다.':'다시 찾아보세요.'}`;
  ST.arrows=[]; if(ST.wrong>=2) ST.sel=p.uci.slice(0,2);
  render();
  setTimeout(()=>{ if(ST&&ST.cls==='ng'){ ST.cls=''; const b=$('#tboard'); if(b) b.classList.remove('ng'); } },400);
}
function advance(msg){
  ST.i++; ST.wrong=0; ST.sel=null; ST.cls='ok'; ST.msg=msg; ST.arrows=[];
  if(ST.i>=line().plies.length){ finish(); return; }
  ST.busy=true; render();
  setTimeout(()=>{ if(!ST) return; ST.cls=''; ST.msg=''; ST.busy=false; autoOpp(false); },650);
}
document.addEventListener('pointerdown',(e)=>{
  const svg=e.target.closest('#tboard svg.board'); if(!svg||!O||!ST||ST.done||ST.busy) return;
  const sq=squareAt(svg,e); if(!sq) return;
  if(ST.sel&&sq!==ST.sel&&!mineAt(sq)){ const u=ST.sel+sq; play(u); return; }
  if(ST.sel&&sq!==ST.sel&&mineAt(sq)){   // 캐슬링을 킹→룩으로 누르는 경우도 받는다
    const p=line().plies[ST.i]; if(/^O-O/.test(p.san)&&ST.sel===p.uci.slice(0,2)){ play(p.uci); return; }
    ST.sel=sq; ST.msg=''; ST.cls=''; ST.arrows=[]; render(); return; }
  if(mineAt(sq)){ ST.sel=ST.sel===sq?null:sq; ST.msg=''; ST.cls=''; ST.arrows=[]; render(); }
});
document.addEventListener('click',(e)=>{
  if(!O||!ST) return;
  const ln=e.target.closest('[data-line]'); if(ln){ e.preventDefault(); LI=+ln.dataset.line; history.replaceState(null,'',`train.html?o=${encodeURIComponent(O.id)}&l=${LI}`); reset(); window.scrollTo(0,0); return; }
  if(e.target.closest('#again')){ reset(); return; }
  if(ST.done||ST.busy) return;
  const p=line().plies[ST.i];
  if(e.target.closest('#hint')){ ST.sel=p.uci.slice(0,2); ST.msg=`<span class="ic">힌트</span>표시한 기물을 움직입니다.`; if(!ST.wrong){ ST.wrong=1; ST.miss++; } render(); return; }
  if(e.target.closest('#show')){ ST.shown++; ST.arrows=[[p.uci,GREEN]]; ST.sel=null; ST.msg=`<span class="ic">정답</span><b class="mono">${esc(p.san)}</b>${p.bad?` · 평소에는 <span class="mono">${esc(p.bad.san)}</span> 을 뒀습니다 (${p.bad.n}번).`:''} 화살표대로 두세요.`; ST.wrong=Math.max(ST.wrong,1); render(); }
});

if(O){ document.title=`${O.key} · 오프닝 연습`; reset(); }
else $('#main').innerHTML=listHTML();
