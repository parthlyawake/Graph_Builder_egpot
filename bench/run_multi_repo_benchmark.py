"""Compatibility entrypoint for the corrected GRAFT-CKG paper benchmark.

The original 2026-10-02 implementation used guessed denominator tokens,
a borrowed AST ranking vector, heuristic substring matches, and hard-coded
baseline redundancy figures. Those results must not be regenerated/published.
Use exact-ID independent labels via --labels and the audited harness below.

For graph accuracy use bench/run_paper_accuracy.py, and for performance use
bench/paper_performance.py. Old RESULT.md numbers are historical only.
"""
from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from bench.run_paper_study import main

if __name__=="__main__":
    main()
