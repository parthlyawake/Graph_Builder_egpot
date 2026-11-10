"""
LSP Augmentation Engine for SCKG / GRAFT-CKG
============================================
Integrates Language Server Protocol (LSP) and SCIP/LSIF code intelligence
to elevate static call confidence from uncertain (c_type=0.5) to exact (c_type=1.0).

Supports:
- Compiler index maps (file, symbol) -> canonical node ID
- Exact callsite resolution (file, line, col, symbol) -> target node ID
- Dynamic LSP callback provider
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable


@dataclass
class LSPDefinition:
    source_file: str
    symbol_name: str
    target_node_id: str
    line: Optional[int] = None
    column: Optional[int] = None
    confidence: float = 1.0


class LSPIndexProvider:
    """Provides exact compiler/LSP symbol definition lookup."""

    def __init__(self):
        # Key: (source_file, symbol_name) -> target_node_id
        self._by_symbol: Dict[Tuple[str, str], str] = {}
        # Key: (source_file, line, symbol_name) -> target_node_id
        self._by_line_symbol: Dict[Tuple[str, int, str], str] = {}
        # Optional dynamic hook
        self._dynamic_resolver: Optional[Callable[[str, Optional[int], str], Optional[str]]] = None

    def register(self, source_file: str, symbol_name: str, target_node_id: str, line: Optional[int] = None):
        norm_file = source_file.replace("\\", "/")
        self._by_symbol[(norm_file, symbol_name)] = target_node_id
        if line is not None:
            self._by_line_symbol[(norm_file, line, symbol_name)] = target_node_id

    def set_dynamic_resolver(self, resolver: Callable[[str, Optional[int], str], Optional[str]]):
        self._dynamic_resolver = resolver

    def resolve(self, source_file: str, symbol_name: str, line: Optional[int] = None) -> Optional[str]:
        norm_file = source_file.replace("\\", "/")
        if line is not None:
            target = self._by_line_symbol.get((norm_file, line, symbol_name))
            if target:
                return target

        target = self._by_symbol.get((norm_file, symbol_name))
        if target:
            return target

        # Check by basename match if full path differed
        base = os.path.basename(norm_file)
        for (f, sym), tid in self._by_symbol.items():
            if sym == symbol_name and (f.endswith("/" + base) or os.path.basename(f) == base):
                return tid

        if self._dynamic_resolver:
            return self._dynamic_resolver(norm_file, line, symbol_name)

        return None

    def load_from_dict(self, mapping: Dict[str, Any]):
        """Load definitions from a dictionary format:
        { "file.py:symbol": "target_node_id", ... } or
        { "definitions": [ {"file": ..., "symbol": ..., "target": ..., "line": ...} ] }
        """
        if "definitions" in mapping and isinstance(mapping["definitions"], list):
            for item in mapping["definitions"]:
                self.register(
                    item.get("file", ""),
                    item.get("symbol", ""),
                    item.get("target", item.get("target_id", "")),
                    item.get("line")
                )
        else:
            for k, target in mapping.items():
                if ":" in k:
                    f, sym = k.split(":", 1)
                    self.register(f, sym, str(target))
                else:
                    self.register("", k, str(target))

    def load_from_file(self, json_path: str):
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.load_from_dict(data)
