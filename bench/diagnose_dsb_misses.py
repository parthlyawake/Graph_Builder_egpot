"""Post-hoc exploratory replay and beam diagnosis of the locked DeathStarBench misses."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import networkx as nx

from bench import egpot_multi_eval as locked
from bench.analyze_dsb_distance import RESULTS, markdown_table
from bench.analyze_dsb_final import load_record
from eg_pot import CandidateStep, PathState, non_dominated_sort


STATUS = "post-hoc exploratory"
OBJECTIVES = ("relevance", "hop_efficiency", "contract_consistency", "entropy")
CLASSES = {
    "a": "Pruned by width-4 selection",
    "b": "Blocked by edge eligibility",
    "c": "Never a candidate because a path predecessor was not returned",
    "d": "Other",
}
EVIDENCE = Path(r"C:\dev\egpot_repos\labels_draft")
SOURCE_TABLES = {"dsb_social": "socialnetwork_source_evidence.md",
                 "dsb_media": "medianetwork_source_evidence.md"}
SOURCE_REV = "6ecb09706140f8730b5385c08f1386c654c3c526"
BUDGET = 40


def retrieve(retriever, label, *, trace=None):
    """Keep the method's request limited to the frozen query, start and budget."""
    return retriever.retrieve(query=label["query"], start_node=label["start_node"],
                              node_budget=BUDGET, trace=trace).discovery_order


def require_equal(actual, expected, identity):
    if actual != expected:
        difference = next((i for i, (a, b) in enumerate(zip(actual, expected), 1) if a != b),
                          min(len(actual), len(expected)) + 1)
        raise ValueError(f"{identity}: replay differs at returned rank {difference}. "
                         f"Replayed {len(actual)}, saved {len(expected)}. Diagnosis aborted.")


def verify_replays(cohorts):
    checked = {}
    for app, cohort in cohorts.items():
        rows, retriever = cohort["rows"], cohort["retriever"]
        for row in rows:
            require_equal(retrieve(retriever, row["label"]), row["returned_nodes"], f"{app}/{row['id']}")
        checked[app] = len(rows)
    return checked


def load_cohorts():
    head = locked.git("rev-parse", "HEAD")
    locked.verify_dsb_frozen_code(head)
    for path in ("eg_pot.py", "bench/egpot_eval.py", "bench/egpot_multi_eval.py"):
        if locked.git("diff", "--name-only", "6ba6e1cf", "--", path):
            raise ValueError(f"Working-tree replay code differs from the locked run: {path}")
    cohorts = {}
    for app, count in (("dsb_social", 28), ("dsb_media", 18)):
        repo = locked.REGISTRY[app]
        path = RESULTS / f"{app}_final_6ba6e1cf.json"
        rows, identity = load_record(path, app, repo)
        data = locked.read_json(path)
        configs = data["configs"]
        if configs["edge_policy"] != locked.dsb_settings(locked.load_settings())["edge_policy"]:
            raise ValueError(f"{app}: unexpected edge policy")
        spec = locked.spec_at(configs["main"]["egpot_full"], BUDGET)
        config = spec["config"]
        if (config["beam_width"], config["seed"], config["use_pareto"], config["use_mcts"],
                spec["choke_point"]) != (4, 0, True, False, True):
            raise ValueError(f"{app}: unexpected beam, seed, objective selection or choke setting")
        main = [row for row in rows if (row["experiment"], row["method"], row["node_budget"], row["seed"])
                == ("main", "egpot_full", BUDGET, 0)]
        if len(main) != count:
            raise ValueError(f"{app}: expected {count} replay rows")
        locked.initialize_worker(repo.graph, locked.DSB_EDGE_POLICY)
        retriever = locked.make_engine("egpot_full", spec)
        cohorts[app] = {"rows": main, "retriever": retriever, "identity": identity, "spec": spec}
    return cohorts


