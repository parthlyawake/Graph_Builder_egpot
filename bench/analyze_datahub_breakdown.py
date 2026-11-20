"""Report exploratory slices from the frozen DataHub record and saved metadata."""
from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "bench/labels/datahub_egpot_queries.json"
TOPOLOGY = ROOT / "bench/results/datahub_edge_audit_v3.json"
LOCKED_SHA256 = "8d80369f3a03c4dcece78df9ebdcb8a0b562601736b2ddd87840318a2b0852d9"
METHODS = (
    "egpot_full_w4", "egpot_full_w12", "egpot_no_contracts_w4",
    "ppr", "scalar_beam", "mcts_standard", "vector_topk", "bfs",
)
BUDGETS = (10, 20, 40)
NEIGHBORHOOD = "within_two_hops_including_start"


def load_inputs(record_path):
    record_bytes = record_path.read_bytes()
    if sha256(record_bytes).hexdigest() != LOCKED_SHA256:
        raise ValueError("Result bytes do not match the DataHub locked record")
    record = json.loads(record_bytes)
    hashes = record["identity"]["verified_hashes"]
    label_bytes = LABELS.read_bytes()
    audit = json.loads(TOPOLOGY.read_bytes())
    if (sha256(label_bytes).hexdigest() != hashes["labels"]
            or audit["labels_sha256"] != hashes["labels"]
            or audit["graphml_sha256"] != hashes["graph"]):
        raise ValueError("Label or topology provenance does not match the locked inputs")

    labels = {row["id"]: row for row in json.loads(label_bytes)}
    topology = {row["link"]: row for row in audit["topology"]}
    links = defaultdict(list)
    for label in labels.values():
        links[label["link_id"]].append(label)
    if set(links) != set(topology):
        raise ValueError("Topology does not cover the locked links")
    for link_id, pair in links.items():
        if (len(pair) != 2 or {row["type"] for row in pair} != {"explicit", "indirect"}
                or len({row["start_node"] for row in pair}) != 1
                or any(row["module_pair"] != topology[link_id]["module_pair"]
                       or len(row["gold_nodes"]) != 2
                       or row["gold_path"] != [row["start_node"], *row["gold_nodes"]] for row in pair)):
            raise ValueError(f"Inconsistent source labels for {link_id}")
    return labels, topology, result_index(record["rows"], labels)


def result_index(rows, labels):
    index = {}
    for row in rows:
        method, budget, query_id = row["method"], row["node_budget"], row["id"]
        if row["experiment"] != "main" or row["seed"] != 0 or method not in METHODS:
            continue
        key = method, budget, query_id
        label = labels[query_id]
        if key in index or (row["link_id"], row["type"]) != (label["link_id"], label["type"]):
            raise ValueError(f"Duplicate or mislabeled result row {key}")
        found = set(label["gold_nodes"]) & set(row["returned_nodes"])
        if found != set(row["gold_found"]) or row["hit"] != int(len(found) == 2):
            raise ValueError(f"Inconsistent gold outcomes in {key}")
        index[key] = found
    expected = {(method, budget, query) for method in METHODS for budget in BUDGETS for query in labels}
    if index.keys() != expected:
        raise ValueError("Selected results do not match the planned main seed-0 rows")
    return index


def neighborhood_terciles(topology):
    """Keep both wordings of each link together when dividing the ranked sizes."""
    links = sorted(topology, key=lambda link: (topology[link][NEIGHBORHOOD], link))
    size, remainder = divmod(len(links), 3)
    offset = 0
    for i, name in enumerate(("Small", "Middle", "Large")):
        next_offset = offset + size + (i < remainder)
        group = links[offset:next_offset]
        low, high = (topology[link][NEIGHBORHOOD] for link in (group[0], group[-1]))
        yield f"{name} tercile ({low:,} to {high:,} nodes)", set(group)
        offset = next_offset


def hit_count(index, cohort, method, budget):
    return sum(len(index[method, budget, label["id"]]) == 2 for label in cohort)


