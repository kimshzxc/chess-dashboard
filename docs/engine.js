/* 브라우저 스톡피시(19 라이트, 단일 스레드) 래퍼. 워커로 띄우고 한 번에 한 국면씩 분석한다.
   Engine.analyse(fen, {depth, movetime}) → {cp: 백 기준 cp(외통은 ±(10000 − 남은 수×10), 나머지는 ±1500 안), depth, pv: [uci…], best: uci}
   새 요청이 오면 진행 중인 분석은 멈추고, 먼저 들어온 요청의 결과에는 stale=true 가 붙는다. 파일은 docs/vendor/ 에 있다 (같은 출처라 오프라인 캐시에도 든다). */
const Engine=(()=>{
  let w=null, ready=null, onLine=null, seq=0, chain=Promise.resolve();
  function start(){
    if(ready) return ready;
    ready=new Promise((res,rej)=>{
      try{ w=new Worker('vendor/stockfish-19-lite-single.js'); }catch(e){ rej(new Error('워커를 만들 수 없습니다')); return; }
      const t=setTimeout(()=>rej(new Error('엔진이 응답하지 않습니다')),25000);
      w.onmessage=(e)=>{ const line=typeof e.data==='string'?e.data:(e.data&&e.data.data)||'';
        if(line==='uciok'){ w.postMessage('setoption name UCI_AnalyseMode value true'); w.postMessage('isready'); }
        else if(line==='readyok'&&t){ clearTimeout(t); res(); }
        else if(onLine) onLine(line); };
      w.onerror=(e)=>{ clearTimeout(t); rej(new Error((e&&e.message)||'엔진 파일을 불러오지 못했습니다')); };
      w.postMessage('uci');
    });
    ready.catch(()=>{ ready=null; });   // 실패하면 다음에 다시 시도할 수 있게
    return ready;
  }
  function run(fen,o,my){
    const turnW=fen.split(' ')[1]==='w';
    return new Promise((res)=>{
      let last=null;
      onLine=(l)=>{
        if(l.startsWith('info ')&&l.includes(' score ')&&l.includes(' pv ')){
          if(/ multipv (\d+)/.test(l)&&RegExp.$1!=='1') return;
          const d=/ depth (\d+)/.exec(l), s=/ score (cp|mate) (-?\d+)/.exec(l), pv=/ pv (.+)$/.exec(l);
          if(!s||!pv) return;
          let cp=s[1]==='cp'?Math.max(-1500,Math.min(1500,+s[2])):(+s[2]>0?10000-10*(+s[2]):-10000+10*Math.abs(+s[2]));
          if(!turnW) cp=-cp;
          const moves=pv[1].trim().split(/\s+/);
          last={cp,depth:d?+d[1]:0,pv:moves,best:moves[0]||null};
          if(my!==seq) w.postMessage('stop');   // 더 새 요청이 기다리고 있으면 여기서 멈춘다
        } else if(l.startsWith('bestmove')){
          onLine=null; const bm=l.split(/\s+/)[1];
          if(last&&bm&&bm!=='(none)'&&last.best!==bm){ last.best=bm; last.pv=[bm]; }
          res(Object.assign(last||{cp:null,depth:0,pv:[],best:null},{stale:my!==seq}));
        }
      };
      w.postMessage('position fen '+fen);
      w.postMessage(`go depth ${o.depth||14}${o.movetime?` movetime ${o.movetime}`:''}`);
    });
  }
  function analyse(fen,o={}){
    const my=++seq;
    if(onLine&&w) w.postMessage('stop');
    const p=chain.then(()=>start()).then(()=>my!==seq?{stale:true,cp:null,pv:[],best:null,depth:0}:run(fen,o,my));
    chain=p.catch(()=>{});
    return p;
  }
  return {start,analyse,get loaded(){ return !!ready; }};
})();
