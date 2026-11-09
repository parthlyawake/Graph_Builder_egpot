"""Regression checks for missing optional native language grammars."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from graft_ckg import CKGBuilder
from polyglot import TreeSitterExtractor


class MissingGrammarGuardTests(unittest.TestCase):
    def test_java_source_requires_java_grammar(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "Service.java").write_text("class Service {}", encoding="utf-8")
            extensions = TreeSitterExtractor.EXTENSIONS - {".java"}
            with patch.object(TreeSitterExtractor, "EXTENSIONS", extensions):
                with self.assertRaisesRegex(RuntimeError, "tree-sitter-java"):
                    CKGBuilder(temp).build()

    def test_csharp_source_requires_csharp_grammar(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "Service.cs").write_text("class Service {}", encoding="utf-8")
            extensions = TreeSitterExtractor.EXTENSIONS - {".cs"}
            with patch.object(TreeSitterExtractor, "EXTENSIONS", extensions):
                with self.assertRaisesRegex(RuntimeError, "tree-sitter-c-sharp"):
                    CKGBuilder(temp).build()

    def test_both_missing_packages_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "Service.java").write_text("class Service {}", encoding="utf-8")
            Path(temp, "Service.cs").write_text("class Service {}", encoding="utf-8")
            extensions = TreeSitterExtractor.EXTENSIONS - {".java", ".cs"}
            with patch.object(TreeSitterExtractor, "EXTENSIONS", extensions):
                with self.assertRaises(RuntimeError) as error:
                    CKGBuilder(temp).build()
            self.assertIn("tree-sitter-java", str(error.exception))
            self.assertIn("tree-sitter-c-sharp", str(error.exception))


if __name__ == "__main__":
    unittest.main()
