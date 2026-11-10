"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),L=require("../js/final_test_logic.js");
let groups=0;function check(name,fn){fn();groups++;console.log("PASS "+name);}
check("component verdicts implement all thresholds",()=>{
  assert.equal(L.componentVerdict(2,3),"Supported");assert.equal(L.componentVerdict(2,0),"Inconclusive");assert.equal(L.componentVerdict(1,-2),"Inconclusive");assert.equal(L.componentVerdict(1,1),"Inconclusive");assert.equal(L.componentVerdict(0,-1),"Not supported");
});
check("MCTS sign and support rules",()=>{
  assert.equal(L.mctsVerdict(2,2),"Supported");assert.equal(L.mctsVerdict(1,-1),"Inconclusive (sign differs between splits)");assert.equal(L.mctsVerdict(0,1),"Inconclusive (sign differs between splits)");assert.equal(L.mctsVerdict(0,0),"Not supported");assert.equal(L.mctsVerdict(1,1),"Inconclusive");
});
check("60 percent ratio and small-budget rules",()=>{
  assert.equal(L.ratioVerdict(6,10,6,10),"Supported");assert.equal(L.ratioVerdict(6,10,7,10),"Inconclusive");assert.equal(L.ratioVerdict(7,10,7,10),"Not supported");assert.equal(L.ratioVerdict(6,null,6,null),"Not supported");assert.equal(L.smallVerdict(3,4),"Supported");assert.equal(L.smallVerdict(3,2),"Inconclusive");assert.equal(L.smallVerdict(2,2),"Not supported");
});
function tiny(){
  const data={rows:[],weights:[],seeds:[],provenance:{split_links:{dev:[1,2],test:[3,4]}}};
  const methods=["egpot_full","egpot_full_mcts","egpot_no_pareto","egpot_no_pareto_mcts","egpot_no_contracts","egpot_no_entropy","egpot_no_choke_point",...L.baselines];
  for(const split of ["dev","test"])for(const b of [10,20,40])for(const method of methods){
    let hits=2;if(method==="egpot_full")hits=3;if(method.includes("no_pareto"))hits=4;if(method==="egpot_no_contracts")hits=1;if(method==="egpot_no_entropy")hits=split==="dev"?1:3;if(method==="egpot_no_choke_point")hits=3;if(method==="egpot_full_mcts")hits=split==="dev"?4:2;if(method==="scalar_beam")hits=3;if(b===40&&["ppr","mcts_standard"].includes(method))hits=4;
    for(let i=0;i<4;i++){const hit=Number(i<hits);data.rows.push({method,node_budget:b,split,id:split+i,hit,gold_recall:hit?1:.5,path_coverage:hit?1:2/3,precision:.2,nodes_returned:8,nodes_to_hit:hit?(method.startsWith("egpot")?6:method==="ppr"?12:method==="mcts_standard"?10:9):null,precision_at_hit:hit?1/3:null,latency_s:.01});}
  }
  for(const [method,hits] of [["equal",4],["emphasis_a",2],["dirichlet_a",3]])for(let i=0;i<4;i++)data.weights.push({experiment:"weights",method,split:"test",node_budget:20,hit:Number(i<hits)});
  for(const seed of [0,1])for(let i=0;i<4;i++)data.seeds.push({seed,method:"egpot_full_mcts",node_budget:20,hit:Number(i<seed+2)});
  return data;
}
const synthetic=tiny();
check("best other excludes every EG-POT variant and ablation",()=>{
  assert.equal(L.bestBaseline(synthetic,10).method,"scalar_beam");assert.equal(L.bestBaseline(synthetic,10).hits,3);assert.equal(L.bestBaseline(synthetic,40).method,"mcts_standard");assert.equal(L.bestBaseline(synthetic,40,"test",true).nodes_to_hit,10);
});
check("generated sentences use hand-computed synthetic numbers",()=>{
  const stories=L.findings(synthetic).map(r=>r.text);assert.ok(stories[0].includes("3/4 test questions, returning 8 nodes"));assert.ok(stories[0].includes("Beam search (one score) with 3/4"));assert.ok(stories[2].includes("10 (1.67x as many)"));assert.ok(stories.some(t=>t.includes("Across 2 random seeds it scored between 2 and 3")));assert.ok(stories.some(t=>t.includes("dev: not recorded")));assert.equal(L.weightCounts(synthetic).below,1);assert.equal(L.weightCounts(synthetic).equal,1);assert.equal(L.weightCounts(synthetic).count,2);
});
check("scorecard and runtime thresholds from synthetic rows",()=>{
  const c=L.scorecard(synthetic);assert.equal(c.find(r=>r.id==="contracts").verdict,"Supported");assert.equal(c.find(r=>r.id==="entropy").verdict,"Inconclusive");assert.equal(c.find(r=>r.id==="choke").verdict,"Not supported");assert.ok(c.find(r=>r.id==="mcts").verdict.includes("sign differs"));assert.equal(c.find(r=>r.id==="efficiency").verdict,"Supported");assert.equal(L.thresholds(synthetic).find(r=>r.method==="ppr").budget,40);
});
const scope={window:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../data/online_boutique/results_test.js"),"utf8"),scope);const real=JSON.parse(JSON.stringify(scope.window.VIZ_RESULTS_TEST)),saved=JSON.parse(fs.readFileSync(path.join(__dirname,"../../bench/results",real.provenance.source_file),"utf8"));
check("saved record and generated headlines agree",()=>{
  for(const b of [10,20]){const test=L.stats(real,"egpot_full",b),dev=L.stats(real,"egpot_full",b,"dev"),source=saved.summary.per_method.find(r=>r.split==="test"&&r.method==="egpot_full"&&r.budget===b);assert.equal(test.hits,14);assert.equal(test.n,14);assert.equal(dev.hits,15);assert.equal(dev.n,16);assert.equal(test.hits,source.hit_count);assert.equal(test.nodes_to_hit,source.nodes_to_hit);assert.ok(L.findings(real).find(r=>r.text.startsWith(`At a budget of ${b}`)).text.includes("14/14"));}
});
check("real mechanical scorecard and comparison",()=>{
  const c=L.scorecard(real);assert.equal(c.find(r=>r.id==="contracts").verdict,"Supported");assert.equal(c.find(r=>r.id==="entropy").verdict,"Inconclusive");assert.equal(c.find(r=>r.id==="pareto").verdict,"Not supported");assert.equal(c.find(r=>r.id==="efficiency").verdict,"Supported");for(const r of L.comparison(real)){const s=saved.summary.dev_vs_test.find(s=>s.method===r.method&&s.budget===r.budget);assert.ok(Math.abs(s.delta_hit_rate_points-r.delta)<1e-9);}
});
check("test weight histogram excludes reference, keeps equal control",()=>{
  const w=L.weightCounts(real);assert.equal(w.all.length,55);assert.equal(w.count,54);assert.deepEqual([w.below,w.equal,w.above],[14,40,0]);assert.equal(L.weightCounts(real,"dev"),null);
});
check("latency has no effect on findings or verdicts",()=>{
  const changed=JSON.parse(JSON.stringify(real));changed.rows.forEach(r=>r.latency_s=999);assert.deepEqual(L.findings(changed),L.findings(real));assert.deepEqual(L.scorecard(changed),L.scorecard(real));
});
check("wording: unchanged components and plain-English success averages",()=>{
  const text=L.findings(real).map(r=>r.text).join("\n");assert.ok(text.includes("leaves EG-POT's test hits unchanged at 14/14 at budget 20 (dev: 15/16 to 13/16)"));assert.ok(text.includes("Averages count only the questions each method answered correctly, so they cover different sets of questions."));assert.ok(!text.includes("These means use each method's hits"));
});
check("alternative weighting counts come from the supplied vectors",()=>{
  assert.ok(L.findings(real).some(r=>r.text.includes("54 alternative weightings (4 single-objective emphasis vectors and 50 random draws)")));assert.ok(L.findings(synthetic).some(r=>r.text.includes("2 alternative weightings (1 single-objective emphasis vectors and 1 random draws)")));
});
check("existing matching DEV weights are read, never reconstructed",()=>{
  const shim={window:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../data/online_boutique/results_extra.js"),"utf8"),shim);const extra=JSON.parse(JSON.stringify(shim.window.VIZ_RESULTS_EXTRA)),counts=L.devWeightCounts(real,extra,20);assert.deepEqual([counts.below,counts.equal,counts.above],[20,3,31]);assert.ok(L.findings(real,extra).some(r=>r.text.includes("dev run: 20 worse, 3 tied, 31 better")));assert.equal(L.devWeightCounts(real,extra,15),null);const changed=JSON.parse(JSON.stringify(extra));changed.weights.find(r=>r.weights).weights[0]+=.1;assert.equal(L.devWeightCounts(real,changed,20),null);assert.ok(L.findings(real,changed).some(r=>r.text.includes("dev: not recorded")));
});
console.log(`Final test logic: ${groups} groups passed.`);
console.log("GENERATED SCORECARD\n"+L.scorecard(real).map(c=>`${c.title}: ${c.verdict} | dev: ${c.dev} | test: ${c.test}`).join("\n"));
