import sys, os, time, json
sys.path.insert(0, '.')
from multi_repo import WorkspaceCKGBuilder
import networkx as nx
import random
import yaml

def generate_advanced_html():
    print("Building full workspace graph...")
    ws_path = os.path.join('repos', 'online-boutique', 'workspace.yaml')
    original_cwd = os.getcwd()
    os.chdir(os.path.dirname(ws_path))
    try:
        with open('workspace.yaml') as f:
            cfg = yaml.safe_load(f)
        ws = WorkspaceCKGBuilder(cfg)
        ws.build()
        g = getattr(ws, 'workspace_graph', getattr(ws, 'graph', None))
    finally:
        os.chdir(original_cwd)
        
    if g is None:
        print("Error: Could not find graph.")
        return

    print(f"Graph built with {g.number_of_nodes()} nodes, {g.number_of_edges()} edges.")
    
    # We will extract a nice big subgraph: all services, contracts, and depth=2 around contracts
    contract_edges = []
    for u, v, d in g.edges(data=True):
        if any(isinstance(val, str) and val in ('IMPLEMENTS', 'CONSUMES', 'HTTP_CALLS') for val in d.values()):
            contract_edges.append((u, v, d))
    
    nodes_of_interest = set()
    for u, v, _ in contract_edges:
        nodes_of_interest.add(u)
        nodes_of_interest.add(v)
        
    expanded_nodes = set(nodes_of_interest)
    # Expand 2 hops
    for _ in range(2):
        current_expansion = set()
        for node in expanded_nodes:
            for neighbor in g.successors(node):
                current_expansion.add(neighbor)
            for predecessor in g.predecessors(node):
                current_expansion.add(predecessor)
        expanded_nodes.update(current_expansion)
        
    # Cap at ~600 nodes to keep browser performance smooth
    if len(expanded_nodes) > 600:
        other = list(expanded_nodes - nodes_of_interest)
        random.seed(42)
        expanded_nodes = nodes_of_interest.union(set(random.sample(other, 600 - len(nodes_of_interest))))
        
    subg = g.subgraph(list(expanded_nodes)).copy()
    print(f"Extracted subgraph with {subg.number_of_nodes()} nodes and {subg.number_of_edges()} edges.")

    # Prepare JSON data for Vis.js
    repo_colors = {
        'frontend': '#4285F4', # Blue (Go)
        'checkoutservice': '#0F9D58', # Green (Go)
        'emailservice': '#F4B400', # Yellow (Python)
        'recommendationservice': '#DB4437', # Red (Python)
        'paymentservice': '#ab47bc', # Purple (JS)
        'currencyservice': '#ab47bc',
        'cartservice': '#00bcd4', # Cyan (C#)
        'productcatalogservice': '#0F9D58',
        'shippingservice': '#0F9D58',
    }

    nodes_json = []
    edges_json = []

    for node_id, data in subg.nodes(data=True):
        repo = data.get('repo', 'unknown')
        color = repo_colors.get(repo, '#dddddd')
        shape = 'dot'
        if 'proto' in data.get('file', '').lower():
            color = '#ffffff'
            shape = 'diamond'
            
        label = data.get('name', str(node_id).split(':')[-1])
        if len(label) > 25:
            label = label[:22] + "..."
            
        size = 15
        if node_id in nodes_of_interest: size = 25
        if data.get('type') == 'service': size = 35
        
        nodes_json.append({
            "id": node_id,
            "label": label,
            "color": {"background": color, "border": "#333333"},
            "size": size,
            "shape": shape,
            "repo": repo,
            "file": data.get('file', 'N/A'),
            "node_type": data.get('type', 'unknown'),
            "full_name": data.get('name', str(node_id))
        })

    for u, v, data in subg.edges(data=True):
        edge_type = 'UNKNOWN'
        for val in data.values():
            if isinstance(val, str) and val in ('IMPLEMENTS', 'CONSUMES', 'HTTP_CALLS', 'CALLS', 'DEFINES', 'IMPORTS', 'DATA_FLOW'):
                edge_type = val
                break
        color = '#cccccc'
        width = 1
        dashes = False
        
        if edge_type == 'CONSUMES':
            color = '#ff5252'
            width = 3
        elif edge_type == 'IMPLEMENTS':
            color = '#69f0ae'
            width = 3
        elif edge_type == 'CALLS':
            color = '#40c4ff'
            width = 2
        elif edge_type == 'DEFINES':
            color = '#e0e0e0'
            dashes = True
            
        edges_json.append({
            "from": u,
            "to": v,
            "label": edge_type,
            "color": color,
            "width": width,
            "dashes": dashes,
            "font": {"size": 10, "color": "#666666", "align": "middle"}
        })

    # Generate HTML with advanced UI
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>GRAFT-CKG: Advanced Polyglot Graph</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style type="text/css">
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #ffffff; /* White background requested */
            display: flex;
            height: 100vh;
            color: #333333;
        }}
        #sidebar {{
            width: 350px;
            background-color: #f8f9fa;
            border-right: 1px solid #dee2e6;
            display: flex;
            flex-direction: column;
            box-shadow: 2px 0 5px rgba(0,0,0,0.05);
            z-index: 10;
        }}
        #controls {{
            padding: 20px;
            border-bottom: 1px solid #dee2e6;
        }}
        #info-panel {{
            padding: 20px;
            flex-grow: 1;
            overflow-y: auto;
        }}
        #mynetwork {{
            flex-grow: 1;
            height: 100%;
        }}
        h2, h3 {{ margin-top: 0; color: #1a73e8; }}
        .form-group {{ margin-bottom: 15px; }}
        label {{ display: block; margin-bottom: 5px; font-weight: bold; font-size: 14px; }}
        input[type="text"], select {{
            width: 100%;
            padding: 8px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            box-sizing: border-box;
        }}
        button {{
            background-color: #1a73e8;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 4px;
            cursor: pointer;
            width: 100%;
            font-weight: bold;
        }}
        button:hover {{ background-color: #1557b0; }}
        .info-item {{ margin-bottom: 10px; font-size: 14px; }}
        .info-label {{ font-weight: bold; color: #555; }}
        .info-value {{ word-break: break-all; font-family: monospace; background: #eee; padding: 2px 4px; border-radius: 3px; }}
        .legend {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; font-size: 12px; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .color-box {{ width: 12px; height: 12px; border-radius: 50%; border: 1px solid #333; }}
    </style>
</head>
<body>

<div id="sidebar">
    <div id="controls">
        <h2>GRAFT-CKG Explorer</h2>
        
        <div class="form-group">
            <label>🔍 RAG Search (Node Name/Keyword)</label>
            <input type="text" id="rag-search" placeholder="e.g. Checkout, recommend, grpc...">
        </div>
        
        <div class="form-group">
            <label>🎯 Multi-hop Traversal (from selection)</label>
            <select id="hop-select">
                <option value="0">0 Hops (Exact Selection)</option>
                <option value="1" selected>1 Hop</option>
                <option value="2">2 Hops</option>
                <option value="3">3 Hops</option>
                <option value="4">4 Hops (Deep Traversal)</option>
            </select>
        </div>
        
        <button onclick="applySearch()">Search & Highlight</button>
        <button onclick="resetGraph()" style="background-color: #6c757d; margin-top: 10px;">Reset View</button>
        
        <div class="legend">
            <div class="legend-item"><div class="color-box" style="background:#4285F4"></div> Go (Frontend)</div>
            <div class="legend-item"><div class="color-box" style="background:#0F9D58"></div> Go (Backend)</div>
            <div class="legend-item"><div class="color-box" style="background:#F4B400"></div> Python</div>
            <div class="legend-item"><div class="color-box" style="background:#ab47bc"></div> Node.js</div>
            <div class="legend-item"><div class="color-box" style="background:#00bcd4"></div> C#</div>
            <div class="legend-item"><div class="color-box" style="background:#ffffff; border-radius:0;"></div> Protobuf</div>
        </div>
    </div>
    
    <div id="info-panel">
        <h3>Node Information</h3>
        <div id="node-details">
            <p>Click on a node to view its detailed properties and connections.</p>
        </div>
    </div>
</div>

<div id="mynetwork"></div>

<script type="text/javascript">
    // Data from Python
    const rawNodes = {json.dumps(nodes_json)};
    const rawEdges = {json.dumps(edges_json)};
    
    const nodes = new vis.DataSet(rawNodes);
    const edges = new vis.DataSet(rawEdges);
    
    // Build adjacency list for fast hop traversal
    const adj = {{}};
    rawNodes.forEach(n => adj[n.id] = []);
    rawEdges.forEach(e => {{
        adj[e.from].push(e.to);
        adj[e.to].push(e.from); // undirected for traversal visibility
    }});

    const container = document.getElementById('mynetwork');
    const data = {{ nodes: nodes, edges: edges }};
    const options = {{
        nodes: {{ font: {{ color: '#333333' }} }},
        edges: {{ smooth: {{ type: 'continuous' }} }},
        physics: {{
            barnesHut: {{ gravitationalConstant: -3000, centralGravity: 0.3, springLength: 150 }},
            stabilization: {{ iterations: 200 }}
        }},
        interaction: {{ hover: true, tooltipDelay: 200 }}
    }};
    
    const network = new vis.Network(container, data, options);
    
    // RAG Search & Highlight
    function applySearch() {{
        const term = document.getElementById('rag-search').value.toLowerCase();
        const hops = parseInt(document.getElementById('hop-select').value);
        
        if (!term) return;
        
        let startNodes = rawNodes.filter(n => n.full_name.toLowerCase().includes(term) || n.repo.toLowerCase().includes(term)).map(n => n.id);
        
        if (startNodes.length === 0) {{
            alert("No nodes found matching keyword.");
            return;
        }}
        
        highlightNodes(startNodes, hops);
    }}
    
    function highlightNodes(startNodes, hops) {{
        let visibleNodes = new Set(startNodes);
        
        // BFS for hops
        let queue = [...startNodes];
        let currentHop = 0;
        
        // Simple level-based BFS
        for(let h=0; h<hops; h++) {{
            let nextQueue = [];
            queue.forEach(u => {{
                adj[u].forEach(v => {{
                    if (!visibleNodes.has(v)) {{
                        visibleNodes.add(v);
                        nextQueue.push(v);
                    }}
                }});
            }});
            queue = nextQueue;
        }}
        
        // Update styling
        const updateNodes = [];
        rawNodes.forEach(n => {{
            if (visibleNodes.has(n.id)) {{
                updateNodes.push({{id: n.id, color: Object.assign({{}}, n.color, {{opacity: 1.0}}), hidden: false}});
            }} else {{
                updateNodes.push({{id: n.id, color: Object.assign({{}}, n.color, {{opacity: 0.1}}), hidden: false}}); // fade out
            }}
        }});
        nodes.update(updateNodes);
        
        // Focus camera on the first start node
        network.focus(startNodes[0], {{scale: 1.2, animation: true}});
    }}
    
    function resetGraph() {{
        document.getElementById('rag-search').value = "";
        const updateNodes = rawNodes.map(n => ({{id: n.id, color: Object.assign({{}}, n.color, {{opacity: 1.0}}), hidden: false}}));
        nodes.update(updateNodes);
        network.fit({{animation: true}});
    }}

    // Node click event for detailed info
    network.on("click", function (params) {{
        if (params.nodes.length > 0) {{
            const nodeId = params.nodes[0];
            const nodeData = rawNodes.find(n => n.id === nodeId);
            
            // If they just clicked a node, also highlight its hops
            const hops = parseInt(document.getElementById('hop-select').value);
            highlightNodes([nodeId], hops);
            
            // Update side panel
            let html = `
                <div class="info-item"><div class="info-label">Node ID</div><div class="info-value">${{nodeData.id}}</div></div>
                <div class="info-item"><div class="info-label">Symbol Name</div><div class="info-value">${{nodeData.full_name}}</div></div>
                <div class="info-item"><div class="info-label">Type</div><div class="info-value">${{nodeData.node_type}}</div></div>
                <div class="info-item"><div class="info-label">Repository</div><div class="info-value">${{nodeData.repo}}</div></div>
                <div class="info-item"><div class="info-label">File</div><div class="info-value">${{nodeData.file}}</div></div>
            `;
            
            // Get connected edges
            const connectedEdges = rawEdges.filter(e => e.from === nodeId || e.to === nodeId);
            html += `<div class="info-item"><div class="info-label">Connected Edges (${{connectedEdges.length}})</div><ul>`;
            connectedEdges.slice(0, 10).forEach(e => {{
                const dir = e.from === nodeId ? '→ OUT' : '← IN';
                const other = e.from === nodeId ? e.to : e.from;
                const otherNode = rawNodes.find(n => n.id === other);
                html += `<li style="font-size:12px"><b>${{e.label}}</b> ${{dir}} to<br><i>${{otherNode.label}}</i></li>`;
            }});
            if (connectedEdges.length > 10) html += `<li style="font-size:12px">...and ${{connectedEdges.length - 10}} more</li>`;
            html += `</ul></div>`;
            
            document.getElementById('node-details').innerHTML = html;
        }} else {{
            // Clicked background
            document.getElementById('node-details').innerHTML = "<p>Click on a node to view its detailed properties and connections.</p>";
            resetGraph();
        }}
    }});

</script>
</body>
</html>
"""

    output_file = "advanced_polyglot_ui.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Advanced UI saved to {output_file}")

if __name__ == '__main__':
    generate_advanced_html()