def full_trace(retriever, row):
    """Observe the frozen trace callback before its 60-candidate display cap."""
    engine = retriever.engine
    rounds = []
    original = engine._trace_round

    def observe(frontier, steps, vectors, details, selected, new_nodes, collected, number):
        output = original(frontier, steps, vectors, details, selected, new_nodes, collected, number)
        fronts = non_dominated_sort(vectors)
        front_by_index = {idx: rank for rank, front in enumerate(fronts, 1) for idx in front}
        preceding = collected - len(new_nodes)
        rounds.append({
            "round": number, "frontier": frontier, "fronts": fronts, "selected": selected[:],
            "width_order": engine._select_top_indices(steps, vectors, engine.config.beam_width),
            "new_nodes": new_nodes, "collected_before": preceding, "collected_after": collected,
            "candidates": [{**asdict(step), "vector": list(vector), "front": front_by_index[idx],
                            "state_id": details[idx]["state_id"]}
                           for idx, (step, vector) in enumerate(zip(steps, vectors, strict=True))],
        })
        return output

    trace = {}
    engine._trace_round = observe
    try:
        actual = retrieve(retriever, row["label"], trace=trace)
    finally:
        del engine._trace_round
    require_equal(actual, row["returned_nodes"], row["id"] + " traced")
    return {"rounds": rounds, "stop_reason": trace["steps"][-1]["reason"]}


def edge_options(view, origin, target, relation=None):
    graph = view.graph
    admitted = set(view.neighbors(origin))
    result = []
    for direction, (u, v) in (("out", (origin, target)), ("in", (target, origin))):
        for key, data in graph.get_edge_data(u, v, default={}).items():
            name = data.get("relation", "LINK")
            if relation is not None and name != relation:
                continue
            allowed = (target, name, direction, key) in admitted
            if allowed:
                reason, code = "eligible", "eg_pot.py:171–192"
            elif name in view.edge_policy.excluded_relations:
                reason, code = "relation excluded", "eg_pot.py:175–185"
            elif (view.use_choke_point and direction == "in" and name == "DEFINES_RPC"
                  and view.node_type(origin) == "rpc_contract"):
                reason, code = "incoming DEFINES_RPC at rpc_contract", "eg_pot.py:184–186"
            else:
                reason, code = "other eligibility rule", "eg_pot.py:171–192"
            result.append({"from_node": origin, "to_node": target, "from_type": view.node_type(origin),
                           "to_type": view.node_type(target), "raw_source": u, "raw_target": v,
                           "direction": direction, "relation": name, "edge_key": key,
                           "layer": data.get("layer", ""), "eligible": allowed,
                           "contract_match_withheld": name in view.edge_policy.no_contract_match_relations,
                           "rule": reason, "code": code})
    return sorted(result, key=lambda e: (not e["eligible"], e["relation"], e["direction"], str(e["edge_key"])))


def gold_walk(view, label):
    start, contract, handler = (label[k] for k in ("start_node", "contract_node", "handler_node"))
    return [[e for e in edge_options(view, u, v, relation) if e["direction"] == direction]
            for u, v, relation, direction in ((start, contract, "CONSUMES", "out"),
                                               (contract, handler, "IMPLEMENTS", "in"))]


def shortest_path(view, label, gold, walk):
    start = label["start_node"]
    graph = view.graph.to_undirected(as_view=True)
    if gold not in graph or not nx.has_path(graph, start, gold):
        return None
    ranking = lambda nodes: (sum(not any(e["eligible"] for e in edge_options(view, u, v))
                                 for u, v in zip(nodes, nodes[1:])), tuple(nodes))
    paths = nx.all_shortest_paths(graph, start, gold)
    nodes = min(paths, key=ranking)
    canonical = walk[:1] if gold == label["contract_node"] else walk
    if len(nodes) - 1 == len(canonical) and all(any(e["eligible"] for e in hop) for hop in canonical):
        edges = [next(e for e in hop if e["eligible"]) for hop in canonical]
    else:
        edges = [edge_options(view, u, v)[0] for u, v in zip(nodes, nodes[1:])]
    return {"nodes": [start, *(e["to_node"] for e in edges)], "edges": edges, "hops": len(edges)}


def classify(target, trace, eligible_graph, start, returned, path):
    offered = [(r, idx) for r in trace["rounds"] for idx, c in enumerate(r["candidates"])
               if c["to_node"] == target]
    if offered:
        for round_, idx in offered:
            # Any top-four offer omitted only when the remaining global budget
            # ran out is a separate stop mechanism.
            if idx in round_["width_order"]:
                return "d", round_["round"], offered
        return "a", offered[0][0]["round"], offered
    if target in eligible_graph and not nx.has_path(eligible_graph, start, target):
        return "b", None, offered
    if path and any(node not in returned for node in path["nodes"][1:-1]):
        return "c", None, offered
    return "d", None, offered


def objective_ranks(vectors, idx):
    return {name: 1 + sum(row[j] > vectors[idx][j] for row in vectors)
            for j, name in enumerate(OBJECTIVES)}


