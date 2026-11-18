(function () {
  "use strict";
  const graph = window.VIZ_GRAPH;
  if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    window.VizData = {error: "Local graph data is missing. Run python -B -m bench.export_viz_graph, then reopen this page."};
    return;
  }
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  const outgoing = new Map(graph.nodes.map(n => [n.id, []]));
  const incoming = new Map(graph.nodes.map(n => [n.id, []]));
  graph.edges.forEach((edge, index) => {
    edge.viewId = "e" + index;
    if (outgoing.has(edge.source)) outgoing.get(edge.source).push(edge);
    if (incoming.has(edge.target)) incoming.get(edge.target).push(edge);
  });
  const compare = (a, b) => a.relation.localeCompare(b.relation) || a.source.localeCompare(b.source) || a.target.localeCompare(b.target) || a.key.localeCompare(b.key);
  [...outgoing.values(), ...incoming.values()].forEach(edges => edges.sort(compare));
  window.VizData = {graph, byId, outgoing, incoming, queries: window.VIZ_QUERIES || [],
    colors: new Map(graph.meta.services.map(s => [s.name, s.color])),
    contract: n => n.type.includes("contract") || n.type === "http_endpoint",
    element(tag, className, text) { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; }
  };
})();
