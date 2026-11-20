"""Compare keyed attributed graphs built from existing non-locked test sources."""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.abc
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


class FrozenModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, ref):
        # Only modules changed between the frozen builder and v2 need an overlay.
        names = ['graft_ckg', 'multi_repo', 'polyglot', 'graphql_java_bindings',
                 'http_extended', 'graph_builder_http']
        self.sources = {name: subprocess.check_output(['git', 'show', f'{ref}:{name}.py'])
                        for name in names}

    def find_spec(self, fullname, path=None, target=None):
        return importlib.util.spec_from_loader(fullname, self) if fullname in self.sources else None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path = str(Path.cwd() / (module.__name__ + '.py'))
        module.__file__ = path
        exec(compile(self.sources[module.__name__], path, 'exec'), module.__dict__)


def graph_digest(graph):
    digest = hashlib.sha256()
    for row in sorted(graph.nodes(data=True)):
        digest.update(json.dumps(row, sort_keys=True, default=str).encode() + b'\n')
    for row in sorted(graph.edges(keys=True, data=True)):
        digest.update(json.dumps(row, sort_keys=True, default=str).encode() + b'\n')
    return digest.hexdigest()


def snapshot(frozen):
    if frozen:
        sys.meta_path.insert(0, FrozenModules('egpot-bench-builder-v1'))
    from bench.egpot_width_sweep_dev import guard
    from multi_repo import RepoConfig, WorkspaceCKGBuilder, WorkspaceConfig
    import proto_compiler

    source = Path.cwd()
    configs = {
        'multi_repo_system': WorkspaceConfig.from_file(str(source / 'examples/multi_repo_system/workspace.yaml')),
        'polyglot_system': WorkspaceConfig(base_dir=str(source / 'examples/polyglot_system'),
                                           repositories=[RepoConfig('fixture', '.')]),
        'polyglot_api': WorkspaceConfig(base_dir=str(source / 'benchmarks/polyglot_api'),
                                        repositories=[RepoConfig('backend', 'backend'), RepoConfig('frontend', 'frontend')]),
    }
    sys.addaudithook(guard)
    result = {}
    for name, config in configs.items():
        if not frozen:
            config.contract_bindings_v2 = True
        with (redirect_stdout(io.StringIO()),
              patch.object(proto_compiler, 'compile_proto_file', return_value=(None, 'guarded source fallback'))):
            graph = WorkspaceCKGBuilder(config).build()
        result[name] = dict(nodes=len(graph), edges=graph.number_of_edges(), sha256=graph_digest(graph))
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--frozen', action='store_true')
    print(json.dumps(snapshot(cli.parse_args().frozen), sort_keys=True))
