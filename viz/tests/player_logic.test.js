"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const L=require("../js/player_logic.js");
const root=path.join(__dirname,"../data/online_boutique");
const trace=JSON.parse(fs.readFileSync(path.join(root,"traces/ob01_explicit__egpot_full__b20.json"),"utf8"));
let previous=new Set([trace.start_node]);
trace.steps.forEach((step,i)=>{
  const state=L.stepState(trace,i),collected=new Set(state.collected);
  for(const n of previous)assert.ok(collected.has(n));
  assert.ok(collected.size<=trace.node_budget);
  if(step.kind==="egpot_round"){
    assert.ok(state.selected.every(n=>state.candidates.some(c=>c.to_node===n)));
    assert.ok(L.caption(step).includes(`${step.candidates_total} neighbors considered`));
    assert.ok(L.caption(step).includes(`Beam picks ${step.selected.length}`));
  }
  previous=collected;
});
assert.deepEqual([...previous],trace.final.visited_order);
const rows=[{idx:0,to_node:"z",front_index:1,final_vector:[1,1,1,1]},
 {idx:1,to_node:"b",front_index:0,final_vector:[.1,.1,.1,.1]},
 {idx:2,to_node:"a",front_index:0,final_vector:[.9,.9,.9,.9]}];
assert.deepEqual(L.sortCandidates(rows).map(c=>c.idx),[2,1,0]);
const ids=[trace.start_node,...trace.final.visited_order,"not relevant"];
const graph={nodes:ids.map(id=>({id})),edges:[{source:ids[0],target:ids[1]},{source:ids[0],target:"not relevant"}]};
const sub=L.subgraph(trace,graph);
assert.ok(sub.nodes.some(n=>n.id===trace.start_node));
assert.ok(trace.final.visited_order.every(id=>sub.nodes.some(n=>n.id===id)));
assert.ok(!sub.nodes.some(n=>n.id==="not relevant"));
assert.equal(sub.edges.length,1);
const gold={gold_nodes:[trace.final.visited_order[1]],gold_path:trace.final.ordered_path};
const rawCandidate={idx:0,to_node:"known",front_index:0,immediate_vector:[.84,.80,1,0],lookahead_vector:[0,0,0,0],final_vector:[.42,.40,.5,0]};
const caption=L.caption({kind:"egpot_round",round:1,candidates_total:1,candidates:[rawCandidate],selected:[0],candidates_truncated:0});
assert.ok(caption.includes("relevance 0.84, hop 0.80, contract 1.00, entropy 0.00"));
assert.ok(caption.includes("lookahead-adjusted score 0.33"));
assert.equal(L.answer(trace,L.stepState(trace,trace.steps.length-1),gold).hit,true);
for(const file of fs.readdirSync(path.join(root,"traces")).filter(f=>f.endsWith(".json"))){
  const run=JSON.parse(fs.readFileSync(path.join(root,"traces",file),"utf8"));
  const state=L.stepState(run,run.steps.length-1);
  assert.deepEqual(new Set(state.collected),new Set(run.final.visited_order),file);
}
console.log("Player logic: 8 groups passed, including immediate captions and all 320 traces.");
