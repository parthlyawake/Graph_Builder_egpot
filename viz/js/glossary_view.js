(function(){
  "use strict";
  const G=window.VIZ_GLOSSARY,el=window.VizData.element;
  // Flip this one option, then call GlossaryUI.refresh(), to link every occurrence.
  window.GLOSSARY_LINK_FIRST_ONLY_PER_BLOCK ??= true;
  let popover,anchor;
  function position(){
    if(!anchor||!popover||popover.hidden)return;
    const box=anchor.getBoundingClientRect(),panel=popover.getBoundingClientRect(),gap=8;
    let top=box.bottom+gap;if(top+panel.height>innerHeight-gap)top=box.top-panel.height-gap;
    popover.style.top=Math.max(gap,Math.min(top,innerHeight-panel.height-gap))+"px";
    popover.style.left=Math.max(gap,Math.min(box.left,innerWidth-panel.width-gap))+"px";
  }
  function close(restore=true){
    const old=anchor;anchor=null;if(!popover)return;
    if(popover.matches(":popover-open"))popover.hidePopover();popover.hidden=true;
    if(old){old.setAttribute("aria-expanded","false");if(restore&&old.isConnected)old.focus();}
  }
  function open(button,key){
    if(anchor===button){close();return;}
    close(false);anchor=button;const entry=G[key];
    if(!popover){popover=el("div","glossary-popover");popover.id="glossary-popover";popover.setAttribute("popover","manual");popover.setAttribute("role","dialog");popover.setAttribute("aria-labelledby","glossary-popover-title");document.body.append(popover);}
    const heading=el("h2","",entry.label);heading.id="glossary-popover-title";
    const dismiss=el("button","glossary-close","Close");dismiss.type="button";dismiss.onclick=()=>close();
    popover.replaceChildren(el("div","eyebrow","PLAIN-ENGLISH GUIDE"),heading,el("p","glossary-short",entry.short),el("p","",entry.long),dismiss);
    popover.hidden=false;if(popover.showPopover)popover.showPopover();button.setAttribute("aria-expanded","true");position();
  }
  function help(key){
    const entry=G[key];if(!entry)throw new Error("Missing glossary entry: "+key);
    const button=el("button","glossary-link",entry.label);button.type="button";
    button.dataset.glossary=key;button.setAttribute("aria-label","Explain "+entry.label);button.setAttribute("aria-haspopup","dialog");button.setAttribute("aria-expanded","false");button.setAttribute("aria-controls","glossary-popover");
    button.addEventListener("click",event=>{event.preventDefault();event.stopPropagation();open(button,key);});return button;
  }
  function label(key,text){const button=help(key);button.classList.add("glossary-label");button.textContent=text??G[key].label;return button;}
  function refresh(root=document){
    const seen=new Map(),nodes=[...root.querySelectorAll(".glossary-link,[data-repeat-glossary]")];
    for(const node of nodes){
      if(node.closest(".glossary-popover"))continue;
      const key=node.dataset.glossary||node.dataset.repeatGlossary,cell=node.closest("td,th"),block=cell||node.closest("p");
      if(!block)continue;
      const exempt=cell&&(cell.closest("thead")||cell.cellIndex===0),keys=seen.get(block)||new Set();seen.set(block,keys);
      const repeat=window.GLOSSARY_LINK_FIRST_ONLY_PER_BLOCK&&!exempt&&keys.has(key);keys.add(key);
      if(repeat&&node.tagName==="BUTTON"){if(anchor===node)close(false);const plain=el("span","glossary-repeat",node.textContent);plain.dataset.repeatGlossary=key;node.replaceWith(plain);}
      else if(!repeat&&node.dataset.repeatGlossary){node.replaceWith(label(key,node.textContent));}
    }
  }
  function sortHeader(th,key,text,onSort){
    th.replaceChildren(key?label(key,text):document.createTextNode(text));const arrow=el("button","glossary-sort"," \u2195");arrow.type="button";arrow.setAttribute("aria-label","Sort by "+text);arrow.onclick=event=>{event.stopPropagation();onSort();};th.append(arrow);th.onclick=onSort;
  }
  document.addEventListener("click",event=>{if(anchor&&!popover.contains(event.target)&&!event.target.closest(".glossary-link"))close();});
  document.addEventListener("keydown",event=>{if(anchor&&event.key==="Escape"){event.preventDefault();event.stopPropagation();close();}},true);
  window.addEventListener("resize",position);window.addEventListener("scroll",position,true);
  const changes={egpot_full:"Four objectives; Pareto selection; no lookahead",egpot_full_mcts:"Adds MCTS lookahead",egpot_no_pareto:"Pareto selection replaced",egpot_no_entropy:"Entropy gain switched off",egpot_no_contracts:"Contract consistency switched off",egpot_no_choke_point:"RPC choke-point rule switched off",vector_topk:"Text ranking; graph ignored",bfs:"Question ignored; breadth-first expansion",greedy_walk:"One relevance-only path"};
  function panel(expanded=false){
    const details=el("details","glossary-panel panel");details.open=expanded;details.append(el("summary","","What do these names mean?"));const content=el("div","glossary-content"),table=el("table","glossary-table"),head=el("tr");["Name","What changes","Explanation"].forEach(t=>head.append(el("th","",t)));const thead=el("thead");thead.append(head);table.append(thead);const body=el("tbody");
    Object.keys(G).filter(k=>k.startsWith("egpot_")||k.startsWith("vector_bfs_")||["vector_topk","bfs","greedy_walk","ppr","scalar_beam","community_graphrag","mcts_standard"].includes(k)||k.endsWith("_no_choke")).forEach(key=>{const row=el("tr"),name=el("th");name.append(label(key));row.append(name,el("td","",changes[key]||(key.endsWith("_no_choke")?"Choke-point rule off":key.endsWith("_mcts")?changes[key.replace(/_mcts$/,"")]+"; MCTS on":"Retrieval baseline")),el("td","",G[key].short));body.append(row);});table.append(body);content.append(table);
    for(const [title,keys] of [["The four scores and Pareto front",["score_relevance","score_hop","score_contract","score_entropy","pareto_front"]],["Metrics",["hit","gold_recall","precision","path_coverage","ordered_path_match","nodes_returned","nodes_to_hit","latency_s"]],["Query types",["explicit","indirect"]],["Experiment terms",["weighting","seed"]]]){content.append(el("h3","",title));keys.forEach(key=>{const p=el("p");p.append(label(key),document.createTextNode(" — "+G[key].short));content.append(p);});}details.append(content);return details;
  }
  function selectorHelp(select,keyOf){const span=el("span","selector-help");select.after(span);const update=()=>{const keys=[keyOf(select.value)].flat().filter(Boolean);span.replaceChildren(...keys.map(help));};span.refresh=update;select.addEventListener("change",update);for(const option of select.options){const key=keyOf(option.value);if(typeof key==="string"&&G[key])option.title=G[key].short;}update();return span;}
  function svgHelp(node,key){
    const ns=node.namespaceURI,group=document.createElementNS(ns,"g"),foreign=document.createElementNS(ns,"foreignObject"),x=Number(node.getAttribute("x")||0),y=Number(node.getAttribute("y")||0),align=node.getAttribute("text-anchor"),width=Math.max(35,node.textContent.length*7+8);
    foreign.setAttribute("x",align==="middle"?x-width/2:align==="end"?x-width:x);foreign.setAttribute("y",y-15);foreign.setAttribute("width",width);foreign.setAttribute("height",30);foreign.setAttribute("class","glossary-svg");foreign.style.overflow="visible";
    const button=label(key,node.textContent);foreign.append(button);group.append(foreign);return group;
  }
  if(typeof MutationObserver!=="undefined"){let pending=false;new MutationObserver(()=>{if(!pending){pending=true;queueMicrotask(()=>{pending=false;refresh();});}}).observe(document.body,{childList:true,subtree:true});}
  window.GlossaryUI={help,label,panel,selectorHelp,svgHelp,changes,refresh,sortHeader,close};
})();
