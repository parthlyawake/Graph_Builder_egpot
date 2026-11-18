(function(){
  "use strict";
  const L=window.ResultsLogic,el=window.VizData.element,ns="http"+":"+"//www.w3.org/2000/svg";
  const metrics={hit:"Hit rate",gold_recall:"Recall",path_coverage:"Path coverage",nodes_returned:"Nodes returned",nodes_to_hit:"Nodes to hit (hits only)",latency_s:"Latency"};
  function svg(tag,attrs={},text){const node=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));if(text!==undefined)node.textContent=text;return node;}
  function option(select,value,text){const node=el("option","",text);node.value=value;select.append(node);}
  function field(parent,name,select){const label=el("label","",name);label.append(select);parent.append(label);}
  const banner="Dev split only · 16 queries (8 links) · one repo · differences of one query are not meaningful";
  class ResultsView{
    constructor(){this.panel=document.getElementById("results-panel");this.rows=L.mergeRows(window.VIZ_RESULTS.rows,window.VIZ_RESULTS_EXTRA?.rows||[]);this.sort={budget:20,ascending:false};this.build();}
    build(){
      this.panel.append(el("div","dev-banner",banner+". See the Final test tab for the locked held-out run."));const controls=el("div","analytics-controls");
      this.budget=el("select");[...new Set(this.rows.map(r=>r.budget))].sort((a,b)=>a-b).forEach(b=>option(this.budget,b,b));this.budget.value="20";field(controls,"Budget",this.budget);
      this.type=el("select");["all","explicit","indirect"].forEach(t=>option(this.type,t,t));field(controls,"Query type",this.type);
      this.metric=el("select");Object.entries(metrics).forEach(([key,title])=>option(this.metric,key,title));field(controls,"Metric",this.metric);
      window.GlossaryUI.selectorHelp(this.metric,v=>v);window.GlossaryUI.selectorHelp(this.type,v=>v==="all"?["explicit","indirect"]:v);
      this.scale=el("select");option(this.scale,"log","log");option(this.scale,"linear","linear");field(controls,"x-axis",this.scale);
      const all=el("label","compare-budgets");this.all=el("input");this.all.type="checkbox";this.all.checked=true;all.append(this.all,document.createTextNode("Compare all budgets"));controls.append(all,el("span","tiny muted","Best values, including ties, are highlighted. Nodes-to-hit excludes misses."));
      this.chartOnly=el("input");this.chartOnly.type="checkbox";this.chartOnly.checked=true;const chartFilter=el("label");chartFilter.append(this.chartOnly,document.createTextNode("Chart: only methods with data at this budget"));controls.append(chartFilter);window.ExtraViews.jumps(controls,[["results-thresholds","Thresholds"],["results-matched","Matched size"],["results-seeds","Seeds"]]);this.panel.append(controls,window.GlossaryUI.panel(false));this.body=el("div","analytics-body");this.panel.append(this.body);
      [this.budget,this.type,this.metric,this.all,this.scale,this.chartOnly].forEach(control=>control.onchange=()=>this.render());this.render();
    }
    render(){
      this.body.replaceChildren();const top=el("div","results-top"),tableCard=el("section","panel analytic-card results-method-comparison"),chartCard=el("section","panel analytic-card results-retrieval-efficiency");
      const heading=el("h2");heading.append(window.GlossaryUI.label(this.metric.value,metrics[this.metric.value]));tableCard.append(el("div","eyebrow","METHOD COMPARISON"),heading);this.table(tableCard);
      chartCard.append(el("div","eyebrow","RETRIEVAL EFFICIENCY"),el("h2","","Coverage for the nodes collected"),this.chart(),el("p","tiny muted","Points span measured budgets; counts label the selected budget. Hover for budget, hit count and latency. Connecting lines guide the eye."));top.append(tableCard,chartCard);this.body.append(top);
      window.ExtraViews.results(this);const caveats=el("section","panel analytic-card results-caveats");caveats.append(el("h2","","Where EG-POT does not win"));
      const beats=L.notWins(this.rows,Number(this.budget.value),this.type.value);
      if(!beats.length)caveats.append(el("p","muted","No compared baseline or ablation improves these means at the selected budget."));
      beats.forEach(v=>{const p=el("p"),value=v.metric==="latency_s"?v.value.toFixed(3)+" s":["hit","gold_recall","path_coverage"].includes(v.metric)?(100*v.value).toFixed(1)+"%":v.value.toFixed(1),base=v.metric==="latency_s"?v.baseline.toFixed(3)+" s":["hit","gold_recall","path_coverage"].includes(v.metric)?(100*v.baseline).toFixed(1)+"%":v.baseline.toFixed(1);p.append(window.GlossaryUI.label(v.method,L.labels[v.method]),document.createTextNode(": "),window.GlossaryUI.label(v.metric,metrics[v.metric]),document.createTextNode(" "+value+" vs "+base+" "+L.hitSuffix(v)+"."));caveats.append(p);});
      caveats.append(el("p","tiny muted","Fewer returned nodes or lower latency alone does not imply better retrieval. Nodes-to-hit means use only each method’s hits; hit subsets may differ."));this.body.append(caveats);
      const grid=el("section","panel analytic-card query-grid-card");grid.append(el("div","eyebrow","INDIVIDUAL QUERIES"),el("h2","","Outcomes at budget "+this.budget.value),el("p","tiny muted","Green = hit · amber = partial recall · red = miss · — = not run. Click to inspect a stored trace."));this.grid(grid);this.body.append(grid);
      this.body.append(el("p","analytics-note",window.VIZ_RESULTS.meta.note_latency+". "+window.VIZ_RESULTS.meta.generated_note));
    }
    table(parent){
      const metric=this.metric.value,budgets=this.all.checked?[...new Set(this.rows.map(r=>r.budget))].sort((a,b)=>a-b):[Number(this.budget.value)];
      const methods=L.methodNames(this.rows).filter(m=>budgets.some(b=>L.summary(this.rows,m,b,this.type.value)));
      const sorted=[...methods].sort((a,b)=>{const va=L.summary(this.rows,a,this.sort.budget,this.type.value)?.[metric],vb=L.summary(this.rows,b,this.sort.budget,this.type.value)?.[metric];if(va===undefined||va===null)return vb===undefined||vb===null?a.localeCompare(b):1;if(vb===undefined||vb===null)return -1;return (this.sort.ascending?va-vb:vb-va)||a.localeCompare(b);});
      const wrap=el("div","table-scroll results-comparison-wrap"),table=el("table","metric-table results-comparison-table"),head=el("tr"),cols=el("colgroup");cols.append(el("col","comparison-method-col"));budgets.forEach(()=>cols.append(el("col")));table.append(cols);head.append(el("th","","Method"));
      const best=new Map();budgets.forEach(b=>{const th=el("th"),button=el("button","",String(b)+(this.sort.budget===b?(this.sort.ascending?" ↑":" ↓"):" ↕"));button.onclick=()=>{this.sort={budget:b,ascending:this.sort.budget===b?!this.sort.ascending:L.lower.has(metric)};this.render();};th.append(button);head.append(th);best.set(b,L.bestPerColumn(methods.map(method=>({method,value:L.summary(this.rows,method,b,this.type.value)?.[metric]??null})),metric));});
      const thead=el("thead");thead.append(head);table.append(thead);const body=el("tbody");
      sorted.forEach(method=>{const tr=el("tr"),name=el("th");name.append(window.GlossaryUI.label(method,L.labels[method]));tr.append(name);budgets.forEach(b=>{const s=L.summary(this.rows,method,b,this.type.value),isBest=best.get(b).includes(method),td=el("td",isBest?"best":""),formatted=L.format(s,metric),split=formatted.indexOf(" · ");
        if(split<0)td.append(el("span","comparison-value",formatted));else{const separator=el("span","comparison-separator"," · ");separator.setAttribute("aria-hidden","true");td.append(el("span","comparison-value",formatted.slice(0,split)),separator,el("span","comparison-detail",formatted.slice(split+3)));}
        if(isBest)td.title=best.get(b).length>1?"Tied best value":"Best value";tr.append(td);});body.append(tr);});table.append(body);wrap.append(table);parent.append(wrap,el("p","tiny muted comparison-legend","— means not run at this budget, or no hits when showing nodes-to-hit."));
    }
    chart(){
      const methods=L.methodNames(this.rows).filter(m=>!this.chartOnly.checked||L.summary(this.rows,m,Number(this.budget.value),this.type.value)),colors=methods.map(m=>`hsl(${L.methodNames(this.rows).indexOf(m)*137.508%360} 65% 65%)`),chart=svg("svg",{viewBox:"0 0 540 280",class:"efficiency-chart extra-efficiency",role:"img","aria-label":"Mean nodes returned versus hit rate"}),layout=el("div","results-efficiency"),legend=el("div","results-chart-legend");
      const filtered=L.select(this.rows,{type:this.type.value}),maxNodes=Math.max(200,...filtered.map(r=>r.nodes_returned)),log=this.scale.value==="log",minimum=Math.min(10,...filtered.map(r=>r.nodes_returned)),x=n=>log?55+(Math.log(Math.max(minimum,n))-Math.log(minimum))/(Math.log(maxNodes)-Math.log(minimum))*450:55+n/maxNodes*450,y=h=>235-h*200;
      for(const tick of [0,.25,.5,.75,1]){chart.append(svg("line",{x1:55,x2:505,y1:y(tick),y2:y(tick),class:"chart-grid"}),svg("text",{x:46,y:y(tick)+4,"text-anchor":"end"},(100*tick)+"%"));}
      for(const tick of log?[10,20,50,100,200]:[0,maxNodes/2,maxNodes])chart.append(svg("text",{x:x(tick),y:253,"text-anchor":"middle"},tick.toFixed(0)));
      chart.append(window.GlossaryUI.svgHelp(svg("text",{x:280,y:271,"text-anchor":"middle"},"Mean nodes returned ("+this.scale.value+")"),"nodes_returned"),window.GlossaryUI.svgHelp(svg("text",{x:55,y:17},"Hit rate · counts on points"),"hit"));
      const occupied=[];
      methods.forEach((method,i)=>{const budgets=[...new Set(filtered.filter(r=>r.method===method).map(r=>r.budget))].sort((a,b)=>a-b),points=budgets.map(b=>({b,s:L.summary(filtered,method,b)}));
        chart.append(svg("polyline",{points:points.map(p=>x(p.s.nodes_returned)+","+y(p.s.hit)).join(" "),fill:"none",stroke:colors[i],"stroke-width":1.5,opacity:.7}));
        const locations=new Map();points.forEach(p=>{const key=p.s.nodes_returned.toFixed(5)+":"+p.s.hit.toFixed(5);if(!locations.has(key))locations.set(key,[]);locations.get(key).push(p);});
        for(const group of locations.values()){
          const s=group[0].s,budgetsHere=group.map(p=>p.b),px=x(s.nodes_returned),py=y(s.hit),label=(budgetsHere.length>2?budgetsHere[0]+"…"+budgetsHere.at(-1):budgetsHere.join("/"))+": "+s.hits+"/"+s.n;
          const circle=svg("circle",{cx:px,cy:py,r:4,fill:colors[i],tabindex:0});circle.append(svg("title",{},group.map(p=>`${L.labels[method]} · budget ${p.b} · ${(100*p.s.hit).toFixed(1)}% (${p.s.hits}/${p.s.n}) · nodes ${p.s.nodes_returned.toFixed(1)} · ${p.s.latency_s.toFixed(3)} s`).join("\n")));chart.append(circle);
          if(!budgetsHere.includes(Number(this.budget.value)))continue;
          const width=label.length*4.6,tx=Math.max(58,Math.min(px+6,510-width));let ty=py-8;
          for(const offset of [-8,-22,17,31,-36,45,59,-50]){const candidate=Math.max(30,Math.min(230,py+offset));if(!occupied.some(r=>tx<r.x+r.w&&tx+width>r.x&&Math.abs(candidate-r.y)<12)){ty=candidate;break;}}
          occupied.push({x:tx,y:ty,w:width});chart.append(svg("line",{x1:px,y1:py,x2:tx,y2:ty-3,stroke:colors[i],opacity:.35}),svg("text",{x:tx,y:ty,style:"fill:"+colors[i],class:"point-label"},label));
        }
        const item=el("div","results-chart-key"),swatch=el("span","results-chart-swatch");swatch.style.background=colors[i];item.append(swatch,window.GlossaryUI.label(method,L.labels[method]));legend.append(item);
      });layout.append(chart,legend);return layout;
    }
    grid(parent){
      const budget=Number(this.budget.value),rows=L.select(this.rows,{budget,type:this.type.value}),ids=[...new Set(rows.map(r=>r.query_id))].sort(),methods=L.methodNames(this.rows).filter(m=>rows.some(r=>r.method===m));
      const wrap=el("div","table-scroll"),table=el("table","query-grid"),thead=el("thead"),head=el("tr");head.append(el("th","","Query"));methods.forEach(m=>{const th=el("th");th.append(window.GlossaryUI.label(m,L.labels[m]));head.append(th);});thead.append(head);table.append(thead);const body=el("tbody");
      ids.forEach(id=>{const query=window.VizData.queries.find(q=>q.id===id),tr=el("tr"),name=el("th");name.append(el("strong","",id+" · "+query.type),el("span","",query.query));tr.append(name);
        methods.forEach(method=>{const r=rows.find(r=>r.query_id===id&&r.method===method),td=el("td");if(r){const button=el("button",r.hit?"hit":r.gold_recall>0?"partial":"miss",r.hit?"✓":r.gold_recall>0?"½":"×");button.title=`Recall ${r.gold_recall.toFixed(3)}; hit ${r.hit}; ${r.nodes_returned} nodes. Open trace if available.`;button.onclick=()=>this.openTrace(id,method,budget);td.append(button);}else td.textContent="—";tr.append(td);});body.append(tr);});table.append(body);wrap.append(table);this.gridStatus=el("p","grid-status","");this.gridStatus.setAttribute("role","status");parent.append(this.gridStatus,wrap);
    }
    async openTrace(id,method,budget){
      try{if(!window.VIZ_TRACE_INDEX)await new Promise((resolve,reject)=>{const s=document.createElement("script");s.src="data/online_boutique/traces_index.js";s.onload=resolve;s.onerror=()=>reject(new Error("Local trace index is missing."));document.head.append(s);});
        if(!window.VIZ_TRACE_INDEX.some(t=>t.query_id===id&&t.method===method&&t.budget===budget)){this.gridStatus.textContent="No step-by-step trace was exported for this method yet.";this.gridStatus.scrollIntoView({block:"nearest"});return;}
        window.VizApp.showTab("player");const p=window.VizApp.player;p.query.value=id;p.method.value=method;p.budget.value=String(budget);await p.load();
      }catch(error){this.gridStatus.textContent=error.message;}
    }
  }
  window.ResultsUI={el,svg,field,option,banner};window.ResultsView=ResultsView;
})();
