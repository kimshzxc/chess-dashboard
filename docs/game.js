/* 게임 상세 페이지. shared.js 다음에 module 로 로드된다. */
document.body.insertAdjacentHTML('afterbegin', await fetch('pieces.svg').then(r=>r.text()));
$('#tpanel-slot').innerHTML=themePanel(); applyMode();
$('#backbtn').innerHTML=icon('back')+'게임 목록';
const params=new URLSearchParams(location.search);
const ID=params.get('id'); let G=null, IDX=0, FLIP=false, SHOW_BEST=true;
let COACH=null;   // coach.json: 전체 기간의 집중 과제와 유형별 최근 빈도 (없어도 페이지는 동작한다)
const CLS={best:['최선','best'],good:['좋음','good'],inacc:['부정확','inacc'],mist:['실수','mist'],blun:['대실수','blun'],miss:['외통 놓침','blun']};
const CLSCOLOR={best:'var(--c-best)',good:'var(--c-good)',inacc:'var(--c-inacc)',mist:'var(--c-mist)',blun:'var(--c-blun)',miss:'var(--c-blun)'};

async function load(){
  const coach=fetch('coach.json',{cache:'no-cache'}).then(r=>r.ok?r.json():null).catch(()=>null);
  try{ const r=await fetch(`games/${ID}.json`,{cache:'no-cache'}); if(!r.ok) throw new Error(r.status); G=await r.json(); }
  catch(e){ $('#main').innerHTML=`<div class="empty">게임 데이터를 찾을 수 없습니다 (${esc(ID)}). 아직 분석·업로드되지 않았을 수 있습니다.</div>`; return; }
  COACH=await coach;
  FLIP = G.my_color==='b';
  const p=+params.get('ply'); IDX = (p>0&&p<=G.plies.length)? p : 0;
  document.title=`${G.white} vs ${G.black} · 게임 분석`;
  renderHead(); renderMain(); draw();
}
function renderHead(){
  $('#head').innerHTML=`<div class="players"><span><b>${esc(G.white)}</b><span class="sub">백 · ${G.welo}</span></span><span class="res ${G.outcome}">${G.result} · ${G.outcome==='W'?'승':G.outcome==='L'?'패':'무'}</span><span><b>${esc(G.black)}</b><span class="sub">흑 · ${G.belo}</span></span></div>
  <div class="sub" style="margin-top:6px">${G.date} · ${esc(G.termination||'')} · <a href="${esc(G.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>
  <div class="sub" style="color:var(--muted)">${esc(G.eco_name)}</div>`;
}
/* 이 판의 교훈: 내 실수를 유형별로 묶고, 평소에도 반복하는 유형인지 알려 준다 */
function lessonsHTML(){
  const by={}; G.plies.forEach((p,i)=>{ if(p.mine&&p.cat) (by[p.cat]=by[p.cat]||[]).push({p,i}); });
  const cost=k=>by[k].reduce((a,x)=>a+x.p.wp_loss,0);
  const keys=Object.keys(by).sort((a,b)=>cost(b)-cost(a));
  let h=`<div class="card lessons" id="lessons"><h3 style="margin-top:0">이 판의 교훈 <span class="sub">(승률을 10%p 이상 잃은 내 수)</span></h3>`;
  if(!keys.length) return h+`<div class="sub">그런 수가 하나도 없었습니다. 깨끗한 판입니다.</div></div>`;
  const focus=(COACH&&COACH.focus)||[], hit=focus.filter(k=>by[k]);
  if(focus.length) h+=`<div class="lv">${hit.length?`집중 과제 ${focus.length}가지 중 <b>${hit.length}가지가 또 나왔습니다.</b>`:`집중 과제 ${focus.length}가지는 <b>하나도 안 나왔습니다.</b>`}</div>`;
  for(const k of keys){ const m=catOf(k), c=COACH&&COACH.cats&&COACH.cats[k];
    h+=`<div class="lesson"><div class="lh"><b>${esc(m.n)}</b>${focus.includes(k)?'<span class="chip me">집중 과제</span>':''}<span class="lc">−${cost(k).toFixed(0)}%p</span></div>
      <div class="lm">${by[k].map(({p,i})=>`<span class="lmv" data-jump="${i+1}">${mv(p)}</span>`).join('')}</div>
      <div class="sub">${c?`최근 ${COACH.k}판 중 ${c.recent}판에서 나온 유형 · `:''}두기 전에: ${esc(m.rule)} <a href="index.html?cat=${k}#mistakes">다른 사례 ›</a></div></div>`; }
  return h+'</div>';
}
function renderMain(){
  const s=G.summary, n=G.plies.length;
  let h=`<div class="stick"><div class="boardwrap"><div class="evalbar" id="evalbar"><div class="w"></div><span></span></div><div id="board" style="flex:1;min-width:0"></div></div>`;
  h+=`<div class="strip" id="strip">`+G.plies.map((p,i)=>`${p.mover==='w'?`<span class="num">${p.move}.</span>`:''}<span class="mv" data-jump="${i+1}"><i style="background:${CLSCOLOR[p.cls]}"></i>${esc(p.san)}</span>`).join('')+`</div>`;
  h+=`<div class="vctl"><span class="btn nav" data-go="0">⏮</span><span class="btn nav" data-go="-1">‹</span><span class="btn nav" data-go="1">›</span><span class="btn nav" data-go="9">⏭</span></div></div>`;
  h+=`<div class="opts"><span class="btn ${SHOW_BEST?'on':''}" id="optbest">정답 화살표</span><span class="btn" id="optflip">판 뒤집기</span></div>`;
  h+=`<div class="info card" id="info"></div>`;
  h+=lessonsHTML();
  h+=`<div class="card"><div class="sub">평가 그래프 (누르면 이동 · 점: 실수/대실수)</div>${graphSVG()}</div>`;
  const cs=clockSVG();
  if(cs) h+=`<div class="card"><div class="sub">남은 시간 (누르면 그 수로 이동)</div>${cs}<div class="legend"><span><i class="lk" style="background:var(--s1)"></i>나</span><span><i class="lk" style="background:var(--s2)"></i>상대</span><span><i class="dotk"></i>내가 45초 이상 쓴 수</span></div></div>`;
  const cnt=(who)=>{ const c={best:0,good:0,inacc:0,mist:0,blun:0}; G.plies.forEach(p=>{ if(p.mine===who){ const k=p.cls==='miss'?'blun':p.cls; c[k]=(c[k]||0)+1; } }); return c; };
  const cm=cnt(1), co=cnt(0);
  h+=`<div class="tiles">
    <div class="tile"><div class="k">정확도</div><div class="v">${s.accuracy}%</div><div class="d">상대 ${s.opp_accuracy}%</div></div>
    <div class="tile"><div class="k">내 수 분류</div><div class="v sm"><span style="color:var(--c-blun)">${cm.blun}</span> / <span style="color:var(--c-mist)">${cm.mist}</span> / <span style="color:var(--c-inacc)">${cm.inacc}</span></div><div class="d">대실수 / 실수 / 부정확 · 최선 ${cm.best}</div></div>
    <div class="tile"><div class="k">상대 수 분류</div><div class="v sm"><span style="color:var(--c-blun)">${co.blun}</span> / <span style="color:var(--c-mist)">${co.mist}</span> / <span style="color:var(--c-inacc)">${co.inacc}</span></div><div class="d">대실수 / 실수 / 부정확 · 최선 ${co.best}</div></div>
    <div class="tile"><div class="k">시계 (나 / 상대)</div><div class="v sm">${clk(s.my_clock_20)} / ${clk(s.opp_clock_20)}</div><div class="d">20수 시점 · 종료시 ${clk(s.my_final_clock)} / ${clk(s.opp_final_clock)}</div></div>
  </div>`;
  const key=G.plies.map((p,i)=>({p,i})).filter(x=>x.p.mine&&x.p.wp_loss>=10).sort((a,b)=>b.p.wp_loss-a.p.wp_loss).slice(0,5);
  if(key.length){
    h+=`<div class="card"><h3 style="margin-top:0">내 핵심 실수 <span class="sub">(누르면 그 장면으로)</span></h3>`;
    key.forEach(({p,i})=>{ h+=`<div class="key" data-jump="${i+1}"><span class="cls ${CLS[p.cls][1]}">${CLS[p.cls][0]}</span> <span class="mono">${mv(p)}</span> 대신 <span class="mono">${esc(p.best)}</span> ${catTag(p.cat)} <span class="sub">· ${ev(p.cp_before)} → ${ev(p.cp_after)} · 남은시간 ${clk(p.clock)}${p.spent!=null?` · ${Math.round(p.spent)}초 사용`:''}</span></div>`; });
    h+='</div>';
  }
  h+=`<div class="card"><h3 style="margin-top:0">수 목록 <span class="sub">점: 수의 평가 · 작은 숫자: 그 수에 쓴 시간</span></h3><div class="legend">`+Object.entries({best:'최선',good:'좋음',inacc:'부정확',mist:'실수',blun:'대실수'}).map(([k,v])=>`<span><i style="background:${CLSCOLOR[k]}"></i>${v}</span>`).join('')+`</div><div class="mlist">`;
  for(let i=0;i<n;i+=2){
    const w=G.plies[i], b=G.plies[i+1];
    const cell=(p,idx)=> p?`<div class="mv" data-jump="${idx}"><i style="background:${CLSCOLOR[p.cls]}"></i><span class="mono">${esc(p.san)}</span><span class="t">${p.spent!=null?Math.round(p.spent)+'s':''}</span></div>`:'<div></div>';
    h+=`<div class="num">${w.move}.</div>${cell(w,i+1)}${cell(b,i+2)}`;
  }
  h+=`</div></div>`;
  $('#main').innerHTML=h;
  $('#foot').textContent=`Stockfish 19 depth ${G.depth||14} · 정답 수순 depth ${G.pv_depth||16}`;
}
/* 남은 시간 그래프: 나와 상대의 시계를 수 순서로. 가장 큰 약점이 시간 관리라서 어디서 시간을 썼는지 보이게 한다. */
let CLK=null;   // {L,pw,n} 현재 수 표시선 위치 계산용
function clockSVG(){
  const n=G.plies.length; if(n<2||!G.plies.some(p=>p.clock!=null)) return '';
  const W=360,H=150,L=40,R=46,T=12,B=22,pw=W-L-R,ph=H-T-B;
  const first=(mine)=>{ const p=G.plies.find(q=>!!q.mine===mine&&q.clock!=null); return p?p.clock+(p.spent||0):null; };
  let cm=first(true), co=first(false); const me=[cm], op=[co];   // 0 = 시작, i = i번째 수를 둔 뒤. 자기 차례가 아닐 때는 직전 값 유지
  G.plies.forEach(p=>{ if(p.clock!=null){ if(p.mine) cm=p.clock; else co=p.clock; } me.push(cm); op.push(co); });
  const all=[...me,...op].filter(v=>v!=null); if(all.length<4) return '';
  const top=Math.max(60,Math.ceil(Math.max(...all)/60)*60), step=top>=600?300:top>=240?120:60;
  const x=i=>L+i/n*pw, y=v=>T+(1-v/top)*ph;
  const path=(a)=>a.map((v,i)=>v==null?'':`${i&&a[i-1]!=null?'L':'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  let h=`<div class="tchart-wrap"><svg class="tchart xchart" id="cchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="수별 남은 시간">`;
  for(let v=0;v<=top;v+=step) h+=`<line x1="${L}" x2="${W-R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"/><text x="${L-6}" y="${(y(v)+4).toFixed(1)}" font-size="11" text-anchor="end" fill="var(--muted)">${clk(v)}</text>`;
  h+=`<line id="ccur" x1="${L}" x2="${L}" y1="${T}" y2="${T+ph}" stroke="var(--muted)" stroke-width="1"/>`;
  h+=`<path d="${path(op)}" fill="none" stroke="var(--s2)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  h+=`<path d="${path(me)}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  G.plies.forEach((p,i)=>{ if(p.mine&&p.spent!=null&&p.spent>=45&&p.clock!=null) h+=`<circle cx="${x(i+1).toFixed(1)}" cy="${y(p.clock).toFixed(1)}" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>`; });
  // 끝점: 색 점 + 값 (글자는 본문색). 두 값이 붙으면 위아래로 벌린다
  const em=me[n], eo=op[n]; let ym=em!=null?y(em):null, yo=eo!=null?y(eo):null;
  if(ym!=null&&yo!=null&&Math.abs(ym-yo)<13){ const mid=(ym+yo)/2, up=ym<=yo; ym=mid+(up?-6.5:6.5); yo=mid+(up?6.5:-6.5); }
  if(eo!=null) h+=`<circle cx="${x(n).toFixed(1)}" cy="${y(eo).toFixed(1)}" r="4" fill="var(--s2)" stroke="var(--surface)" stroke-width="2"/><text x="${W-R+8}" y="${(yo+4).toFixed(1)}" font-size="11.5" font-weight="600" fill="var(--text2)">${clk(eo)}</text>`;
  if(em!=null) h+=`<circle cx="${x(n).toFixed(1)}" cy="${y(em).toFixed(1)}" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/><text x="${W-R+8}" y="${(ym+4).toFixed(1)}" font-size="11.5" font-weight="700" fill="var(--text)">${clk(em)}</text>`;
  h+=`<text x="${L}" y="${H-5}" font-size="11" fill="var(--muted)">1수</text><text x="${W-R}" y="${H-5}" font-size="11" text-anchor="end" fill="var(--muted)">${Math.ceil(n/2)}수</text>`;
  h+=`<g class="xc" style="display:none"><line class="xc-l" y1="${T}" y2="${T+ph}" stroke="var(--text2)" stroke-width="1"/><circle class="xc-d" r="5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/><circle class="xc-d" r="5" fill="var(--s2)" stroke="var(--surface)" stroke-width="2"/></g>`;
  h+=`</svg><div class="tip"></div></div>`;
  CLK={L,pw,n};
  CHARTS.cchart={N:n+1,L,pw,W,x,ys:(i,k)=>{ const v=k===0?me[i]:op[i]; return v==null?null:y(v); },
    tip:i=>({head:i?`${G.plies[i-1].move}수 ${G.plies[i-1].mover==='w'?'백':'흑'}`:'시작', rows:[{c:'var(--s1)',k:'나',v:clk(me[i])},{c:'var(--s2)',k:'상대',v:clk(op[i])}]}),
    pick:i=>go(i)};
  return h;
}
function graphSVG(){
  const n=G.plies.length, W=360, H=90, mid=H/2;
  const pts=G.fens.map((_,i)=>{ const e=i===0?0:G.plies[i-1].cp_w; return [i/n*W, mid - Math.max(-1,Math.min(1,e/1000))*(mid-3)]; });
  const area=`M0 ${mid} `+pts.map(p=>'L'+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ')+` L${pts[pts.length-1][0].toFixed(1)} ${mid} Z`;
  let marks='';
  G.plies.forEach((p,i)=>{ if(p.cls==='blun'||p.cls==='miss'||p.cls==='mist'){ const q=pts[i+1]; marks+=`<circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="3" fill="${p.cls==='mist'?'#ffa459':'#fa412d'}"/>`; } });
  return `<svg class="graph" id="graph" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><rect width="${W}" height="${H}" fill="#403d39"/><path d="${area}" fill="#f0f0f0"/><path d="M0 ${mid} L${W} ${mid}" stroke="#888" stroke-width=".5"/>${marks}<line id="gcur" x1="0" y1="0" x2="0" y2="${H}" stroke="#2a78d6" stroke-width="1.5"/></svg>`;
}
function draw(){
  const n=G.plies.length; const fen=G.fens[IDX]; const p=IDX>0?G.plies[IDX-1]:null; const nx=IDX<n?G.plies[IDX]:null;
  const arrows=[];
  if(SHOW_BEST){ if(p&&p.cls!=='best'&&p.cls!=='good'&&p.best_uci) arrows.push([p.best_uci,GREEN]); else if(nx&&nx.best_uci) arrows.push([nx.best_uci,GREEN]); }
  $('#board').innerHTML=boardSVG(fen,{flip:FLIP,arrows,last:p?[p.uci.slice(0,2),p.uci.slice(2,4)]:[]});
  const cpw=p?p.cp_w:0; const wp=Math.abs(cpw)>=9000?(cpw>0?100:0):(50+50*(2/(1+Math.exp(-0.00368208*cpw))-1));
  const bar=$('#evalbar'); const wEl=bar.querySelector('.w');
  wEl.style.height=wp+'%'; if(FLIP){wEl.style.top='0';wEl.style.bottom='auto';} else {wEl.style.top='auto';wEl.style.bottom='0';}
  const sp=bar.querySelector('span'); sp.textContent=evW(cpw).replace('+',''); const whiteAhead=cpw>=0; sp.style.color=whiteAhead?'#000':'#fff';
  const atBottom = whiteAhead ? !FLIP : FLIP; sp.style.top=atBottom?'auto':'2px'; sp.style.bottom=atBottom?'2px':'auto';
  let info='';
  if(!p) info=`<b>시작 국면</b> · › 버튼, 판 스와이프, 수 목록, 그래프로 이동` + (nx&&SHOW_BEST?`<div class="sub">초록 화살표: 이 국면의 엔진 추천 ${esc(nx.best)}</div>`:'');
  else {
    const who=p.mine?'나':'상대'; const c=CLS[p.cls];
    info=`<div><span class="cls ${c[1]}">${c[0]}</span> <b>${mv(p)}</b> <span class="sub">(${who}) · 평가 ${ev(p.cp_before)} → ${ev(p.cp_after)}${p.wp_loss?` · 승률 −${p.wp_loss}%p`:''}</span></div>`;
    if(p.cls!=='best'&&p.cls!=='good'&&p.best) info+=`<div style="margin-top:3px">정답은 <b class="mono">${esc(p.best)}</b> (초록 화살표)</div>`;
    else if(nx&&SHOW_BEST) info+=`<div class="sub" style="margin-top:3px">다음 국면 엔진 추천: ${esc(nx.best)} (초록 화살표)</div>`;
    if(p.mine&&p.cat) info+=`<div style="margin-top:5px">${catTag(p.cat,COACH&&COACH.focus&&COACH.focus.includes(p.cat)?'rep':'')} <span class="sub">${esc(catOf(p.cat).d)}</span></div>`;
    info+=`<div class="sub" style="margin-top:3px">남은 시간 ${clk(p.clock)}${p.spent!=null?` · 이 수에 ${Math.round(p.spent)}초`:''}</div>`;
    const L=G.lines[String(IDX)];
    if(L&&L.best_line&&L.best_line.length) info+=`<div class="sub" style="margin-top:3px">정답 수순: <span class="mono">${esc(L.best_line.map(s=>s.san).join(' '))}</span></div>`;
    if(L&&L.refutation&&L.refutation.length) info+=`<div class="sub">내 수 뒤 반격: <span class="mono">${esc(L.refutation.map(s=>s.san).join(' '))}</span></div>`;
  }
  $('#info').innerHTML=info;
  document.querySelectorAll('.mv[data-jump]').forEach(el=>el.classList.toggle('cur',+el.dataset.jump===IDX));
  { const st=$('#strip'), c=st&&st.querySelector('.mv.cur'); if(st) st.scrollTo({left:c?c.offsetLeft-st.offsetLeft-st.clientWidth/2+c.clientWidth/2:0,behavior:'smooth'}); }
  const g=$('#gcur'); if(g){ g.setAttribute('x1',(IDX/n*360).toFixed(1)); g.setAttribute('x2',(IDX/n*360).toFixed(1)); }
  const cc=$('#ccur'); if(cc&&CLK){ const X=(CLK.L+IDX/CLK.n*CLK.pw).toFixed(1); cc.setAttribute('x1',X); cc.setAttribute('x2',X); }
  applyTheme();
}
function go(i){ IDX=Math.max(0,Math.min(G.plies.length,i)); draw(); }
document.addEventListener('click',(e)=>{
  if(!G) return;
  const j=e.target.closest('[data-jump]'); if(j){ go(+j.dataset.jump); return; }
  const nv=e.target.closest('[data-go]'); if(nv){ const g=+nv.dataset.go; go(g===0?0:g===9?G.plies.length:IDX+g); return; }
  if(e.target.closest('#optbest')){ SHOW_BEST=!SHOW_BEST; $('#optbest').classList.toggle('on',SHOW_BEST); draw(); return; }
  if(e.target.closest('#optflip')){ FLIP=!FLIP; draw(); return; }
  const gr=e.target.closest('#graph'); if(gr){ const r=gr.getBoundingClientRect(); go(Math.round((e.clientX-r.left)/r.width*G.plies.length)); }
});
document.addEventListener('keydown',(e)=>{ if(!G) return; if(e.key==='ArrowLeft') go(IDX-1); else if(e.key==='ArrowRight') go(IDX+1); else if(e.key==='Home') go(0); else if(e.key==='End') go(G.plies.length); });
let tx=null; document.addEventListener('touchstart',e=>{ if(e.target.closest('.board')) tx=e.touches[0].clientX; },{passive:true});
document.addEventListener('touchend',e=>{ if(tx==null) return; const dx=e.changedTouches[0].clientX-tx; tx=null; if(Math.abs(dx)>40) go(IDX+(dx<0?1:-1)); },{passive:true});
load();
