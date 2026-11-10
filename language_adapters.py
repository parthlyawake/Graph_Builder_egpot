"""Common entry point and capability contract for all seven source languages.

Capabilities are extraction features implemented in source, not accuracy claims.
Every adapter receives the same builder and must produce the shared node/edge
schema. Repository-specific resolver passes remain in CKGBuilder.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from polyglot import TreeSitterExtractor


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    extensions: tuple[str, ...]
    parser: str
    package: str | None
    features: tuple[str, ...]


# This inventory describes implemented extraction paths, NOT validated recall.
BASE = ("file_nodes", "functions", "dependencies", "source_locations")
SPECS = (
    LanguageSpec("python", (".py",), "ast", None,
                 BASE + ("classes", "dataflow", "http", "grpc")),
    LanguageSpec("javascript", (".js", ".jsx"), "tree_sitter", "tree-sitter-javascript",
                 BASE + ("classes", "dataflow", "http", "grpc")),
    LanguageSpec("typescript", (".ts", ".tsx"), "tree_sitter", "tree-sitter-typescript",
                 BASE + ("classes", "interfaces", "dataflow", "http", "grpc")),
    LanguageSpec("go", (".go",), "tree_sitter", "tree-sitter-go",
                 BASE + ("structs", "receiver_methods", "dataflow", "http", "grpc")),
    LanguageSpec("java", (".java",), "tree_sitter", "tree-sitter-java",
                 BASE + ("classes", "interfaces", "dataflow", "spring_http", "grpc", "messaging")),
    LanguageSpec("csharp", (".cs",), "tree_sitter", "tree-sitter-c-sharp",
                 BASE + ("classes", "interfaces", "dataflow", "aspnet_http", "grpc")),
    LanguageSpec("kotlin", (".kt", ".kts"), "tree_sitter", "tree-sitter-kotlin",
                 BASE + ("classes", "dataflow", "spring_http", "grpc", "messaging")),
)
BY_EXTENSION = {ext: spec for spec in SPECS for ext in spec.extensions}
# Other known application languages are reported, never treated as parsed.
KNOWN_UNSUPPORTED = frozenset({
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh",
    ".rs", ".rb", ".php", ".lua", ".ex", ".exs", ".erl",
    ".swift", ".scala", ".sc", ".dart", ".pl", ".r",
})


def spec_for(path: str) -> LanguageSpec | None:
    return BY_EXTENSION.get(Path(path).suffix.lower())


def parser_available(spec: LanguageSpec) -> bool:
    if spec.parser == "ast":
        return True
    # The Go extension is always declared by the legacy visitor, even when
    # its optional grammar import failed. Use actual import availability.
    import polyglot
    flags = {
        "go": "_GO_AVAILABLE",
        "java": "_JAVA_AVAILABLE",
        "csharp": "_CSHARP_AVAILABLE",
        "kotlin": "_KOTLIN_AVAILABLE",
    }
    if spec.name in flags:
        return (bool(getattr(polyglot, flags[spec.name], False))
                and all(ext in TreeSitterExtractor.EXTENSIONS for ext in spec.extensions))
    return all(ext in TreeSitterExtractor.EXTENSIONS for ext in spec.extensions)


class LanguageAdapter:
    """The stable adapter interface: parse(builder, path, full_path) -> diagnostics.

    Existing language-specific AST walkers remain behind this boundary until
    equivalent source-grounded fixtures justify migrating each implementation.
    """

    def __init__(self, spec: LanguageSpec):
        self.spec = spec

    def extract(self, builder, rel_path: str, full_path: str) -> dict:
        if not parser_available(self.spec):
            raise RuntimeError(
                f"{self.spec.name}: missing grammar {self.spec.package}; "
                "install the declared project dependencies"
            )
        if self.spec.parser == "ast":
            # Existing Python visitor swallows parse errors. Validate first so
            # the build report cannot silently mark broken input as parsed.
            source = Path(full_path).read_bytes()
            ast.parse(source, filename=rel_path)
            builder._parse_python_file(rel_path, full_path)
            return {"syntax_errors": False}
        extractor = TreeSitterExtractor(Path(full_path).suffix.lower())
        return extractor.extract(builder, rel_path, full_path) or {"syntax_errors": False}


def adapter_for(path: str) -> LanguageAdapter | None:
    spec = spec_for(path)
    return LanguageAdapter(spec) if spec else None


def advertised_capabilities() -> dict:
    return {
        spec.name: {
            "extensions": list(spec.extensions),
            "parser": spec.parser,
            "installed": parser_available(spec),
            "implemented_extraction_features": list(spec.features),
            "verified_accuracy": None,
        }
        for spec in SPECS
    }
