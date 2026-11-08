(function(root,factory){if(typeof module==="object"&&module.exports)module.exports=factory(require("./results_logic.js"));else root.FinalTestLogic=factory(root.ResultsLogic);})(typeof window==="object"?window:globalThis,function(R){
  "use strict";
  const baselines=["vector_topk","bfs","greedy_walk","vector_bfs_k2","ppr","scalar_beam","community_graphrag","mcts_standard"];
  const labels={...R.labels,egpot_full:"EG-POT (full)",egpot_full_mcts:"EG-POT + MCTS"};
  const mean=values=>values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
  const fmt=value=>value===null||value===undefined?"not recorded":Number(value.toFixed(2)).toString();
  function stats(data,method,budget,split="test"){
    const rows=data.rows.filter(r=>r.method===method&&r.node_budget===budget&&r.split===split);
    if(!rows.length)return null;
    const hits=rows.filter(r=>r.hit),out={method,budget,split,n:rows.length,hits:hits.length,hit_rate:hits.length/rows.length};
    for(const key of ["gold_recall","nodes_returned","path_coverage","precision","latency_s"])out[key]=mean(rows.map(r=>r[key]));
    out.nodes_to_hit=mean(hits.map(r=>r.nodes_to_hit));out.precision_at_hit=mean(hits.map(r=>r.precision_at_hit));return out;
  }
  const budgets=data=>[...new Set(data.rows.map(r=>r.node_budget))].sort((a,b)=>a-b);
  const methods=data=>R.methodNames(data.rows);
  const hitText=s=>s?s.hits+"/"+s.n:"not recorded";
  function bestBaseline(data,budget,split="test",efficiency=false){
    const values=baselines.map(m=>stats(data,m,budget,split)).filter(Boolean).filter(s=>!efficiency||(s.hit_rate>=.9&&s.nodes_to_hit!==null));
    return values.sort((a,b)=>(efficiency?0:b.hits-a.hits)||(a.nodes_to_hit??Infinity)-(b.nodes_to_hit??Infinity)||a.method.localeCompare(b.method))[0]||null;
  }
  function componentVerdict(dev,test){
    if(dev>=2&&test>=2)return "Supported";
    if(dev>=2||test>=2||Math.max(dev,test)===1)return "Inconclusive";
    return "Not supported";
  }
  function mctsVerdict(dev,test){
    if(dev>=2&&test>=2)return "Supported";
    if(Math.sign(dev)!==Math.sign(test))return "Inconclusive (sign differs between splits)";
    if(dev<=0&&test<=0)return "Not supported";
    return "Inconclusive";
  }
  function ratioVerdict(devFull,devBaseline,testFull,testBaseline){
    const qualifies=(full,base)=>full!==null&&base!==null&&full<=.6*base;
    const a=qualifies(devFull,devBaseline),b=qualifies(testFull,testBaseline);
    return a&&b?"Supported":a||b?"Inconclusive":"Not supported";
  }
  const smallVerdict=(dev,test)=>dev>=3&&test>=3?"Supported":dev>=3||test>=3?"Inconclusive":"Not supported";
  const signed=n=>(n>0?"+":"")+fmt(n);
  function scorecard(data){
    const result=[],base={dev:stats(data,"egpot_full",20,"dev"),test:stats(data,"egpot_full",20)};
    const rule="At budget 20: Supported if full minus ablation is at least 2 hits on BOTH splits; Inconclusive if only one reaches 2, or the largest delta is 1; Not supported otherwise.";
    for(const [id,title,key] of [["contracts","The contract score helps","egpot_no_contracts"],["choke","The choke-point rule helps","egpot_no_choke_point"],["entropy","The entropy score helps","egpot_no_entropy"],["pareto","Pareto selection beats an equal-weight sum","egpot_no_pareto"]]){
      const dev=stats(data,key,20,"dev"),test=stats(data,key,20),a=base.dev.hits-dev.hits,b=base.test.hits-test.hits;
      result.push({id,title,keys:["egpot_full",key],dev:`${hitText(base.dev)} vs ${hitText(dev)} (delta ${signed(a)})`,test:`${hitText(base.test)} vs ${hitText(test)} (delta ${signed(b)})`,dev_delta:a,test_delta:b,verdict:componentVerdict(a,b),rule});
    }
    const md=stats(data,"egpot_full_mcts",20,"dev"),mt=stats(data,"egpot_full_mcts",20),a=md.hits-base.dev.hits,b=mt.hits-base.test.hits;
    result.push({id:"mcts",title:"MCTS lookahead helps",keys:["egpot_full_mcts"],dev:`${hitText(base.dev)} to ${hitText(md)} (delta ${signed(a)})`,test:`${hitText(base.test)} to ${hitText(mt)} (delta ${signed(b)})`,verdict:mctsVerdict(a,b),rule:"At budget 20: MCTS minus full. Supported if at least 2 on BOTH; Inconclusive (sign differs between splits) if the signs differ (treating zero as its own sign); Not supported if both are <= 0; otherwise Inconclusive. Rules are applied in that order."});
    const ed=stats(data,"egpot_full",40,"dev"),et=stats(data,"egpot_full",40),bd=bestBaseline(data,40,"dev",true),bt=bestBaseline(data,40,"test",true);
    result.push({id:"efficiency",title:"EG-POT needs fewer nodes than the best baseline",keys:["egpot_full","nodes_to_hit"],dev:`${fmt(ed.nodes_to_hit)} (${hitText(ed)} hits) vs ${bd?labels[bd.method]+" "+fmt(bd.nodes_to_hit)+" ("+hitText(bd)+" hits)":"no qualifying baseline"}`,test:`${fmt(et.nodes_to_hit)} (${hitText(et)} hits) vs ${bt?labels[bt.method]+" "+fmt(bt.nodes_to_hit)+" ("+hitText(bt)+" hits)":"no qualifying baseline"}`,verdict:ratioVerdict(ed.nodes_to_hit,bd?.nodes_to_hit??null,et.nodes_to_hit,bt?.nodes_to_hit??null),rule:"At budget 40, among the eight baselines reaching >=90% hits on each split, use the lowest mean nodes-to-hit. Supported if EG-POT uses <=60% of that mean on BOTH splits; Inconclusive on one; Not supported otherwise. Means exclude misses."});
    const sd=stats(data,"egpot_full",10,"dev"),st=stats(data,"egpot_full",10),sb=bestBaseline(data,10,"dev"),sc=bestBaseline(data,10);
    result.push({id:"small",title:"EG-POT beats the best baseline at a small budget (10)",keys:["egpot_full","budget"],dev:`${hitText(sd)} vs ${labels[sb.method]} ${hitText(sb)} (delta ${signed(sd.hits-sb.hits)})`,test:`${hitText(st)} vs ${labels[sc.method]} ${hitText(sc)} (delta ${signed(st.hits-sc.hits)})`,verdict:smallVerdict(sd.hits-sb.hits,st.hits-sc.hits),rule:"At budget 10, full minus the best of the eight baselines. Supported if at least 3 extra hits on BOTH splits; Inconclusive on one; Not supported otherwise."});
    return result;
  }
  function comparison(data){return budgets(data).flatMap(b=>methods(data).map(method=>{const dev=stats(data,method,b,"dev"),test=stats(data,method,b);return {method,budget:b,dev,test,delta:100*(test.hit_rate-dev.hit_rate)};}));}
  function thresholds(data){return baselines.filter(m=>data.rows.some(r=>r.method===m)).map(method=>({method,budget:budgets(data).find(b=>stats(data,method,b)?.hit_rate>=.9)??null}));}
  function weightCounts(data,split="test",budget=20){
    const rows=data.weights.filter(r=>r.experiment==="weights"&&r.split===split&&r.node_budget===budget);
    if(!rows.length)return null;
    const grouped=new Map();for(const r of rows)grouped.set(r.method,(grouped.get(r.method)||0)+r.hit);
    const reference=stats(data,"egpot_full",budget,split),all=[...grouped].map(([id,hits])=>({id,hits})),study=all.filter(r=>r.id!=="equal");
    return {all,study,count:study.length,reference:reference.hits,n:reference.n,below:study.filter(r=>r.hits<reference.hits).length,equal:study.filter(r=>r.hits===reference.hits).length,above:study.filter(r=>r.hits>reference.hits).length};
  }
  function devWeightCounts(data,extra,budget){
    if(!extra||extra.meta?.split!=="dev")return null;
    const expected=data.provenance?.configs?.protocol?.weight_vectors,records=extra.weights?.filter(r=>Array.isArray(r.weights)),reference=stats(data,"egpot_full",budget,"dev"),saved=extra.weights?.find(r=>r.id==="pareto_reference");
    if(!expected||!records||!reference||records.length!==Object.keys(expected).length||extra.meta.n_queries!==reference.n||saved?.["hit_b"+budget]!==reference.hits)return null;
    const ids=new Set(records.map(r=>r.id));if(ids.size!==records.length||Object.keys(expected).some(id=>!ids.has(id)))return null;
    if(records.some(r=>r.weights.length!==expected[r.id]?.length||r.weights.some((v,i)=>Math.abs(v-expected[r.id][i])>1e-12)||!Number.isFinite(r["hit_b"+budget])))return null;
    const study=records.filter(r=>r.id!=="equal"),hits=study.map(r=>r["hit_b"+budget]);
    return {count:study.length,below:hits.filter(h=>h<reference.hits).length,equal:hits.filter(h=>h===reference.hits).length,above:hits.filter(h=>h>reference.hits).length,source:"dev run"};
  }
  function findings(data,devExtra=null){
    const out=[],add=(text,keys)=>out.push({text,keys});
    for(const b of budgets(data).filter(b=>b===10||b===20)){
      const full=stats(data,"egpot_full",b),other=bestBaseline(data,b);
      add(`At a budget of ${b} nodes, ${labels.egpot_full} found all the answer nodes for ${hitText(full)} test questions, returning ${fmt(full.nodes_returned)} nodes on average. The best other method at that budget was ${labels[other.method]} with ${hitText(other)}.`,["budget","egpot_full",other.method,"hit","nodes_returned"]);
    }
    const full=stats(data,"egpot_full",40),best=bestBaseline(data,40);
    add(`When ${labels.egpot_full} succeeds, it has found the last answer node after ${fmt(full.nodes_to_hit)} nodes on average. ${labels[best.method]} needs ${fmt(best.nodes_to_hit)} (${fmt(best.nodes_to_hit/full.nodes_to_hit)}x as many) and reaches ${hitText(best)} at budget ${best.budget}. Averages count only the questions each method answered correctly, so they cover different sets of questions.`,["egpot_full",best.method,"nodes_to_hit","hit","budget"]);
    const cards=scorecard(data);
    for(const [id,component,key] of [["contracts","the contract score","egpot_no_contracts"],["choke","the choke-point rule","egpot_no_choke_point"],["entropy","the entropy score","egpot_no_entropy"]]){
      const test=stats(data,"egpot_full",20),off=stats(data,key,20),dev=stats(data,"egpot_full",20,"dev"),doff=stats(data,key,20,"dev"),card=cards.find(c=>c.id===id);
      const change=test.hits===off.hits?`leaves EG-POT's test hits unchanged at ${hitText(test)}`:`changes EG-POT's test hits from ${hitText(test)} to ${hitText(off)}`,devChange=dev.hits===doff.hits?`unchanged at ${hitText(dev)}`:`${hitText(dev)} to ${hitText(doff)}`;
      add(`Switching off ${component} ${change} at budget ${test.budget} (dev: ${devChange}) — ${card.verdict==="Inconclusive"?"the effect differs between dev and test":"consistent on both splits"}.`,[key,"egpot_full","hit","budget"]);
    }
    const equal=stats(data,"egpot_no_pareto",20),pareto=stats(data,"egpot_full",20),w=weightCounts(data),dw=weightCounts(data,"dev")||devWeightCounts(data,devExtra,pareto.budget),emphasis=w.study.filter(r=>r.id.startsWith("emphasis_")).length,draws=w.study.filter(r=>r.id.startsWith("dirichlet_")).length;
    add(`Equal weights scored ${hitText(equal)} against Pareto's ${hitText(pareto)}. Across ${w.count} alternative weightings (${emphasis} single-objective emphasis vectors and ${draws} random draws) at budget ${pareto.budget}, ${w.below} did worse than Pareto, ${w.equal} tied, ${w.above} did better ${dw?`(dev run: ${dw.below} worse, ${dw.equal} tied, ${dw.above} better)`:"(dev: not recorded in the locked JSON)"}. The study pool is ${emphasis} emphasis vectors plus ${draws} Dirichlet draws; equal weights are a separate control.`,["egpot_no_pareto","pareto_front","weighting","budget"]);
    const on=stats(data,"egpot_full_mcts",20),d=stats(data,"egpot_full",20,"dev"),dm=stats(data,"egpot_full_mcts",20,"dev"),seedRows=data.seeds.filter(r=>r.method==="egpot_full_mcts"&&r.node_budget===20),groups=new Map();seedRows.forEach(r=>groups.set(r.seed,(groups.get(r.seed)||0)+r.hit));
    add(`Adding the lookahead (MCTS) changed EG-POT's test hits from ${pareto.hits} to ${on.hits} at budget ${on.budget} (dev: ${d.hits} to ${dm.hits}). Across ${groups.size} random seeds it scored between ${Math.min(...groups.values())} and ${Math.max(...groups.values())}.`,["egpot_full_mcts","seed","hit","budget"]);
    const ts=thresholds(data),never=ts.filter(r=>r.budget===null),reached=ts.filter(r=>r.budget!==null),maxBudget=Math.max(...budgets(data));
    add(reached.map(r=>`${labels[r.method]} first reaches 90% hits at a budget of ${r.budget}`).join("; ")+`; ${never.map(r=>labels[r.method]).join(", ")} ${never.length?"never reach it":"are not below it"} within ${maxBudget}.`,[...baselines,"hit","budget"]);
    const ft=stats(data,"egpot_full",20),fd=stats(data,"egpot_full",20,"dev"),change=comparison(data).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta)||a.method.localeCompare(b.method)||a.budget-b.budget)[0];
    add(`Comparing dev with test for ${labels.egpot_full}, hits went from ${hitText(fd)} to ${hitText(ft)} at budget ${ft.budget}: ${ft.hit_rate>fd.hit_rate?"did better":ft.hit_rate<fd.hit_rate?"did worse":"did the same"} by hit rate. The largest dev-to-test change across all methods and measured budgets was ${labels[change.method]} at budget ${change.budget}: ${signed(change.delta)} percentage points (${hitText(change.dev)} to ${hitText(change.test)}).`,["egpot_full",change.method,"hit","budget"]);
    return out;
  }
  function caveat(data){const rows=data.rows.filter(r=>r.split==="test"),n=new Set(rows.map(r=>r.id)).size,l=data.provenance.split_links.test.length;return `${n} queries from ${l} links in one repository, written by the project team; differences of one query are not meaningful. All graph-based baselines use the same choke-point rule, so they benefit from it too. The test split has now been used once; further changes to the method should be validated on new repositories, not by re-running it. Step-by-step traces were not exported for the test queries.`;}
  return {baselines,labels,fmt,stats,budgets,methods,hitText,bestBaseline,componentVerdict,mctsVerdict,ratioVerdict,smallVerdict,scorecard,comparison,thresholds,weightCounts,devWeightCounts,findings,caveat};
});
