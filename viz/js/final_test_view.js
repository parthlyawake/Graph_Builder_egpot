(function(){
  "use strict";
  const L=window.FinalTestLogic,G=window.GlossaryUI,U=window.ResultsUI,{el,svg}=U;
  const extraTerms={"mean nodes-to-hit":"nodes_to_hit","Mean nodes-to-hit":"nodes_to_hit","Nodes-to-hit":"nodes_to_hit","Precision-at-hit":"precision_at_hit","hit rate":"hit","hit-rate":"hit","equal-weight sum":"egpot_no_pareto","explicit":"explicit","indirect":"indirect","budget":"budget","hit":"hit","hits":"hit","recall":"gold_recall","mean nodes":"nodes_returned","nodes-to-hit":"nodes_to_hit","precision-at-hit":"precision_at_hit","contract score":"score_contract","entropy score":"score_entropy","choke-point rule":"egpot_no_choke_point","Pareto":"pareto_front","equal weights":"egpot_no_pareto","Equal weights":"egpot_no_pareto","MCTS":"egpot_full_mcts","EG-POT":"egpot_full","EG-POT's":"egpot_full","seeds":"seed","weightings":"weighting"};
  const terms=[...Object.entries(L.labels).map(([key,name])=>[name,key]),...Object.entries(extraTerms)].sort((a,b)=>b[0].length-a[0].length);
  function prose(text,className=""){
    const p=el("p",className);let cursor=0;
    // Prefer the longest matching method/component name, attaching help inline.
    while(cursor<text.length){let found=null;for(const [name,key] of terms){const index=text.indexOf(name,cursor);if(index<0||index>0&&/[A-Za-z]/.test(text[index-1])||/[A-Za-z]/.test(text[index+name.length]||""))continue;if(!found||index<found.index)found={index,name,key};}
      if(!found){p.append(document.createTextNode(text.slice(cursor)));break;}
      p.append(document.createTextNode(text.slice(cursor,found.index)),G.label(found.key,found.name));cursor=found.index+found.name.length;
    }return p;
  }
  function card(id,title){const node=el("section","panel analytic-card final-card");node.id=id;node.append(el("h2","",title));return node;}
  function table(parent,headers){const scroll=el("div","table-scroll"),node=el("table","metric-table final-table"),head=el("thead"),tr=el("tr"),body=el("tbody");headers.forEach(h=>{const th=el("th");th.append(Array.isArray(h)?G.label(h[1],h[0]):document.createTextNode(h));tr.append(th);});head.append(tr);node.append(head,body);scroll.append(node);parent.append(scroll);return {node,body,head:tr};}
  const cell=(value,kind="td",className="")=>el(kind,className,value===null?"—":String(value));
  function methodCell(name){const node=el("th");node.append(G.label(name,L.labels[name]));return node;}
  class FinalTestView{
    constructor(){
      this.panel=document.getElementById("final-test-panel");this.data=window.VIZ_RESULTS_TEST;
      if(!this.data){this.panel.append(el("p","","The frozen final-test export is unavailable."));return;}
      this.sort={key:"hits",ascending:false};const d=this.data,tests=d.rows.filter(r=>r.split==="test"),n=new Set(tests.map(r=>r.id)).size,links=d.provenance.split_links.test.length;
      this.panel.append(el("div","dev-banner final-banner",`Locked test run · code frozen at commit ${d.provenance.commit.slice(0,8)} · test split = ${links} links / ${n} queries · run once, no tuning · one repo`));
      const nav=el("nav","final-jumps");for(const [id,title] of [["final-findings","What we found"],["final-scorecard","Claims"],["final-main","Main table"],["final-comparison","Dev vs test"],["final-choke","Choke-point"],["final-seeds","Seeds"],["final-weights","Weights"],["final-misses","Misses"]]){const button=el("button","text-button",title);button.onclick=()=>document.getElementById(id).scrollIntoView({block:"start"});nav.append(button);}this.panel.append(nav);
      this.body=el("div","analytics-body final-body");this.panel.append(this.body);
      this.intro();this.findings();this.scorecard();this.main();this.comparison();this.choke();this.seeds();this.weights();this.misses();
      const caveats=el("aside","panel final-caveats");caveats.id="final-caveats";caveats.append(el("strong","","Caveats"),prose(L.caveat(d)));this.panel.append(caveats);
    }
    intro(){
      const node=card("final-intro","What this is"),p=this.data.provenance;
      node.append(prose("The questions were split by link into a dev set, used while building, and a test set, set aside. The explicit and indirect questions about the same link stayed together."));
      node.append(prose(`The code was frozen and committed as ${p.commit.slice(0,8)}. The test was run once on all methods with the exact same settings as dev. Nothing was tuned afterwards.`));
      node.append(prose("A budget is the maximum number of code nodes a method may return, standing in for how much the AI assistant must read. A hit means all answer nodes were found. Nodes-to-hit and precision-at-hit average only successful queries; always read their hit counts too."));
      const details=el("details","final-provenance");details.append(el("summary","","Provenance: frozen commit, UTC time, versions, hashes and seeds"));
      const dl=el("dl","final-provenance-list");for(const [key,value] of [["Commit",p.commit],["UTC",p.timestamp_utc],["Versions",JSON.stringify(p.versions)],["Record byte SHA-256",p.source_record_sha256],["Deterministic SHA-256 (timing excluded)",p.deterministic_sha256],["Seeds",p.seeds.join(", ")],["Split links",JSON.stringify(p.split_links)]])dl.append(el("dt","",key),el("dd","",value));details.append(dl);
      p.missing_fields.forEach(text=>details.append(prose(text,"final-unavailable")));node.append(details);this.body.append(node);
    }
    findings(){const node=card("final-findings","What we found");L.findings(this.data,window.VIZ_RESULTS_EXTRA).forEach(r=>node.append(prose(r.text)));this.body.append(node);}
    scorecard(){
      const node=card("final-scorecard","Claims scorecard");node.append(prose("Verdicts follow the stated rule mechanically. One query is not a meaningful difference.","final-rule-note"));
      const t=table(node,["Claim","Dev numbers","Test numbers","Verdict","Rule"]);
      L.scorecard(this.data).forEach(c=>{const row=el("tr"),claim=cell("","th"),dev=cell(""),test=cell(""),verdict=cell(""),rule=cell("");claim.append(prose(c.title));dev.append(prose(c.dev));test.append(prose(c.test));const chip=el("span","verdict-chip "+(c.verdict.startsWith("Inconclusive")?"inconclusive":c.verdict==="Supported"?"supported":"not-supported"),c.verdict);verdict.append(chip);rule.append(prose(c.rule));row.append(claim,dev,test,verdict,rule);t.body.append(row);});this.body.append(node);
    }
    main(){
      const node=card("final-main","Main methods · test split"),controls=el("div","extra-controls"),select=el("select");L.budgets(this.data).forEach(b=>U.option(select,b,b));select.value="20";select.setAttribute("aria-label","Final test budget");const budgetLabel=el("label");budgetLabel.append(G.label("budget","Budget"),select);controls.append(budgetLabel);node.append(controls,prose("Best values, including ties, are highlighted. Nodes-to-hit and precision-at-hit exclude misses; their hit count is shown."));
      const target=el("div");node.append(target);this.mainBudget=select;
      const columns=[["method","Method",null],["hits","Hits k/N","hit"],["gold_recall","Recall","gold_recall"],["nodes_returned","Mean nodes","nodes_returned"],["nodes_to_hit","Nodes-to-hit · hits only","nodes_to_hit"],["precision_at_hit","Precision-at-hit","precision_at_hit"]];
      const draw=()=>{target.replaceChildren();const values=L.methods(this.data).map(m=>L.stats(this.data,m,Number(select.value))),t=table(target,columns.map(([,label,key])=>key?[label,key]:label));
        [...t.head.children].forEach((th,i)=>{const [key,label,help]=columns[i];G.sortHeader(th,help,label,()=>{this.sort={key,ascending:this.sort.key===key?!this.sort.ascending:["method","nodes_returned","nodes_to_hit"].includes(key)};draw();});});
        const best={};for(const [key] of columns.slice(1)){const numbers=values.map(v=>v[key]).filter(v=>v!==null);best[key]=["nodes_returned","nodes_to_hit"].includes(key)?Math.min(...numbers):Math.max(...numbers);}
        values.sort((a,b)=>{const key=this.sort.key,x=a[key],y=b[key];if(x===null)return y===null?a.method.localeCompare(b.method):1;if(y===null)return -1;return (typeof x==="string"?L.labels[x].localeCompare(L.labels[y]):x-y)*(this.sort.ascending?1:-1)||a.method.localeCompare(b.method);}).forEach(s=>{const row=el("tr");row.append(methodCell(s.method));for(const [key] of columns.slice(1)){const value=key==="hits"?L.hitText(s):key==="nodes_to_hit"?(s[key]===null?"\u2014":L.fmt(s[key]))+` (${s.hits}/${s.n} hits)`:key==="gold_recall"||key==="precision_at_hit"?s[key]===null?"—":(s[key]*100).toFixed(1)+"%":L.fmt(s[key]);row.append(cell(value,"td",s[key]!==null&&Math.abs(s[key]-best[key])<1e-10?"best":""));}t.body.append(row);});};select.onchange=draw;draw();this.body.append(node);
    }
    comparison(){const node=card("final-comparison","Dev vs test · every method and budget"),t=table(node,["Method",["Budget","budget"],["Dev hits","hit"],["Test hits","hit"],["Change in hit-rate points","hit"]]);L.comparison(this.data).forEach(s=>{const r=el("tr");r.append(methodCell(s.method),cell(s.budget),cell(L.hitText(s.dev)),cell(L.hitText(s.test)),cell((s.delta>0?"+":"")+L.fmt(s.delta)+" pp","td",s.delta>0?"positive":s.delta<0?"negative":""));t.body.append(r);});this.body.append(node);}
    choke(){const node=card("final-choke","Choke-point rule · test baselines"),t=table(node,["Method",["Budget","budget"],["ON hits","hit"],["OFF hits","hit"],["ON mean nodes","nodes_returned"],["OFF mean nodes","nodes_returned"],"Change in hit queries"]);node.insertBefore(prose("Delta is OFF minus ON. Normal graph-based baselines all use the same choke-point rule."),node.children[1]);this.data.summary.choke.forEach(s=>{const row=el("tr");row.append(methodCell(s.method),cell(s.budget),cell(s.on_hits+"/"+s.n),cell(s.off_hits+"/"+s.n),cell(L.fmt(s.on_nodes)),cell(L.fmt(s.off_nodes)),cell((s.delta_queries>0?"+":"")+s.delta_queries));t.body.append(row);});this.body.append(node);}
    weights(){
      const node=card("final-weights","Weight robustness · test split"),s=L.weightCounts(this.data);node.append(prose(`At budget 20, ${s.below} of ${s.count} study weightings did worse than Pareto, ${s.equal} tied, ${s.above} did better. The dot plot includes all ${s.all.length} vectors, including equal weights. Weights are a distribution, not a tuning exercise.`));
      const chart=svg("svg",{viewBox:"0 0 920 235",class:"final-weight-dots",role:"img","aria-label":"Test hits across all weight vectors, with Pareto reference"}),counts=new Map(),low=Math.min(...s.all.map(v=>v.hits)),high=Math.max(...s.all.map(v=>v.hits),s.reference),x=h=>100+(h-low)/(high-low||1)*700;
      chart.append(svg("line",{x1:x(s.reference),x2:x(s.reference),y1:20,y2:194,stroke:"#e6b94a","stroke-dasharray":"5 5","stroke-width":2}),svg("text",{x:35,y:16},"Each dot = one weight vector · dashed line = Pareto ("+s.reference+"/"+s.n+")"));
      s.all.sort((a,b)=>a.id.localeCompare(b.id)).forEach(v=>{const i=counts.get(v.hits)||0;counts.set(v.hits,i+1);const circle=svg("circle",{cx:x(v.hits)+(i%5-2)*10,cy:184-Math.floor(i/5)*14,r:v.id==="equal"?5:3.5,fill:v.id==="equal"?"#e6b94a":"#67dfc4",tabindex:0});circle.append(svg("title",{},v.id+": "+v.hits+"/"+s.n+" hits"));chart.append(circle);});for(let h=low;h<=high;h++)chart.append(svg("text",{x:x(h),y:212,"text-anchor":"middle"},h+"/"+s.n));node.append(chart,prose("Gold dot: equal-weight control. DEV weight-distribution runs were not recorded in this frozen JSON; no DEV weight comparison is reconstructed.","final-unavailable"));
      const t=table(node,[["Budget","budget"],"Type",["Vectors","weighting"],["Pareto hits","hit"],"Min","Q25","Median","Q75","Max","Mean","Worse","Tie","Better"]);this.data.summary.weight_distribution.forEach(s=>{const row=el("tr");[s.budget,s.type,s.vectors,s.pareto+"/"+s.queries,...["min","q25","median","q75","max","mean","below","equal","above"].map(k=>L.fmt(s[k]))].forEach(v=>row.append(cell(v)));t.body.append(row);});this.body.append(node);
    }
    seeds(){const node=card("final-seeds","Seeds · test split"),t=table(node,["Method",["Budget","budget"],...this.data.provenance.seeds.map(s=>["Seed "+s,"seed"]),["Mean hits","hit"],["Min hits","hit"],["Max hits","hit"]]);this.data.summary.seeds.forEach(s=>{const row=el("tr"),n=s.runs[0].n;row.append(methodCell(s.method),cell(s.budget));for(const r of s.runs)row.append(cell(r.hit_count+"/"+r.n));row.append(cell(L.fmt(s.mean_hits)+"/"+n),cell(s.min_hits+"/"+n),cell(s.max_hits+"/"+n));t.body.append(row);});this.body.append(node);}
    misses(){const node=card("final-misses","Misses at budget 20 · test split");for(const method of ["egpot_full","egpot_no_pareto","mcts_standard"]){const title=el("h3");title.append(G.label(method,L.labels[method]));node.append(title);const misses=this.data.summary.test_misses_budget20.filter(r=>r.method===method);if(!misses.length)node.append(el("p","","No misses."));for(const miss of misses){const block=el("div","final-miss");block.append(el("strong","",miss.query_id),el("p","",miss.query));miss.missing_gold_nodes.forEach(id=>block.append(el("code","",id)));node.append(block);}}this.body.append(node);}
  }
  window.FinalTestView=FinalTestView;
})();
