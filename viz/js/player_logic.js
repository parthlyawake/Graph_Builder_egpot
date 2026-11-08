(function (root, factory) {
  "use strict";
  const logic = factory();
  if (typeof module === "object" && module.exports) module.exports = logic;
  else root.PlayerLogic = logic;
})(typeof window === "object" ? window : globalThis, function () {
  "use strict";
  const mean = vector => vector.reduce((sum, value) => sum + value, 0) / vector.length;
  const sortCandidates = rows => [...rows].sort((a,b) => a.front_index - b.front_index || mean(b.final_vector)-mean(a.final_vector) || String(a.to_node).localeCompare(String(b.to_node)) || a.idx-b.idx);
  function stepState(trace, index) {
    const collected = new Set([trace.start_node]), seen = new Set([trace.start_node]);
    const end = Math.max(0, Math.min(index, trace.steps.length-1));
    for (let i=0;i<=end;i++) {
      const step=trace.steps[i];
      if(step.kind==="egpot_round") {
        (step.beam_before||[]).forEach(s=>s.nodes.forEach(n=>seen.add(n)));
        step.candidates.forEach(c=>{seen.add(c.from_node);seen.add(c.to_node);});
        step.new_nodes.forEach(n=>{collected.add(n);seen.add(n);});
      } else if(step.kind==="bfs_layer") {
        step.frontier.forEach(n=>seen.add(n));step.added.forEach(n=>{seen.add(n);collected.add(n);});
      } else if(step.kind==="greedy_step") {
        seen.add(step.from);step.options.forEach(o=>seen.add(o.to));
        if(step.chosen){seen.add(step.chosen);collected.add(step.chosen);}
      } else if(step.kind==="vector_rank") {
        step.ranking.forEach(r=>{seen.add(r.node);collected.add(r.node);});
      }
    }
    const current=trace.steps[end];
    const candidates=current.kind==="egpot_round"?current.candidates:[];
    const selected=candidates.filter(c=>c.selected).map(c=>c.to_node);
    if(current.kind==="greedy_step"&&current.chosen)selected.push(current.chosen);
    if(current.kind==="bfs_layer")selected.push(...current.added);
    if(current.kind==="vector_rank")selected.push(...current.ranking.map(r=>r.node));
    return {index:end,current,collected:[...collected],seen:[...seen],candidates,selected:[...new Set(selected)],stopReason:current.kind==="stop"?current.reason:null};
  }
  function subgraph(trace, graph) {
    const ids=new Set([trace.start_node,...trace.final.visited_order,...trace.final.ordered_path]);
    trace.final.edges.forEach(e=>{ids.add(e[0]);ids.add(e[2]);});
    trace.steps.forEach(s=>{
      (s.beam_before||[]).forEach(b=>b.nodes.forEach(n=>ids.add(n)));
      (s.candidates||[]).forEach(c=>{ids.add(c.from_node);ids.add(c.to_node);});
      (s.frontier||[]).forEach(n=>ids.add(n));(s.added||[]).forEach(n=>ids.add(n));
      (s.options||[]).forEach(o=>ids.add(o.to));if(s.from)ids.add(s.from);if(s.chosen)ids.add(s.chosen);
      (s.ranking||[]).forEach(r=>ids.add(r.node));
    });
    return {nodes:graph.nodes.filter(n=>ids.has(n.id)),edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
  }
  function caption(step) {
    if(step.kind==="egpot_round") {
      const front=step.candidates.filter(c=>c.front_index===0), picks=step.selected.length;
      const best=sortCandidates(front)[0];
      const raw=best?best.immediate_vector.map(v=>v.toFixed(2)):[];
      return `Round ${step.round}: ${step.candidates_total} neighbors considered. ${front.length} stored candidates on front 0${best?`; ${best.to_node} (immediate: relevance ${raw[0]}, hop ${raw[1]}, contract ${raw[2]}, entropy ${raw[3]})${best.lookahead_vector?`; lookahead-adjusted score ${mean(best.final_vector).toFixed(2)}`:""}`:""}. Beam picks ${picks}.${step.candidates_truncated?` ${step.candidates_truncated} candidates omitted from the stored display.`:""}`;
    }
    if(step.kind==="bfs_layer")return `Layer ${step.layer}: ${step.frontier.length} frontier nodes; ${step.added.length} nodes added.`;
    if(step.kind==="greedy_step")return `${step.options.length} stored options from ${step.from}. ${step.chosen?`Chose ${step.chosen}.`:"No unvisited neighbor remains."}`;
    if(step.kind==="vector_rank")return `Ranked ${step.ranking.length} selected nodes by relevance, including the budget-counted start node.`;
    return `Stopped: ${step.reason.replaceAll("_"," ")}.`;
  }
  function discoveries(trace) {
    const found=new Map([[trace.start_node,{position:1,round:0,index:-1}]]);
    trace.steps.forEach((s,index)=>{
      if(s.kind==="vector_rank"){
        s.ranking.forEach((r,i)=>found.set(r.node,{position:i+1,round:1,index}));return;
      }
      const added=s.new_nodes||s.added||(s.chosen?[s.chosen]:[]);
      added.forEach(n=>{if(!found.has(n))found.set(n,{position:found.size+1,round:s.round??s.layer??index+1,index});});
    });
    return found;
  }
  function answer(trace,state,gold) {
    const events=discoveries(trace),visited=new Set(state.collected);
    return {nodes:state.collected.length,hit:gold.gold_nodes.every(n=>visited.has(n)),
      targets:gold.gold_nodes.map(id=>({id,found:visited.has(id),event:visited.has(id)?events.get(id):null})),
      finalRecall:gold.gold_nodes.filter(n=>trace.final.visited_order.includes(n)).length/gold.gold_nodes.length};
  }
  return {mean,sortCandidates,stepState,subgraph,caption,discoveries,answer};
});
