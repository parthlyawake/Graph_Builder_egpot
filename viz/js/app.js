(function () {
  "use strict";
  const data = window.VizData, details = document.getElementById("details");
  if (!data || data.error || !window.vis) {details.textContent = data && data.error || "The local graph library could not be loaded."; return;}
  const el = data.element;
  const defaultTypes = new Set(["function", "class", "interface", "rpc_contract", "service_contract", "http_endpoint"]);
  const defaultRelations = new Set(["CALLS", "CONSUMES", "IMPLEMENTS", "DEFINES_RPC"]);
  const filters = {types: new Set(defaultTypes), relations: new Set(defaultRelations), services: new Set(data.graph.meta.services.map(s => s.name))};
  const boxes = {};
  let graph;
  function showDetails(node) {
    details.replaceChildren();
    details.append(el("div", "eyebrow", node ? "NODE INSPECTOR" : "INSPECT A CONNECTION"));
    if (!node) {
      details.append(el("div", "empty-icon", "⌖"), el("h2", "", "Follow the connections"), el("p", "intro", "Select a node to inspect its source location and the relationships around it. Click a connection in the lists to keep exploring."));
      const tip = el("div", "tip-card"); tip.append(el("strong", "", "A map of service boundaries"), document.createTextNode("Colors identify services. Diamonds represent contracts. Filters reveal the lower-level symbols behind each service.")); details.append(tip); return;
    }
    details.append(el("h2", "", node.name), el("div", "node-id", node.id));
    details.append(el("span", "node-tag", node.type), el("span", "node-tag", node.layer || "No layer"));
    const meta = el("dl", "metadata");
    [["Service", node.repo], ["Source", node.file ? node.file + ":" + node.line_no : "No source location"], ["Layer", node.layer || "—"]].forEach(([key,value]) => {meta.append(el("dt", "", key), el("dd", "", value));});
    details.append(meta, el("h3", "", "Docstring"), el("p", "docstring", node.docstring || "No docstring recorded."));
    for (const [heading, edges, other] of [["Out edges", data.outgoing.get(node.id), "target"], ["In edges", data.incoming.get(node.id), "source"]]) {
      details.append(el("h3", "", heading + " · " + edges.length));
      const list = el("div", "edge-list");
      if (!edges.length) list.append(el("p", "muted small", "No recorded edges."));
      edges.forEach(edge => {
        const button = el("button", "edge-link"); button.append(el("span", "relation", edge.relation), document.createTextNode(edge[other]));
        button.addEventListener("click", () => graph.select(edge[other], true)); list.append(button);
      }); details.append(list);
    }
  }
  function render(fit) {
    document.getElementById("type-tally").textContent = filters.types.size + " / " + data.graph.meta.node_types.length;
    graph.render(filters, fit);
  }
  function buildFilters(containerId, category, values, counts) {
    const container = document.getElementById(containerId); boxes[category] = new Map();
    values.forEach(value => {
      const label = el("label", "filter-row");
      const box = document.createElement("input"); box.type = "checkbox"; box.checked = filters[category].has(value); box.setAttribute("aria-label", category + ": " + value);
      box.addEventListener("change", () => {if (box.checked) filters[category].add(value); else filters[category].delete(value); render(false);});
      boxes[category].set(value, box); label.append(box);
      if (category === "services") {const swatch = el("span", "swatch"); swatch.style.backgroundColor = data.colors.get(value); label.append(swatch);}
      label.append(el("span", "filter-name", value), el("span", "filter-count", String(counts.get(value) || 0))); container.append(label);
    });
  }
  const count = (values, field) => {const counts = new Map(); values.forEach(item => counts.set(item[field], (counts.get(item[field]) || 0) + 1)); return counts;};
  buildFilters("type-filters", "types", data.graph.meta.node_types, count(data.graph.nodes, "type"));
  buildFilters("relation-filters", "relations", data.graph.meta.relations, count(data.graph.edges, "relation"));
  buildFilters("service-filters", "services", data.graph.meta.services.map(s => s.name), count(data.graph.nodes, "repo"));
  graph = new GraphExplorer(data, showDetails, (nodes, edges) => {
    const counts = document.getElementById("counts"); counts.replaceChildren(el("strong", "", nodes.toLocaleString()), document.createTextNode(" / " + data.graph.meta.node_count.toLocaleString() + " nodes  ·  "), el("strong", "", edges.toLocaleString()), document.createTextNode(" / " + data.graph.meta.edge_count.toLocaleString() + " edges"));
  });
  graph.reveal = id => {const node = data.byId.get(id); filters.types.add(node.type); filters.services.add(node.repo); boxes.types.get(node.type).checked = true; boxes.services.get(node.repo).checked = true; render(false);};
  document.getElementById("reset-filters").addEventListener("click", () => {
    filters.types = new Set(defaultTypes); filters.relations = new Set(defaultRelations); filters.services = new Set(data.graph.meta.services.map(s => s.name));
    Object.entries(boxes).forEach(([category, inputs]) => inputs.forEach((box, key) => {box.checked = filters[category].has(key);}));
    graph.search = ""; graph.selected = null; document.getElementById("search").value = ""; graph.allLabels = false; document.getElementById("all-labels").checked = false; showDetails(null); render(true);
  });
  document.getElementById("all-services").addEventListener("click", () => {boxes.services.forEach((box,key) => {box.checked = true; filters.services.add(key);}); render(true);});
  document.getElementById("all-labels").addEventListener("change", event => {graph.allLabels = event.target.checked; graph.style();});
  document.getElementById("search").addEventListener("input", event => {graph.search = event.target.value.trim().toLowerCase(); graph.clear();});
  document.getElementById("search").addEventListener("keydown", event => {if (event.key === "Enter") {event.preventDefault(); graph.searchFirst();}});
  document.getElementById("fit").addEventListener("click", () => graph.fit());
  document.getElementById("zoom-in").addEventListener("click", () => graph.zoom(1.25));
  document.getElementById("zoom-out").addEventListener("click", () => graph.zoom(.8));
  document.getElementById("theme-toggle").addEventListener("click", event => {
    const light = document.documentElement.dataset.theme !== "light"; document.documentElement.dataset.theme = light ? "light" : "dark";
    event.target.textContent = light ? "Dark theme" : "Light theme"; event.target.setAttribute("aria-label", "Switch to " + (light ? "dark" : "light") + " theme"); graph.style();
  });
  let player = null, results = null, ablations = null, compare = null, explainer = null;
  function tab(name) {
    const isGraph = name === "graph";
    document.getElementById("graph-panel").hidden = !isGraph;
    document.getElementById("placeholder").hidden = ["graph","how","player","results","ablations","compare"].includes(name);
    document.getElementById("player-panel").hidden = name !== "player";
    if (name === "player") {if (!player) {player = new window.TraversalPlayer(); window.VizApp.player = player;} player.activate();}
    else if (player) player.pause();
    document.getElementById("results-panel").hidden = name !== "results";
    document.getElementById("ablations-panel").hidden = name !== "ablations";
    if (name === "results" && !results) {results = new window.ResultsView(); window.VizApp.results = results;}
    if (name === "ablations" && !ablations) {ablations = new window.AblationView(); window.VizApp.ablations = ablations;}
    document.getElementById("compare-panel").hidden = name !== "compare";
    if (name === "compare") {if (!compare) {compare = new window.CompareView(); window.VizApp.compare = compare;} compare.activate();}
    else if (compare) compare.pause();
    document.getElementById("how-panel").hidden = name !== "how";
    if (name === "how") {if (!explainer) {explainer = new window.ExplainerView(); window.VizApp.explainer = explainer;} explainer.activate();}
    const titles={graph:["Graph Explorer","01 / EXPLORE"],how:["How EG-POT works","02 / METHOD"],player:["Traversal player","03 / PLAYBACK"],compare:["Compare methods","04 / COMPARE"],ablations:["Ablations","05 / COMPONENTS"],results:["Results","06 / EVALUATE"]};
    document.querySelector(".subtitle").textContent=titles[name][0];
    document.querySelector(".tab-note").textContent=titles[name][1];
    document.title="Online Boutique · "+titles[name][0];
    document.querySelectorAll("[data-tab]").forEach(button => {const active = button.dataset.tab === name; button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active)); if (active) document.getElementById("placeholder-title").textContent = button.textContent;});
    if (isGraph) {graph.network.redraw(); graph.fit();}
  }
  document.querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => tab(button.dataset.tab)));
  document.getElementById("back-to-graph").addEventListener("click", () => tab("graph"));
  showDetails(null); render(true);
  // Public UI controller for local inspection and future tabs; no network layer.
  window.VizApp = {graph, filters, selectNode: id => graph.select(id, true), showTab: tab};
})();
