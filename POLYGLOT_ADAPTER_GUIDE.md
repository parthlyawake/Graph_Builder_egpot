# Polyglot adapters: shared contract and capability diagnostics

Seven languages are registered in language_adapters.py. Each uses the same
LanguageAdapter.extract(builder, path, full_path) interface, returning parse
diagnostics. Python uses the built-in AST; JavaScript, TypeScript, Go, Java,
C#, and Kotlin reuse the current Tree-sitter visitor in polyglot.py.
The shared graph schema, deferred calls, dataflow and contract registries
remain owned by CKGBuilder.

This is **architectural standardization**, not a claim of full semantic parity.
Each language can have a grammar installed and still have incomplete call,
dataflow, inheritance or framework binding resolution. Advertised features
identify code paths that exist, NOT independently verified accuracy.

## Capability and coverage report

After building:

    builder = CKGBuilder("/path/to/repo")
    graph = builder.build()
    report = builder.get_language_report()

report contains:
- capabilities: grammar availability and implemented extraction paths;
- languages: discovered / parsed / partial / failed file counts;
- parse_errors: affected filenames and diagnostic messages;
- unsupported_files: known source-language extensions omitted;
- complete: whether every detected supported source file parsed cleanly.

Parse errors are never silently counted as successful extraction. Installed
grammars are required for discovered files of the seven languages. Unsupported
languages are reported but not parsed.

Run adapter tests:

    python -m unittest tests.test_language_adapters

## Adding an eighth language

1. Add a LanguageSpec with extensions, grammar package and feature inventory.
2. Extend TreeSitterExtractor or implement a separate adapter behind the
   same extract interface. Emit graph nodes using add_ckg_node, edges using
   add_ckg_edge, symbols using register_symbol, and defer uncertain call and
   contract resolution through existing registries.
3. Add the grammar to requirements.txt and pyproject.toml.
4. Write source-grounded positive and negative fixtures. Check each parser
   construct and exact triple with bench/verify_graph_accuracy.py.
5. Measure accuracy per language and relation type; do not mark a feature
   verified solely because the file parsed or graph invariants passed.

## Known remaining parity work

- Cross-language import and method-resolution correctness varies.
- Existing declaration and parameter patterns are language-specific.
- Runtime framework binding rules are not yet complete for all seven.
- Graph build reports capability, not precision or recall. The accuracy
  verifier requires independent labels and closed scopes to report F1.
- Incremental refresh still needs per-language full-rebuild equivalence tests.

Follow-up engineering should move each language's visitor branches into
independent modules once fixture coverage protects their behavior. Avoid
a broad rewrite of the combined visitor without those tests.

## Parity smoke tests

Run `python -m unittest tests.test_seven_language_smoke` with all grammar
packages installed. These tests exercise identical function/call concepts in
seven syntaxes and detect regressions; source-grounded integration benchmarks
remain necessary for comprehensive semantic accuracy.

The report distinguishes `complete` (all recognized supported code parsed
without errors) from `full_source_coverage` (no known unsupported application
files also discovered). Neither field certifies semantic correctness.