def gate_round(trace, origin, target):
    entries = [(r, idx) for r in trace["rounds"] for idx, c in enumerate(r["candidates"])
               if c["from_node"] == origin and c["to_node"] == target]
    return {"offered_rounds": sorted({r["round"] for r, _ in entries}),
            "selected_rounds": sorted({r["round"] for r, idx in entries if idx in r["selected"]})}


def compare_offer(engine, round_, idx, target, returned):
    candidates = round_["candidates"]
    vectors = [tuple(c["vector"]) for c in candidates]
    vector = vectors[idx]
    kept = []
    for other in round_["selected"]:
        winner = candidates[other]
        kept.append({"index": other, "node": winner["to_node"], "vector": winner["vector"],
                     "front": winner["front"],
                     "lower_objectives_for_missing": [name for name, a, b
                         in zip(OBJECTIVES, vector, vectors[other]) if a < b]})
    steps = [CandidateStep(**{k: c[k] for k in CandidateStep.__dataclass_fields__}) for c in candidates]
    flips = {}
    rank_before = engine._select_top_indices(steps, vectors, len(steps)).index(idx) + 1
    rank_after = {}
    for objective in ("hop_efficiency", "entropy"):
        j = OBJECTIVES.index(objective)
        adjusted = [tuple(0 if i == j else x for i, x in enumerate(v)) for v in vectors]
        order = engine._select_top_indices(steps, adjusted, len(steps))
        rank_after[objective] = order.index(idx) + 1
        chosen = order[:engine.config.beam_width]
        prior = set(returned[:round_["collected_before"]])
        reaches = False
        for i in chosen:
            prior.add(steps[i].to_node)
            if steps[i].to_node == target:
                reaches = True
                break
            if len(prior) >= BUDGET:
                break
        flips[objective] = reaches
    return {"round": round_["round"], "index": idx, "candidate": candidates[idx],
            "objective_ranks": objective_ranks(vectors, idx), "kept": kept,
            "selection_rank": rank_before, "selection_rank_if_objective_equalized": rank_after,
            "selected_if_objective_equalized_this_round": flips}


def local_profile(engine, label, walk):
    start = label["start_node"]
    query = label["query"]
    root = PathState([start], [], {start: 0}, {}, {start})
    steps = engine._candidate_steps(query, root)
    evidence = next((edge for edge in walk[0] if edge["eligible"]), None)
    result = {"round_1_candidates": len(steps), "contract_tip_handler": None}
    if evidence:
        entry = next(step for step in steps if (step.to_node, step.edge_key, step.direction)
                     == (evidence["to_node"], evidence["edge_key"], evidence["direction"]))
        state = root.extend(entry)
        options = engine._candidate_steps(query, state)
        vectors = [engine.candidate_vector(query, state, step) for step in options]
        for idx, step in enumerate(options):
            if (step.to_node == label["handler_node"] and step.relation == "IMPLEMENTS"
                    and step.direction == "in"):
                result["contract_tip_handler"] = {
                    "candidates": len(options), "vector": list(vectors[idx]),
                    "ranks": objective_ranks(vectors, idx)}
                break
    return result


def source_row(app, label, table):
    method = label["contract_node"].rsplit(".", 1)[-1]
    handler = label["handler_node"].rsplit(".", 1)[-1]
    caller = label["start_node"].rsplit(".", 1)[-1]
    rows = [line.split("|") for line in table.splitlines() if line.startswith("| `")]
    matches = [row for row in rows if len(row) >= 8 and row[3].strip().endswith(f".{method}`")
               and f"::{handler}`" in row[5] and f"::{caller}`" in row[4]]
    if len(matches) != 1:
        return None
    match = matches[0]
    return {"table": SOURCE_TABLES[app], "method": match[3].strip(" `"),
            "caller": match[4].strip(), "handler": match[5].strip(),
            "idl": match[6].strip(), "registration": match[7].strip()}


