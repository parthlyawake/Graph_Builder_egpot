"""Per-language AST-to-CKG extraction smoke tests.

These verify basic declaration and call extraction only. They do not certify
full feature parity or edge precision/recall across large repositories.
"""
import tempfile
import unittest
from pathlib import Path

from language_adapters import SPECS, parser_available
from graft_ckg import CKGBuilder

FIXTURES = {
    "python": (".py", "def helper():\n    return 1\n\ndef run():\n    return helper()\n", {"helper", "run"}),
    "javascript": (".js", "function helper() { return 1; }\nfunction run() { return helper(); }\n", {"helper", "run"}),
    "typescript": (".ts", "function helper(): number { return 1; }\nfunction run(): number { return helper(); }\n", {"helper", "run"}),
    "go": (".go", "package main\nfunc helper() int { return 1 }\nfunc run() int { return helper() }\n", {"helper", "run"}),
    "java": (".java", "class Service { int helper() { return 1; } int run() { return helper(); } }\n", {"helper", "run"}),
    "csharp": (".cs", "class Service { int helper() { return 1; } int run() { return helper(); } }\n", {"helper", "run"}),
    "kotlin": (".kt", "class Service {\n fun helper(): Int { return 1 }\n fun run(): Int { return helper() }\n}\n", {"helper", "run"}),
    "ruby": (".rb", "def helper\n  1\nend\ndef run\n  helper()\nend\n", {"helper", "run"}),
    "lua": (".lua", "function helper() return 1 end\nfunction run() return helper() end\n", {"helper", "run"}),
    "cpp": (".cpp", "int helper() { return 1; }\nint run() { return helper(); }\n", {"helper", "run"}),
    "c": (".c", "int helper() { return 1; }\nint run() { return helper(); }\n", {"helper", "run"}),
    "scala": (".scala", "object Service { def helper(): Int = 1; def run(): Int = helper() }\n", {"helper", "run"}),
}


class SevenLanguageSmokeTests(unittest.TestCase):
    def test_every_registered_language_has_a_fixture(self):
        self.assertEqual({s.name for s in SPECS}, set(FIXTURES))

    def test_each_language_extracts_functions_and_records_calls(self):
        for spec in SPECS:
            with self.subTest(language=spec.name):
                if not parser_available(spec):
                    self.skipTest("Required grammar unavailable for " + spec.name)
                extension, content, expected = FIXTURES[spec.name]
                with tempfile.TemporaryDirectory() as folder:
                    Path(folder, "source" + extension).write_text(content, encoding="utf-8")
                    builder = CKGBuilder(folder)
                    graph = builder.build()
                    report = builder.get_language_report()
                    self.assertEqual(report["languages"][spec.name]["parsed"], 1, report["parse_errors"])
                    self.assertEqual(report["languages"][spec.name]["partial"], 0)
                    self.assertEqual(report["languages"][spec.name]["failed"], 0)
                    actual = {d.get("name") for _, d in graph.nodes(data=True)
                              if d.get("type") in {"function", "method"}}
                    self.assertTrue(expected <= actual, (spec.name, expected - actual))
                    self.assertTrue(
                        any(d.get("relation") in {"CALLS", "POLYMORPHIC_CALL"}
                            for _, _, d in graph.edges(data=True)),
                        "No call-graph edge extracted for " + spec.name
                    )


if __name__ == "__main__":
    unittest.main()
