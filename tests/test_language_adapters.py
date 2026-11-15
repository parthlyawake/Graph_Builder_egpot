"""Uniform adapter registry and seven-language build visibility."""
import tempfile
import unittest
from pathlib import Path

from language_adapters import SPECS, advertised_capabilities, adapter_for, spec_for
from graft_ckg import CKGBuilder


class AdapterContractTests(unittest.TestCase):
    def test_all_seven_have_one_common_entry_point(self):
        self.assertGreaterEqual(len(SPECS), 11)
        for spec in SPECS:
            for extension in spec.extensions:
                adapter = adapter_for("sample" + extension)
                self.assertEqual(adapter.spec.name, spec.name)
                self.assertTrue(callable(adapter.extract))
        self.assertIsNone(adapter_for("unknown.rs"))

    def test_capability_declarations_are_explicit_and_not_accuracy_claims(self):
        report = advertised_capabilities()
        self.assertEqual(set(report), {
            "python", "javascript", "typescript", "go", "java", "csharp", "kotlin",
            "ruby", "lua", "cpp", "c"
        })
        self.assertTrue(all(v["verified_accuracy"] is None for v in report.values()))

    def test_unsupported_source_files_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "unit.py").write_text("def run(): pass\n", encoding="utf-8")
            Path(tmp, "engine.rs").write_text("fn run() {}\n", encoding="utf-8")
            builder = CKGBuilder(tmp)
            builder.build()
            report = builder.get_language_report()
            self.assertEqual(report["languages"]["python"]["parsed"], 1)
            self.assertEqual(report["unsupported_files"][".rs"], 1)
            self.assertFalse(report["full_source_coverage"])

    def test_invalid_python_is_not_reported_as_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "invalid.py").write_text("def invalid(:\n", encoding="utf-8")
            builder = CKGBuilder(tmp)
            builder.build()
            report = builder.get_language_report()
            self.assertEqual(report["languages"]["python"]["failed"], 1)
            self.assertFalse(report["complete"])


if __name__ == "__main__":
    unittest.main()
