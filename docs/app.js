/* 대시보드. shared.js(공용 함수) 다음에 module 로 로드된다. */
const [PIECES, DATA] = await Promise.all([
  fetch('pieces.svg').then(r=>r.text()),
  fetch('stats.json',{cache:'no-cache'}).then(r=>r.json()),
]);
document.body.insertAdjacentHTML('afterbegin', PIECES);
document.title = `${DATA.username} 래피드 분석`;
let W = 'all';
$('#tpanel-slot').innerHTML=themePanel(); applyMode();

const gameLink=(url,ply)=>`game.html?id=${gameId(url)}${ply?`&ply=${ply}`:''}`;
const plyOf=(w)=> (w.move-1)*2+(w.mover==='w'?1:2);

function blunderCard(w){
  const head=`<div class="h"><b><span class="mono">${mv(w)}</span> 대신 <span class="mono">${esc(w.best)}</span></b><span class="s">${w.date}</span></div>
      <div class="s">${catTag(w.cat)} ${ev(w.cp_before)} → ${ev(w.cp_after)} (−${w.wp_loss}%p) · ${w.color==='w'?'백':'흑'} vs ${esc(w.opp)} · ${PH[w.phase]} · 남은시간 ${clk(w.clock)}${w.spent!=null?` · 이 수에 ${Math.round(w.spent)}초`:''}</div>
      <div class="links"><a href="${gameLink(w.url,plyOf(w))}">게임 전체 보기 →</a><a href="${esc(w.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>`;
  return `<div class="game"><div class="m">${head}${w.fen?blunderViewer(w):''}</div></div>`;
}
function blunderRow(w, wid, extra){
  return `<div class="game"><div class="m"><div class="h"><b><span class="mono">${mv(w)}</span> 대신 <span class="mono">${esc(w.best)}</span></b><span class="s">${extra||w.date}</span></div>
      <div class="s">${catTag(w.cat)} ${ev(w.cp_before)} → ${ev(w.cp_after)}${w.wp_loss?` (−${w.wp_loss}%p)`:''} · vs ${esc(w.opp)} · ${PH[w.phase]||''} · 남은시간 ${clk(w.clock)}</div>
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
/* 몇 수째에 실수가 몰리는지: 1~15수 막대 */
function moveHist(by){
  const mx=Math.max(...by,1), W=360, H=92, L=4, B=18, T=14, bw=(W-L*2)/by.length, ph=H-T-B;
  let h=`<svg class="mhist" viewBox="0 0 ${W} ${H}" role="img" aria-label="수별 실수 횟수">`;
  by.forEach((v,i)=>{ const bh=v/mx*ph, x=L+i*bw+2, y=T+ph-bh;
    if(v) h+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw-4).toFixed(1)}" height="${Math.max(2,bh).toFixed(1)}" rx="3" fill="var(--s1)"><title>${i+1}수: ${v}회</title></rect>`;
    if(v&&v===mx) h+=`<text x="${(x+bw/2-2).toFixed(1)}" y="${(y-4).toFixed(1)}" font-size="11" font-weight="700" text-anchor="middle" fill="var(--text)">${v}</text>`;
    h+=`<text x="${(x+bw/2-2).toFixed(1)}" y="${H-4}" font-size="10.5" text-anchor="middle" fill="var(--muted)">${i+1}</text>`; });
  return h+`<line x1="${L}" x2="${W-L}" y1="${T+ph+.5}" y2="${T+ph+.5}" stroke="var(--line2)"/></svg>`;
}
const catBars=(cats,n)=>{ const top=cats.slice(0,n); return bars(top.map(c=>({label:catOf(c.key).n,me:c.n,fmt:v=>v+'회'})),Math.max(...top.map(c=>c.n),1)); };
function openingProfile(op, color){
  const m=op.mist; if(!m) return '';
  const base=((coachOf(DATA.windows[W]).early||{}).per_game_by_color||{})[color];
  let h=`<div class="tiles3">
    <div class="tile"><div class="k">15수 안 실수</div><div class="v">${m.per_game}<small>/판</small></div><div class="d">내 ${color==='w'?'백':'흑'} 평균 ${base??'-'}</div></div>
    <div class="tile"><div class="k">처음 틀어지는 수</div><div class="v">${m.first_slip!=null?m.first_slip+'<small>수</small>':'-'}</div><div class="d">실수 없이 15수를 지난 판 ${m.clean}</div></div>
    <div class="tile"><div class="k">승률</div><div class="v">${op.score}<small>%</small></div><div class="d">${op.win}승 ${op.draw}무 ${op.loss}패</div></div>
  </div>`;
  if(m.n){
    h+=`<h3>몇 수째에 틀리나 <span class="sub">(15수 안 실수 ${m.n}개)</span></h3>${moveHist(m.by_move)}`;
    h+=`<h3>이 오프닝에서 많이 나오는 유형</h3>${catBars(m.cats,4)}`;
  }
  return h;
}
function openingBody(op, color){
  let h=openingProfile(op,color);
  const tr=op.trouble||[];
  h+=`<h3>같은 자리에서 반복한 실수 <span class="sub">(같은 국면, 같은 수를 2번 이상)</span></h3>`;
  if(tr.length) tr.forEach((w,i)=>{ h+=blunderRow(w,`tr${color}${OPEN_SEL[color]}_${i}`,`${w.n}번 · 평균 손실 ${w.avg_loss}`); });
  else h+=`<div class="sub">아직 없습니다. 이 오프닝에서는 매번 다른 자리에서 틀립니다.</div>`;
  h+=`<h3>자주 두는 수순</h3><div class="legend"><span><i style="background:${BLUE}"></i>내 다음 수</span><span><i style="background:${GRAY}"></i>상대 다음 수</span><span><i style="background:${RED}"></i>자주 틀리는 수</span><span><i style="background:${GREEN}"></i>엔진 정답</span></div>`+openingViewer(op,color);
  return h;
}
function openingSection(S){
  const ea=coachOf(S).early;
  let h=`<section id="s-open" data-view="mistakes" data-sub="open"><h2>수순 탐색기<small>양쪽의 첫 두 수씩이 같은 판끼리 · 15수 안에서 승률을 10%p 이상 잃은 수와 자주 두는 진행</small></h2>`;
  if(ea&&ea.n){
    const all=[...(S.openings.w||[]).map(r=>[r,'백']),...(S.openings.b||[]).map(r=>[r,'흑'])].filter(x=>x[0].mist&&x[0].n>=5).sort((a,b)=>b[0].mist.per_game-a[0].mist.per_game);
    h+=`<div class="card"><div class="sub" style="margin-bottom:8px">오프닝 단계 전체: 판당 <b>${ea.per_game}개</b>, 가장 흔한 유형</div>${catBars(ea.cats,5)}`;
    if(all.length>1) h+=`<div class="sub" style="margin-top:10px">실수가 가장 잦은 오프닝은 <b>${all[0][1]} <span class="mono">${esc(all[0][0].moves)}</span></b> (판당 ${all[0][0].mist.per_game}개), 가장 깨끗한 오프닝은 <b>${all[all.length-1][1]} <span class="mono">${esc(all[all.length-1][0].moves)}</span></b> (판당 ${all[all.length-1][0].mist.per_game}개)입니다.</div>`;
    h+=`</div>`;
  }
  for(const [col,name] of [['w','백'],['b','흑']]){
    const rows=S.openings[col]||[];
    h+=`<div class="card"><h3 style="margin-top:0">${name}으로</h3>`;
    if(!rows.length){h+='<div class="empty">데이터 부족</div></div>';continue;}
    h+=`<div class="oplist">`+rows.map((r,i)=>`<div class="opitem ${i===OPEN_SEL[col]?'on':''}" data-op="${col}" data-i="${i}"><div><span class="mono">${esc(r.moves)}</span><div class="nm">${esc(r.name)} · ${r.n}판${r.mist?` · 15수 안 실수 판당 ${r.mist.per_game}${r.mist.cats.length?` · 주로 ${esc(catOf(r.mist.cats[0].key).n)}`:''}`:''}</div></div><div class="sc" style="color:${r.score<45?'var(--loss)':r.score>=60?'var(--win)':'inherit'}">${r.score}%</div></div>`).join('')+`</div>`;
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
  h+=vals.map((v,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="var(--s1)" opacity=".28"/>`).join('');
  h+=`<path d="${roll.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  h+=`<text x="${L}" y="${H-6}" font-size="11" fill="var(--muted)">${t.series[0][0]}</text><text x="${W-R}" y="${H-6}" font-size="11" text-anchor="end" fill="var(--muted)">${t.series[N-1][0]}</text><text x="${(L+pw/2).toFixed(1)}" y="${H-6}" font-size="11" text-anchor="middle" fill="var(--muted)">게임 순서 →</text>`;
  h+=`<g class="xc" style="display:none"><line class="xc-l" y1="${T}" y2="${T+ph}" stroke="var(--text2)" stroke-width="1"/><circle class="xc-d" r="5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/></g>`;
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
  const line=vals.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
  h+=`<defs><linearGradient id="rgrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--s1)" stop-opacity=".32"/><stop offset="1" stop-color="var(--s1)" stop-opacity="0"/></linearGradient></defs>`;
  h+=`<path d="${line} L${x(N-1).toFixed(1)} ${T+ph} L${L} ${T+ph} Z" fill="url(#rgrad)"/>`;
  h+=`<path d="${line}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  const rr=N>120?1.9:N>60?2.6:3.6;
  h+=series.map((s,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(s[1]).toFixed(1)}" r="${rr}" fill="${col[s[2]]||col.D}"/>`).join('');
  h+=`<text x="${L}" y="${H-6}" font-size="11" fill="var(--muted)">${series[0][0]}</text><text x="${W-R}" y="${H-6}" font-size="11" text-anchor="end" fill="var(--muted)">${series[N-1][0]}</text>`;
  h+=`<g class="xc" style="display:none"><line class="xc-l" y1="${T}" y2="${T+ph}" stroke="var(--text2)" stroke-width="1"/><circle class="xc-d" r="5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/></g>`;
  h+=`</svg><div class="tip"></div></div>`;
  const nm={W:'승',L:'패',D:'무'};
  CHARTS.rchart={N,L,pw,W,x,ys:i=>y(vals[i]),tip:i=>`${series[i][0]} · ${series[i][1]} · ${nm[series[i][2]]||''}`};
  return h;
}
function trendView(w){
  const t=w.trend; if(!t) return '<div class="empty">추이 데이터가 없습니다.</div>';
  let h=`<div class="sub" style="margin-bottom:10px">지표: <b>${esc(t.label)}</b> · ${t.lower_better?'낮을수록 좋음':'높을수록 좋음'} · 이 기간 ${t.n}판 기준</div>`;
  if(w.ev&&!w.ev.confident) h+=`<div class="evnote">이 보완점은 아직 가설입니다. 근거가 ${w.ev.n}${esc(w.ev.unit)}뿐이라 평소와의 차이가 우연일 수 있습니다${w.ev.p!=null?` (p=${w.ev.p.toFixed(2)})`:''}. 판이 더 쌓이면 다시 판단합니다.</div>`;
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
const WNAME={all:'전체 기간','30d':'최근 30일','7d':'최근 7일'};
function openSheet(i){
  const S=DATA.windows[W]; const w=typeof i==='string' ? (c=>c&&{title:catOf(c.key).n,trend:c.trend})(catData(S,i)) : S&&S.weaknesses[i]; if(!w) return;
  $('#sheet-title').textContent=w.title; $('#sheet-sub').textContent=WNAME[W]+' 기준 추이';
  $('#sheet-body').innerHTML=trendView(w); $('#sheet-body').scrollTop=0;
  $('#sheet').classList.add('open'); document.body.style.overflow='hidden';
}
function closeSheet(){ $('#sheet').classList.remove('open'); document.body.style.overflow=''; delete CHARTS.tchart; }
document.addEventListener('click',(e)=>{
  const c=e.target.closest('[data-weak]'); if(c){ openSheet(+c.dataset.weak); return; }
  const ct=e.target.closest('[data-cattrend]'); if(ct){ openSheet(ct.dataset.cattrend); return; }
  if(e.target.closest('#sheet-x')||e.target===$('#sheet')) closeSheet();
});
document.addEventListener('keydown',(e)=>{ if(e.key==='Escape') closeSheet(); });

/* ---------- 코치: 실수 유형 (stats.json 의 coach) ---------- */
const coachOf=(S)=>(S&&S.coach)||{cats:[],focus:[],n:0,games:0};
const catData=(S,k)=>coachOf(S).cats.find(c=>c.key===k);
const TREND={better:['줄어드는 중','good'],maybe_better:['줄어드는 조짐','good'],flat:['변화 없음',''],maybe_worse:['늘어나는 조짐','serious'],worse:['늘어나는 중','critical'],insufficient:['판 수 부족','']};
const trendChip=(t)=>{ const m=TREND[t&&t.status]||TREND.insufficient; return `<span class="chip ${m[1]}">${m[0]}</span>`; };
/* 최근 판(왼쪽이 오래된 판)마다 이 유형이 나왔는지 */
const seqDots=(r)=>`<span class="seq" role="img" aria-label="최근 ${r.k}판 중 ${r.games}판에서 발생">${r.seq.map(v=>`<i class="${v?'hit':''}"></i>`).join('')}</span>`;
const recentLine=(c,chip=true)=>`<div class="fline">${seqDots(c.recent)}<span>최근 ${c.recent.k}판 중 <b>${c.recent.games}판</b>에서 나옴</span>${chip?trendChip(c.trend):''}</div>`;
let OPEN_CAT=null;
function focusRow(c,i){
  const m=catOf(c.key);
  return `<a class="frow" href="#mistakes" data-opencat="${c.key}"><span class="rk">${i+1}</span><div class="nm"><b>${esc(m.n)}</b><div class="q">${esc(m.q)}</div>
    <div class="fline">${seqDots(c.recent)}<span>최근 ${c.recent.k}판 중 ${c.recent.games}판</span>${trendChip(c.trend)}</div></div><div class="shr"><b>${c.share}%</b></div></a>`;
}
function lastGameCard(S){
  const g=S.recent[0]; if(!g) return '';
  const focus=coachOf(S).focus, cats=g.cats||[], hit=focus.filter(k=>cats.some(c=>c[0]===k));
  const res=g.outcome==='W'?'승':g.outcome==='L'?'패':'무';
  let v;
  if(!cats.length) v='승률을 10%p 이상 잃은 수가 하나도 없었습니다.';
  else if(!focus.length) v=`실수 ${cats.reduce((a,c)=>a+c[1],0)}개.`;
  else if(hit.length) v=`집중 과제 ${focus.length}가지 중 <b>${hit.length}가지가 또 나왔습니다.</b>`;
  else v=`집중 과제 ${focus.length}가지는 이 판에 <b>하나도 안 나왔습니다.</b> 다른 유형의 실수만 있었습니다.`;
  return `<a class="card lastg" href="${gameLink(g.url)}"><div class="h"><div><div class="k">직전 판 피드백</div><b>${g.date.slice(5)} ${g.color==='w'?'백':'흑'} vs ${esc(g.opp)} · ${res}</b></div><span class="go">복기 ›</span></div>
    <div class="v">${v}</div>${cats.length?`<div class="ctags">${cats.map(([k,n])=>catTag(k,focus.includes(k)?'rep':'').replace('</span>',`${n>1?` ×${n}`:''}</span>`)).join('')}</div>`:''}</a>`;
}
function coachSection(S){
  const co=coachOf(S); if(!co.cats.length) return '';
  const focus=co.focus.map(k=>catData(S,k)).filter(Boolean);
  return `<section id="s-coach" data-view="home"><h2>집중 과제<small>잃은 승률이 가장 큰 실수 유형 ${focus.length}가지와 두기 전 확인할 질문 · 누르면 사례</small></h2>
    <div class="card flist">${focus.map(focusRow).join('')}</div>${lastGameCard(S)}</section>`;
}
/* 유형 하나의 상황 진단: 시간이 없어서인지, 서둘러서인지, 이기고 있어서인지 */
function catDiag(c){
  const x=c.ctx||{}, out=[];
  if(x.low_clock>=25) out.push(`<b>${x.low_clock}%</b>가 남은 시간 30초 미만에서 나왔습니다. 시간 관리가 원인의 큰 부분입니다.`);
  else if(x.calm>=75) out.push(`<b>${x.calm}%</b>가 시간이 1분 넘게 남았을 때 나왔습니다. 시간이 모자라서가 아니라 확인을 건너뛰어서 생깁니다.`);
  if(x.fast>=20) out.push(`<b>${x.fast}%</b>는 시간이 있는데도 5초 안에 둔 수입니다.`);
  if(x.slow>=25) out.push(`<b>${x.slow}%</b>는 30초 넘게 생각하고 둔 수입니다. 오래 본다고 걸러지지 않으니, 마지막에 확인할 질문을 하나 정해 두세요.`);
  if(x.winning>=35) out.push(`<b>${x.winning}%</b>가 +3 이상 유리하던 국면에서 나왔습니다. 이기고 있을 때 확인이 느슨해집니다.`);
  return out;
}
function catBody(c){
  const m=catOf(c.key), ph=(c.ctx||{}).phase||{};
  let h=`<div class="sub" style="margin-top:10px">${esc(m.d)}</div>${recentLine(c,false)}`;
  const dg=catDiag(c);
  h+=`<ul class="diag">${dg.map(t=>`<li>${t}</li>`).join('')}<li>국면: 오프닝 ${ph.opening||0} · 중반 ${ph.middlegame||0} · 엔드게임 ${ph.endgame||0} · ${c.games}판(전체의 ${c.game_rate}%)에서 나옴</li></ul>`;
  h+=`<div class="rule"><span>두기 전에</span>${esc(m.rule)}</div>`;
  h+=`<div class="links cact"><span class="btn" data-cattrend="${c.key}">추이 분석</span>${c.puzzles?`<a class="btn on" href="puzzle.html?cat=${c.key}">이 유형 퍼즐 ${c.puzzles}개 ›</a>`:''}</div>`;
  h+=`<h3>최근 사례</h3>`;
  (c.examples||[]).forEach((w,i)=>{ h+= i===0 ? blunderCard(w) : blunderRow(w,`cx${c.key}${i}`); });
  return h;
}
function catsSection(S){
  const co=coachOf(S);
  let h=`<section id="s-cats" data-view="mistakes" data-sub="cats"><h2>실수 유형<small>승률을 10%p 이상 잃은 내 수 ${co.n}개 · 막대는 그 유형으로 잃은 승률의 비중 · 누르면 진단과 사례</small></h2>`;
  if(!co.cats.length) return h+'<div class="empty">이 기간에는 해당하는 실수가 없습니다.</div></section>';
  if(!catData(S,OPEN_CAT)) OPEN_CAT=co.cats[0].key;
  const mx=Math.max(...co.cats.map(c=>c.share),1);
  for(const c of co.cats){ const m=catOf(c.key), open=c.key===OPEN_CAT;
    h+=`<div class="card cat ${open?'open':''}" id="cat-${c.key}"><div class="cath" data-cat="${c.key}" role="button" aria-expanded="${open}">
      <div class="ct"><b>${esc(m.n)}</b>${co.focus.includes(c.key)?'<span class="chip me">집중 과제</span>':''}<span class="shr">${c.share}%</span></div>
      <div class="cbar"><i style="width:${(c.share/mx*100).toFixed(1)}%"></i></div>
      <div class="sub">${CATG[m.g]} · ${c.n}회 · 평균 −${c.avg}%p ${trendChip(c.trend)}</div></div>
      <div class="catb">${open?catBody(c):''}</div></div>`; }
  return h+'</section>';
}
function showCat(key, scroll){
  const S=DATA.windows[W]; if(!catData(S,key)) return;
  OPEN_CAT=key;
  document.querySelectorAll('#s-cats .cat').forEach(el=>{ const k=el.id.slice(4), open=k===key, b=el.querySelector('.catb');
    el.classList.toggle('open',open); el.querySelector('.cath').setAttribute('aria-expanded',open);
    b.innerHTML=open?catBody(catData(S,k)):''; if(open){ drawAll(b); applyTheme(); } });
  if(scroll){ const el=document.getElementById('cat-'+key); if(el) el.scrollIntoView({block:'start'}); }
}
function setSub(v){ SUB=v; try{sessionStorage.setItem('chess-sub',v)}catch(e){}; applyView(); }
document.addEventListener('click',(e)=>{
  const sb=e.target.closest('#subtabs button'); if(sb){ setSub(sb.dataset.sub); return; }
  const oc=e.target.closest('[data-opencat]');
  if(oc){ e.preventDefault(); setSub('cats'); if(VIEW!=='mistakes'){ VIEW='mistakes'; history.pushState(null,'','#mistakes'); applyView(); } showCat(oc.dataset.opencat,true); return; }
  const ch=e.target.closest('.cath'); if(ch){ const k=ch.dataset.cat; if(k===OPEN_CAT){ OPEN_CAT='-'; const el=ch.parentElement; el.classList.remove('open'); ch.setAttribute('aria-expanded','false'); el.querySelector('.catb').innerHTML=''; } else showCat(k,true); }
});

/* ---------- 오프닝 성적표: 내가 고른 수순 / 상대가 고른 수순 (stats.json 의 repertoire) ---------- */
const VERD={weak:['취약','critical'],weak_hint:['취약 조짐','serious'],strong:['강점','good'],strong_hint:['강점 조짐','good'],even:['평균 수준','']};
const verdChip=(r)=>{ const v=VERD[r.verdict]||VERD.even; return `<span class="chip ${v[1]}">${v[0]}</span>`; };
const SIDE={mine:'내가 고른 수순',opp:'상대가 고른 수순'};
const repOf=(S,id)=>{ const [c,side,i]=id.split('|'); const R=(S.repertoire||{})[c]; return R&&R[side]&&R[side][+i]; };
function repRow(r,id){
  const tot=r.n||1;
  return `<div class="oprow" data-rep="${id}" role="button"><div class="om"><div class="ok"><span class="mono">${esc(r.key)}</span>${r.other?' <span class="sub">그 외</span>':''}</div>
    <div class="nm">주로 ${esc(r.name)} · ${r.n}판 ${r.win}승 ${r.draw}무 ${r.loss}패${r.book?' · 연습 가능':''}</div>
    <div class="wdl"><i style="width:${r.win/tot*100}%;background:var(--win)"></i><i style="width:${r.draw/tot*100}%;background:var(--draw)"></i><i style="width:${r.loss/tot*100}%;background:var(--loss)"></i></div></div>
    <div class="os"><b>${r.score}%</b>${verdChip(r)}</div></div>`;
}
/* 취약·강점 순위: 평균과의 차이 × √판수 (판이 많을수록, 차이가 클수록 앞) */
function repRanked(S){
  const all=[]; for(const c of 'wb') for(const side of ['mine','opp']) (((S.repertoire||{})[c]||{})[side]||[]).forEach((r,i)=>all.push({r,id:`${c}|${side}|${i}`,c,side,z:r.diff*Math.sqrt(r.n)}));
  const pick=(pre,sgn)=>{ const seen=new Set(); return all.filter(x=>x.r.verdict.startsWith(pre)).sort((a,b)=>(a.r.verdict.endsWith('hint')-b.r.verdict.endsWith('hint'))||sgn*(a.z-b.z))
    .filter(x=>{ const k=x.c+x.r.n+'/'+x.r.win+'/'+x.r.loss+x.r.name; if(seen.has(k)) return false; seen.add(k); return true; }); };   // 두 갈래에 같은 판 묶음이 겹치면 하나만
  return {weak:pick('weak',1), strong:pick('strong',-1)};
}
function repSummary(S){
  const k=repRanked(S); if(!k.weak.length&&!k.strong.length) return '';
  const col=(title,arr)=>arr.length?`<div class="k">${title}</div>`+arr.slice(0,3).map(x=>repRow(x.r,x.id).replace('<div class="nm">',`<div class="nm">${x.c==='w'?'백':'흑'} · ${SIDE[x.side]} · `)).join(''):'';
  return `<div class="card repcard" id="rep-sum">${col('취약한 오프닝',k.weak)}${col('강한 오프닝',k.strong)}</div>`;
}
function repSection(S){
  const R=S.repertoire; if(!R) return '';
  let h=`<section id="s-rep" data-view="stats"><h2>오프닝 성적<small>내가 고른 수순과 상대가 고른 수순별 승률 · 같은 색의 내 평균과 비교 · 누르면 그 오프닝의 코칭과 연습</small></h2>`+repSummary(S)+`<div class="more" style="padding:0 0 12px"><a class="btn" href="train.html">오프닝 연습 목록</a></div>`;
  for(const [c,name] of [['w','백'],['b','흑']]){
    const B=R[c]&&R[c].base; if(!B) continue;
    h+=`<div class="card repcard"><h3 style="margin-top:0">${name}으로 <span class="sub">${B.n}판 · 평균 승률 ${B.score}%</span></h3>`;
    for(const side of ['mine','opp']){
      const rows=R[c][side]||[]; if(!rows.length) continue;
      const N=5, fid=`fold-rep-${c}-${side}`;
      h+=`<div class="k">${SIDE[side]} <span class="sub">(${c==='w'===(side==='mine')?'백':'흑'}의 첫 수들)</span></div>`;
      rows.forEach((r,i)=>{ if(i===N) h+=`<div class="fold" id="${fid}" hidden>`; h+=repRow(r,`${c}|${side}|${i}`); });
      if(rows.length>N) h+=`</div><div class="more"><span class="btn" data-fold="${fid}" data-unit="개">나머지 ${rows.length-N}개 보기</span></div>`;
    }
    h+='</div>';
  }
  return h+'</section>';
}
const cpTxt=(v)=>v==null?'-':(v>0?'+':v<0?'−':'')+(Math.abs(v)/100).toFixed(1);
function repView(r,c,side){
  const B=DATA.windows[W].repertoire[c].base, m=r.mist, color=c==='w'?'백':'흑', weak=r.verdict.startsWith('weak'), strong=r.verdict.startsWith('strong');
  const v=VERD[r.verdict]||VERD.even, cls=weak?(r.verdict==='weak'?'worse':'maybe_worse'):strong?'better':'';
  let h=`<div class="sub" style="margin-bottom:10px">${color} · ${SIDE[side]} · 주로 <b>${esc(r.name)}</b>로 이어짐</div>`;
  h+=`<div class="verdict ${cls}"><span class="ic">${v[0]}</span>${r.n}판 승률 <b>${r.score}%</b> (${r.win}승 ${r.draw}무 ${r.loss}패). 내 ${color} 평균 ${B.score}%보다 ${Math.abs(r.diff)}%p ${r.diff<0?'낮습니다':'높습니다'}.
    <div class="p">${r.ev.p!=null?`나머지 ${color} 판과 비교한 p=${r.ev.p<0.001?'<0.001':r.ev.p.toFixed(2)}`:''}${r.verdict.endsWith('hint')?' · 판 수가 적어 아직 우연일 수 있습니다':''}</div></div>`;
  const dE=r.eval15!=null&&B.eval15!=null?r.eval15-B.eval15:null, dC=r.clock15!=null&&B.clock15!=null?r.clock15-B.clock15:null, dM=+(m.per_game-B.mist_pg).toFixed(2);
  if(r.book) h+=`<a class="card pz trainlink" href="train.html?o=${encodeURIComponent(r.id)}"><div><b>이 오프닝 직접 두어 보기</b><div class="sub">메인라인과 상대가 자주 두는 갈래 ${r.book}개 라인 · 15수까지</div></div><span class="btn on">연습 ›</span></a>`;
  h+=`<div class="tiles3"><div class="tile"><div class="k">15수 시점 형세</div><div class="v">${cpTxt(r.eval15)}</div><div class="d">내 ${color} 평균 ${cpTxt(B.eval15)}</div></div>
    <div class="tile"><div class="k">15수 안 실수</div><div class="v">${m.per_game}<small>/판</small></div><div class="d">평균 ${B.mist_pg}</div></div>
    <div class="tile"><div class="k">15수 시점 시계</div><div class="v">${clk(r.clock15)}</div><div class="d">평균 ${clk(B.clock15)}</div></div></div>`;
  // 진단
  const f=[], todo=[]; const peak=m.by_move.indexOf(Math.max(...m.by_move))+1, top=m.cats[0], L=r.decisive;
  if(dE!=null&&dE<=-80) { f.push(`<b>오프닝에서 이미 밀립니다.</b> 15수를 둔 시점의 평균 형세가 ${cpTxt(r.eval15)}로 내 평균(${cpTxt(B.eval15)})보다 ${(Math.abs(dE)/100).toFixed(1)}점 나쁩니다.`); todo.push(`이 수순의 처음 8~10수를 하나로 정해 외웁니다. 아래 "자주 틀리는 수"부터 고칩니다.`); }
  else if(r.eval15!=null&&r.eval15>=100&&r.diff<0) { f.push(`<b>오프닝은 잘 나옵니다</b>(15수 시점 ${cpTxt(r.eval15)}). 승률이 낮은 이유는 그 뒤, 중반에 있습니다.`); todo.push(`유리하게 나온 뒤가 문제입니다. 기물을 교환해 단순화하고, 매 수 상대의 체크·잡는 수를 먼저 봅니다.`); }
  else if(dE!=null&&dE>=80) f.push(`<b>오프닝에서 앞서 나옵니다.</b> 15수 시점 평균 형세 ${cpTxt(r.eval15)} (내 평균 ${cpTxt(B.eval15)}).`);
  else if(r.eval15!=null) f.push(`15수 시점 평균 형세는 ${cpTxt(r.eval15)}로 내 평균(${cpTxt(B.eval15)})과 비슷합니다.`);
  if(r.ahead.n>=3||r.behind.n>=3) f.push(`15수에 +1 이상 앞선 ${r.ahead.n}판의 승률 ${pct(r.ahead.score)}, −1 이하로 뒤진 ${r.behind.n}판의 승률 ${pct(r.behind.score)}.${r.ahead.n>=4&&r.ahead.score<60?' <b>앞서고도 자주 놓칩니다.</b>':''}${r.behind.n>=4&&r.behind.score<=25?' 뒤지면 거의 못 뒤집습니다.':''}`);
  if(m.n){ f.push(`15수 안 실수가 판당 ${m.per_game}개로 평균(${B.mist_pg})보다 ${dM>=0.3?'<b>많습니다</b>':dM<=-0.3?'적습니다':'비슷합니다'}. 가장 많이 틀리는 수는 <b>${peak}수째</b>(${m.by_move[peak-1]}회)${m.first_slip!=null?`, 처음 틀어지는 수는 보통 ${m.first_slip}수`:''}입니다.`);
    if(top&&top.n>=3){ f.push(`가장 많은 유형은 <b>${esc(catOf(top.key).n)}</b> (${top.n}회, 15수 안 실수의 ${Math.round(top.n/m.n*100)}%).`); todo.push(`${peak}수 근처에서 한 번 멈추고 확인합니다: "${esc(catOf(top.key).q)}"`); } }
  if(L.n) f.push(`진 ${r.loss}판 중 승부를 가른 실수가 15수 안에 나온 판은 <b>${L.early}판</b>, 그 뒤에 나온 판은 ${L.n-L.early}판입니다.${L.cats.length?` 그 실수의 유형: ${L.cats.map(([k,n])=>`${esc(catOf(k).n)} ${n}`).join(', ')}.`:''}`);
  if(dC!=null&&dC<=-30){ f.push(`15수까지 평균보다 <b>${Math.round(-dC)}초 더</b> 씁니다. 수순이 손에 익지 않았다는 신호입니다.`); if(!todo.length) todo.push('처음 10수를 정해 두고 10초 안에 둡니다.'); }
  (r.trouble||[]).slice(0,2).forEach(t=>todo.push(`${t.move}수 <span class="mono">${esc(t.san)}</span> 대신 <span class="mono">${esc(t.best)}</span> (같은 자리에서 ${t.n}번 틀림).`));
  if(strong&&!todo.length) todo.push(side==='mine'?'잘 맞는 수순입니다. 계속 쓰세요.':'상대가 이렇게 나오면 유리합니다. 지금 방식대로 두세요.');
  if(weak&&side==='mine'&&r.n>=8&&dE!=null&&dE<=-80) todo.push('고쳐도 나아지지 않으면 같은 자리에서 더 성적이 좋은 다른 수순으로 바꾸는 것도 방법입니다.');
  h+=`<h3>코치 진단</h3><ul class="diag card">${f.map(t=>`<li>${t}</li>`).join('')}</ul>`;
  if(todo.length) h+=`<h3>다음에 할 일</h3><div class="card checklist"><ol>${todo.slice(0,4).map(t=>`<li>${t}</li>`).join('')}</ol></div>`;
  if(m.n){ h+=`<h3>몇 수째에 틀리나 <span class="sub">(15수 안 실수 ${m.n}개)</span></h3><div class="card">${moveHist(m.by_move)}</div><h3>많이 나오는 유형</h3><div class="card">${catBars(m.cats,5)}</div>`; }
  if((r.trouble||[]).length){ h+=`<h3>자주 틀리는 수 <span class="sub">(같은 국면, 같은 수를 2번 이상)</span></h3><div class="card">`; r.trouble.forEach((w,i)=>{ h+=blunderRow(w,`rt${c}${side}${i}`,`${w.n}번 · 평균 손실 ${w.avg_loss}`); }); h+='</div>'; }
  if((r.review||[]).length) h+=`<h3>복기할 판 <span class="sub">(최근에 진 판)</span></h3><div class="card">${r.review.map(g=>`<a class="rv" href="${gameLink(g.url)}"><span>${g.date} vs ${esc(g.opp)}</span><span class="sub">정확도 ${g.accuracy??'-'}% ›</span></a>`).join('')}</div>`;
  return h+`<div class="method">묶는 기준: ${SIDE[side]}은 ${c==='w'===(side==='mine')?'백의 처음 3수':'흑의 처음 2수'}가 같은 판입니다(판 수가 적은 갈래는 한 수 짧게 묶어 "그 외"). 취약·강점은 같은 색 평균 승률과 8%p 이상 차이 날 때 붙이고, 8판 미만이거나 Welch t 검정 p가 0.1 이상이면 "조짐"으로 낮춥니다.</div>`;
}
function openRep(id){
  const S=DATA.windows[W], r=repOf(S,id); if(!r) return; const [c,side]=id.split('|');
  $('#sheet-title').textContent=r.key+(r.other?' 그 외':''); $('#sheet-sub').textContent=WNAME[W]+' · 오프닝 코칭';
  const b=$('#sheet-body'); b.innerHTML=repView(r,c,side); b.scrollTop=0; drawAll(b); applyTheme();
  $('#sheet').classList.add('open'); document.body.style.overflow='hidden';
}
document.addEventListener('click',(e)=>{
  const t=e.target.closest('[data-rep]'); if(t) openRep(t.dataset.rep);
});

function spark(evals, worstPly){
  if(!evals||evals.length<2) return '';
  const n=evals.length, W=300, H=44, mid=H/2;
  const pts=evals.map((e,i)=>[i/(n-1)*W, mid - Math.max(-1,Math.min(1,e/1000))*(mid-2)]);
  const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area=`M0 ${mid} `+pts.map(p=>'L'+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ')+` L${W} ${mid} Z`;
  let dot=''; if(worstPly!=null&&worstPly<n){ const p=pts[worstPly]; dot=`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3.5" fill="${RED}"/>`; }
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="0" y1="${mid}" x2="${W}" y2="${mid}" stroke="var(--line)"/><path d="${area}" fill="var(--s1)" opacity=".14"/><path d="${d}" fill="none" stroke="var(--s1)" stroke-width="1.5"/>${dot}</svg>`;
}
function bars(rows, max){
  let h='<div class="bars">';
  for(const r of rows){
    const fmt=r.fmt||((x)=>x);
    if(r.opp!==undefined){
      h+=`<div class="lbl">${esc(r.label)}</div><div class="pair"><div class="bar" style="width:${Math.max(2,r.me/max*100*0.78)}%"><span>${fmt(r.me)}</span></div><div class="bar opp" style="width:${Math.max(2,r.opp/max*100*0.78)}%"><span>${fmt(r.opp)}</span></div></div>`;
    } else {
      const k=r.note?(r.note.length>8?0.4:0.6):0.78;
      h+=`<div class="lbl">${esc(r.label)}</div><div><div class="bar" style="width:${Math.max(2,r.me/max*100*k)}%"><span>${fmt(r.me)}${r.note?` <span style="position:static;color:var(--muted)">${esc(r.note)}</span>`:''}</span></div></div>`;
    }
  }
  return h+'</div>';
}
const legend = ()=>`<div class="legend"><span><i style="background:var(--s1)"></i>나</span><span><i style="background:var(--s2)"></i>상대</span></div>`;

/* 화면(탭): 홈 / 게임 / 복기 / 통계. 주소의 #games 등으로 유지된다 */
const VIEWS=['home','games','mistakes','stats'];
let VIEW=VIEWS.includes(location.hash.slice(1))?location.hash.slice(1):'home';
const SUBS=['cats','open','worst'];
let SUB='cats'; try{ const v=sessionStorage.getItem('chess-sub'); if(SUBS.includes(v)) SUB=v; }catch(e){}
function applyView(){
  document.querySelectorAll('#main>section').forEach(s=>{ s.hidden=s.dataset.view!==VIEW||(!!s.dataset.sub&&s.dataset.sub!==SUB); });
  document.querySelectorAll('#subtabs button').forEach(b=>b.classList.toggle('on',b.dataset.sub===SUB));
  document.querySelectorAll('#tabbar a').forEach(a=>a.classList.toggle('on',a.dataset.tab===VIEW));
}
window.addEventListener('hashchange',()=>{ const v=location.hash.slice(1)||'home'; if(VIEWS.includes(v)&&v!==VIEW){ VIEW=v; applyView(); window.scrollTo(0,0); } });
function puzzleStreakText(){
  try{ const hst=JSON.parse(localStorage.getItem('puzzle-history')||'{}'); let d=new Date(Date.now()+9*3600*1000), n=0;
    const key=x=>x.toISOString().slice(0,10); if(!hst[key(d)]) d=new Date(d-864e5);
    while(hst[key(d)]){ n++; d=new Date(d-864e5); }
    if(n>0) return `<span class="streak">${n}일 연속</span> · 내가 실제로 틀린 국면에서 최선 수 찾기`; }catch(e){}
  return '내가 실제로 틀린 국면에서 최선 수 찾기';
}
function render(){
  const S = DATA.windows[W];
  document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.w===W));
  $('#title').textContent = `${DATA.username} · 래피드 분석`;
  $('#foot').innerHTML = `마지막 갱신 ${DATA.generated} (KST) · Stockfish 19 depth ${(DATA.meta||{}).depth||14}, 수순 depth ${(DATA.meta||{}).pv_depth||16} · 게임이 끝나면 1~2분 안에 자동 갱신<br>기물: maestro (sadsnake1, CC BY-NC-SA 4.0), cburnett (GPLv2+), merida (GPLv2+), alpha (Eric Bentzen), california (Jerry S., CC BY-NC-SA 4.0)`;
  if(!S){ $('#subtitle').textContent=''; $('#main').innerHTML='<div class="empty">이 기간에 분석된 래피드 게임이 없습니다.</div>'; return; }
  const o=S.overview, t=S.time, c=S.conversion, tc=S.tactics;
  $('#subtitle').textContent = `${o.games}판 · 백 ${pct(o.score_w)} · 흑 ${pct(o.score_b)}`;
  let h='';
  const rd=o.rating-o.rating_start;
  const up=rd>0, dn=rd<0; const tot=o.win+o.draw+o.loss||1;
  h+=`<section class="hero" id="hero" data-view="home"><div class="herocard">
    <div class="k">래피드 레이팅</div>
    <div class="big">${o.rating}<span class="delta ${up?'up':dn?'down':''}">${up?'▲':dn?'▼':''} ${Math.abs(rd)}</span></div>
    <div class="meta">최고 ${o.rating_best} · ${o.rating_start}에서 시작 · ${o.first_date.slice(5)} ~ ${o.last_date.slice(5)}</div>
    ${S.rating_series&&S.rating_series.length>1?ratingChart(S.rating_series):''}
    <div class="lg"><span><i class="dot" style="background:var(--win)"></i>승</span><span><i class="dot" style="background:var(--loss)"></i>패</span><span><i class="dot" style="background:var(--draw)"></i>무</span><span>그래프를 누르면 값 표시</span></div>
  </div>
  <div class="mini3">
    <div class="tile"><div class="k">승률</div><div class="v">${o.score}%</div><div class="wdl"><i style="width:${o.win/tot*100}%;background:var(--win)"></i><i style="width:${o.draw/tot*100}%;background:var(--draw)"></i><i style="width:${o.loss/tot*100}%;background:var(--loss)"></i></div><div class="d">${o.win}승 ${o.draw}무 ${o.loss}패</div></div>
    <div class="tile"><div class="k">정확도</div><div class="v">${o.accuracy}%</div><div class="d">상대 ${o.opp_accuracy}%</div></div>
    <div class="tile"><div class="k">대실수/판</div><div class="v">${o.blunders_pg}</div><div class="d">상대 ${o.opp_blunders_pg}</div></div>
  </div>
  </section>`;
  h+=coachSection(S);
  h+=`<section data-view="home" class="pzs"><a class="card pz" href="puzzle.html"><div><b>오늘의 퍼즐 10개</b><div class="sub">${puzzleStreakText()}</div></div><span class="btn on">풀기 ›</span></a></section>`;
  h+=`<section id="s-weak" data-view="home"><h2>경기 운영<small>시간·틸트 등 통계에서 뽑은 보완점 · 누르면 추이</small></h2>`;
  if(!S.weaknesses.length) h+='<div class="empty">두드러진 약점이 없습니다.</div>';
  const WEAK_N=3;
  for(const w of S.weaknesses){ if(S.weaknesses.indexOf(w)===WEAK_N) h+=`<div class="fold" id="fold-weak" hidden>`; const ic={critical:'중요',serious:'주의',warning:'참고',good:'강점',hint:'표본 부족'}[w.level]||'';
    h+=`<div class="card weak ${w.level}" data-weak="${S.weaknesses.indexOf(w)}"><div class="t"><span class="ic">${ic}</span>${esc(w.title)}</div><p>${esc(w.text)}</p><div class="go">추이 분석 ›</div></div>`; }
  if(S.weaknesses.length>WEAK_N) h+=`</div><div class="more"><span class="btn" data-fold="fold-weak" data-unit="개">나머지 ${S.weaknesses.length-WEAK_N}개 보기</span></div>`;
  h+='</section>';
  // 최근 게임
  const RECENT_N=6, FOCUS=coachOf(S).focus;
  h+=`<section id="s-recent" data-view="games"><h2>최근 게임<small>카드를 누르면 전체 수순 분석 · 태그는 그 판의 실수 유형 (테두리: 집중 과제)</small></h2><div class="card">`;
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
      ${g.cats&&g.cats.length?`<div class="ctags">${g.cats.map(([k,n])=>catTag(k,FOCUS.includes(k)?'rep':'').replace('</span>',`${n>1?` ×${n}`:''}</span>`)).join('')}</div>`:''}
      ${w&&w.wp_loss>=10?`<div class="w">결정적 실수 <span class="mono">${mv(w)}</span> → 정답 <span class="mono">${esc(w.best)}</span> (${ev(w.cp_before)} → ${ev(w.cp_after)}, 남은시간 ${clk(w.clock)})</div>`:''}
      <div class="links">${w&&w.fen?`<span class="btn" data-expand="${wid}">장면 보기</span>`:''}<a href="${gameLink(g.url)}">전체 분석 →</a><a href="${esc(g.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>
      ${w&&w.fen?`<div id="${wid}" hidden data-w='${esc(JSON.stringify({...w,color:g.color,opp:g.opp,date:g.date,url:g.url}))}'></div>`:''}
    </div></div></div>`;
  });
  if(S.recent.length>RECENT_N) h+=`</div><div class="more"><span class="btn" data-fold="fold-recent" data-unit="판">나머지 ${S.recent.length-RECENT_N}판 보기</span></div>`;
  h+='</div></section>';
  h+=`<section data-view="mistakes" class="subnav"><div class="tabs" id="subtabs"><button data-sub="cats">유형별</button><button data-sub="open">오프닝별</button><button data-sub="worst">큰 실수</button></div></section>`;
  h+=catsSection(S);
  h+=openingSection(S);
  // 최악의 실수
  const WORST_N=8;
  h+=`<section id="s-worst" data-view="mistakes" data-sub="worst"><h2>가장 큰 실수<small>승률 30%p 이상 손해 · 빨강 내 수, 초록 정답</small></h2><div class="card">`;
  if(!S.worst.length) h+='<div class="empty">없음</div>';
  S.worst.forEach((w,i)=>{ if(i===WORST_N) h+=`<div class="fold" id="fold-worst" hidden>`; h+= i<3 ? blunderCard(w) : blunderRow(w,`ww${i}`); });
  if(S.worst.length>WORST_N) h+=`</div><div class="more"><span class="btn" data-fold="fold-worst" data-unit="개">나머지 ${S.worst.length-WORST_N}개 보기</span></div>`;
  h+='</div></section>';
  h+=repSection(S);
  // 시간
  h+=`<section id="s-time" data-view="stats"><h2>시간 관리</h2><div class="card">${legend()}<div class="sub" style="margin-bottom:6px">N수 시점 남은 시간 (중앙값)</div>`;
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
    h+=`<section id="s-tilt" data-view="stats"><h2>틸트·세션<small>30분 이상 비면 새 세션으로 봄 · 괄호는 판 수</small></h2><div class="tiles">
      <div class="tile"><div class="k">직전 판 패배 후 승률</div><div class="v" style="color:${aL.score!=null&&aL.score<=o.score-8?'var(--loss)':'inherit'}">${pct(aL.score)}</div><div class="d">${aL.n||0}판 · 승리 후 ${pct(aW.score)} (${aW.n||0}판)</div></div>
      <div class="tile"><div class="k">세션</div><div class="v">${tl.sessions.n}</div><div class="d">보통 ${tl.sessions.median_len}판 · 최장 ${tl.sessions.max_len}판 · 6판 이상 ${tl.sessions.long}회</div></div>
    </div>`;
    const sb=(rows)=>bars(rows.filter(r=>r.n).map(r=>({label:r.label,me:r.score,fmt:pct,note:`(${r.n}판${r.accuracy!=null?`, 정확도 ${r.accuracy}%`:''})`})),100);
    h+=`<div class="card"><div class="sub" style="margin-bottom:6px">같은 세션에서 연패한 뒤의 승률</div>${sb(tl.streak)}</div>`;
    h+=`<div class="card"><div class="sub" style="margin-bottom:6px">세션 안에서 몇 판째인가에 따른 승률</div>${sb(tl.session_pos)}</div>`;
    h+=`<div class="card"><div class="sub" style="margin-bottom:6px">시간대별 승률 (KST)</div>${sb(tl.hours)}</div></section>`;
  }
  // 국면
  h+=`<section id="s-phase" data-view="stats"><h2>국면별</h2><div class="card"><table><tr><th>국면</th><th class="n">수</th><th class="n">정확도</th><th class="n">상대</th><th class="n">대실수율</th></tr>`;
  for(const p of S.phase) h+=`<tr><td>${p.label}</td><td class="n">${p.moves}</td><td class="n">${p.accuracy}%</td><td class="n">${p.opp_accuracy}%</td><td class="n">${p.blunder_rate}%</td></tr>`;
  h+=`</table></div>`;
  if(S.blunder_by_move.length) h+=`<div class="card"><div class="sub" style="margin-bottom:6px">수 구간별 대실수율</div>${bars(S.blunder_by_move.map(b=>({label:b.label+'수',me:b.rate,fmt:pct})),Math.max(...S.blunder_by_move.map(b=>b.rate),1))}</div>`;
  h+='</section>';
  const cw=c.winning, cl=c.losing;
  h+=`<section data-view="stats"><h2>마무리와 역전</h2><div class="tiles">
    <div class="tile"><div class="k">+3 이상 유리했던 판</div><div class="v">${cw.n?Math.round(cw.won/cw.n*100):0}% 승</div><div class="d">${cw.n}판 중 ${cw.won}승 ${cw.draw}무 <b style="color:var(--loss)">${cw.lost}패</b></div></div>
    <div class="tile"><div class="k">-3 이하 불리했던 판</div><div class="v">${cl.n?Math.round(cl.won/cl.n*100):0}% 역전</div><div class="d">${cl.n}판 중 ${cl.won}승 ${cl.draw}무 ${cl.lost}패</div></div>
  </div></section>`;
  const hungRows=Object.entries(tc.hung).sort((a,b)=>b[1]-a[1]);
  h+=`<section data-view="stats"><h2>전술</h2><div class="tiles">
    <div class="tile"><div class="k">기물 방치 (한 수에 잡히는 기물)</div><div class="v">${tc.hung_total}</div><div class="d">판당 ${tc.hung_pg} · ${hungRows.map(([k,v])=>`${k} ${v}`).join(' · ')||'-'}<br>시간 1분 이상 남았을 때 ${tc.hung_with_time}회</div></div>
    <div class="tile"><div class="k">공짜 기물 안 잡음</div><div class="v">${tc.missed_free}</div><div class="d">잡는 수가 최선(+2 이상)인데 다른 수</div></div>
    <div class="tile"><div class="k">외통 놓침</div><div class="v">${tc.missed_mate_total}</div><div class="d">${Object.entries(tc.missed_mate).map(([k,v])=>`${k}${k==='5'?'+':''}수 외통 ${v}`).join(' · ')||'-'}</div></div>
  </div></section>`;
  if(S.monthly.length>1){
    h+=`<section data-view="stats"><h2>월별 추이</h2><div class="card"><table><tr><th>월</th><th class="n">판</th><th class="n">승률</th><th class="n">정확도</th><th class="n">대실수/판</th><th class="n">레이팅</th></tr>`;
    for(const m of S.monthly) h+=`<tr><td>${m.month}</td><td class="n">${m.games}</td><td class="n">${m.score}%</td><td class="n">${m.accuracy}%</td><td class="n">${m.blunders_pg}</td><td class="n">${m.rating}</td></tr>`;
    h+='</table></div></section>';
  }
  $('#main').innerHTML=h;
  drawAll(); applyTheme(); applyView();
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
{ const q=new URLSearchParams(location.search); if(q.get('w')&&DATA.windows[q.get('w')]){ W=q.get('w'); render(); } if(q.get('weak')!=null) openSheet(+q.get('weak'));
  if(q.get('cat')&&catData(DATA.windows[W],q.get('cat'))){ VIEW='mistakes'; setSub('cats'); showCat(q.get('cat'),true); } }
