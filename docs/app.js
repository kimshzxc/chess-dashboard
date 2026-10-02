/* 대시보드. shared.js(공용 함수) 다음에 module 로 로드된다. */
const [PIECES, DATA] = await Promise.all([
  fetch('pieces.svg').then(r=>r.text()),
  fetch('stats.json',{cache:'no-cache'}).then(r=>r.json()),
]);
document.body.insertAdjacentHTML('afterbegin', PIECES);
document.title = `${DATA.username} 래피드 분석`;
let W = 'all';
$('#tpanel-slot').innerHTML=themePanel();

const gameLink=(url,ply)=>`game.html?id=${gameId(url)}${ply?`&ply=${ply}`:''}`;
const plyOf=(w)=> (w.move-1)*2+(w.mover==='w'?1:2);

function blunderCard(w){
  const head=`<div class="h"><b><span class="mono">${mv(w)}</span> 대신 <span class="mono">${esc(w.best)}</span></b><span class="s">${w.date}</span></div>
      <div class="s">${ev(w.cp_before)} → ${ev(w.cp_after)} (−${w.wp_loss}%p) · ${w.color==='w'?'백':'흑'} vs ${esc(w.opp)} · ${PH[w.phase]} · 남은시간 ${clk(w.clock)}${w.spent!=null?` · 이 수에 ${Math.round(w.spent)}초`:''}</div>
      <div class="links"><a href="${gameLink(w.url,plyOf(w))}">게임 전체 보기 →</a><a href="${esc(w.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>`;
  return `<div class="game"><div class="m">${head}${w.fen?blunderViewer(w):''}</div></div>`;
}
function blunderRow(w, wid, extra){
  return `<div class="game"><div class="m"><div class="h"><b><span class="mono">${mv(w)}</span> 대신 <span class="mono">${esc(w.best)}</span></b><span class="s">${extra||w.date}</span></div>
      <div class="s">${ev(w.cp_before)} → ${ev(w.cp_after)}${w.wp_loss?` (−${w.wp_loss}%p)`:''} · vs ${esc(w.opp)} · ${PH[w.phase]||''} · 남은시간 ${clk(w.clock)}</div>
      <div class="links"><span class="btn" data-expand="${wid}">장면 보기</span><a href="${gameLink(w.url,plyOf(w))}">게임 전체 보기 →</a><a href="${esc(w.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>
      <div id="${wid}" hidden data-w='${esc(JSON.stringify(w))}'></div></div></div>`;
}

/* 오프닝 경로 뷰어 */
function openingViewer(op, color){
  const path=op.path||[]; if(path.length<2) return '<div class="empty">데이터 부족</div>';
  const flip=color==='b'; const states=[];
  for(let k=0;k<path.length;k++){
    const cur=path[k], nx=path[k+1];
    const st={fen:cur.fen, san:cur.san, arrows:[], last:cur.uci?[cur.uci.slice(0,2),cur.uci.slice(2,4)]:[], bad:!!cur.problem,
              num: cur.san? (cur.mover==='w'?`${cur.move}.`:(k===1?`${cur.move}...`:'')) : ''};
    let cap='';
    if(k>0){
      cap = cur.mine? `나 ${esc(cur.san)} · ${cur.n}판 승률 ${cur.score}%` : `상대 ${esc(cur.san)} · ${cur.n}판`;
      if(cur.mine && cur.avg_loss!=null) cap+=` · 평균 손실 ${cur.avg_loss}`;
      if(cur.problem) cap+=` · <b style="color:${RED}">정답 ${esc(cur.best)}</b>`;
      if(cur.alts&&cur.alts.length) cap+=`<div class="altbox">다른 선택: ${cur.alts.map(a=>`${esc(a.san)}(${a.n})`).join(', ')}</div>`;
    } else cap = `${op.moves} 이후 · ${op.n}판 승률 ${op.score}% · › 로 진행`;
    if(nx){ st.arrows.push([nx.uci, nx.problem?RED:(nx.mine?BLUE:GRAY)]); if(nx.problem&&nx.best_uci) st.arrows.push([nx.best_uci,GREEN]);
      if(nx.problem) cap+=`<div style="color:${RED}">다음 수 ${esc(nx.san)} 이 자주 문제 → 정답 ${esc(nx.best)}</div>`; }
    st.caption=cap; states.push(st);
  }
  return viewer({flip,lines:[{label:'진행',states}]});
}
let OPEN_SEL={w:0,b:0};
function openingBody(op, color){
  let h=openingViewer(op,color);
  const tr=op.trouble||[];
  if(tr.length){
    h+=`<h3>이 오프닝에서 반복되는 실수</h3>`;
    tr.forEach((w,i)=>{ h+=blunderRow(w,`tr${color}${OPEN_SEL[color]}_${i}`,`${w.n}번 · 평균 손실 ${w.avg_loss}`); });
  }
  return h;
}
function openingSection(S){
  let h=`<section id="s-open"><h2>오프닝 탐색기<small>내가 자주 두는 수순을 판에서 확인</small></h2>
  <div class="legend"><span><i style="background:${BLUE}"></i>내 다음 수</span><span><i style="background:${GRAY}"></i>상대 다음 수</span><span><i style="background:${RED}"></i>자주 틀리는 수</span><span><i style="background:${GREEN}"></i>엔진 정답</span></div>`;
  for(const [col,name] of [['w','백'],['b','흑']]){
    const rows=S.openings[col]||[];
    h+=`<div class="card"><h3 style="margin-top:0">${name}으로</h3>`;
    if(!rows.length){h+='<div class="empty">데이터 부족</div></div>';continue;}
    h+=`<div class="oplist">`+rows.map((r,i)=>`<div class="opitem ${i===OPEN_SEL[col]?'on':''}" data-op="${col}" data-i="${i}"><div><span class="mono">${esc(r.moves)}</span><div class="nm">${esc(r.name)} · ${r.n}판 · 15수 내 대실수 ${r.early_blunders}</div></div><div class="sc" style="color:${r.score<45?'var(--loss)':r.score>=60?'var(--win)':'inherit'}">${r.score}%</div></div>`).join('')+`</div>`;
    h+=`<div id="op-${col}">${openingBody(rows[OPEN_SEL[col]],col)}</div></div>`;
  }
  return h+'</section>';
}
document.addEventListener('click',(e)=>{
  const t=e.target.closest('[data-op]'); if(!t) return;
  const col=t.dataset.op, i=+t.dataset.i; OPEN_SEL[col]=i;
  const S=DATA.windows[W]; document.querySelectorAll(`[data-op="${col}"]`).forEach(x=>x.classList.toggle('on',+x.dataset.i===i));
  const box=document.getElementById('op-'+col); box.innerHTML=openingBody(S.openings[col][i],col); drawAll(box); applyTheme();
});
document.addEventListener('click',(e)=>{
  const t=e.target.closest('[data-expand]'); if(!t) return;
  const box=document.getElementById(t.dataset.expand); const w=JSON.parse(box.dataset.w||'null');
  if(!box.innerHTML && w){ box.innerHTML=blunderViewer(w); drawAll(box); applyTheme(); }
  box.hidden=!box.hidden; t.textContent=box.hidden?'장면 보기':'접기';
});

