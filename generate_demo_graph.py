import sys, os, time
sys.path.insert(0, '.')
from multi_repo import WorkspaceCKGBuilder
import networkx as nx
from pyvis.network import Network
import random
import yaml

def generate_graph_html():
    print("Building full workspace graph...")
    # Properly construct the path as in eval script
    ws_path = os.path.join('repos', 'online-boutique', 'workspace.yaml')
    original_cwd = os.getcwd()
    os.chdir(os.path.dirname(ws_path))
    try:
        with open('workspace.yaml') as f:
            cfg = yaml.safe_load(f)
        ws = WorkspaceCKGBuilder(cfg)
        ws.build()
        # Ensure we can access the graph correctly. 
        # In run_multi_system_eval it accesses via ws.graph or similar. Let's look for the right attribute.
        g = getattr(ws, 'workspace_graph', getattr(ws, 'graph', None))
    finally:
        os.chdir(original_cwd)
        
    if g is None:
        print("Error: Could not find graph attribute on builder.")
        return

    print(f"Graph built with {g.number_of_nodes()} nodes, {g.number_of_edges()} edges.")
    
    # We want a manageable subgraph for the visualizer.
    # Let's extract nodes involved in contracts, plus their immediate neighbors.
    contract_edges = [(u, v, d) for u, v, d in g.edges(data=True) if any(val in ('IMPLEMENTS', 'CONSUMES', 'HTTP_CALLS') for val in d.values())]
    
    if not contract_edges:
        print("No contract edges found.")
        return
        
    nodes_of_interest = set()
    for u, v, _ in contract_edges:
        nodes_of_interest.add(u)
        nodes_of_interest.add(v)
        
    # Expand by 1 hop for context
    expanded_nodes = set(nodes_of_interest)
    for node in nodes_of_interest:
        for neighbor in g.successors(node):
            # Only add CALLS or DEFINES to keep it small
            for _, _, d in g.out_edges(node, data=True):
                if d.get('edge_type', '') in ('CALLS', 'DEFINES'):
                    expanded_nodes.add(neighbor)
        for predecessor in g.predecessors(node):
            for _, _, d in g.in_edges(predecessor, data=True):
                if d.get('edge_type', '') in ('CALLS', 'DEFINES'):
                    expanded_nodes.add(predecessor)

    # Subgraph
    subg = g.subgraph(list(expanded_nodes)).copy()
    print(f"Extracted subgraph with {subg.number_of_nodes()} nodes and {subg.number_of_edges()} edges.")
    
    # Optional: Keep it even smaller (max 100 nodes)
    if subg.number_of_nodes() > 150:
        print("Trimming graph...")
        # Keep all contract nodes, trim some expanded ones
        nodes_to_keep = set(nodes_of_interest)
        other_nodes = list(expanded_nodes - nodes_of_interest)
        random.seed(42)
        nodes_to_keep.update(random.sample(other_nodes, min(len(other_nodes), 100)))
        subg = g.subgraph(list(nodes_to_keep)).copy()

    # Pyvis setup
    net = Network(height="800px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=200)

    # Colors by repo/service
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

    # Add nodes
    for node_id, data in subg.nodes(data=True):
        repo = data.get('repo', 'unknown')
        color = repo_colors.get(repo, '#999999')
        if 'proto' in data.get('file', '').lower():
            color = '#ffffff' # White for protobuf contracts
            
        label = data.get('name', str(node_id).split(':')[-1])
        if len(label) > 25:
            label = label[:22] + "..."
            
        title = f"ID: {node_id}\nType: {data.get('type')}\nRepo: {repo}\nFile: {data.get('file')}"
        
        # Make contract nodes bigger
        size = 25 if node_id in nodes_of_interest else 15
        if data.get('type') == 'service': size = 35
        
        net.add_node(node_id, label=label, title=title, color=color, size=size)

    # Add edges
    for u, v, data in subg.edges(data=True):
        edge_type = data.get('edge_type', data.get('type', 'UNKNOWN'))
        
        color = '#666666'
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
        elif edge_type == 'DEFINES':
            color = '#b0bec5'
            dashes = True
            
        net.add_edge(u, v, title=edge_type, color=color, width=width, dashes=dashes)

    output_file = "polyglot_graph_demo.html"
    net.save_graph(output_file)
    print(f"Interactive graph saved to {output_file}")

if __name__ == '__main__':
    generate_graph_html()
