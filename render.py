"""stats payload → 대시보드(index.html) + 게임 상세 페이지(game.html). 체스판/테마 코드는 두 페이지가 공유."""
import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
PIECE_SETS = (("maestro", "50"), ("cburnett", "45"), ("merida", "50"), ("alpha", "2048"), ("california", "400"))


def grain_uri():
    import base64
    path = os.path.join(ROOT, "pieces", "grain.png")
    if not os.path.exists(path):
        return ""
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def _namespace_ids(inner, prefix):
    """SVG 내부 id(그라디언트/필터/클립패스)에 접두어를 붙인다.
    60개 기물 SVG가 한 문서에 들어가면 id="a" 같은 이름이 겹쳐서
    흑 기물의 url(#a)가 백 기물의 그라디언트를 가리키게 된다."""
    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    if not ids:
        return inner
    inner = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', inner)
    inner = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{prefix}-{m.group(1)})' if m.group(1) in ids else m.group(0), inner)
    inner = re.sub(r'(xlink:href|href)="#([^"]+)"', lambda m: f'{m.group(1)}="#{prefix}-{m.group(2)}"' if m.group(2) in ids else m.group(0), inner)
    return inner


def piece_symbols():
    """pieces/<set>/*.svg → <symbol id="<set>-wK"> 묶음."""
    out = []
    for name, vb in PIECE_SETS:
        for p in ("wK", "wQ", "wR", "wB", "wN", "wP", "bK", "bQ", "bR", "bB", "bN", "bP"):
            path = os.path.join(ROOT, "pieces", name, f"{p}.svg")
            if not os.path.exists(path):
                continue
            svg = open(path, encoding="utf-8").read()
            m = re.search(r'viewBox="([^"]*)"', svg)
            viewbox = m.group(1) if m else f"0 0 {vb} {vb}"
            inner = re.sub(r"^.*?<svg[^>]*>", "", svg, count=1, flags=re.S)
            inner = re.sub(r"</svg>\s*$", "", inner, flags=re.S)
            inner = _namespace_ids(inner, f"{name}-{p}")
            out.append(f'<symbol id="{name}-{p}" viewBox="{viewbox}">{inner}</symbol>')
    g = grain_uri()
    if g:
        out.append(f'<image id="grain-img" href="{g}" x="0" y="0" width="800" height="800" preserveAspectRatio="none"/>')
    return '<svg width="0" height="0" style="position:absolute"><defs>' + "".join(out) + "</defs></svg>"


