(function () {
  "use strict";
  const L=window.PlayerLogic,D=window.VizData,el=D.element;
  const labels={egpot_full:"EG-POT · full, no lookahead",egpot_full_mcts:"EG-POT · full + MCTS",egpot_no_pareto:"EG-POT · weighted sum",egpot_no_pareto_mcts:"EG-POT · weighted sum + MCTS",egpot_no_entropy:"EG-POT · no entropy",egpot_no_contracts:"EG-POT · no contracts",egpot_no_choke_point:"EG-POT · no choke-point rule",vector_topk:"Vector similarity · top K",bfs:"Breadth-first search",greedy_walk:"Greedy relevance walk"};
  const objectives=["Relevance","Hop efficiency","Contract","Entropy"];
  const scripts=new Map();
  function loadScript(path,ready) {
    if(ready())return Promise.resolve();
    if(scripts.has(path))return scripts.get(path);
    const promise=new Promise((resolve,reject)=>{
      const script=document.createElement("script");script.src=path;
      script.onload=()=>ready()?resolve():reject(new Error("Local script loaded without the expected data: "+path));
      script.onerror=()=>{script.remove();scripts.delete(path);reject(new Error("Missing local data file: "+path+". Run python -B -m bench.export_traces_js, then retry."));};
      document.head.append(script);
    });scripts.set(path,promise);return promise;
  }
  class TraversalPlayer {
    constructor(){
      this.panel=document.getElementById("player-panel");this.index=0;this.trace=null;this.revealed=false;this.expanded=false;this.candidate=null;this.timer=null;this.serial=0;
      this.query=document.getElementById("player-query");this.method=document.getElementById("player-method");this.budget=document.getElementById("player-budget");
      D.queries.filter(q=>q.split==="dev").forEach(q=>{const option=el("option","",`${q.id} · ${q.type} · ${q.query}`);option.value=q.id;this.query.append(option);});
      Object.entries(labels).forEach(([id,label])=>{const option=el("option","",label);option.value=id;this.method.append(option);});
      this.methodHelp=window.GlossaryUI.selectorHelp(this.method,value=>value);
      [this.query,this.method,this.budget].forEach(input=>input.addEventListener("change",()=>this.load()));
      document.getElementById("player-prev").onclick=()=>this.go(this.index-1);
      document.getElementById("player-next").onclick=()=>this.go(this.index+1);
      document.getElementById("player-reset").onclick=()=>this.go(0);
      document.getElementById("player-play").onclick=()=>this.timer?this.pause():this.play();
      document.getElementById("player-speed").onchange=()=>{if(this.timer){this.pause();this.play();}};
      document.getElementById("player-slider").oninput=e=>this.go(Number(e.target.value));
      document.getElementById("player-reveal").onclick=()=>this.reveal();
      document.getElementById("player-fit").onclick=()=>this.network&&this.network.fit({animation:false});
      document.addEventListener("keydown",e=>{if(this.panel.hidden||!this.trace||/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(e.key==="ArrowRight"||e.key==="ArrowLeft"){e.preventDefault();this.go(this.index+(e.key==="ArrowRight"?1:-1));}});
      document.getElementById("theme-toggle").addEventListener("click",()=>{if(this.trace&&!this.panel.hidden)this.renderGraph();});
    }
    async activate(){if(!this.network){this.nodes=new vis.DataSet();this.edges=new vis.DataSet();this.network=new vis.Network(document.getElementById("player-network"),{nodes:this.nodes,edges:this.edges},{physics:false,layout:{improvedLayout:false,randomSeed:0},interaction:{hover:true},nodes:{shape:"dot",chosen:false,font:{color:"#e5edf6",face:"Segoe UI",size:12,strokeWidth:3}},edges:{chosen:false,smooth:false,arrows:{to:{enabled:true,scaleFactor:.4}}}});}if(!this.trace)await this.load();else{this.network.redraw();this.network.fit({animation:false});}}
    pause(){if(this.timer)clearInterval(this.timer);this.timer=null;document.getElementById("player-play").textContent="Play";}
    play(){if(!this.trace)return;if(this.index===this.trace.steps.length-1)this.go(0);document.getElementById("player-play").textContent="Pause";this.timer=setInterval(()=>{if(this.index>=this.trace.steps.length-1){this.pause();return;}this.go(this.index+1,false);},1300/Number(document.getElementById("player-speed").value));}
    go(index,pause=true){if(!this.trace)return;if(pause)this.pause();this.index=Math.max(0,Math.min(index,this.trace.steps.length-1));this.candidate=null;this.render();}
    async load(){
      this.pause();const serial=++this.serial;this.trace=null;this.revealed=false;this.expanded=false;this.candidate=null;
      this.methodHelp.refresh();
      const query=D.queries.find(q=>q.id===this.query.value);
      document.getElementById("player-query-text").textContent=query.query;
      document.getElementById("player-start").textContent=query.start_node;
      document.getElementById("player-inspector").replaceChildren(el("p","muted","Loading the selected local trace…"));
      document.getElementById("player-inspector").scrollTop=0;
      document.getElementById("player-answer").hidden=true;document.getElementById("player-metrics").hidden=true;
      document.getElementById("player-reveal").textContent="Reveal answer";
      document.getElementById("player-status").textContent="Loading local trace…";
      this.nodes&&this.nodes.clear();this.edges&&this.edges.clear();
      try {
        await loadScript("data/online_boutique/traces_index.js",()=>Array.isArray(window.VIZ_TRACE_INDEX));
        const entry=window.VIZ_TRACE_INDEX.find(r=>r.query_id===this.query.value&&r.method===this.method.value&&r.budget===Number(this.budget.value));
        if(!entry)throw new Error("No exported trace matches these selectors. Export the requested DEV run first.");
        const traceId=entry.path.split("/").pop().replace(/\.json$/,"");
        if(!/^[a-zA-Z0-9_-]+$/.test(traceId))throw new Error("Invalid trace filename in local index.");
        await loadScript("data/online_boutique/traces_js/"+traceId+".js",()=>Boolean(window.VIZ_TRACES&&window.VIZ_TRACES[traceId]));
        if(serial!==this.serial)return;
        this.entry=entry;this.trace=window.VIZ_TRACES[traceId];this.index=0;this.subgraph=L.subgraph(this.trace,D.graph);this.positions=new Map();
        const first=new Map([[this.trace.start_node,0]]);
        this.trace.steps.forEach((_,i)=>L.stepState(this.trace,i).seen.forEach(n=>{if(!first.has(n))first.set(n,i+1);}));
        const groups=new Map();this.subgraph.nodes.forEach(n=>{const level=first.get(n.id)??this.trace.steps.length;if(!groups.has(level))groups.set(level,[]);groups.get(level).push(n.id);});
        for(const [level,ids] of groups)ids.sort().forEach((id,i)=>{const angle=2*Math.PI*i/ids.length,r=level===0?0:200+level*105;this.positions.set(id,{x:Math.cos(angle)*r,y:Math.sin(angle)*r});});
        document.getElementById("player-slider").max=this.trace.steps.length-1;
        document.getElementById("player-status").textContent="Local trace ready · "+this.subgraph.nodes.length+" relevant nodes";
        this.render();
      }catch(error){if(serial!==this.serial)return;document.getElementById("player-status").textContent="Unable to load trace";document.getElementById("player-inspector").replaceChildren(el("div","player-error",error.message));}
    }
    render(){
      if(!this.trace)return;this.state=L.stepState(this.trace,this.index);const s=this.state.current;
      document.getElementById("player-step-label").textContent=s.kind==="stop"?"Stopped · "+s.reason.replaceAll("_"," "):(s.kind==="egpot_round"?"Round "+s.round+" of "+this.trace.steps.filter(x=>x.kind==="egpot_round").length:"Step "+(this.index+1)+" of "+this.trace.steps.length);
      document.getElementById("player-counter").textContent=this.state.collected.length+" / "+this.trace.node_budget+" nodes collected";
      document.getElementById("player-counter").append(window.GlossaryUI.help("nodes_returned"));
      document.getElementById("player-slider").value=this.index;
      document.getElementById("player-prev").disabled=this.index===0;document.getElementById("player-next").disabled=this.index===this.trace.steps.length-1;
      this.renderGraph();this.renderInspector();this.renderAnswer();
    }
    renderGraph(){
      const state=this.state,light=document.documentElement.dataset.theme==="light",gold=this.revealed?window.VIZ_GOLD[this.trace.query_id]:null;
      const seen=new Set(state.seen),collected=new Set(state.collected),selected=new Set(state.selected),current=new Set(state.candidates.map(c=>c.to_node));
      if(gold)gold.gold_path.forEach(n=>seen.add(n));
      const topFive=new Set([...new Set([...state.candidates].sort((a,b)=>L.mean(b.final_vector)-L.mean(a.final_vector)||a.to_node.localeCompare(b.to_node)||a.idx-b.idx).map(c=>c.to_node))].slice(0,5));
      const rows=[...seen].map(id=>D.byId.get(id)).filter(Boolean),items=rows.map(node=>{
        const candidate=state.candidates.filter(c=>c.to_node===node.id).sort((a,b)=>L.mean(b.final_vector)-L.mean(a.final_vector))[0];
        const isGold=gold&&gold.gold_nodes.includes(node.id),color=D.colors.get(node.repo),isSelected=selected.has(node.id),isCollected=collected.has(node.id);
        const position=this.positions.get(node.id)||{x:0,y:0};
        return {id:node.id,...position,shape:node.id===this.trace.start_node?"star":D.contract(node)?"diamond":"dot",size:node.id===this.trace.start_node?23:candidate?11+L.mean(candidate.final_vector)*17:13,
          label:node.id===this.trace.start_node||isSelected||isGold||topFive.has(node.id)?node.name:"",borderWidth:isGold?5:isSelected?4:2,
          color:{background:isCollected?color:"rgba(0,0,0,0)",border:isGold?"#e6b94a":isSelected?"#82fbe0":current.has(node.id)?"#8898aa":"#58677b"},
          font:{size:17,vadjust:topFive.has(node.id)?8:0,color:light?"#1e354e":"#e5edf6",strokeColor:light?"#f7fafc":"#0d1622"},title:node.name+" · "+node.repo+(candidate?" | Immediate: "+objectives.map((name,i)=>name+" "+candidate.immediate_vector[i].toFixed(2)).join(", "):"")};
      });
      const edges=D.graph.edges.filter(e=>seen.has(e.source)&&seen.has(e.target)).map(e=>({id:"real_"+e.viewId,from:e.source,to:e.target,width:.65,color:{color:light?"#a0adbb":"#52617a",opacity:.25}}));
      if(state.current.kind==="egpot_round")state.candidates.forEach(c=>edges.push({id:"step_"+c.idx,from:c.from_node,to:c.to_node,width:c.selected?3:1,dashes:!c.selected,color:{color:c.selected?"#67dfc4":"#738da9",opacity:c.selected?1:.55}}));
      if(state.current.kind==="greedy_step"&&state.current.chosen)edges.push({id:"greedy",from:state.current.from,to:state.current.chosen,width:3,color:{color:"#67dfc4"}});
      if(gold)gold.gold_path.slice(1).forEach((id,i)=>{
        const previous=gold.gold_path[i];
        const edge=D.graph.edges.find(e=>e.source===previous&&e.target===id)||D.graph.edges.find(e=>e.source===id&&e.target===previous);
        if(edge)edges.push({id:"answer_"+i,from:edge.source,to:edge.target,width:3,dashes:[6,5],color:{color:"#e6b94a"}});
      });
      this.nodes.clear();this.edges.clear();this.nodes.add(items);this.edges.add(edges);
      this.network.fit({animation:false});
    }
    renderInspector(){
      const panel=document.getElementById("player-inspector"),step=this.state.current;panel.replaceChildren();
      panel.append(el("div","eyebrow","STEP INSPECTOR"),el("p","player-caption",L.caption(step)));
      if(step.kind==="egpot_round"){
        const rows=L.sortCandidates(step.candidates);panel.append(this.parallel(rows),el("p","tiny muted","Parallel coordinates: final vectors used for selection."));
        const key=el("div","bar-key");["score_relevance","score_hop","score_contract","score_entropy","pareto_front"].forEach(k=>key.append(window.GlossaryUI.label(k)));panel.append(key);
        panel.append(el("p","tiny muted","R/H/C/E numbers are immediate values. Bars: immediate (blue), lookahead (violet), final (mint). Hover an objective to see all three values."));
        const table=el("div","candidate-table");
        (this.expanded?rows:rows.slice(0,15)).forEach(c=>{
          const button=el("button","candidate-row"+(c.selected?" picked":""));button.setAttribute("data-candidate",c.idx);
          button.append(el("span","candidate-name",D.byId.get(c.to_node)?.name||c.to_node),el("span","candidate-front","F"+c.front_index+(c.selected?" ✓":"")));
          const bars=el("div","candidate-bars");c.final_vector.forEach((v,i)=>{
            const cell=el("div","objective-cell");cell.title=objectives[i]+": immediate "+c.immediate_vector[i].toFixed(3)+", lookahead "+(c.lookahead_vector?c.lookahead_vector[i].toFixed(3):"not used")+", final "+v.toFixed(3);cell.append(el("span","objective-value","RHCE"[i]+" "+c.immediate_vector[i].toFixed(2)),window.GlossaryUI.help(["score_relevance","score_hop","score_contract","score_entropy"][i]));
            const values=c.lookahead_vector?[[c.immediate_vector[i],"immediate"],[c.lookahead_vector[i],"lookahead"],[v,"final"]]:[[c.immediate_vector[i],"immediate"],[v,"final"]];
            values.forEach(([value,kind])=>{const track=el("span","bar-track");const fill=el("i","bar-fill "+kind);fill.style.width=(100*value)+"%";track.append(fill);cell.append(track);});bars.append(cell);
          });button.append(bars);button.onclick=()=>{this.candidate=c;this.renderRollouts(c);};table.append(button);
        });panel.append(table);
        if(rows.length>15){const toggle=el("button","text-button",this.expanded?"Show first 15":"Show all "+rows.length);toggle.onclick=()=>{this.expanded=!this.expanded;this.renderInspector();};panel.append(toggle);}
        const rollout=el("div","rollout-panel");rollout.id="player-rollouts";panel.append(rollout);
        if(this.candidate)this.renderRollouts(this.candidate);
      }else if(step.kind==="bfs_layer"){
        this.list(panel,"Frontier",step.frontier);this.list(panel,"Added this layer",step.added);
      }else if(step.kind==="greedy_step"){
        panel.append(el("h3","","Options · "+step.options.length));step.options.forEach(o=>panel.append(el("div","baseline-option"+(o.to===step.chosen?" picked":""),(o.to===step.chosen?"✓ ":"")+(D.byId.get(o.to)?.name||o.to)+" · "+o.score.toFixed(4))));
      }else if(step.kind==="vector_rank"){
        panel.append(el("h3","","Selected ranking"));step.ranking.forEach((r,i)=>panel.append(el("div","baseline-option",(i+1)+". "+(D.byId.get(r.node)?.name||r.node)+" · "+r.score.toFixed(4))));
      }else this.list(panel,"Final collected nodes",this.trace.final.visited_order);
    }
    list(panel,title,ids){panel.append(el("h3","",title+" · "+ids.length));ids.forEach(id=>panel.append(el("div","baseline-option",D.byId.get(id)?.name||id)));}
    parallel(rows){
      const ns="http"+":"+"//www.w3.org/2000/svg";const svg=document.createElementNS(ns,"svg");svg.setAttribute("viewBox","0 0 400 135");svg.classList.add("parallel-chart");svg.setAttribute("aria-label","Four-objective parallel coordinates");
      const xs=[34,144,254,364];objectives.forEach((name,i)=>{const line=document.createElementNS(ns,"line");Object.entries({x1:xs[i],x2:xs[i],y1:12,y2:100,stroke:"#52617a"}).forEach(([k,v])=>line.setAttribute(k,v));svg.append(line);const text=document.createElementNS(ns,"text");text.setAttribute("x",xs[i]);text.setAttribute("y",122);text.setAttribute("text-anchor","middle");text.textContent=["Relevance","Hop","Contract","Entropy"][i];svg.append(window.GlossaryUI.svgHelp(text,["score_relevance","score_hop","score_contract","score_entropy"][i]));});
      [...rows].sort((a,b)=>Number(a.selected)-Number(b.selected)).forEach(c=>{const line=document.createElementNS(ns,"polyline");line.setAttribute("points",c.final_vector.map((v,i)=>xs[i]+","+(100-v*88)).join(" "));line.setAttribute("fill","none");line.setAttribute("stroke",c.selected?"#67dfc4":c.front_index===0?"#b2a0fa":"#64748b");line.setAttribute("stroke-width",c.selected?2.7:c.front_index===0?1.8:1);line.setAttribute("opacity",c.selected?1:c.front_index===0?.8:.22);const title=document.createElementNS(ns,"title");title.textContent=D.byId.get(c.to_node)?.name||c.to_node;line.append(title);svg.append(line);});return svg;
    }
    renderRollouts(c){const panel=document.getElementById("player-rollouts");if(!panel)return;panel.replaceChildren(el("h3","",D.byId.get(c.to_node)?.name||c.to_node));
      for(const [name,vector] of [["Immediate",c.immediate_vector],["Lookahead",c.lookahead_vector],["Final",c.final_vector]])panel.append(el("div","vector-comparison",name+": "+(vector?vector.map(v=>v.toFixed(3)).join(" / "):"not used")));
      if(c.rollouts){panel.append(el("p","tiny muted","First "+c.rollouts.samples.length+" of "+c.rollouts.count+" simulated rollouts; normalized discounted returns."));c.rollouts.samples.forEach((sample,i)=>{const card=el("div","rollout-card");card.append(el("strong","","Sample "+(i+1)),el("p","",sample.nodes.map(n=>D.byId.get(n)?.name||n).join(" → ")),el("code","",sample.return_vector.map(v=>v.toFixed(3)).join(" / ")));panel.append(card);});}else panel.append(el("p","tiny muted","Lookahead is disabled for this run."));panel.scrollIntoView({block:"nearest",behavior:"smooth"});
    }
    async reveal(){if(!this.trace)return;if(this.revealed){this.revealed=false;document.getElementById("player-reveal").textContent="Reveal answer";this.renderGraph();this.renderAnswer();return;}
      const serial=this.serial;const button=document.getElementById("player-reveal");button.textContent="Loading answer…";
      try{await loadScript("data/online_boutique/gold.js",()=>Boolean(window.VIZ_GOLD));if(serial!==this.serial)return;if(!window.VIZ_GOLD[this.trace.query_id])throw new Error("No DEV answer exists for this query.");this.revealed=true;button.textContent="Hide answer";this.renderGraph();this.renderAnswer();}catch(error){button.textContent="Reveal answer";document.getElementById("player-status").textContent=error.message;}}
    renderAnswer(){const card=document.getElementById("player-answer"),footer=document.getElementById("player-metrics");card.hidden=!this.revealed;footer.hidden=!this.revealed;card.replaceChildren();footer.replaceChildren();if(!this.revealed)return;
      const gold=window.VIZ_GOLD[this.trace.query_id],result=L.answer(this.trace,this.state,gold);
      card.append(el("div","eyebrow","ANSWER · AT THIS STEP"),el("strong","",result.nodes+" nodes collected · Hit "+(result.hit?"yes":"no")));
      result.targets.forEach(t=>card.append(el("p","",(D.byId.get(t.id)?.name||t.id)+": "+(t.found?"found at round/layer "+t.event.round+", position "+t.event.position:"not collected yet"))));
      const metric=window.VIZ_RESULTS?.rows.find(r=>r.query_id===this.trace.query_id&&r.method===this.trace.method&&r.budget===this.trace.node_budget);
      footer.textContent="Final run · hit "+((metric?.hit??this.entry.hit)?"yes":"no")+" · recall "+(100*(metric?.gold_recall??result.finalRecall)).toFixed(0)+"% · "+(metric?.nodes_returned??this.trace.final.visited_order.length)+" nodes · latency "+(metric?metric.latency_s.toFixed(3)+" s":"not recorded");
      ["hit","gold_recall","nodes_returned","latency_s"].forEach(k=>footer.append(window.GlossaryUI.help(k)));
    }
  }
  // Share the existing local-script loader without changing player loading.
  window.TraceData={loadScript,async load(queryId,method,budget){
    await loadScript("data/online_boutique/traces_index.js",()=>Array.isArray(window.VIZ_TRACE_INDEX));
    const entry=window.VIZ_TRACE_INDEX.find(r=>r.query_id===queryId&&r.method===method&&r.budget===Number(budget));
    if(!entry)throw new Error("No stored trace for "+queryId+", "+method+", budget "+budget+".");
    const id=entry.path.split("/").pop().replace(/\.json$/,"");
    if(!/^[a-zA-Z0-9_-]+$/.test(id))throw new Error("Invalid trace filename in local index.");
    await loadScript("data/online_boutique/traces_js/"+id+".js",()=>Boolean(window.VIZ_TRACES&&window.VIZ_TRACES[id]));return window.VIZ_TRACES[id];
  }};
  window.TraversalPlayer=TraversalPlayer;
})();
