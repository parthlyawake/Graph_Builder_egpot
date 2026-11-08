"""Copy the frozen final-test record into an offline script; never run retrieval."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def find_record(directory: Path) -> Path:
    files = sorted(p for p in directory.glob("test_final_*.json")
                   if not p.stem.endswith("_secondlook"))
    if len(files) != 1:
        raise ValueError(f"Expected exactly one non-secondlook record; found {len(files)}: "
                         + ", ".join(p.name for p in files))
    return files[0]


def build_payload(path: Path, *, inspect=False):
    raw = path.read_bytes()
    data = json.loads(raw)
    if inspect:
        print("TOP_LEVEL_KEYS " + json.dumps(list(data)), flush=True)
        print("SAMPLE_ROW " + json.dumps(data["rows"][0], sort_keys=True), flush=True)
    if data.get("status") != "completed" or data.get("second_look"):
        raise ValueError("A completed first-look record is required")
    missing = []
    if not any(r.get("experiment") == "weights" and r.get("split") == "dev" for r in data["rows"]):
        missing.append("DEV weight-distribution runs are not recorded; DEV weight counts cannot be shown from this record.")
    if not any("sha256" in key for key in data.get("inputs", {})):
        missing.append("Frozen graph and label SHA-256 hashes are not recorded; current input hashes are not substituted.")
    protocol = data["configs"]["protocol"]
    return {"provenance":{"commit":data["commit"],"timestamp_utc":data["utc_timestamp"],
                "versions":data["versions"],"deterministic_sha256":data["deterministic_sha256"],
                "source_record_sha256":hashlib.sha256(raw).hexdigest(),"source_file":path.name,
                "seeds":protocol["seeds"],"split_links":data["split_links"],
                "inputs":data["inputs"],"configs":data["configs"],"missing_fields":missing,
                "second_look":data["second_look"],"previous_results":data["previous_results"]},
            "rows":[r for r in data["rows"] if r["experiment"] == "main"],
            "choke":[r for r in data["rows"] if r["experiment"] == "choke"],
            "seeds":[r for r in data["rows"] if r["experiment"] == "seeds"],
            "weights":[r for r in data["rows"] if r["experiment"] in ("weights","pareto_reference")],
            "summary":data["summary"]}


def encode(payload):
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ("window.VIZ_RESULTS_TEST = " + text + ";\n").encode("utf-8")


def non_latency_content(value):
    """Timing is retained in the export, but excluded from content comparisons.

    The source-byte hash necessarily covers latency too; the frozen record's
    separate deterministic_sha256 field already excludes timing.
    """
    if isinstance(value, dict):
        return {k:non_latency_content(v) for k,v in value.items()
                if k not in {"latency_s","source_record_sha256"}}
    if isinstance(value, list):
        return [non_latency_content(v) for v in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir",type=Path,default=ROOT/"bench/results")
    parser.add_argument("--output",type=Path,default=ROOT/"viz/data/online_boutique/results_test.js")
    args = parser.parse_args(argv)
    try:
        source = find_record(args.results_dir)
        payload = build_payload(source,inspect=True)
    except ValueError as exc:
        parser.error(str(exc))
    content = encode(payload)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(content)
    print("ROW_COUNTS " + json.dumps({k:len(payload[k]) for k in ("rows","choke","seeds","weights")}),flush=True)
    print(f"EXPORTED {args.output} bytes={len(content)}",flush=True)
    for warning in payload["provenance"]["missing_fields"]:
        print("MISSING: " + warning,flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