# ------------------------------------------------------------------ 공유 CSS / JS
SHARED_CSS = r"""
:root{
  color-scheme:light;
  --bg:#f4f3ef;--surface:#ffffff;--line:#e2e0d9;--text:#111110;--text2:#4d4c48;--muted:#85837d;
  --me:#2a78d6;--opp:#eb6834;--me-soft:#dbe9fb;
  --good:#149a14;--warning:#e6a300;--serious:#e8763f;--critical:#d03b3b;
  --win:#149a14;--loss:#d03b3b;--draw:#85837d;
  --sq-l:#EBECD0;--sq-d:#739552;--sq-hl:rgba(255,255,51,.5);
  --c-best:#81b64c;--c-good:#96af8b;--c-inacc:#f7c631;--c-mist:#ffa459;--c-blun:#fa412d;
  --r:14px;
}
@media (prefers-color-scheme:dark){:root{
  color-scheme:dark;--bg:#111110;--surface:#1c1c1b;--line:#31312e;--text:#f5f5f2;--text2:#c8c7bc;--muted:#8f8d86;
  --me:#4a92ea;--opp:#e0673a;--me-soft:#1e3d66;
}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;padding:0 16px calc(28px + env(safe-area-inset-bottom,0px))}
button{font:inherit}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:calc(14px + env(safe-area-inset-top,0px)) 0 6px;max-width:720px;margin:0 auto}
.topbar>div{min-width:0}
header{position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2;border-bottom:1px solid var(--line)}
header>*{max-width:720px;margin-left:auto;margin-right:auto}
h1{font-size:22px;line-height:1.25;margin:0 0 4px;letter-spacing:-.01em;font-weight:700}
.sub{color:var(--text2);font-size:13.5px;line-height:1.45}
main{max-width:720px;margin:0 auto}
section{margin-top:28px;scroll-margin-top:118px}
h2{font-size:19px;margin:0 0 12px;line-height:1.3;font-weight:700}
h2 small{display:block;font-weight:400;color:var(--muted);font-size:13px;margin:2px 0 0}
h3{font-size:15.5px;margin:16px 0 8px;color:var(--text2);font-weight:600}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;margin-bottom:10px}
.tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
@media (min-width:720px){.tiles{grid-template-columns:repeat(4,minmax(0,1fr))}}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:12px 14px;min-width:0}
.tile .k{font-size:13px;color:var(--text2);line-height:1.3}
.tile .v{font-size:28px;font-weight:700;line-height:1.15;margin-top:4px;white-space:nowrap;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tile .v.sm{font-size:19px}
.tile .d{font-size:12.5px;color:var(--muted);margin-top:4px;line-height:1.4}
.tile .d b{font-weight:600}
a{color:var(--me);text-decoration:none}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.95em}
.empty{color:var(--muted);font-size:14px;padding:24px 0;text-align:center}
footer{margin-top:32px;font-size:12px;color:var(--muted);text-align:center;line-height:1.5}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 16px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);font-size:14.5px;font-weight:500;cursor:pointer;user-select:none;-webkit-tap-highlight-color:transparent;white-space:nowrap}
.btn:active{transform:scale(.97)}
.btn.on{background:var(--me);color:#fff;border-color:var(--me)}
.btn.red{border-color:var(--critical);color:var(--critical)}.btn.red.on{background:var(--critical);color:#fff}
.btn.green{border-color:var(--good);color:var(--good)}.btn.green.on{background:var(--good);color:#fff}
.res{width:44px;height:44px;border-radius:12px;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;flex:none}
.res.W{background:var(--win)}.res.L{background:var(--loss)}.res.D{background:var(--draw)}
/* 보드 */
:root[data-tex="0"] .grain{display:none}
.board{width:100%;max-width:440px;aspect-ratio:1;display:block;margin:0 auto;border-radius:6px;overflow:hidden;touch-action:manipulation}
.viewer{margin-top:10px}
.vctl{display:flex;gap:8px;align-items:center;justify-content:center;margin-top:10px;flex-wrap:wrap}
.vctl .nav{width:60px;height:44px;font-size:20px;padding:0}
.vtabs{display:flex;gap:8px;justify-content:center;margin-top:10px;flex-wrap:wrap}
.moves{display:flex;flex-wrap:wrap;gap:5px;justify-content:center;margin-top:10px;font-size:14px}
.moves span{display:inline-flex;align-items:center;min-height:32px;padding:0 9px;border-radius:8px;background:var(--bg);border:1px solid var(--line);cursor:pointer}
.moves span.cur{background:var(--me);color:#fff;border-color:var(--me)}
.moves span.bad{border-color:var(--critical);color:var(--critical)}
.moves span.bad.cur{background:var(--critical);color:#fff}
.moves span.num{border:0;background:none;color:var(--muted);padding:0 2px 0 6px;cursor:default}
.cap{font-size:14px;color:var(--text2);text-align:center;margin-top:8px;min-height:20px;line-height:1.45}
/* 테마 선택 */
.tbtn{flex:none}
.tpanel{display:none;margin:0 auto 10px;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--surface);max-width:720px}
.tpanel.open{display:block}
.tpanel .row{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 12px}
.tpanel .lab{font-size:13px;color:var(--text2);line-height:1.45}
.sw{display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 12px 0 6px;border:1px solid var(--line);border-radius:10px;font-size:14px;cursor:pointer;-webkit-tap-highlight-color:transparent}
.sw.on{border-color:var(--me);box-shadow:0 0 0 1px var(--me)}
.sw i{display:inline-grid;grid-template-columns:1fr 1fr;width:24px;height:24px;border-radius:4px;overflow:hidden}
.sw i b{display:block}
.sw svg{width:26px;height:26px}
"""

