"""SDK server-base provenance for the OpenAPI binder only."""
import ast
from dataclasses import dataclass

from python_contract_requests import PythonRequests, _route, expression


SDK_BASES = frozenset({'self._gms_server', 'self.gms_server', 'self.config.gms_server'})
SDK_SESSIONS = frozenset({'self._session', 'self.session'})


@dataclass(frozen=True)
class SDKBase:
    spelling: str


def sdk_base(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == 'rstrip' and not node.keywords and len(node.args) == 1 and isinstance(
            node.args[0], ast.Constant
        ) and node.args[0].value == '/':
            node = node.func.value
    if isinstance(node, ast.Attribute):
        name = ast.unparse(node)
        if name in SDK_BASES:
            return SDKBase(name)
    return None


class SDKRequests(PythonRequests):
    @staticmethod
    def evaluate(node, values):
        return expression(node, values, sdk_base)

    def _registered_receiver(self, owner, spelling, local):
        if '.' in spelling and spelling not in SDK_SESSIONS:
            return False
        return super()._registered_receiver(owner, spelling, local)

    def requests(self):
        for endpoint, method, parts, origin in self.request_values():
            if not parts or not isinstance(parts[0], SDKBase) or len(parts) < 2:
                continue
            if not isinstance(parts[1], str) or not parts[1].startswith('/') or parts[1].startswith('//'):
                continue
            if any(isinstance(p, SDKBase) for p in parts[1:]):
                continue
            if route := _route((None, *parts[1:])):
                yield endpoint, method, *route, origin, parts[0].spelling


def workspace_sdk_requests(workspace):
    return sorted({row for builder in workspace.repo_builders.values()
                   for row in SDKRequests(builder).requests()})