/* ---------- 보완점 추이 분석 시트 ---------- */
const fmtV=(t,v)=>{ if(v==null||isNaN(v)) return '-';
  if(t.fmt==='pct') return (v*100).toFixed(1)+'%'; if(t.fmt==='pct100') return v.toFixed(1)+'%';
  if(t.fmt==='clock'){ const a=Math.abs(Math.round(v)); return (v<0?'−':'')+`${Math.floor(a/60)}:${String(a%60).padStart(2,'0')}`; }
  return v.toFixed(t.fmt==='num1'?1:2); };
const fmtD=(t,d)=>{ const sg=d>0?'+':d<0?'−':'±'; const a=Math.abs(d);
  if(t.fmt==='pct') return sg+(a*100).toFixed(1)+'%p'; if(t.fmt==='pct100') return sg+a.toFixed(1)+'%p';
  if(t.fmt==='clock') return sg+fmtV(t,a); return sg+a.toFixed(t.fmt==='num1'?1:2); };
const niceStep=(r)=>{ if(r<=0) return 1; const p=Math.pow(10,Math.floor(Math.log10(r))); const m=r/p; return (m<1.5?1:m<3.5?2:m<7.5?5:10)*p; };
const CHARTS={};   // svg id → {N,L,pw,W,x,ys(i),tip(i)} 크로스헤어 툴팁용
function trendChart(t){
  const N=t.series.length; if(N<2) return '';
  const W=360,H=180,L=46,R=14,T=16,B=34,pw=W-L-R,ph=H-T-B;
  const sc=t.fmt==='pct'?100:1;
  const vals=t.series.map(s=>s[1]/s[2]*sc);
  const win=Math.max(5,Math.min(20,Math.round(N/8)));
  const roll=[]; for(let i=0;i<N;i++){ const a=Math.max(0,i-win+1); let sv=0,sn=0; for(let j=a;j<=i;j++){ sv+=t.series[j][1]; sn+=t.series[j][2]; } roll.push(sv/sn*sc); }
  let lo=Math.min(...vals,...roll), hi=Math.max(...vals,...roll); if(hi-lo<1e-9) hi=lo+1;
  const step=niceStep((hi-lo)/3); lo=Math.floor(lo/step)*step; hi=Math.ceil(hi/step)*step;
  const x=i=>L+i/(N-1)*pw, y=v=>T+(1-(v-lo)/(hi-lo))*ph;
  const axisV=v=>t.fmt==='pct'||t.fmt==='pct100'?Math.round(v*10)/10+'%':t.fmt==='clock'?fmtV(t,v):Math.round(v*100)/100;
  const id='tchart'; let h=`<div class="tchart-wrap"><svg class="tchart xchart" id="${id}" viewBox="0 0 ${W} ${H}">`;
  for(let v=lo;v<=hi+1e-9;v+=step){ h+=`<line x1="${L}" x2="${W-R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"/><text x="${L-6}" y="${(y(v)+4).toFixed(1)}" font-size="11" text-anchor="end" fill="var(--muted)">${axisV(v)}</text>`; }
  if(t.k&&t.k<N){ const xs=x(N-t.k-0.5).toFixed(1); h+=`<line x1="${xs}" x2="${xs}" y1="${T}" y2="${T+ph}" stroke="var(--muted)" stroke-width="1"/><text x="${(+xs+4).toFixed(1)}" y="${T+10}" font-size="11" fill="var(--text2)">최근 ${t.k}판</text>`; }
  h+=vals.map((v,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="var(--me)" opacity=".28"/>`).join('');
  h+=`<path d="${roll.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--me)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  h+=`<text x="${L}" y="${H-6}" font-size="11" fill="var(--muted)">${t.series[0][0]}</text><text x="${W-R}" y="${H-6}" font-size="11" text-anchor="end" fill="var(--muted)">${t.series[N-1][0]}</text><text x="${(L+pw/2).toFixed(1)}" y="${H-6}" font-size="11" text-anchor="middle" fill="var(--muted)">게임 순서 →</text>`;
  h+=`<g class="xc" style="display:none"><line class="xc-l" y1="${T}" y2="${T+ph}" stroke="var(--text2)" stroke-width="1"/><circle class="xc-d" r="5" fill="var(--me)" stroke="var(--surface)" stroke-width="2"/></g>`;
  h+=`</svg><div class="tip"></div></div>`;
  CHARTS[id]={N,L,pw,W,x,ys:i=>y(roll[i]),tip:i=>`${t.series[i][0]} · 이 판 ${fmtV(t,vals[i]/sc)} · 최근 ${win}판 평균 ${fmtV(t,roll[i]/sc)}`};
  return h;
}
function ratingChart(series){
  const N=series.length; if(N<2) return '';
  const W=360,H=170,L=40,R=12,T=14,B=30,pw=W-L-R,ph=H-T-B;
  const vals=series.map(s=>s[1]);
  let lo=Math.min(...vals), hi=Math.max(...vals); if(hi-lo<10){ hi=lo+10; }
  const step=niceStep((hi-lo)/3); lo=Math.floor(lo/step)*step; hi=Math.ceil(hi/step)*step;
  const x=i=>L+i/(N-1)*pw, y=v=>T+(1-(v-lo)/(hi-lo))*ph;
  const col={W:'var(--win)',L:'var(--loss)',D:'var(--draw)'};
  let h=`<div class="tchart-wrap"><svg class="tchart xchart" id="rchart" viewBox="0 0 ${W} ${H}">`;
  for(let v=lo;v<=hi+1e-9;v+=step) h+=`<line x1="${L}" x2="${W-R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"/><text x="${L-6}" y="${(y(v)+4).toFixed(1)}" font-size="11" text-anchor="end" fill="var(--muted)">${Math.round(v)}</text>`;
  h+=`<path d="${vals.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--me)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  const rr=N>120?2.2:N>60?3:4;
  h+=series.map((s,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(s[1]).toFixed(1)}" r="${rr}" fill="${col[s[2]]||col.D}" stroke="var(--surface)" stroke-width="1"/>`).join('');
  h+=`<text x="${L}" y="${H-6}" font-size="11" fill="var(--muted)">${series[0][0]}</text><text x="${W-R}" y="${H-6}" font-size="11" text-anchor="end" fill="var(--muted)">${series[N-1][0]}</text>`;
  h+=`<g class="xc" style="display:none"><line class="xc-l" y1="${T}" y2="${T+ph}" stroke="var(--text2)" stroke-width="1"/><circle class="xc-d" r="5" fill="var(--me)" stroke="var(--surface)" stroke-width="2"/></g>`;
  h+=`</svg><div class="tip"></div></div>`;
  const nm={W:'승',L:'패',D:'무'};
  CHARTS.rchart={N,L,pw,W,x,ys:i=>y(vals[i]),tip:i=>`${series[i][0]} · ${series[i][1]} · ${nm[series[i][2]]||''}`};
  return h;
}
function trendView(w){
  const t=w.trend; if(!t) return '<div class="empty">추이 데이터가 없습니다.</div>';
  let h=`<div class="sub" style="margin-bottom:10px">지표: <b>${esc(t.label)}</b> · ${t.lower_better?'낮을수록 좋음':'높을수록 좋음'} · 이 기간 ${t.n}판 기준</div>`;
  if(t.status==='insufficient'){
    h+=`<div class="verdict"><span class="ic">판단 보류</span>해당 게임이 ${t.n}판뿐이라 추이를 판단할 수 없습니다. 10판 이상 쌓이면 분석합니다.</div>`;
    if(t.series.length>=2) h+=`<div class="card">${trendChart(t)}</div>`;
    return h;
  }
  const dir=t.lower_better?(t.delta<0?'줄었습니다':'늘었습니다'):(t.delta>0?'올랐습니다':'내려갔습니다');
  const msg={better:['개선',`최근 ${t.k}판에서 뚜렷이 ${dir}. 우연이라고 보기 어려운 변화입니다.`],
             maybe_better:['개선 조짐',`최근 ${t.k}판에서 ${dir}. 다만 아직 우연일 가능성을 배제할 수 없습니다.`],
             flat:['변화 없음',`최근 ${t.k}판과 이전을 비교하면 차이가 우연 범위 안입니다.`],
             maybe_worse:['악화 조짐',`최근 ${t.k}판에서 ${dir}. 아직 확실하지 않지만 주의가 필요합니다.`],
             worse:['악화',`최근 ${t.k}판에서 뚜렷이 ${dir}. 우연이라고 보기 어려운 변화입니다.`]}[t.status];
  h+=`<div class="verdict ${t.status}"><span class="ic">${msg[0]}</span>${msg[1]}<div class="p">이전 ${t.n_before}판 ${fmtV(t,t.v_before)} → 최근 ${t.n_recent}판 ${fmtV(t,t.v_recent)} (${fmtD(t,t.delta)}) · p=${t.p<0.001?'<0.001':t.p.toFixed(3)}</div></div>`;
  const dc=t.status==='flat'?'inherit':(t.improved?'var(--win)':'var(--loss)');
  h+=`<div class="tiles3"><div class="tile"><div class="k">이전 ${t.n_before}판</div><div class="v">${fmtV(t,t.v_before)}</div></div><div class="tile"><div class="k">최근 ${t.n_recent}판</div><div class="v">${fmtV(t,t.v_recent)}</div></div><div class="tile"><div class="k">변화</div><div class="v" style="color:${dc}">${fmtD(t,t.delta)}</div></div></div>`;
  h+=`<div class="card"><div class="sub" style="margin-bottom:4px">게임별 값(점)과 이동 평균(선) · 누르면 값 표시</div>${trendChart(t)}</div>`;
  if(t.rho!=null){
    const up=t.rho>0, good=t.lower_better?!up:up; const strength=t.rho_p<0.05?'뚜렷한':t.rho_p<0.2?'약한':'';
    const txt=t.rho_p<0.2?`게임을 거듭할수록 ${up?'높아지는':'낮아지는'} ${strength} 경향이 있습니다 (${good?'좋은 방향':'나쁜 방향'}).`:'전체 기간으로 봐도 일관된 방향의 추세는 없습니다.';
    h+=`<div class="verdict ${t.rho_p<0.2?(good?'maybe_better':'maybe_worse'):''}"><span class="ic">전체 기간</span>${txt}<div class="p">순위 상관 ρ=${t.rho.toFixed(2)} · p=${t.rho_p<0.001?'<0.001':t.rho_p.toFixed(3)} · ${t.n}판</div></div>`;
  }
  const unit={day:'날짜',week:'주 (월요일 시작)',month:'월'}[t.unit];
  h+=`<div class="card"><table><tr><th>${unit}</th><th class="n">판</th>${t.rate?'<th class="n">표본</th>':''}<th class="n">값</th></tr>`;
  for(const b of t.buckets) h+=`<tr><td>${b.label}</td><td class="n">${b.games}</td>${t.rate?`<td class="n">${b.n}</td>`:''}<td class="n">${fmtV(t,b.value)}</td></tr>`;
  h+=`</table></div>`;
  h+=`<div class="method">방법: 최근 ${t.k}판과 그 이전을 ${t.rate?'두 비율의 z 검정':'Welch t 검정'}으로 비교했습니다. p값은 두 구간의 차이가 우연히 나타날 확률로, 0.05 미만이면 실제 변화로, 0.2 미만이면 조짐으로 봅니다. 전체 기간 추세는 게임 순서와 지표의 스피어만 순위 상관입니다.${t.rate?' 비율형 지표의 점은 판별 비율이라 표본이 작으면 크게 흔들립니다. 선(이동 평균)을 보세요.':''}</div>`;
  return h;
}
function openSheet(i){
  const S=DATA.windows[W]; const w=S&&S.weaknesses[i]; if(!w) return;
  $('#sheet-title').textContent=w.title; $('#sheet-sub').textContent={all:'전체 기간','30d':'최근 30일','7d':'최근 7일'}[W]+' 기준 추이';
  $('#sheet-body').innerHTML=trendView(w); $('#sheet-body').scrollTop=0;
  $('#sheet').classList.add('open'); document.body.style.overflow='hidden';
}
function closeSheet(){ $('#sheet').classList.remove('open'); document.body.style.overflow=''; delete CHARTS.tchart; }
document.addEventListener('click',(e)=>{
  const c=e.target.closest('[data-weak]'); if(c){ openSheet(+c.dataset.weak); return; }
  if(e.target.closest('#sheet-x')||e.target===$('#sheet')) closeSheet();
});
document.addEventListener('keydown',(e)=>{ if(e.key==='Escape') closeSheet(); });
function tcMove(e){
  const svg=e.target.closest('svg.xchart'); if(!svg) return; const C=CHARTS[svg.id]; if(!C) return;
  const r=svg.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*C.W;
  const i=Math.max(0,Math.min(C.N-1,Math.round((px-C.L)/C.pw*(C.N-1))));
  const g=svg.querySelector('.xc'); g.style.display=''; const X=C.x(i).toFixed(1);
  const l=svg.querySelector('.xc-l'), d=svg.querySelector('.xc-d'); l.setAttribute('x1',X); l.setAttribute('x2',X); d.setAttribute('cx',X); d.setAttribute('cy',C.ys(i).toFixed(1));
  const tip=svg.parentElement.querySelector('.tip'); tip.textContent=C.tip(i); tip.classList.add('on');
}
document.addEventListener('pointerleave',(e)=>{ const svg=e.target&&e.target.closest&&e.target.closest('svg.xchart'); if(!svg) return; const g=svg.querySelector('.xc'); if(g) g.style.display='none'; const tip=svg.parentElement.querySelector('.tip'); if(tip) tip.classList.remove('on'); },true);

function spark(evals, worstPly){
  if(!evals||evals.length<2) return '';
  const n=evals.length, W=300, H=44, mid=H/2;
  const pts=evals.map((e,i)=>[i/(n-1)*W, mid - Math.max(-1,Math.min(1,e/1000))*(mid-2)]);
  const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area=`M0 ${mid} `+pts.map(p=>'L'+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ')+` L${W} ${mid} Z`;
  let dot=''; if(worstPly!=null&&worstPly<n){ const p=pts[worstPly]; dot=`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3.5" fill="${RED}"/>`; }
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="0" y1="${mid}" x2="${W}" y2="${mid}" stroke="var(--line)"/><path d="${area}" fill="var(--me)" opacity=".18"/><path d="${d}" fill="none" stroke="var(--me)" stroke-width="1.5"/>${dot}</svg>`;
}
function bars(rows, max){
  let h='<div class="bars">';
  for(const r of rows){
    const fmt=r.fmt||((x)=>x);
    if(r.opp!==undefined){
      h+=`<div class="lbl">${esc(r.label)}</div><div class="pair"><div class="bar" style="width:${Math.max(2,r.me/max*100*0.78)}%"><span>${fmt(r.me)}</span></div><div class="bar opp" style="width:${Math.max(2,r.opp/max*100*0.78)}%"><span>${fmt(r.opp)}</span></div></div>`;
    } else {
      const k=r.note?(r.note.length>8?0.5:0.62):0.78;
      h+=`<div class="lbl">${esc(r.label)}</div><div><div class="bar" style="width:${Math.max(2,r.me/max*100*k)}%"><span>${fmt(r.me)}${r.note?` <span style="position:static;color:var(--muted)">${esc(r.note)}</span>`:''}</span></div></div>`;
    }
  }
  return h+'</div>';
}
const legend = ()=>`<div class="legend"><span><i style="background:var(--me)"></i>나</span><span><i style="background:var(--opp)"></i>상대</span></div>`;

function render(){
  const S = DATA.windows[W];
  document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.w===W));
  $('#title').textContent = `${DATA.username} · 래피드 분석`;
  $('#foot').innerHTML = `마지막 갱신 ${DATA.generated} (KST) · Stockfish 19 depth ${(DATA.meta||{}).depth||14}, 수순 depth ${(DATA.meta||{}).pv_depth||16} · 게임이 끝나면 1~2분 안에 자동 갱신<br>기물: maestro (sadsnake1, CC BY-NC-SA 4.0), cburnett (GPLv2+), merida (GPLv2+), alpha (Eric Bentzen), california (Jerry S., CC BY-NC-SA 4.0)`;
  if(!S){ $('#subtitle').textContent=''; $('#main').innerHTML='<div class="empty">이 기간에 분석된 래피드 게임이 없습니다.</div>'; return; }
  const o=S.overview, t=S.time, c=S.conversion, tc=S.tactics;
  $('#subtitle').textContent = `${o.first_date} ~ ${o.last_date} · ${o.games}판 · 레이팅 ${o.rating} (최고 ${o.rating_best})`;
  let h='';
  const rd=o.rating-o.rating_start;
  h+=`<section class="hero" style="margin-top:14px"><div class="tiles">
    <div class="tile"><div class="k">전적 · 승률 <b>${o.score}%</b></div><div class="v sm">${o.win}승 ${o.draw}무 ${o.loss}패</div><div class="d">백 ${pct(o.score_w)} · 흑 ${pct(o.score_b)}</div></div>
    <div class="tile"><div class="k">정확도</div><div class="v">${o.accuracy}%</div><div class="d">상대 ${o.opp_accuracy}%</div></div>
    <div class="tile"><div class="k">대실수 / 판</div><div class="v">${o.blunders_pg}</div><div class="d">상대 ${o.opp_blunders_pg}</div></div>
    <div class="tile"><div class="k">레이팅 변화</div><div class="v" style="color:${rd>0?'var(--win)':rd<0?'var(--loss)':'inherit'}">${rd>=0?'+':''}${rd}</div><div class="d">${o.rating_start} → ${o.rating}</div></div>
  </div>
  ${S.rating_series&&S.rating_series.length>1?`<div class="card" style="margin-top:10px"><div class="sub" style="margin-bottom:4px">레이팅 추이 · 판마다 <i class="dot" style="background:var(--win)"></i>승 <i class="dot" style="background:var(--loss)"></i>패 <i class="dot" style="background:var(--draw)"></i>무 · 누르면 값 표시</div>${ratingChart(S.rating_series)}</div>`:''}
  <a class="card pz" href="puzzle.html"><div><b>오늘의 퍼즐 10개</b><div class="sub">내가 실제로 틀린 국면에서 최선 수 찾기</div></div><span class="btn on">풀기 ›</span></a>
  </section>`;
  h+=`<section id="s-weak"><h2>보완점<small>통계에서 자동 추출</small></h2>`;
  if(!S.weaknesses.length) h+='<div class="empty">두드러진 약점이 없습니다.</div>';
  for(const w of S.weaknesses){ const ic={critical:'중요',serious:'주의',warning:'참고',good:'강점'}[w.level]||'';
    h+=`<div class="card weak ${w.level}" data-weak="${S.weaknesses.indexOf(w)}"><div class="t"><span class="ic">${ic}</span>${esc(w.title)}</div><p>${esc(w.text)}</p><div class="go">추이 분석 ›</div></div>`; }
  h+='</section>';
  // 최근 게임
  const RECENT_N=6;
  h+=`<section id="s-recent"><h2>최근 게임<small>카드를 누르면 전체 수순 분석</small></h2><div class="card">`;
  S.recent.forEach((g,gi)=>{
    if(gi===RECENT_N) h+=`<div class="fold" id="fold-recent" hidden>`;
    const how={checkmated:'메이트',resigned:'기권',timeout:'시간',abandoned:'포기',agreed:'합의',repetition:'반복',stalemate:'스테일',insufficient:'기물부족'};
    const endby=g.outcome==='W'?how[g.opp_result]:how[g.my_result];
    const w=g.worst; const wid=`rw${gi}`; const worstPly=w?plyOf(w)-1:null;
    h+=`<div class="game"><div class="row"><div class="res ${g.outcome}">${g.outcome==='W'?'승':g.outcome==='L'?'패':'무'}</div><div class="m">
      <a href="${gameLink(g.url)}" style="color:inherit;display:block"><div class="h"><b>${g.color==='w'?'백':'흑'} vs ${esc(g.opp)} (${g.opp_elo})</b><span class="s dt">${g.date} ›</span></div>
      <div class="s eco">${esc(g.eco_name)}</div>
      <div class="s">${endby||''} · 정확도 ${g.accuracy}% · 대실수 ${g.blunders} 실수 ${g.mistakes}${g.hung?` · 방치 ${g.hung}`:''}${g.missed_mate?` · 외통놓침 ${g.missed_mate}`:''} · 종료시 시계 ${clk(g.my_final_clock)} / ${clk(g.opp_final_clock)}</div>
      ${spark(g.evals, worstPly)}</a>
      ${w&&w.wp_loss>=10?`<div class="w">결정적 실수 <span class="mono">${mv(w)}</span> → 정답 <span class="mono">${esc(w.best)}</span> (${ev(w.cp_before)} → ${ev(w.cp_after)}, 남은시간 ${clk(w.clock)})</div>`:''}
      <div class="links">${w&&w.fen?`<span class="btn" data-expand="${wid}">장면 보기</span>`:''}<a href="${gameLink(g.url)}">전체 분석 →</a><a href="${esc(g.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>
      ${w&&w.fen?`<div id="${wid}" hidden data-w='${esc(JSON.stringify({...w,color:g.color,opp:g.opp,date:g.date,url:g.url}))}'></div>`:''}
    </div></div></div>`;
  });
  if(S.recent.length>RECENT_N) h+=`</div><div class="more"><span class="btn" data-fold="fold-recent" data-unit="판">나머지 ${S.recent.length-RECENT_N}판 보기</span></div>`;
  h+='</div></section>';
  // 최악의 실수
  const WORST_N=8;
  h+=`<section id="s-worst"><h2>가장 큰 실수<small>승률 30%p 이상 손해 · 빨강 내 수, 초록 정답</small></h2><div class="card">`;
  if(!S.worst.length) h+='<div class="empty">없음</div>';
  S.worst.forEach((w,i)=>{ if(i===WORST_N) h+=`<div class="fold" id="fold-worst" hidden>`; h+= i<3 ? blunderCard(w) : blunderRow(w,`ww${i}`); });
  if(S.worst.length>WORST_N) h+=`</div><div class="more"><span class="btn" data-fold="fold-worst" data-unit="개">나머지 ${S.worst.length-WORST_N}개 보기</span></div>`;
  h+='</div></section>';
  // 유형별
  const ex=S.examples||{};
  h+=`<section id="s-ex"><h2>유형별 대표 실수<small>최근 게임부터</small></h2>`;
  for(const [k,label,desc] of [['hung','기물 방치','시간이 1분 이상 남았는데 한 수에 잡히는 기물을 둔 장면'],['missed_mate','외통 놓침','3수 이내 강제 외통이 있었는데 다른 수를 둔 장면'],['collapse','유리한 판 붕괴','+3 이상 유리하다가 한 수로 불리해진 장면']]){
    const arr=ex[k]||[]; if(!arr.length) continue;
    h+=`<div class="card"><h3 style="margin-top:0">${label}</h3><div class="sub">${desc}</div>`;
    const EX_N=5;
    arr.forEach((w,i)=>{ if(i===EX_N) h+=`<div class="fold" id="fold-ex-${k}" hidden>`; h+= i===0 ? blunderCard(w) : blunderRow(w,`ex${k}${i}`); });
    if(arr.length>EX_N) h+=`</div><div class="more"><span class="btn" data-fold="fold-ex-${k}" data-unit="개">나머지 ${arr.length-EX_N}개 보기</span></div>`;
    h+='</div>';
  }
  h+='</section>';
  h+=openingSection(S);
  // 시간
  h+=`<section id="s-time"><h2>시간 관리</h2><div class="card">${legend()}<div class="sub" style="margin-bottom:6px">N수 시점 남은 시간 (중앙값)</div>`;
  h+=bars(t.clock_at.filter(r=>r.me!=null&&r.opp!=null).map(r=>({label:`${r.move}수`,me:r.me,opp:r.opp,fmt:clk})),600);
  h+=`</div><div class="tiles">
    <div class="tile"><div class="k">시간패</div><div class="v">${t.timeouts}</div><div class="d">이기던 판 ${t.timeouts_winning} · 상대 시간패 ${t.opp_timeouts}</div></div>
    <div class="tile"><div class="k">20수에 시간 뒤진 판 승률</div><div class="v">${pct(t.behind_at_20.score)}</div><div class="d">${t.behind_at_20.n}판 · 앞선 판 ${pct(t.ahead_at_20.score)} (${t.ahead_at_20.n}판)</div></div>
    <div class="tile"><div class="k">오프닝 장고 (1~10수, 45초+)</div><div class="v">${t.long_thinks_opening}</div><div class="d">전체 장고 ${t.long_thinks_total}회</div></div>
    <div class="tile"><div class="k">30초 미만으로 끝난 판</div><div class="v">${t.low_clock_games.n}</div><div class="d">그중 패배 ${t.low_clock_games.losses}</div></div>
  </div>`;
  const bc=t.blunder_by_clock, bs=t.blunder_by_spent; const mx=Math.max(...bc.map(b=>b.rate),...bs.map(b=>b.rate),1);
  h+=`<div class="card"><div class="sub" style="margin-bottom:6px">남은 시간별 대실수율</div>${bars(bc.map(b=>({label:b.label,me:b.rate,fmt:pct,note:`(${b.moves}수)`})),mx)}</div>`;
  h+=`<div class="card"><div class="sub" style="margin-bottom:6px">한 수에 쓴 시간별 대실수율</div>${bars(bs.map(b=>({label:b.label,me:b.rate,fmt:pct,note:`(${b.moves}수, 정확도 ${b.accuracy}%)`})),mx)}</div></section>`;
  // 틸트·세션
  const tl=S.tilt;
  if(tl){
    const pick=(arr,l)=>arr.find(x=>x.label===l)||{};
    const aL=pick(tl.after,'직전 판 패배'), aW=pick(tl.after,'직전 판 승리');
    h+=`<section id="s-tilt"><h2>틸트·세션<small>30분 이상 비면 새 세션으로 봄 · 괄호는 판 수</small></h2><div class="tiles">
      <div class="tile"><div class="k">직전 판 패배 후 승률</div><div class="v" style="color:${aL.score!=null&&aL.score<=o.score-8?'var(--loss)':'inherit'}">${pct(aL.score)}</div><div class="d">${aL.n||0}판 · 승리 후 ${pct(aW.score)} (${aW.n||0}판)</div></div>
      <div class="tile"><div class="k">세션</div><div class="v">${tl.sessions.n}</div><div class="d">보통 ${tl.sessions.median_len}판 · 최장 ${tl.sessions.max_len}판 · 6판 이상 ${tl.sessions.long}회</div></div>
    </div>`;
    const sb=(rows)=>bars(rows.filter(r=>r.n).map(r=>({label:r.label,me:r.score,fmt:pct,note:`(${r.n}판${r.accuracy!=null?`, 정확도 ${r.accuracy}%`:''})`})),100);
    h+=`<div class="card"><div class="sub" style="margin-bottom:6px">같은 세션에서 연패한 뒤의 승률</div>${sb(tl.streak)}</div>`;
    h+=`<div class="card"><div class="sub" style="margin-bottom:6px">세션 안에서 몇 판째인가에 따른 승률</div>${sb(tl.session_pos)}</div>`;
    h+=`<div class="card"><div class="sub" style="margin-bottom:6px">시간대별 승률 (KST)</div>${sb(tl.hours)}</div></section>`;
  }
  // 국면
  h+=`<section id="s-phase"><h2>국면별</h2><div class="card"><table><tr><th>국면</th><th class="n">수</th><th class="n">정확도</th><th class="n">상대</th><th class="n">대실수율</th></tr>`;
  for(const p of S.phase) h+=`<tr><td>${p.label}</td><td class="n">${p.moves}</td><td class="n">${p.accuracy}%</td><td class="n">${p.opp_accuracy}%</td><td class="n">${p.blunder_rate}%</td></tr>`;
  h+=`</table></div>`;
  if(S.blunder_by_move.length) h+=`<div class="card"><div class="sub" style="margin-bottom:6px">수 구간별 대실수율</div>${bars(S.blunder_by_move.map(b=>({label:b.label+'수',me:b.rate,fmt:pct})),Math.max(...S.blunder_by_move.map(b=>b.rate),1))}</div>`;
  h+='</section>';
  const cw=c.winning, cl=c.losing;
  h+=`<section><h2>마무리와 역전</h2><div class="tiles">
    <div class="tile"><div class="k">+3 이상 유리했던 판</div><div class="v">${cw.n?Math.round(cw.won/cw.n*100):0}% 승</div><div class="d">${cw.n}판 중 ${cw.won}승 ${cw.draw}무 <b style="color:var(--loss)">${cw.lost}패</b></div></div>
    <div class="tile"><div class="k">-3 이하 불리했던 판</div><div class="v">${cl.n?Math.round(cl.won/cl.n*100):0}% 역전</div><div class="d">${cl.n}판 중 ${cl.won}승 ${cl.draw}무 ${cl.lost}패</div></div>
  </div></section>`;
  const hungRows=Object.entries(tc.hung).sort((a,b)=>b[1]-a[1]);
  h+=`<section><h2>전술</h2><div class="tiles">
    <div class="tile"><div class="k">기물 방치 (한 수에 잡히는 기물)</div><div class="v">${tc.hung_total}</div><div class="d">판당 ${tc.hung_pg} · ${hungRows.map(([k,v])=>`${k} ${v}`).join(' · ')||'-'}<br>시간 1분 이상 남았을 때 ${tc.hung_with_time}회</div></div>
    <div class="tile"><div class="k">공짜 기물 안 잡음</div><div class="v">${tc.missed_free}</div><div class="d">잡는 수가 최선(+2 이상)인데 다른 수</div></div>
    <div class="tile"><div class="k">외통 놓침</div><div class="v">${tc.missed_mate_total}</div><div class="d">${Object.entries(tc.missed_mate).map(([k,v])=>`${k}${k==='5'?'+':''}수 외통 ${v}`).join(' · ')||'-'}</div></div>
  </div></section>`;
  if(S.monthly.length>1){
    h+=`<section><h2>월별 추이</h2><div class="card"><table><tr><th>월</th><th class="n">판</th><th class="n">승률</th><th class="n">정확도</th><th class="n">대실수/판</th><th class="n">레이팅</th></tr>`;
    for(const m of S.monthly) h+=`<tr><td>${m.month}</td><td class="n">${m.games}</td><td class="n">${m.score}%</td><td class="n">${m.accuracy}%</td><td class="n">${m.blunders_pg}</td><td class="n">${m.rating}</td></tr>`;
    h+='</table></div></section>';
  }
  $('#main').innerHTML=h;
  drawAll(); applyTheme();
}
document.addEventListener('click',(e)=>{
  const t=e.target.closest('[data-fold]'); if(!t) return;
  const box=document.getElementById(t.dataset.fold); box.hidden=!box.hidden;
  t.textContent=box.hidden?`나머지 ${box.children.length}${t.dataset.unit} 보기`:'접기';
  if(box.hidden) box.parentElement.scrollIntoView({block:'start'});
});
document.querySelectorAll('#tabs button').forEach(b=>b.addEventListener('click',()=>{closeSheet();W=b.dataset.w;try{localStorage.setItem('chess-window',W)}catch(e){};render();window.scrollTo(0,0)}));
try{const s=localStorage.getItem('chess-window'); if(s&&DATA.windows[s]) W=s;}catch(e){}
render();
{ const q=new URLSearchParams(location.search); if(q.get('w')&&DATA.windows[q.get('w')]){ W=q.get('w'); render(); } if(q.get('weak')!=null) openSheet(+q.get('weak')); }
