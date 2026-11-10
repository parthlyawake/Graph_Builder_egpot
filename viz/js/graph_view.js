(function () {
  "use strict";
  class GraphExplorer {
    constructor(data, onSelect, onCounts) {
      this.data = data; this.onSelect = onSelect; this.onCounts = onCounts;
      this.selected = null; this.hover = null; this.search = ""; this.allLabels = false;
      this.nodes = new vis.DataSet(); this.edges = new vis.DataSet();
      this.positions = this.layout();
      this.network = new vis.Network(document.getElementById("network"), {nodes: this.nodes, edges: this.edges}, {
        physics: false, autoResize: true, layout: {improvedLayout: false, randomSeed: 0},
        interaction: {hover: true, tooltipDelay: 200, hoverConnectedEdges: false, selectConnectedEdges: false},
        nodes: {shape: "dot", borderWidth: 1.5, chosen: false, font: {face: "Segoe UI", size: 12, strokeWidth: 3}},
        edges: {arrows: {to: {enabled: true, scaleFactor: .4}}, width: .7, chosen: false, smooth: false}
      });
      this.network.on("click", event => { if (event.nodes.length) this.select(event.nodes[0], false); else this.clear(); });
      this.network.on("hoverNode", event => { this.hover = event.node; this.style(); });
      this.network.on("blurNode", () => { this.hover = null; this.style(); });
      this.network.on("beforeDrawing", context => this.drawClusters(context));
    }
    layout() {
      const positions = new Map(); this.clusters = [];
      const services = this.data.graph.meta.services.map(s => s.name).filter(s => s !== "contracts");
      const centers = new Map(services.map((name, i) => {
        const angle = i / services.length * Math.PI * 2 - Math.PI / 2;
        return [name, {x: Math.cos(angle) * 1180, y: Math.sin(angle) * 900}];
      }));
      centers.set("contracts", {x: 0, y: 0});
      for (const [name, center] of centers) {
        const nodes = this.data.graph.nodes.filter(n => n.repo === name);
        this.clusters.push({name, ...center});
        nodes.forEach((node, i) => {
          if (name === "contracts") {
            const columns = 4, rows = Math.ceil(nodes.length / columns);
            positions.set(node.id, {x: (i % columns - (columns-1)/2)*150,
                                    y: (Math.floor(i/columns) - (rows-1)/2)*110});
            return;
          }
          const angle = i * Math.PI * (3 - Math.sqrt(5));
          const radius = 24 * Math.sqrt(i + 1);
          positions.set(node.id, {x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius});
        });
      }
      return positions;
    }
    drawClusters(context) {
      const light = document.documentElement.dataset.theme === "light";
      this.clusters.forEach(cluster => {
        const visible = this.visibleNodes.filter(n => n.repo === cluster.name);
        if (!visible.length) return;
        const radius = Math.max(115, ...visible.map(n => {const p = this.positions.get(n.id); return Math.hypot(p.x-cluster.x,p.y-cluster.y) + 38;}));
        context.beginPath(); context.arc(cluster.x, cluster.y, radius, 0, Math.PI * 2);
        context.fillStyle = this.rgba(this.data.colors.get(cluster.name), light ? .045 : .035); context.fill();
        context.strokeStyle = this.rgba(this.data.colors.get(cluster.name), .25); context.lineWidth = 1.5;
        context.setLineDash([6, 8]); context.stroke(); context.setLineDash([]);
        context.font = "600 " + Math.max(16, 10 / this.network.getScale()) + "px Segoe UI"; context.textAlign = "center";
        context.fillStyle = light ? "#526a82" : "#94a8bf";
        context.fillText(cluster.name === "contracts" ? "SHARED CONTRACTS" : cluster.name, cluster.x, cluster.y - radius + 22);
      });
    }
    rgba(hex, alpha) { return "rgba(" + [1,3,5].map(i => parseInt(hex.slice(i,i+2),16)).join(",") + "," + alpha + ")"; }
    render(filters, fit) {
      this.visibleNodes = this.data.graph.nodes.filter(n => filters.types.has(n.type) && filters.services.has(n.repo));
      this.visibleIds = new Set(this.visibleNodes.map(n => n.id));
      this.visibleEdges = this.data.graph.edges.filter(e => filters.relations.has(e.relation) && this.visibleIds.has(e.source) && this.visibleIds.has(e.target));
      this.nodes.clear(); this.edges.clear();
      this.nodes.add(this.visibleNodes.map(n => {
        const degree = this.data.outgoing.get(n.id).length + this.data.incoming.get(n.id).length;
        return {id: n.id, ...this.positions.get(n.id), label: "", size: (this.data.contract(n) ? 15 : 9) + Math.min(9, Math.log1p(degree)*1.7), shape: this.data.contract(n) ? "diamond" : "dot"};
      }));
      this.edges.add(this.visibleEdges.map(e => ({id: e.viewId, from: e.source, to: e.target})));
      if (this.selected && !this.visibleIds.has(this.selected)) {this.selected = null; this.onSelect(null);}
      this.style(); this.onCounts(this.visibleNodes.length, this.visibleEdges.length);
      if (fit) this.fit();
    }
    style() {
      if (!this.visibleNodes) return;
      const light = document.documentElement.dataset.theme === "light";
      const matches = new Set(this.data.graph.nodes.filter(n => !this.search || (n.id + " " + n.name).toLowerCase().includes(this.search)).map(n => n.id));
      const neighborhood = new Set(this.selected ? [this.selected] : []);
      if (this.selected) [...this.data.outgoing.get(this.selected), ...this.data.incoming.get(this.selected)].forEach(e => {neighborhood.add(e.source); neighborhood.add(e.target);});
      const active = id => (!this.selected || neighborhood.has(id)) && (!this.search || matches.has(id));
      this.nodes.update(this.visibleNodes.map(n => {
        const color = this.data.colors.get(n.repo), opacity = active(n.id) ? 1 : .12;
        const focus = n.id === this.selected || n.id === this.hover;
        const match = this.search && matches.has(n.id);
        const label = this.data.contract(n) ? n.name.replace(/([a-z])([A-Z])/g, "$1\n$2") : n.name;
        return {id: n.id, label: this.allLabels || this.data.contract(n) || focus ? label : "",
          borderWidth: focus ? 4 : this.data.contract(n) ? 2.5 : 1,
          color: {background: this.rgba(color, opacity), border: focus || match ? (light ? "#684b00" : "#fff2ad") : this.rgba(color, opacity)},
          font: {color: active(n.id) ? (light ? "#243c54" : "#dbe7f4") : this.rgba(light ? "#243c54" : "#dbe7f4", .12), strokeColor: light ? "#f7fafc" : "#0d1622"}};
      }));
      this.edges.update(this.visibleEdges.map(e => ({id:e.viewId, width: this.selected && (e.source === this.selected || e.target === this.selected) ? 1.8 : .7,
        color: {color: light ? "#61778e" : "#728ba7", opacity: active(e.source) && active(e.target) ? .5 : .055}})));
      const status = document.getElementById("search-status");
      status.classList.toggle("active", !!this.search);
      status.textContent = this.search ? [...matches].filter(id => this.visibleIds.has(id)).length + " visible matches · Enter to focus first" : "";
      this.network.redraw();
    }
    select(id, focus) {
      if (!this.data.byId.has(id)) return;
      if (!this.visibleIds.has(id) && this.reveal) this.reveal(id);
      this.selected = id; this.onSelect(this.data.byId.get(id)); this.style();
      this.network.selectNodes([id], false);
      if (focus) this.network.focus(id, {scale: 1.1, animation: {duration: 300, easingFunction: "easeInOutQuad"}});
    }
    clear() {this.selected = null; this.network.unselectAll(); this.onSelect(null); this.style();}
    fit() {this.network.fit({animation: false});}
    zoom(multiplier) {this.network.moveTo({scale: this.network.getScale() * multiplier, animation: false});}
    searchFirst() {
      const match = this.data.graph.nodes.find(n => this.search && (n.id + " " + n.name).toLowerCase().includes(this.search));
      if (match) this.select(match.id, true);
    }
  }
  window.GraphExplorer = GraphExplorer;
})();
