import json

with open('bench/results/multi_system_eval.json') as f1, open('bench/results/multi_repo_benchmark.json') as f2:
    sys_eval = json.load(f1)
    repo_bench = json.load(f2)

print("=== 1. MULTI-SYSTEM DATA (TABLE I) ===")
for s in sys_eval['systems']:
    print(f"System: {s['name']}")
    print(f"  Langs: {s['langs']}")
    print(f"  LOC: {s['loc']}, Nodes: {s['nodes']}, Edges: {s['edges']}")
    print(f"  Throughput: {s['s_per_kloc']:.4f} s/kLOC, Build Time: {s['build_s']:.3f}s")
    print(f"  Layers: Lsyn={s['lsyn']}, Ldep={s['ldep']}, Lflow={s['lflow']}, Lsem={s['lsem']}, Lcontract={s['lcontract']}")
    print(f"  Contracts: {s['contracts']}, Skews: {s['skews']}, Collisions: {s['collisions']}")
    print(f"  Incremental: {s['incr_ms']:.1f}ms vs Full: {s['full_ms']:.1f}ms (Speedup: {s['speedup']:.1f}x)")

print("\n=== 2. RETRIEVAL BENCHMARK (TABLE II) ===")
for k, v in repo_bench['table2_retrieval_and_grafting'].items():
    print(f"Model: {k:25} | MRR@5: {v['MRR@5']:.3f} | Hits@1: {v['Hits@1']:5.1f}% | Hits@5: {v['Hits@5']:5.1f}% | Rec@10: {v['Context_Recall@10']:5.1f}% | Redundancy: {v['Token_Redundancy_%']:5.1f}%")

print("\n=== 3. LAYER ABLATIONS (TABLE II-B) ===")
for k, v in repo_bench['table2_ablations_section_7b'].items():
    print(f"Config: {k:20} | MRR@5: {v['MRR@5']:.3f} | Delta MRR: {v['Delta_MRR']:+6.3f} | Hits@1: {v['Hits@1']:5.1f}% | Rec@10: {v['Context_Recall@10']:5.1f}% | Delta Rec: {v['Delta_Recall']:+5.1f}% | Redundancy: {v['Token_Redundancy_%']:5.1f}%")

print("\n=== 4. CONTRACT ACCURACY (TABLE III) ===")
for k, v in repo_bench['table3_contract_layer'].items():
    print(f"Relation: {k:15} | Precision: {v.get('precision', 1.0):.4f} | Recall: {v.get('recall', 1.0):.4f} | F1: {v.get('f1', 1.0):.4f}")
