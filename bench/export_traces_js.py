"""Wrap existing trace JSON as local script globals, without changing its data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bench.egpot_eval import split_by_link


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def wrappers(data_dir, labels_path):
    root = Path(data_dir)
    files = {}
    for source in sorted((root / "traces").glob("*.json")):
        trace = json.loads(source.read_text(encoding="utf-8"))
        files[f"traces_js/{source.stem}.js"] = (
            "window.VIZ_TRACES = window.VIZ_TRACES || {}; window.VIZ_TRACES[" +
            encoded(source.stem) + "] = " + encoded(trace) + ";\n").encode("utf-8")
    if not files:
        raise ValueError("No source traces found")
    index = json.loads((root / "traces_index.json").read_text(encoding="utf-8"))
    files["traces_index.js"] = ("window.VIZ_TRACE_INDEX = " + encoded(index) + ";\n").encode("utf-8")
    rows = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    gold = {row["id"]: {"gold_nodes": row["gold_nodes"], "gold_path": row["gold_path"]}
            for row in split_by_link(rows)["dev"]}
    files["gold.js"] = ("window.VIZ_GOLD = " + encoded(gold) + ";\n").encode("utf-8")
    return files


def export(data_dir, labels_path, output_dir=None):
    files = wrappers(data_dir, labels_path)
    output = Path(output_dir or data_dir)
    for relative, data in files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(f"Wrote {len(files)} script wrappers; {sum(map(len, files.values())):,} bytes")
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "viz/data/online_boutique")
    parser.add_argument("--labels", type=Path, default=ROOT / "bench/labels/online_boutique_egpot_queries.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    export(args.data, args.labels, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
