(function(root,factory){const logic=factory();if(typeof module==="object"&&module.exports)module.exports=logic;else root.ResultsLogic=logic;})(typeof window==="object"?window:globalThis,function(){
  "use strict";
  const labels={egpot_full:"EG-POT full",egpot_full_mcts:"EG-POT full + MCTS",egpot_no_pareto:"Equal weighted sum",egpot_no_pareto_mcts:"Equal weighted sum + MCTS",egpot_no_entropy:"No entropy",egpot_no_entropy_mcts:"No entropy + MCTS",egpot_no_contracts:"No contracts",egpot_no_contracts_mcts:"No contracts + MCTS",egpot_no_choke_point:"No choke-point rule",egpot_no_choke_point_mcts:"No choke-point rule + MCTS",vector_topk:"Vector top-K",bfs:"Breadth-first search",greedy_walk:"Greedy relevance walk"};
  const lower=new Set(["nodes_returned","nodes_to_hit","latency_s"]);
  Object.assign(labels,{vector_bfs_k2:"Vector + BFS (2 hops)",vector_bfs_k3:"Vector + BFS (3 hops)",vector_bfs_k4:"Vector + BFS (4 hops)",vector_bfs_k5:"Vector + BFS (5 hops)",ppr:"Personalized PageRank",scalar_beam:"Beam search (one score)",community_graphrag:"Community GraphRAG (text only)",mcts_standard:"Standard MCTS"});
  for(const method of ["bfs","vector_bfs_k2","ppr","scalar_beam","mcts_standard","greedy_walk"])labels[method+"_no_choke"]=labels[method]+" without the choke-point rule";
  const mean=xs=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null;
  function aggregate(rows){
    if(!rows.length)return null;
    const hits=rows.filter(r=>r.hit===1),out={n:rows.length,hits:hits.length};
    for(const key of ["hit","gold_recall","precision","path_coverage","ordered_path_match","nodes_returned","latency_s"])out[key]=mean(rows.map(r=>r[key]));
    out.nodes_to_hit=mean(hits.map(r=>r.nodes_to_hit).filter(n=>n!==null));return out;
  }
  function select(rows,{method,budget,type="all"}={}){return rows.filter(r=>(!method||r.method===method)&&(!budget||r.budget===Number(budget))&&(type==="all"||r.type===type));}
  function summary(rows,method,budget,type="all"){return aggregate(select(rows,{method,budget,type}));}
  function delta(full,ablated){if(!full||!ablated)return null;const d={hit:ablated.hits-full.hits,n:full.n};for(const key of ["gold_recall","nodes_returned","nodes_to_hit"])d[key]=full[key]===null||ablated[key]===null?null:ablated[key]-full[key];return d;}
  function bestPerColumn(entries,metric){const valid=entries.filter(e=>e.value!==null&&Number.isFinite(e.value));if(!valid.length)return [];const best=(lower.has(metric)?Math.min:Math.max)(...valid.map(e=>e.value));return valid.filter(e=>Math.abs(e.value-best)<1e-10).map(e=>e.method);}
  function sentence(component,d,budget,mcts){if(!d)return `No paired data for ${component} at budget ${budget}.`;const count=Math.abs(d.hit),unit=count===1?"query":"queries",effect=d.hit<0?`loses ${count} ${unit}`:d.hit>0?`helps: gains ${count} ${unit}`:"leaves the hit count unchanged (0 queries)";return `Removing ${component} ${effect} at budget ${budget} (${mcts?"MCTS":"no MCTS"}; ${d.n} queries)${Math.abs(d.hit)<=1?"; within 1 query (not meaningful)":""}.`;}
  function ablations(rows,budget,type="all"){
    const components={pareto:"Pareto selection",entropy:"entropy",contracts:"contract consistency",choke_point:"the choke-point rule"},out=[];
    for(const mcts of [false,true])for(const [key,component] of Object.entries(components)){
      const method="egpot_no_"+key+(mcts?"_mcts":""),base="egpot_full"+(mcts?"_mcts":"");
      const full=summary(rows,base,budget,type),ablated=summary(rows,method,budget,type),d=delta(full,ablated);
      out.push({method,component,mcts,full,ablated,delta:d,sentence:sentence(component,d,budget,mcts)});
    }return out;
  }
  function notWins(rows,budget,type="all"){
    const base=summary(rows,"egpot_full",budget,type);if(!base)return [];
    const out=[];for(const method of Object.keys(labels)){if(method==="egpot_full"||method==="egpot_full_mcts")continue;const value=summary(rows,method,budget,type);if(!value)continue;
      for(const metric of ["hit","gold_recall","path_coverage","nodes_returned","nodes_to_hit","latency_s"]){if(base[metric]===null||value[metric]===null)continue;if(metric==="nodes_to_hit"&&value.hits<base.hits)continue;const better=lower.has(metric)?value[metric]<base[metric]-1e-10:value[metric]>base[metric]+1e-10;if(better)out.push({method,metric,value:value[metric],baseline:base[metric],n:value.n,hits:value.hits,baseHits:base.hits,baseN:base.n});}
    }const order=["hit","gold_recall","path_coverage","nodes_returned","nodes_to_hit","latency_s"];return out.sort((a,b)=>order.indexOf(a.metric)-order.indexOf(b.metric)||a.method.localeCompare(b.method));
  }
  function hitSuffix(entry){return "("+(entry.hits<entry.baseHits?"but ":"")+"hit rate "+entry.hits+"/"+entry.n+" vs "+entry.baseHits+"/"+entry.baseN+")";}
  function format(s,metric){if(!s||s[metric]===null)return "—";const value=s[metric];if(["hit","gold_recall","path_coverage"].includes(metric))return (100*value).toFixed(1)+"% · "+(metric==="hit"?"":"hits ")+s.hits+"/"+s.n;return value.toFixed(metric==="latency_s"?3:1)+(metric==="latency_s"?" s":metric==="nodes_to_hit"?" · "+s.hits+"/"+s.n+" hits":"");}
  function mergeRows(...sources){const result=new Map();for(const rows of sources)for(const row of rows||[]){const key=JSON.stringify([row.query_id,row.method,row.budget]);if(!result.has(key))result.set(key,row);}return [...result.values()].sort((a,b)=>a.query_id.localeCompare(b.query_id)||a.method.localeCompare(b.method)||a.budget-b.budget);}
  function methodNames(rows){const available=new Set(rows.map(r=>r.method));return [...Object.keys(labels).filter(m=>available.has(m)),...[...available].filter(m=>!labels[m]).sort()];}
  function firstBudget(rows,method,threshold=1,type="all"){const selected=select(rows,{method,type}),budgets=[...new Set(selected.map(r=>r.budget))].sort((a,b)=>a-b);return budgets.find(b=>summary(selected,method,b).hit>=threshold)??null;}
  function nearestBudget(budgets,target){return [...new Set(budgets)].sort((a,b)=>Math.abs(a-target)-Math.abs(b-target)||a-b)[0]??null;}
  function percentile(values,p){if(!values.length)return null;if(p<0||p>100)throw new Error("Percentile must be within zero and one hundred.");const sorted=[...values].sort((a,b)=>a-b),index=(sorted.length-1)*p/100,lo=Math.floor(index),hi=Math.ceil(index);return sorted[lo]+(sorted[hi]-sorted[lo])*(index-lo);}
  function weightSummary(records){const reference=records.find(r=>r.id==="pareto_reference"),all=records.filter(r=>Array.isArray(r.weights)),study=all.filter(r=>r.id!=="equal");if(!reference||!study.length)return null;const hits=study.map(r=>r.hit_b20),pareto=reference.hit_b20;return {reference,all,study,count:study.length,beat:hits.filter(h=>h>pareto).length,tie:hits.filter(h=>h===pareto).length,lose:hits.filter(h=>h<pareto).length,equal:all.find(r=>r.id==="equal"),q25:percentile(hits,25),median:percentile(hits,50),q75:percentile(hits,75),explicitIdentical:new Set(all.map(r=>r.explicit_hit_b20)).size===1&&all.every(r=>r.hit_b20===r.explicit_hit_b20+r.indirect_hit_b20)};}
  function weightSentence(records){const s=weightSummary(records);return s?`${s.beat} of ${s.count} random weightings beat Pareto, ${s.tie} tie, ${s.lose} do worse`:"No weight distribution was exported.";}
  function seedSummaries(seeds,queries,type="all"){const allowed=new Set(queries.filter(q=>type==="all"||q.type===type).map(q=>q.id)),groups=new Map();for(const r of seeds){if(!allowed.has(r.query_id))continue;const key=JSON.stringify([r.method,r.budget]);if(!groups.has(key))groups.set(key,{method:r.method,budget:r.budget,seeds:new Map()});const group=groups.get(key);if(!group.seeds.has(r.seed))group.seeds.set(r.seed,[]);group.seeds.get(r.seed).push(r);}return [...groups.values()].map(g=>{const values=[...g.seeds].sort((a,b)=>a[0]-b[0]).map(([seed,rows])=>({seed,n:rows.length,hits:rows.reduce((a,r)=>a+r.hit,0),nodes:mean(rows.map(r=>r.nodes_returned))}));return {...g,seeds:values,mean:mean(values.map(r=>r.hits)),min:Math.min(...values.map(r=>r.hits)),max:Math.max(...values.map(r=>r.hits))};}).sort((a,b)=>a.method.localeCompare(b.method)||a.budget-b.budget);}
  return {labels,lower,mean,aggregate,select,summary,delta,bestPerColumn,sentence,ablations,notWins,hitSuffix,format,mergeRows,methodNames,firstBudget,nearestBudget,percentile,weightSummary,weightSentence,seedSummaries};
});