SHARED_JS = r"""
const $ = (s)=>document.querySelector(s);
const esc = (s)=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const clk = (s)=> s==null?'-':`${Math.floor(Math.round(s)/60)}:${String(Math.round(s)%60).padStart(2,'0')}`;
const ev = (cp)=> cp==null?'-':Math.abs(cp)>=9000 ? (cp>0?'#승':'#패') : ((cp>0?'+':'')+(cp/100).toFixed(1));
const evW = (cp)=> cp==null?'-':Math.abs(cp)>=9000 ? ('M'+Math.round((10000-Math.abs(cp))/10)) : ((cp>0?'+':'')+(cp/100).toFixed(1));
const mv = (w)=> `${w.move}.${w.mover==='w'?'':'..'}${w.san}`;
const pct=(v)=> v==null?'-':v+'%';
const PH={opening:'오프닝',middlegame:'중반',endgame:'엔드게임'};
const gameId=(url)=> (url||'').split('/').pop();
const RED='#d03b3b', GREEN='#0ca30c', BLUE='#2a78d6', GRAY='#8a8883';

/* ---------- 테마 (체스닷컴 판 색상 프리셋 + 기물 세트) ---------- */
const GRAIN=__GRAIN__;
const BOARDS={
  wood:{name:'나무 (Dark Wood)',l:'#C8AA77',d:'#815A37',hl:'rgba(255,255,51,.5)',tex:true},
  walnut:{name:'호두나무 (Walnut)',l:'#BCA07C',d:'#75543B',hl:'rgba(255,255,51,.5)',tex:true},
  burled:{name:'옹이나무 (Burled Wood)',l:'#E9C49C',d:'#764226',hl:'rgba(255,255,51,.5)',tex:true},
  green:{name:'초록 (Green)',l:'#EBECD0',d:'#739552',hl:'rgba(255,255,51,.5)'},
  brown:{name:'갈색',l:'#EDD6B0',d:'#B88762',hl:'rgba(255,255,51,.5)'},
  blue:{name:'파랑',l:'#EAE9D2',d:'#4B7399',hl:'rgba(255,255,51,.5)'},
  purple:{name:'보라',l:'#EFEFEF',d:'#8877B7',hl:'rgba(255,255,51,.5)'},
  icy:{name:'얼음바다',l:'#E8EEF2',d:'#5A7E9B',hl:'rgba(255,255,51,.5)'},
  gray:{name:'회색',l:'#DEE3E6',d:'#8B8B8B',hl:'rgba(255,255,51,.5)'},
  bubblegum:{name:'버블검',l:'#FEF3F5',d:'#F9A8C9',hl:'rgba(120,120,255,.4)'},
};
const PSETS={maestro:'마에스트로 (Neo와 비슷)',cburnett:'클래식',merida:'메리다',alpha:'알파',california:'캘리포니아'};
let THEME={v:2,board:'wood',pieces:'maestro'};
try{ const t=JSON.parse(localStorage.getItem('chess-theme')||'null'); if(t&&t.v>=2&&BOARDS[t.board]&&PSETS[t.pieces]) THEME=t; }catch(e){}
function applyTheme(){
  const b=BOARDS[THEME.board]; const r=document.documentElement.style;
  r.setProperty('--sq-l',b.l); r.setProperty('--sq-d',b.d); r.setProperty('--sq-hl',b.hl);
  document.documentElement.dataset.tex = b.tex?'1':'0';
  document.querySelectorAll('svg.board use').forEach(u=>{ const id=u.getAttribute('href').split('-').pop(); u.setAttribute('href',`#${THEME.pieces}-${id}`); });
  document.querySelectorAll('.sw[data-board]').forEach(x=>x.classList.toggle('on',x.dataset.board===THEME.board));
  document.querySelectorAll('.sw[data-pieces]').forEach(x=>x.classList.toggle('on',x.dataset.pieces===THEME.pieces));
  try{localStorage.setItem('chess-theme',JSON.stringify(THEME))}catch(e){}
}
function themePanel(){
  let h=`<div class="tpanel" id="tpanel"><div class="lab">판 색상</div><div class="row">`;
  for(const [k,b] of Object.entries(BOARDS)) h+=`<span class="sw" data-board="${k}"><i><b style="background:${b.l}"></b><b style="background:${b.d}"></b><b style="background:${b.d}"></b><b style="background:${b.l}"></b></i>${b.name}</span>`;
  h+=`</div><div class="lab">기물</div><div class="row">`;
  for(const [k,n] of Object.entries(PSETS)) h+=`<span class="sw" data-pieces="${k}"><svg viewBox="0 0 100 100"><use href="#${k}-wN" width="100" height="100"/></svg>${n}</span>`;
  return h+`</div><div class="lab">체스닷컴 Neo 기물은 저작권 때문에 그대로 넣을 수 없어, 가장 비슷한 무료 세트(마에스트로)를 기본으로 씁니다. 나무 판 색은 체스닷컴 Dark Wood 판에서 추출했습니다.</div></div>`;
}
document.addEventListener('click',(e)=>{
  const tb=e.target.closest('#tbtn'); if(tb){ $('#tpanel').classList.toggle('open'); return; }
  const t=e.target.closest('.sw'); if(!t) return;
  if(t.dataset.board) THEME.board=t.dataset.board; if(t.dataset.pieces) THEME.pieces=t.dataset.pieces; THEME.v=2; applyTheme();
});

/* ---------- 체스판 SVG ---------- */
const FILES='abcdefgh';
function parseFen(fen){
  const rows=fen.split(' ')[0].split('/'); const out=[];
  rows.forEach((r,ri)=>{let f=0; for(const ch of r){ if(/\d/.test(ch)) f+=+ch; else { out.push({sq:FILES[f]+(8-ri), p:(ch===ch.toUpperCase()?'w':'b')+ch.toUpperCase()}); f++; } }});
  return out;
}
function sqXY(sq,flip){ let x=FILES.indexOf(sq[0]), y=8-(+sq[1]); if(flip){x=7-x;y=7-y;} return [x*100,y*100]; }
function arrow(from,to,color,flip){
  const [x1,y1]=sqXY(from,flip).map(v=>v+50),[x2,y2]=sqXY(to,flip).map(v=>v+50);
  const dx=x2-x1,dy=y2-y1,len=Math.hypot(dx,dy); if(!len) return '';
  const ux=dx/len,uy=dy/len, head=28, w=11, ex=x2-ux*head, ey=y2-uy*head, px=-uy, py=ux;
  return `<line x1="${x1+ux*22}" y1="${y1+uy*22}" x2="${ex}" y2="${ey}" stroke="${color}" stroke-width="${w}" stroke-linecap="round" opacity=".85"/>
  <polygon points="${x2},${y2} ${ex+px*18},${ey+py*18} ${ex-px*18},${ey-py*18}" fill="${color}" opacity=".85"/>`;
}
function boardSVG(fen, o={}){
  const flip=!!o.flip; let h=`<svg class="board" viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">`;
  for(let r=0;r<8;r++) for(let f=0;f<8;f++){ const light=(r+f)%2===0; h+=`<rect x="${f*100}" y="${r*100}" width="100" height="100" fill="var(${light?'--sq-l':'--sq-d'})"/>`; }
  if(GRAIN) h+=`<use class="grain" href="#grain-img" opacity=".55" style="mix-blend-mode:overlay"/>`;
  for(const sq of (o.last||[])){ const [x,y]=sqXY(sq,flip); h+=`<rect x="${x}" y="${y}" width="100" height="100" fill="var(--sq-hl)"/>`; }
  for(let i=0;i<8;i++){ const fl=flip?FILES[7-i]:FILES[i], rk=flip?i+1:8-i;
    h+=`<text x="${i*100+4}" y="796" font-size="22" fill="${i%2?'var(--sq-l)':'var(--sq-d)'}" font-family="system-ui" font-weight="600">${fl}</text>`;
    h+=`<text x="784" y="${i*100+24}" font-size="22" fill="${i%2?'var(--sq-d)':'var(--sq-l)'}" font-family="system-ui" font-weight="600">${rk}</text>`; }
  for(const {sq,p} of parseFen(fen)){ const [x,y]=sqXY(sq,flip); h+=`<use href="#${THEME.pieces}-${p}" x="${x}" y="${y}" width="100" height="100"/>`; }
  for(const [uci,color] of (o.arrows||[])){ if(uci) h+=arrow(uci.slice(0,2),uci.slice(2,4),color,flip); }
  return h+'</svg>';
}

/* ---------- 뷰어 ---------- */
const VIEWERS={}; let vid=0;
function viewer(spec){ const id='v'+(++vid); VIEWERS[id]={spec,line:0,idx:0}; return `<div class="viewer" id="${id}"></div>`; }
function drawViewer(id){
  const v=VIEWERS[id], el=document.getElementById(id); if(!el||!v) return;
  const line=v.spec.lines[v.line], st=line.states[v.idx];
  let h=boardSVG(st.fen,{flip:v.spec.flip,arrows:st.arrows,last:st.last});
  if(v.spec.lines.length>1) h+=`<div class="vtabs">`+v.spec.lines.map((l,i)=>`<span class="btn ${l.cls||''} ${i===v.line?'on':''}" data-v="${id}" data-line="${i}">${esc(l.label)}</span>`).join('')+`</div>`;
  h+=`<div class="cap">${st.caption||''}</div>`;
  h+=`<div class="vctl"><span class="btn nav" data-v="${id}" data-go="0">⏮</span><span class="btn nav" data-v="${id}" data-go="-1">‹</span><span class="btn nav" data-v="${id}" data-go="1">›</span><span class="btn nav" data-v="${id}" data-go="9">⏭</span></div>`;
  h+=`<div class="moves">`;
  line.states.forEach((s,i)=>{ if(i===0) return; if(s.num) h+=`<span class="num">${s.num}</span>`; h+=`<span class="${i===v.idx?'cur':''} ${s.bad?'bad':''}" data-v="${id}" data-idx="${i}">${esc(s.san)}</span>`; });
  el.innerHTML=h+`</div>`;
}
document.addEventListener('click',(e)=>{
  const t=e.target.closest('[data-v]'); if(!t) return;
  const v=VIEWERS[t.dataset.v]; if(!v) return;
  if(t.dataset.line!==undefined){ v.line=+t.dataset.line; v.idx=0; }
  else if(t.dataset.idx!==undefined){ v.idx=+t.dataset.idx; }
  else if(t.dataset.go!==undefined){ const n=v.spec.lines[v.line].states.length; const g=+t.dataset.go; v.idx = g===0?0 : g===9? n-1 : Math.max(0,Math.min(n-1,v.idx+g)); }
  drawViewer(t.dataset.v);
});
function drawAll(root){ (root||document).querySelectorAll('.viewer').forEach(el=>{ if(!el.innerHTML) drawViewer(el.id); }); }

/* 실수 국면 뷰어: 정답 수순 / 내 수와 반격 */
function blunderViewer(w){
  const flip=w.color==='b'||w.mover==='b';
  const start={fen:w.fen,arrows:[[w.uci,RED],[w.best_uci,GREEN]],caption:`<span style="color:${RED}">■</span> 내가 둔 수 ${esc(w.san)} &nbsp; <span style="color:${GREEN}">■</span> 정답 ${esc(w.best)}`};
  const lines=[]; const best=(w.best_line||[]);
  if(best.length){
    const states=[start]; let mover=w.mover, move=w.move;
    best.forEach((s,i)=>{ states.push({fen:s.fen,san:s.san,num:mover==='w'?`${move}.`:(i===0?`${move}...`:''),last:[s.uci.slice(0,2),s.uci.slice(2,4)],
      caption:i===0?`정답 ${esc(s.san)} 을 두면 평가 ${ev(w.cp_before)} 유지`:`정답 수순 계속 (${i+1}수째)`});
      if(mover==='b') move++; mover=mover==='w'?'b':'w'; });
    lines.push({label:'정답 수순',cls:'green',states});
  }
  { const ref=(w.refutation||[]); const states=[start]; let mover=w.mover, move=w.move;
    states.push({fen:w.after_fen||w.fen,san:w.san,bad:true,num:mover==='w'?`${move}.`:`${move}...`,last:[w.uci.slice(0,2),w.uci.slice(2,4)],caption:`내가 둔 ${esc(w.san)} → 평가 ${ev(w.cp_before)} 에서 ${ev(w.cp_after)} 로`});
    if(mover==='b') move++; mover=mover==='w'?'b':'w';
    ref.forEach((s,i)=>{ states.push({fen:s.fen,san:s.san,num:mover==='w'?`${move}.`:(i===0?`${move}...`:''),last:[s.uci.slice(0,2),s.uci.slice(2,4)],caption:i===0?`상대의 최선 반격 ${esc(s.san)}`:'반격 수순 계속'});
      if(mover==='b') move++; mover=mover==='w'?'b':'w'; });
    lines.push({label:'내 수와 반격',cls:'red',states});
  }
  return viewer({flip,lines});
}
"""

