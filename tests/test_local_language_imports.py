"""Cross-file relative dependencies for Ruby, Lua and C/C++ imports."""
from pathlib import Path

from graft_ckg import CKGBuilder


def test_unambiguous_cpp_ruby_and_lua_relative_imports(tmp_path):
    files = {
        "cpp/main.cpp": '#include "util.h"\nint run() { return helper(); }\n',
        "cpp/util.h": 'int helper();\n',
        "ruby/main.rb": 'require_relative "./lib"\ndef call\n  work()\nend\n',
        "ruby/lib.rb": 'def work\n  1\nend\n',
        "lua/main.lua": 'local helper = require("module.helper")\nfunction go() return helper.work() end\n',
        "lua/module/helper.lua": 'local M = {}\nfunction M.work() return 1 end\nreturn M\n',
    }
    for name, source in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(source, encoding="utf-8")
    graph = CKGBuilder(str(tmp_path)).build()
    connections = {
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get("relation") == "IMPORTS" and
        u.startswith("file::") and v.startswith("file::")
    }
    for src, tgt in (
        ("cpp/main.cpp", "cpp/util.h"),
        ("ruby/main.rb", "ruby/lib.rb"),
        ("lua/main.lua", "lua/module/helper.lua"),
    ):
        assert ("file::" + src, "file::" + tgt) in connections


def test_unqualified_duplicate_module_does_not_bind_arbitrary_file(tmp_path):
    files = {
        "a/main.cpp": '#include "helpers.h"\nint run() {return 1;}\n',
        "a/nested/helpers.h": "int work();\n",
        "b/nested/helpers.h": "int work();\n",
    }
    for name, source in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(source, encoding="utf-8")
    graph = CKGBuilder(str(tmp_path)).build()
    assert not any(u == "file::a/main.cpp" and v.startswith("file::")
                   and d.get("relation") == "IMPORTS"
                   for u, v, d in graph.edges(data=True))