def hit_table(index, cohort):
    rows = ["| Method | Budget 10 | Budget 20 | Budget 40 |", "|---|---:|---:|---:|"]
    for method in METHODS:
        cells = [f"{hit_count(index, cohort, method, budget)}/{len(cohort)}" for budget in BUDGETS]
        rows.append(f"| `{method}` | {' | '.join(cells)} |")
    return rows


def render(labels, topology, index):
    query_rows = list(labels.values())
    groups = (
        ("a. Query wording", [
            (kind.title(), [row for row in query_rows if row["type"] == kind])
            for kind in ("explicit", "indirect")
        ], "Width 4 leads width 12 at budget 10 in both wording groups. Width 12 leads at budgets "
           "20 and 40 in both. Turning off contract consistency costs more hits for indirect wording "
           "at budget 40."),
        ("b. Gold handler depth", [
            (f"Depth {depth}", [row for row in query_rows
                              if topology[row["link_id"]]["handler_hops"] == depth])
            for depth in (1, 2)
        ], "The two depth-1 links, DH18 and DH24, yield four queries. Both widths hit all four at "
           "every budget, and several baselines also do so at budget 40. The depth-2 group accounts "
           "for the width-4 lead at budget 10 and the width-12 lead at budgets 20 and 40."),
        ("c. Start-node neighborhood size", [
            (name, [row for row in query_rows if row["link_id"] in links])
            for name, links in neighborhood_terciles(topology)
        ], "Width 4 leads width 12 at budget 10 in all three terciles. Width 12 pulls ahead at "
           "budgets 20 and 40 in the small and middle terciles and ties width 4 in the largest."),
        ("d. Module pair", [
            (name, [row for row in query_rows if row["module_pair"] == name])
            for name in ("React \u2192 GraphQL", "Python \u2192 OpenAPI", "Python \u2192 Rest.li")
        ], "Width 4 leads width 12 at budget 10 in every module pair. At budgets 20 and 40 the width-12 "
           "gain comes from React to GraphQL. Both widths hit every Python to OpenAPI and Python to "
           "Rest.li query at those budgets. Standard MCTS ties both widths on OpenAPI at budget 40."),
    )
    lines = [
        "# DataHub post-hoc breakdown",
        "",
        "**Exploratory.** All numbers in this report are exploratory. Counts use the main seed-0 rows "
        "from [the locked result](datahub_final_1cf9dce0.json). Gold roles come from the frozen labels. "
        "Handler depth and two-hop neighborhood size come from the "
        "[saved topology audit](datahub_edge_audit_v3.json). Neighborhood counts include the start. "
        "Terciles rank links by size and then link ID, divide them as evenly as possible with extra "
        "links in the earlier groups, and keep the paired wordings together.",
        "",
    ]
    for section, cohorts, note in groups:
        lines.extend([f"## {section} (exploratory)", ""])
        for name, cohort in cohorts:
            lines.extend([f"### {name} (exploratory)", "", *hit_table(index, cohort), ""])
        lines.extend([note, ""])

    lines.extend([
        "## e. Contract and handler recall (exploratory)", "",
        "Each column counts exact recoveries of the indicated gold node, over the same queries.", "",
        "| Method | Budget | Contract found | Handler found |", "|---|---:|---:|---:|",
    ])
    for method in METHODS[:2]:
        for budget in BUDGETS:
            contract, handler = (
                sum(label["gold_nodes"][role] in index[method, budget, label["id"]] for label in query_rows)
                for role in (0, 1)
            )
            n = len(query_rows)
            lines.append(f"| `{method}` | {budget} | {contract}/{n} ({contract/n:.1%}) "
                         f"| {handler}/{n} ({handler/n:.1%}) |")
    lines.extend(["", "Contracts are nearly always found at both widths. Handler recall follows the "
                  "full-hit pattern. Width 4 leads at budget 10, and width 12 leads at budgets 20 and 40.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = render(*load_inputs(args.record))
    with args.out.open("x", encoding="utf8", newline="\n") as output:
        output.write(report)


if __name__ == "__main__":
    main()