# ------------------------------------------------------------------ 대시보드
DASHBOARD = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>__USERNAME__ 래피드 분석</title>
<style>
__SHARED_CSS__
.tabs{display:flex;gap:4px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:4px}
.tabs button{flex:1;min-height:40px;padding:0;border:0;background:transparent;color:var(--text2);border-radius:9px;font-size:15px;font-weight:500;-webkit-tap-highlight-color:transparent}
.tabs button.on{background:var(--me);color:#fff;font-weight:600}
nav.jump{display:flex;gap:8px;overflow-x:auto;padding:10px 0 2px;scrollbar-width:none}
nav.jump::-webkit-scrollbar{display:none}
nav.jump a{flex:none;display:inline-flex;align-items:center;min-height:36px;padding:0 14px;font-size:14px;font-weight:500;border-radius:18px;background:var(--surface);border:1px solid var(--line);color:var(--text2)}
.hero .tile .k{font-weight:500}
.weak{border-left:5px solid var(--muted);cursor:pointer;-webkit-tap-highlight-color:transparent;position:relative}
.weak:active{transform:scale(.99)}
.weak .go{display:flex;justify-content:flex-end;align-items:center;gap:4px;margin-top:8px;font-size:13.5px;font-weight:600;color:var(--me)}
/* 추이 분석 시트 */
.sheet-bg{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:20;display:none;align-items:flex-end;justify-content:center}
.sheet-bg.open{display:flex}
.sheet{background:var(--bg);width:100%;max-width:720px;max-height:92vh;border-radius:18px 18px 0 0;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 -8px 30px rgba(0,0,0,.2)}
.sheet-h{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line);background:var(--surface);flex:none}
.sheet-h b{font-size:17px;line-height:1.3}
.sheet-h .sub{margin-top:2px}
.sheet-b{overflow-y:auto;padding:14px 16px calc(24px + env(safe-area-inset-bottom,0px));-webkit-overflow-scrolling:touch}
.verdict{border-radius:12px;padding:12px 14px;font-size:15px;line-height:1.5;border:1px solid var(--line);background:var(--surface);border-left:5px solid var(--muted);margin-bottom:10px}
.verdict.better,.verdict.maybe_better{border-left-color:var(--good)}
.verdict.worse{border-left-color:var(--critical)}.verdict.maybe_worse{border-left-color:var(--serious)}
.verdict .p{font-size:13px;color:var(--text2);margin-top:4px}
.verdict .ic{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:7px;color:#fff;background:var(--muted);margin-right:6px;vertical-align:2px}
.verdict.better .ic,.verdict.maybe_better .ic{background:var(--good)}.verdict.worse .ic{background:var(--critical)}.verdict.maybe_worse .ic{background:var(--serious)}
.tiles3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:10px}
.tiles3 .tile{padding:10px 12px}.tiles3 .tile .v{font-size:22px}
.tchart-wrap{position:relative}
.tchart{width:100%;height:auto;display:block;touch-action:pan-y}
.tchart text{font-family:inherit}
.tip{position:absolute;top:6px;left:50%;transform:translateX(-50%);background:var(--text);color:var(--bg);font-size:12.5px;padding:5px 10px;border-radius:8px;white-space:nowrap;pointer-events:none;display:none}
.tip.on{display:block}
.method{font-size:12.5px;color:var(--muted);line-height:1.5;margin-top:10px}
.weak.critical{border-left-color:var(--critical)}.weak.serious{border-left-color:var(--serious)}
.weak.warning{border-left-color:var(--warning)}.weak.good{border-left-color:var(--good)}
.weak .t{font-weight:700;font-size:16.5px;display:flex;align-items:center;gap:8px;line-height:1.3}
.weak .t .ic{font-size:12px;font-weight:600;padding:3px 8px;border-radius:7px;color:#fff;background:var(--muted);flex:none}
.critical .ic{background:var(--critical)}.serious .ic{background:var(--serious)}.warning .ic{background:var(--warning);color:#000}.good .ic{background:var(--good)}
.weak p{margin:6px 0 0;font-size:14.5px;color:var(--text2);line-height:1.55}
.legend{display:flex;gap:14px;font-size:13px;color:var(--text2);margin-bottom:10px;flex-wrap:wrap}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.bars{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;align-items:center;font-size:13.5px}
.bars .lbl{color:var(--text2);white-space:nowrap}
.bar{height:12px;border-radius:0 5px 5px 0;background:var(--me);position:relative}
.bar.opp{background:var(--opp)}
.bar span{position:absolute;left:calc(100% + 6px);top:-4px;font-size:12.5px;color:var(--text2);white-space:nowrap}
.pair{display:flex;flex-direction:column;gap:3px;padding:1px 0}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--text2);font-weight:500;font-size:12.5px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tw{overflow-x:auto}
.game{padding:14px 0;border-bottom:1px solid var(--line);font-size:14.5px}
.game:first-child{padding-top:4px}
.game:last-child{border-bottom:0;padding-bottom:4px}
.game .row{display:flex;gap:12px;align-items:flex-start}
.game .m{flex:1;min-width:0}
.game .m .h{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.game .m .h b{font-weight:600;font-size:15.5px}
.game .m .h .dt{flex:none;white-space:nowrap}
.game .m .eco{color:var(--muted);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.more{display:flex;justify-content:center;padding:12px 0 4px}
.more .btn{width:100%;max-width:360px}
.game .m .s{color:var(--text2);font-size:13px;margin-top:2px;line-height:1.45}
.game .m .w{font-size:13.5px;margin-top:4px;line-height:1.45}
.game .links{display:flex;gap:6px 14px;flex-wrap:wrap;margin-top:8px;align-items:center}
.game .links a{display:inline-flex;align-items:center;min-height:36px;font-size:14px;font-weight:500}
.spark{width:100%;height:52px;display:block;margin-top:8px}
.expand{margin-top:6px}
.oplist{display:flex;flex-direction:column;gap:8px}
.opitem{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:52px;padding:8px 14px;border:1px solid var(--line);border-radius:12px;background:var(--bg);cursor:pointer;font-size:15px;-webkit-tap-highlight-color:transparent}
.opitem.on{border-color:var(--me);background:var(--me-soft)}
.opitem .sc{font-weight:700;font-size:17px;white-space:nowrap}
.opitem .nm{color:var(--text2);font-size:12.5px;margin-top:2px;line-height:1.4}
.altbox{font-size:13px;color:var(--text2);text-align:center;margin-top:4px}
</style>
</head>
<body>
__PIECES__
<div class="topbar">
  <div><h1 id="title"></h1><div class="sub" id="subtitle"></div></div>
  <span class="btn tbtn" id="tbtn">🎨 테마</span>
</div>
<div id="tpanel-slot"></div>
<header>
  <div class="tabs" id="tabs">
    <button data-w="all">전체</button><button data-w="30d">최근 30일</button><button data-w="7d">최근 7일</button>
  </div>
  <nav class="jump">
    <a href="#s-weak">보완점</a><a href="#s-recent">최근 게임</a><a href="#s-worst">큰 실수</a><a href="#s-ex">유형별 실수</a><a href="#s-open">오프닝</a><a href="#s-time">시간</a><a href="#s-phase">국면</a>
  </nav>
</header>
<main id="main"></main>
<footer id="foot"></footer>
<div class="sheet-bg" id="sheet"><div class="sheet"><div class="sheet-h"><div><b id="sheet-title"></b><div class="sub" id="sheet-sub"></div></div><span class="btn" id="sheet-x">닫기</span></div><div class="sheet-b" id="sheet-body"></div></div></div>
<script>
const DATA = __DATA__;
let W = 'all';
__SHARED_JS__
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
let TCH=null;
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
  let h=`<div class="tchart-wrap"><svg class="tchart" id="tchart" viewBox="0 0 ${W} ${H}">`;
  for(let v=lo;v<=hi+1e-9;v+=step){ h+=`<line x1="${L}" x2="${W-R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)" stroke-width="1"/><text x="${L-6}" y="${(y(v)+4).toFixed(1)}" font-size="11" text-anchor="end" fill="var(--muted)">${axisV(v)}</text>`; }
  if(t.k&&t.k<N){ const xs=x(N-t.k-0.5).toFixed(1); h+=`<line x1="${xs}" x2="${xs}" y1="${T}" y2="${T+ph}" stroke="var(--muted)" stroke-width="1"/><text x="${(+xs+4).toFixed(1)}" y="${T+10}" font-size="11" fill="var(--text2)">최근 ${t.k}판</text>`; }
  h+=vals.map((v,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="var(--me)" opacity=".28"/>`).join('');
  h+=`<path d="${roll.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ')}" fill="none" stroke="var(--me)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  h+=`<text x="${L}" y="${H-6}" font-size="11" fill="var(--muted)">${t.series[0][0]}</text><text x="${W-R}" y="${H-6}" font-size="11" text-anchor="end" fill="var(--muted)">${t.series[N-1][0]}</text><text x="${(L+pw/2).toFixed(1)}" y="${H-6}" font-size="11" text-anchor="middle" fill="var(--muted)">게임 순서 →</text>`;
  h+=`<g id="tc" style="display:none"><line id="tc-l" y1="${T}" y2="${T+ph}" stroke="var(--text2)" stroke-width="1"/><circle id="tc-d" r="5" fill="var(--me)" stroke="var(--surface)" stroke-width="2"/></g>`;
  h+=`</svg><div class="tip" id="ttip"></div></div>`;
  TCH={t,N,L,pw,W,x,y,vals,roll,win};
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
function closeSheet(){ $('#sheet').classList.remove('open'); document.body.style.overflow=''; TCH=null; }
document.addEventListener('click',(e)=>{
  const c=e.target.closest('[data-weak]'); if(c){ openSheet(+c.dataset.weak); return; }
  if(e.target.closest('#sheet-x')||e.target===$('#sheet')) closeSheet();
});
document.addEventListener('keydown',(e)=>{ if(e.key==='Escape') closeSheet(); });
function tcMove(e){
  const svg=e.target.closest('#tchart'); if(!svg||!TCH) return;
  const r=svg.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*TCH.W;
  const i=Math.max(0,Math.min(TCH.N-1,Math.round((px-TCH.L)/TCH.pw*(TCH.N-1))));
  const g=$('#tc'); g.style.display=''; const X=TCH.x(i).toFixed(1);
  $('#tc-l').setAttribute('x1',X); $('#tc-l').setAttribute('x2',X); $('#tc-d').setAttribute('cx',X); $('#tc-d').setAttribute('cy',TCH.y(TCH.roll[i]).toFixed(1));
  const t=TCH.t, sc=t.fmt==='pct'?100:1;
  $('#ttip').textContent=`${t.series[i][0]} · 이 판 ${fmtV(t,TCH.vals[i]/sc)} · 최근 ${TCH.win}판 평균 ${fmtV(t,TCH.roll[i]/sc)}`; $('#ttip').classList.add('on');
}
document.addEventListener('pointermove',tcMove); document.addEventListener('pointerdown',tcMove);
document.addEventListener('pointerleave',(e)=>{ if(e.target&&e.target.id==='tchart'){ const g=$('#tc'); if(g) g.style.display='none'; $('#ttip')&&$('#ttip').classList.remove('on'); } },true);

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
  $('#foot').innerHTML = `마지막 갱신 ${DATA.generated} (KST) · Stockfish 19 depth 14, 수순 depth 16 · 10분마다 자동 갱신<br>기물: maestro (sadsnake1, CC BY-NC-SA 4.0), cburnett (GPLv2+), merida (GPLv2+), alpha (Eric Bentzen), california (Jerry S., CC BY-NC-SA 4.0)`;
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
  </div></section>`;
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
</script>
</body>
</html>
"""

# ------------------------------------------------------------------ 게임 상세 페이지
GAME_PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>게임 분석</title>
<style>
__SHARED_CSS__
header{position:static;border-bottom:0;padding:calc(10px + env(safe-area-inset-top,0px)) 0 0}
.top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.players{display:flex;justify-content:space-between;align-items:center;font-size:15px;margin-top:12px;gap:8px;line-height:1.35}
.players b{font-weight:600}
.boardwrap{display:flex;gap:10px;align-items:stretch;max-width:470px;margin:12px auto 0}
.evalbar{width:22px;border-radius:6px;overflow:hidden;background:#403d39;position:relative;flex:none}
.evalbar .w{position:absolute;left:0;right:0;background:#f0f0f0;transition:height .2s}
.evalbar span{position:absolute;left:0;right:0;text-align:center;font-size:10px;font-weight:700;font-family:ui-monospace,Menlo,monospace}
.boardwrap .board{flex:1;max-width:440px;margin:0}
.info{max-width:470px;margin:10px auto 0;font-size:14.5px;line-height:1.5}
.cls{display:inline-block;padding:2px 8px;border-radius:7px;color:#fff;font-size:12px;font-weight:600;vertical-align:1px}
.cls.best{background:var(--c-best)}.cls.good{background:var(--c-good)}.cls.inacc{background:var(--c-inacc);color:#000}.cls.mist{background:var(--c-mist);color:#000}.cls.blun{background:var(--c-blun)}
.graph{width:100%;height:100px;display:block;margin-top:10px;cursor:pointer;border-radius:8px;overflow:hidden}
.mlist{display:grid;grid-template-columns:40px 1fr 1fr;font-size:15px;margin-top:10px}
.mlist>div{padding:5px 8px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;min-height:40px}
.mlist .num{color:var(--muted);font-size:12px;justify-content:flex-end}
.mlist .mv{cursor:pointer;border-radius:8px;-webkit-tap-highlight-color:transparent}
.mlist .mv.cur{background:var(--me-soft)}
.mlist .mv i{width:9px;height:9px;border-radius:50%;flex:none;display:inline-block}
.mlist .mv .t{font-size:11.5px;color:var(--muted);margin-left:auto;white-space:nowrap}
.legend{display:flex;gap:12px;font-size:12.5px;color:var(--text2);flex-wrap:wrap;margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
.opts{display:flex;gap:8px;justify-content:center;margin-top:10px;flex-wrap:wrap}
.key{padding:10px 0;border-bottom:1px solid var(--line);font-size:14.5px;line-height:1.5;cursor:pointer}
.key:last-child{border-bottom:0}
</style>
</head>
<body>
__PIECES__
<header>
  <div class="top"><a href="index.html" class="btn">← 대시보드</a><span class="btn" id="tbtn">🎨 테마</span></div>
  <div id="tpanel-slot"></div>
  <div id="head"></div>
</header>
<main id="main"><div class="empty">불러오는 중…</div></main>
<footer id="foot"></footer>
<script>
__SHARED_JS__
$('#tpanel-slot').innerHTML=themePanel();
const params=new URLSearchParams(location.search);
const ID=params.get('id'); let G=null, IDX=0, FLIP=false, SHOW_BEST=true;
const CLS={best:['최선','best'],good:['좋음','good'],inacc:['부정확','inacc'],mist:['실수','mist'],blun:['대실수','blun'],miss:['외통 놓침','blun']};
const CLSCOLOR={best:'var(--c-best)',good:'var(--c-good)',inacc:'var(--c-inacc)',mist:'var(--c-mist)',blun:'var(--c-blun)',miss:'var(--c-blun)'};

async function load(){
  try{ const r=await fetch(`games/${ID}.json`,{cache:'no-cache'}); if(!r.ok) throw new Error(r.status); G=await r.json(); }
  catch(e){ $('#main').innerHTML=`<div class="empty">게임 데이터를 찾을 수 없습니다 (${esc(ID)}). 아직 분석·업로드되지 않았을 수 있습니다.</div>`; return; }
  FLIP = G.my_color==='b';
  const p=+params.get('ply'); IDX = (p>0&&p<=G.plies.length)? p : 0;
  document.title=`${G.white} vs ${G.black} · 게임 분석`;
  renderHead(); renderMain(); draw();
}
function renderHead(){
  $('#head').innerHTML=`<div class="players"><span><b>${esc(G.white)}</b> (${G.welo}) <span class="sub">백</span></span><span class="res ${G.outcome}" style="width:auto;padding:0 12px;height:32px;font-size:14px">${G.result} · ${G.outcome==='W'?'승':G.outcome==='L'?'패':'무'}</span><span><span class="sub">흑</span> <b>${esc(G.black)}</b> (${G.belo})</span></div>
  <div class="sub" style="margin-top:6px">${G.date} · ${esc(G.termination||'')} · <a href="${esc(G.url)}" target="_blank" rel="noopener">체스닷컴 ↗</a></div>
  <div class="sub" style="color:var(--muted)">${esc(G.eco_name)}</div>`;
}
function renderMain(){
  const s=G.summary, n=G.plies.length;
  let h=`<div class="boardwrap"><div class="evalbar" id="evalbar"><div class="w"></div><span></span></div><div id="board" style="flex:1;min-width:0"></div></div>`;
  h+=`<div class="vctl"><span class="btn nav" data-go="0">⏮</span><span class="btn nav" data-go="-1">‹</span><span class="btn nav" data-go="1">›</span><span class="btn nav" data-go="9">⏭</span></div>`;
  h+=`<div class="opts"><span class="btn ${SHOW_BEST?'on':''}" id="optbest">정답 화살표</span><span class="btn" id="optflip">판 뒤집기</span></div>`;
  h+=`<div class="info card" id="info"></div>`;
  h+=`<div class="card"><div class="sub">평가 그래프 (누르면 이동 · 점: 실수/대실수)</div>${graphSVG()}</div>`;
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
    key.forEach(({p,i})=>{ h+=`<div class="key" data-jump="${i+1}"><span class="cls ${CLS[p.cls][1]}">${CLS[p.cls][0]}</span> <span class="mono">${mv(p)}</span> 대신 <span class="mono">${esc(p.best)}</span> <span class="sub">· ${ev(p.cp_before)} → ${ev(p.cp_after)} · 남은시간 ${clk(p.clock)}${p.spent!=null?` · ${Math.round(p.spent)}초 사용`:''}</span></div>`; });
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
  $('#foot').textContent='Stockfish 19 depth 14 · 정답 수순 depth 16';
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
    info+=`<div class="sub" style="margin-top:3px">남은 시간 ${clk(p.clock)}${p.spent!=null?` · 이 수에 ${Math.round(p.spent)}초`:''}</div>`;
    const L=G.lines[String(IDX)];
    if(L&&L.best_line&&L.best_line.length) info+=`<div class="sub" style="margin-top:3px">정답 수순: <span class="mono">${esc(L.best_line.map(s=>s.san).join(' '))}</span></div>`;
    if(L&&L.refutation&&L.refutation.length) info+=`<div class="sub">내 수 뒤 반격: <span class="mono">${esc(L.refutation.map(s=>s.san).join(' '))}</span></div>`;
  }
  $('#info').innerHTML=info;
  document.querySelectorAll('.mlist .mv').forEach(el=>el.classList.toggle('cur',+el.dataset.jump===IDX));
  const g=$('#gcur'); if(g){ g.setAttribute('x1',(IDX/n*360).toFixed(1)); g.setAttribute('x2',(IDX/n*360).toFixed(1)); }
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
</script>
</body>
</html>
"""


def _fill(template, **kw):
    out = template
    for k, v in kw.items():
        out = out.replace("__" + k + "__", v)
    return out


def render_html(payload):
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return _fill(DASHBOARD, USERNAME=payload["username"], PIECES=piece_symbols(), SHARED_CSS=SHARED_CSS,
                 SHARED_JS=SHARED_JS.replace("__GRAIN__", "true" if grain_uri() else "false"), DATA=data)


def render_game_page():
    return _fill(GAME_PAGE, PIECES=piece_symbols(), SHARED_CSS=SHARED_CSS, SHARED_JS=SHARED_JS.replace("__GRAIN__", "true" if grain_uri() else "false"))