def diagnose_app(app, cohort, previous, table):
    rows, retriever = cohort["rows"], cohort["retriever"]
    view = retriever.graph_view
    graph = view.graph
    degrees = graph.to_undirected(as_view=True).degree
    eligible_graph = nx.DiGraph()
    eligible_graph.add_nodes_from(graph)
    eligible_graph.add_edges_from((node, target) for node in graph for target, *_ in view.neighbors(node))
    walks = {row["id"]: gold_walk(view, row["label"]) for row in rows}
    controls = [row for row in rows if row["hit"] and all(walks[row["id"]])
                and nx.shortest_path_length(graph.to_undirected(as_view=True), row["label"]["start_node"],
                                            row["label"]["handler_node"]) == 2]
    traces, misses = {}, []
    for row in rows:
        if row["hit"]:
            continue
        label, query_id = row["label"], row["id"]
        start, contract, handler = (label[k] for k in ("start_node", "contract_node", "handler_node"))
        trace = full_trace(retriever, row)
        traces[query_id] = trace
        walk = walks[query_id]
        control = min(controls, key=lambda c: (
            c["label"]["start_node"] != start, c["type"] != row["type"],
            abs(degrees[c["label"]["start_node"]] - degrees[start]),
            abs(degrees[c["label"]["contract_node"]] - degrees[contract]), c["id"]))
        cp = control["label"]
        control_data = {"id": control["id"], "type": control["type"], "start_degree": degrees[cp["start_node"]],
                        "contract_degree": degrees[cp["contract_node"]],
                        **local_profile(retriever.engine, cp, walks[control["id"]])}
        profile = local_profile(retriever.engine, label, walk)
        evidence = source_row(app, label, table)
        for role, target in (("contract", contract), ("handler", handler)):
            if target in row["returned_nodes"]:
                continue
            path = shortest_path(view, label, target, walk)
            category, round_number, offered = classify(
                target, trace, eligible_graph, start, set(row["returned_nodes"]), path)
            missing_builder = handler not in graph or not walk[1]
            misses.append({
                "app": app, "id": query_id, "type": row["type"], "start": start,
                "gold": target, "role": role, "shortest_path": path,
                "gold_walk": walk, "classification": category, "round": round_number,
                "path_trace": [gate_round(trace, u, v) for u, v in zip(path["nodes"], path["nodes"][1:])]
                if path else [],
                "gold_offers": [compare_offer(retriever.engine, r, idx, target, row["returned_nodes"])
                                for r, idx in offered],
                "handler_offers": [{"round": r["round"], "index": idx,
                                    "ranks": objective_ranks([c["vector"] for c in r["candidates"]], idx)}
                                   for r in trace["rounds"] for idx, c in enumerate(r["candidates"])
                                   if c["to_node"] == handler],
                "previous": previous[query_id, target], "start_degree": degrees[start],
                "contract_degree": degrees[contract], "comparison_profile": profile, "control": control_data,
                "source_evidence": evidence, "source_verified_builder_gap": missing_builder if evidence else None,
            })
    return traces, misses
def analyze():
    cohorts = load_cohorts()
    checks = verify_replays(cohorts)
    prior = locked.read_json(RESULTS / "dsb_distance_analysis.json")["egpot_full_budget_40_misses"]
    previous = {(r["id"], r["missing_gold_id"]): r["frontier_or_pruned"] for r in prior}
    all_traces, misses, source_hashes = {}, [], {}
    for app, cohort in cohorts.items():
        path = EVIDENCE / SOURCE_TABLES[app]
        table = path.read_text(encoding="utf-8")
        if SOURCE_REV not in table:
            raise ValueError(f"Source evidence revision mismatch: {path}")
        source_hashes[app] = locked.sha256(path)
        traces, app_misses = diagnose_app(app, cohort, previous, table)
        all_traces[app] = traces
        misses.extend(app_misses)
    if len(misses) != 16 or sum(map(len, all_traces.values())) != 9:
        raise ValueError("Unexpected set of misses")
    if any(row["source_evidence"] is None for row in misses):
        raise ValueError("A missed link could not be matched uniquely to its source evidence row")
    counts = {}
    for scope in (*cohorts, "pooled"):
        counts[scope] = dict.fromkeys(CLASSES, 0)
        for miss in misses:
            if scope in (miss["app"], "pooled"):
                counts[scope][miss["classification"]] += 1
    summary = {"width_pruned": counts["pooled"]["a"], "edge_rule_blocked": counts["pooled"]["b"],
               "builder_gap": sum(m["source_verified_builder_gap"] for m in misses)}
    for objective in ("entropy", "hop_efficiency"):
        summary[f"{objective}_handler_rank_improvements"] = sum(
            m["role"] == "handler" and any(
                o["selection_rank_if_objective_equalized"][objective] < o["selection_rank"]
                for o in m["gold_offers"]) for m in misses)
        summary[f"{objective}_handler_selection_flips"] = sum(
            m["role"] == "handler" and m["classification"] == "a"
            and any(o["selected_if_objective_equalized_this_round"][objective] for o in m["gold_offers"])
            for m in misses)
    return {"analysis_type": STATUS, "replay_counts": checks,
            "inputs": {app: {**c["identity"], "effective_spec": c["spec"]} for app, c in cohorts.items()},
            "source_evidence_sha256": source_hashes, "objective_order": OBJECTIVES,
            "classification_counts": counts, "misses": misses, "traces": all_traces,
            "evidence_support": summary}


