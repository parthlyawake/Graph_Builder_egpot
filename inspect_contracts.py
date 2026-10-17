import sys; sys.path.insert(0, '.')
from multi_repo import WorkspaceCKGBuilder
import yaml

with open('repos/online-boutique/workspace.yaml') as f:
    cfg = yaml.safe_load(f)

ws = WorkspaceCKGBuilder(cfg)
ws.build()
g = ws.workspace_graph

contracts = [(u,v,d) for u,v,d in g.edges(data=True) if d.get('edge_type','') in ('IMPLEMENTS','CONSUMES', 'HTTP_CALLS')]
print(f'Contract edges: {len(contracts)}')

# Also find some CALLS edges to provide surrounding context
calls = [(u,v,d) for u,v,d in g.edges(data=True) if d.get('edge_type','') == 'CALLS']

print("\n--- CONTRACT EDGES ---")
for u,v,d in contracts:
    print(f"{d['edge_type']}: {u} -> {v}")
    
print("\n--- SAMPLE CALLS EDGES ---")
for u,v,d in calls[:5]:
    print(f"{d['edge_type']}: {u} -> {v}")
