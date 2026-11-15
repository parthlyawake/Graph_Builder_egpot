"""Unambiguous local imports for source languages with path-based module loading.

Unqualified filenames are never bound to an arbitrary directory. Only imports
that resolve to exactly one indexed file become asserted file dependencies.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath


def _candidate_paths(source, import_path, extensions, *, dot_as_sep=False):
    module = import_path.replace(".", "/") if dot_as_sep else import_path
    basedir = str(PurePosixPath(source).parent)
    bases = [posixpath.normpath(posixpath.join(basedir, module))]
    if "/" not in module and not module.startswith("."):
        bases.append(module)
    result = []
    for base in bases:
        if base == ".." or base.startswith("../") or base.startswith("/"):
            continue
        result.append(base)
        if PurePosixPath(base).suffix.lower() not in extensions:
            result.extend(base + ext for ext in extensions)
            result.extend(posixpath.join(base, "index" + ext) for ext in extensions)
    return result


def bind_literal_imports(builder):
    known = {
        file for file in builder.raw_file_lines
        if f"file::{builder.repo_prefix}{file}" in builder.graph
    }
    for file, lines in sorted(builder.raw_file_lines.items()):
        ext = PurePosixPath(file).suffix.lower()
        text = "\n".join(lines)
        imports = []
        if ext in {".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx"}:
            imports = [
                (match.group(1), (".h", ".hh", ".hpp", ".hxx", ".c", ".cpp"), False)
                for match in re.finditer(r'(?m)^\s*#\s*include\s*"([^"\n]+)"', text)
            ]
        elif ext == ".rb":
            imports = [
                (m.group(1), (".rb",), False)
                for m in re.finditer(r"(?m)^\s*require_relative\s*[\(\s]*['\"]([^'\"]+)['\"]", text)
            ]
            imports += [
                (m.group(1), (".rb",), False)
                for m in re.finditer(r"(?m)^\s*require\s*[\(\s]*['\"]([^'\"]+)['\"]", text)
            ]
        elif ext == ".lua":
            imports = [
                (m.group(1), (".lua",), True)
                for m in re.finditer(
                    r"\brequire\s*[\(\s]*['\"]([^'\"]+)['\"]", text
                )
            ]
        if not imports:
            continue
        source_id = f"file::{builder.repo_prefix}{file}"
        seen = set()
        for path, suffixes, dotted in imports:
            possibilities = {
                item for item in _candidate_paths(file, path, suffixes,
                                                   dot_as_sep=dotted)
                if item in known
            }
            if len(possibilities) != 1:
                continue
            target = next(iter(possibilities))
            if target == file or target in seen:
                continue
            seen.add(target)
            target_id = f"file::{builder.repo_prefix}{target}"
            builder.add_ckg_edge(source_id, target_id, "IMPORTS", "Ldep")