def vector(values):
    return "(" + ", ".join(f"{v:.5f}" for v in values) + ")"


def edge_text(edge):
    arrow = "→" if edge["direction"] == "out" else "←"
    return (f"`{edge['from_node']}` ({edge['from_type']}) {arrow}{edge['relation']}{arrow} "
            f"`{edge['to_node']}` ({edge['to_type']}) [{edge['rule']}, `{edge['code']}`]")


def ranks(profile):
    handler = profile["contract_tip_handler"]
    return "/".join(map(str, handler["ranks"].values())) if handler else "—"


def markdown(report):
    lines = [f"# DeathStarBench miss diagnosis ({STATUS})", "",
             "All 46 discovery-order lists matched the locked rows exactly before tracing. "
             "The nine traced lists matched again. The JSON contains every frontier path, scored "
             "candidate, objective vector, Pareto front and actual selection with no display cap.", "",
             f"## Miss classification ({STATUS})", ""]
    lines += markdown_table(["App", *CLASSES], (
        (app, *(counts[k] for k in CLASSES)) for app, counts in report["classification_counts"].items()))
    lines.extend([*(f"- **{key}** {name}" for key, name in CLASSES.items()), "",
                  "A candidate in the top four can still be omitted if the global budget is reached "
                  "during the round. Category (a) requires the target to have been offered, with "
                  "every offer below width four. Category (b) requires that no eligible route exists. "
                  "Category (c) identifies a missing predecessor on the reported shortest path.", "",
                  f"## Path and eligibility ({STATUS})", "",
                  "Forward and backward arrows describe the stored edge direction relative to the "
                  "walk. Shortest paths are raw undirected paths. Ties prefer the canonical gold "
                  "walk when equally short and eligible, then an eligible path and stable node IDs. "
                  "The eligibility column uses `GraphView.neighbors`. The relation exclusion check "
                  "and incoming RPC rule are in `eg_pot.py:171–192`. Policy D withholds a score "
                  "in `contract_consistency` at `eg_pot.py:359–368`.", "",
                  "```python",
                  "if (self.use_choke_point and relation == \"DEFINES_RPC\"",
                  "        and self.node_type(n) == \"rpc_contract\"):",
                  "    continue",
                  "```", ""])
    lines += markdown_table(["Query", "Type", "Start", "Missing ID", "Hops", "Path eligibility",
                             "Rounds offered per hop", "Class / round"], (
        (m["id"], m["type"], f"`{m['start']}`", f"{m['role']} `{m['gold']}`",
         m["shortest_path"]["hops"], "<br>".join(edge_text(e) for e in m["shortest_path"]["edges"]),
         " → ".join(",".join(map(str, gate["offered_rounds"])) or "never"
                    for gate in m["path_trace"]), f"{m['classification']} / {m['round'] or '—'}")
        for m in report["misses"]))
    lines.extend([f"## Five previously beyond-frontier cases ({STATUS})", "",
                  "A successful control from the same app has the same canonical edge types for "
                  "every row. Eligibility of a reverse IMPLEMENTS hop does not depend on the "
                  "query. The RPC choke applies to incoming DEFINES_RPC from an rpc_contract.", ""])
    lines += markdown_table(["Query", "Reverse IMPLEMENTS", "Choke block", "Contract match withheld",
                             "Contract offered / selected rounds", "Successful control with same eligible edge types"], (
        (m["id"], "eligible" if any(e["eligible"] for e in m["gold_walk"][1]) else "blocked or absent",
         "yes" if any("DEFINES_RPC" in e["rule"] for e in m["gold_walk"][1]) else "no",
         "yes" if any(e["contract_match_withheld"] for e in m["gold_walk"][1]) else "no",
         f"{m['path_trace'][0]['offered_rounds']} / {m['path_trace'][0]['selected_rounds']}",
         m["control"]["id"]) for m in report["misses"] if m["previous"] == "beyond returned frontier"))
    lines.extend([f"## Successful depth-2 controls ({STATUS})", "",
                  "Controls share the canonical CONSUMES / reverse IMPLEMENTS edges. Selection "
                  "prefers the same start and query type, then nearest start and contract degrees. "
                  "To compare both queries even when a contract was pruned, the handler rank uses "
                  "all eligible extensions of the canonical contract-tip path in isolation. "
                  "Observed global ranks for the affected runs are in the JSON. Rank 1 is best, "
                  "with ties sharing ranks. Order is relevance / hop efficiency / contract consistency / entropy.", ""])
    by_query = {m["id"]: m for m in report["misses"]}
    lines += markdown_table(["Miss", "Control", "Start degree miss / control",
                             "Contract degree miss / control", "Round 1 candidates miss / control",
                             "Handler objective ranks miss / control"], (
        (m["id"], c["id"], f"{m['start_degree']} / {c['start_degree']}",
         f"{m['contract_degree']} / {c['contract_degree']}",
         f"{p['round_1_candidates']} / {c['round_1_candidates']}", f"{ranks(p)} vs {ranks(c)}")
        for m in by_query.values() for c, p in [(m["control"], m["comparison_profile"])]))
    lines.extend([f"## Beam trace and objective comparisons ({STATUS})", "",
                  "Vectors are relevance, hop efficiency, contract consistency and entropy. "
                  "Pareto fronts precede mean objective, then deterministic keys. "
                  "Several selected steps can share a target through parallel edges or distinct paths "
                  "(`eg_pot.py:488–522`). The JSON retains every offer and all selected vectors. "
                  "The table shows the first offer for each missing ID and the candidates selected in that round.", ""])
    lines += markdown_table(["Query / missing role", "Round", "Missing vector and front",
                             "Kept node / vector / missing objective lower"], (
        (f"{m['id']} / {m['role']}", offer["round"],
         f"{vector(offer['candidate']['vector'])} / {offer['candidate']['front']}",
         "<br>".join(f"`{k['node']}` {vector(k['vector'])} / "
                      + (", ".join(k["lower_objectives_for_missing"]) or "none")
                      for k in offer["kept"]))
        for m in report["misses"] for offer in m["gold_offers"][:1]))
    lines += markdown_table(["Query", "Round", "Frontier tips", "Scored", "Pareto front sizes", "Selected targets"], (
        (query_id, r["round"], "<br>".join(f"`{b['last_node']}`" for b in r["frontier"]),
         len(r["candidates"]), ", ".join(str(len(f)) for f in r["fronts"]) or "—",
         "<br>".join(f"`{r['candidates'][i]['to_node']}`" for i in r["selected"]) or "—")
        for traces in report["traces"].values() for query_id, trace in traces.items() for r in trace["rounds"]))
    lines.extend([f"## What the evidence supports ({STATUS})", "",
                  "Scoring evidence uses a within-round check. Equalizing one objective with "
                  "the candidate pool fixed can improve an offer's rank or change selection "
                  "subject to the remaining budget. These are separate counts of missing IDs "
                  "with at least one such round. They establish an effect in that round only.", ""])
    labels = {"width_pruned": "Pruned by width 4 (missing IDs)",
              "entropy_handler_rank_improvements": "Handler rank improved with entropy equalized",
              "entropy_handler_selection_flips": "Handler selection flipped with entropy equalized",
              "hop_efficiency_handler_rank_improvements": "Handler rank improved with hop efficiency equalized",
              "hop_efficiency_handler_selection_flips": "Handler selection flipped with hop efficiency equalized",
              "edge_rule_blocked": "Edge eligibility blocked the target (missing IDs)",
              "builder_gap": "Handler or IMPLEMENTS missing despite source evidence (missing IDs)"}
    lines += markdown_table(["Evidence", "Count"], ((label, report["evidence_support"][key])
                                                     for key, label in labels.items()))
    lines.extend(["The pinned source evidence tables supplied the handler, IDL and registration "
                  "citations below. Their SHA-256 values are in the JSON.", ""])
    lines += markdown_table(["Link query", "Source evidence table", "Handler", "IDL", "Registration evidence"], (
        (m["id"], s["table"], s["handler"], s["idl"], s["registration"])
        for m in by_query.values() for s in [m["source_evidence"]]))
    return "\n".join(lines)


def main():
    outputs = {RESULTS / "dsb_miss_diagnosis.json": lambda report: json.dumps(
        report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        RESULTS / "dsb_miss_diagnosis.md": markdown}
    if any(path.exists() for path in outputs):
        raise SystemExit("Diagnosis outputs already exist")
    report = analyze()
    rendered = {path: render(report) for path, render in outputs.items()}
    for path, contents in rendered.items():
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        print(path)


if __name__ == "__main__":
    main()
