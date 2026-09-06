# GRAFT-CKG: 4-Layer Code Knowledge Graph Engine

Implementation of the **GRAFT-CKG** framework for whole-repository code knowledge graph construction, multi-layer explainability, and deterministic context retrieval for software engineering agents.

---

## 1. Project Structure

```
graft-ckg/
├── graft_ckg.py        # Core 4-Layer CKG Engine (Lsyn, Ldep, Lflow, Lsem)
├── serve_ckg.py        # Clean Interactive Web Workbench (Localhost:8080)
├── eval_ckg.py         # Automated Evaluation Suite (Tables I & II replication)
├── visualize.py        # Multi-format Exporter (Gephi Lite, Cosmograph, HTML)
├── requirements.txt    # Minimal Python dependencies
├── presentation_guide.md # Paper breakdown & presentation reference
├── README.md           # Instructions & Documentation
└── math_app/           # Lightweight sample codebase for instant testing
```

---

## 2. Setup on Any Device (Windows, Mac, Linux)

### Prerequisites
- Python 3.9+ (Python 3.10, 3.11, 3.12, 3.13 supported)
- Git (optional, for cloning test repositories)

### Installation (1-Line Command)
```bash
pip install -r requirements.txt
```

---

## 3. Quick Start Commands

### A. Run on Any Python Repository
```bash
python graft_ckg.py /path/to/any/python/repo --verify
```

### B. Interactive Query Shell (Fast Exploration)
```bash
python graft_ckg.py /path/to/any/python/repo --interactive
```
Inside the interactive shell:
- `explain <symbol>`: Full 4-layer breakdown (`Lsyn`, `Ldep`, `Lflow`, `Lsem`).
- `rag <query>`: Natural language semantic search & Subtree Grafting.
- `adj <node_id>`: Adjacency traversal.
- `verify`: Health check & call resolution statistics.

### C. Direct CLI Queries
```bash
# 1. Multi-Layer Explanation
python graft_ckg.py /path/to/repo --explain "ClassOrFunctionName"

# 2. Natural Language RAG Query
python graft_ckg.py /path/to/repo --rag "parse authorization token"

# 3. Layer-Filtered Adjacency
python graft_ckg.py /path/to/repo --adjacency "target_node_id" --layers Ldep Lflow
```

### D. Launch Interactive Visual Workbench (Browser UI)
```bash
# Launch interactive graph workbench on localhost:8080
python serve_ckg.py math_app
# Or on any large repository:
python serve_ckg.py /path/to/any/python/repo
```
Features:
- Pure white UI aesthetic with circular nodes and directed edges
- Node selection with bottom-right floating pop-up inspector (shows qualified name, file, lines, docstrings, source slice)
- $N$-Hop BFS neighborhood isolation (1-hop, 2-hop, 3-hop) with background dimming/shading
- Static topology locking (zero perpetual movement)

---

## 4. Evaluation & Benchmark Suite

Replicates the experimental evaluation protocols from Table I and Table II of the GRAFT-CKG paper:
```bash
# Run unit verification & downstream retrieval benchmark
python eval_ckg.py

# Or evaluate a specific custom repository
python eval_ckg.py --repo /path/to/any/repo
```

Metrics reported:
- **MRR@5** (Mean Reciprocal Rank)
- **Hits@1** & **Hits@5** Accuracy
- **Context Recall@10**
- **Token Redundancy Ratio**
- **Extraction Latency** (s/kLOC)

---

## 5. Visualization

Export your graph to standard formats for online or offline viewing:
```bash
# 1. Export graph from CKG builder
python graft_ckg.py /path/to/repo --export my_graph.graphml

# 2. Generate web-ready formats
python visualize.py my_graph.graphml --output my_viewer.html
```

### Supported Viewers:
1. **[Gephi Lite](https://gephi.org/gephi-lite/):** Drag & drop `my_graph.gexf` or `my_graph.graphml`.
2. **[Cosmograph](https://cosmograph.app/run):** Drag & drop `my_graph.json` (60 FPS GPU WebGL rendering).
3. **Local Browser:** Double-click `my_viewer.html` for instant offline D3 physics visualization.
