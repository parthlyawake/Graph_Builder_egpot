(function(root,factory){
  const logic=factory(typeof module==="object"&&module.exports?require("./results_logic.js"):root.ResultsLogic);
  if(typeof module==="object"&&module.exports)module.exports=logic;else root.ExplainerLogic=logic;
})(typeof window==="object"?window:globalThis,function(R){
  "use strict";
  const scoreKeys=["score_relevance","score_hop","score_contract","score_entropy"];
  const baselineMethods=["vector_topk","bfs","greedy_walk"];
  function firstRound(trace){const round=trace.steps.find(s=>s.kind==="egpot_round");if(!round)throw new Error("No beam round in this trace.");return round;}
  function route(graph,start,question=""){
    const byId=new Map(graph.nodes.map(n=>[n.id,n]));
    const consumes=graph.edges.filter(e=>e.source===start&&e.relation==="CONSUMES"&&byId.get(e.target)?.type==="rpc_contract")
      .sort((a,b)=>Number(question.includes(byId.get(b.target).name))-Number(question.includes(byId.get(a.target).name))||a.target.localeCompare(b.target));
    for(const edge of consumes){const implementsEdge=graph.edges.filter(e=>e.target===edge.target&&e.relation==="IMPLEMENTS"&&byId.get(e.source)?.type==="function").sort((a,b)=>a.source.localeCompare(b.source))[0];
      if(implementsEdge)return {nodes:[byId.get(start),byId.get(edge.target),byId.get(implementsEdge.source)],edges:[edge,implementsEdge]};}
    throw new Error("No verified caller–contract–handler route in the loaded graph.");
  }
  function fourCandidates(trace,graph){
    const byId=new Map(graph.nodes.map(n=>[n.id,n])),candidates=firstRound(trace).candidates;
    const contract=candidates.find(c=>byId.get(c.to_node)?.type==="rpc_contract");
    const stub=candidates.find(c=>byId.get(c.to_node)?.type==="external_func"&&byId.get(c.to_node).name.startsWith("grpc.")&&byId.get(c.to_node).name.endsWith(byId.get(contract?.to_node)?.name||""));
    const constructor=candidates.find(c=>byId.get(c.to_node)?.type==="external_func"&&/New.*Client$/.test(byId.get(c.to_node).name));
    const chosen=[contract,stub,constructor];
    const zero=candidates.find(c=>c.immediate_vector[0]===0&&!chosen.some(x=>x?.to_node===c.to_node));
    if([...chosen,zero].some(c=>!c))throw new Error("The stored round lacks a requested candidate category.");
    return [...chosen,zero].map((candidate,i)=>({candidate,role:["RPC contract","Client call stub","Client constructor","Zero-relevance candidate"][i],node:byId.get(candidate.to_node)}));
  }
  function ties(candidates){
    const groups=new Map();candidates.forEach(c=>{const key=JSON.stringify(c.final_vector);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(c.idx);});
    const repeated=[...groups.values()].filter(g=>g.length>1);
    return {groups:repeated,tiedCandidates:repeated.reduce((n,g)=>n+g.length,0),extraDuplicates:repeated.reduce((n,g)=>n+g.length-1,0)};
  }
  function roundSizes(trace){return trace.steps.filter(s=>s.kind==="egpot_round").map(s=>({round:s.round,collected:s.collected_size_after}));}
  function stopReason(trace){return trace.steps.findLast(s=>s.kind==="stop")?.reason||"not recorded";}
  function firstRollout(trace){for(const round of trace.steps){const candidate=round.candidates?.find(c=>c.rollouts?.samples?.length);if(candidate)return {round,candidate};}return null;}
  function baselineSentence(rows,budget){
    const values=baselineMethods.map(method=>({method,s:R.summary(rows,method,budget,"indirect")})).filter(v=>v.s);
    if(!values.length)return "No indirect-query baseline results are available at this budget.";
    const best=Math.max(...values.map(v=>v.s.hit)),winners=values.filter(v=>Math.abs(v.s.hit-best)<1e-10);
    return winners.map(v=>R.labels[v.method]+" ("+v.s.hits+"/"+v.s.n+")").join(" and ")+(winners.length===1?" does best":" tie for best")+" on indirect questions among these baselines at budget "+budget+".";
  }
  function cost(rows,budget){return {plain:R.summary(rows,"egpot_full",budget),mcts:R.summary(rows,"egpot_full_mcts",budget)};}
  function switches(rows,budget){
    const base=R.summary(rows,"egpot_full",budget);
    return ["egpot_no_pareto","egpot_no_entropy","egpot_no_contracts","egpot_no_choke_point","egpot_full_mcts"].map(method=>({method,base,value:R.summary(rows,method,budget),delta:R.delta(base,R.summary(rows,method,budget))}));
  }
  function findings(rows,budgets){
    const sentences=[];
    for(const budget of budgets){
      for(const full of ["egpot_full","egpot_full_mcts"]){const base=R.summary(rows,full,budget);if(!base)continue;
        const matching=Object.keys(R.labels).filter(m=>m!==full&&!m.startsWith("egpot_full")).map(method=>({method,s:R.summary(rows,method,budget)})).filter(v=>v.s&&v.s.hit>=base.hit);
        sentences.push("Budget "+budget+": "+R.labels[full]+" hits "+base.hits+"/"+base.n+". "+(matching.length?matching.map(v=>R.labels[v.method]+" "+(v.s.hit>base.hit?"beats":"matches")+" it ("+v.s.hits+"/"+v.s.n+")").join("; ")+".":"No listed baseline or ablation matches its hit count."));
      }
      for(const row of R.ablations(rows,budget).filter(r=>["egpot_no_contracts","egpot_no_choke_point"].includes(r.method))){if(row.delta)sentences.push(row.sentence);}
      const c=cost(rows,budget);if(c.plain&&c.mcts)sentences.push("Budget "+budget+": MCTS mean latency is "+c.mcts.latency_s.toFixed(3)+" s versus "+c.plain.latency_s.toFixed(3)+" s without lookahead; mean nodes returned are "+c.mcts.nodes_returned.toFixed(1)+" versus "+c.plain.nodes_returned.toFixed(1)+".");
    }return sentences;
  }
  return {scoreKeys,baselineMethods,firstRound,route,fourCandidates,ties,roundSizes,stopReason,firstRollout,baselineSentence,cost,switches,findings};
});
