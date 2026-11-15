"""Local compiler-index and Language Server Protocol resolution.

Opt-in configuration: repository/.sckg_lsp.json
{
  "scip_indexes": ["index.scip.json"],
  "definition_indexes": ["definitions.json"],
  "servers": {"python": ["pylsp"]},
  "timeout_seconds": 5
}
SCIP files must be JSON exports; language servers must be installed locally.
No downloads or remote LSP calls are performed. No ambiguous definition is
promoted to an exact binding.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from lsp_augmenter import LSPIndexProvider

LANGUAGES = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescriptreact",
    ".js": "javascript", ".jsx": "javascriptreact", ".java": "java",
    ".cs": "csharp", ".go": "go", ".kt": "kotlin",
}


def _relative(root, location):
    if location.startswith("file://"):
        p = Path(unquote(urlparse(location).path))
    else:
        p = Path(location)
        if not p.is_absolute():
            p = Path(root) / p
    try:
        return p.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def _definition_node(builder, path, line):
    matches = [
        nid for nid, data in builder.graph.nodes(data=True)
        if data.get("type") in {"function", "class", "interface", "method"} and
        data.get("file", "").removeprefix(builder.repo_prefix) == path and
        data.get("line_no") == line
    ]
    return matches[0] if len(matches) == 1 else None


def import_scip_json(builder, path, provider):
    """Resolve SCIP occurrences with exact symbol IDs and declaration positions."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    documents = data.get("documents", ())
    definitions = {}
    for document in documents:
        rel = document.get("relative_path", "").replace("\\", "/")
        for occurrence in document.get("occurrences", ()):
            if int(occurrence.get("symbol_roles", 0)) & 1:
                position = occurrence.get("range") or []
                if not position:
                    continue
                target = _definition_node(builder, rel, int(position[0]) + 1)
                if target:
                    definitions.setdefault(occurrence["symbol"], set()).add(target)
    added = 0
    for document in documents:
        rel = document.get("relative_path", "").replace("\\", "/")
        lines = builder.raw_file_lines.get(rel, ())
        for occurrence in document.get("occurrences", ()):
            if int(occurrence.get("symbol_roles", 0)) & 1:
                continue
            targets = definitions.get(occurrence.get("symbol"), ())
            if len(targets) != 1:
                continue
            position = occurrence.get("range") or []
            if len(position) < 2:
                continue
            row, column = int(position[0]), int(position[1])
            if not 0 <= row < len(lines):
                continue
            name = re.match(r"[A-Za-z_$][\w$]*", lines[row][column:])
            if not name:
                continue
            provider.register(rel, name.group(0), next(iter(targets)), line=row + 1)
            added += 1
    return added


class LanguageServer:
    """Persistent local JSON-RPC server with Content-Length framing."""

    def __init__(self, command, root, timeout=5):
        self.root = Path(root).resolve()
        self.timeout = max(0.25, float(timeout))
        self.proc = subprocess.Popen(
            list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=str(self.root), bufsize=0)
        self.responses = queue.Queue()
        self.serial = 0
        self.opened = set()
        self._lock = threading.Lock()
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._request("initialize", {
            "processId": os.getpid(), "rootUri": self.root.as_uri(),
            "capabilities": {"textDocument": {"definition": {"linkSupport": True}}},
            "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
        })
        self._notify("initialized", {})

    def _read_loop(self):
        stream = self.proc.stdout
        try:
            while stream and not stream.closed:
                length = None
                while True:
                    line = stream.readline()
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1].strip())
                if length is None or length > 16_000_000:
                    return
                payload = stream.read(length)
                if len(payload) != length:
                    return
                try:
                    packet = json.loads(payload.decode("utf-8"))
                except ValueError:
                    continue
                if "id" in packet and ("result" in packet or "error" in packet):
                    self.responses.put(packet)
        finally:
            self.responses.put({"error": {"message": "server stream closed"}})

    def _send(self, packet):
        payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
        with self._lock:
            self.proc.stdin.write(frame)
            self.proc.stdin.flush()

    def _notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method, params):
        self.serial += 1
        current = self.serial
        self._send({"jsonrpc": "2.0", "id": current, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Language server timed out: {method}")
            try:
                packet = self.responses.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f"Language server timed out: {method}") from exc
            if packet.get("id") == current:
                return None if "error" in packet else packet.get("result")
            if "id" not in packet:
                raise RuntimeError("Language server terminated")

    def definition(self, rel, line, col):
        source = self.root / rel
        if not source.is_file():
            return None
        uri = source.resolve().as_uri()
        if uri not in self.opened:
            self._notify("textDocument/didOpen", {
                "textDocument": {
                    "uri": uri,
                    "languageId": LANGUAGES.get(source.suffix.lower(), "plaintext"),
                    "version": 1,
                    "text": source.read_text(encoding="utf-8", errors="replace"),
                }
            })
            self.opened.add(uri)
        return self._request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": col},
        })

    def close(self):
        if self.proc.poll() is None:
            try:
                self._request("shutdown", {})
                self._notify("exit", {})
            except (TimeoutError, OSError, RuntimeError):
                pass
            self.proc.terminate()
        try:
            self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class CompilerResolver:
    """Map an actual source callsite through a local LSP definition to graph ID."""

    def __init__(self, builder, commands, timeout):
        self.builder = builder
        self.commands = commands
        self.timeout = timeout
        self.sessions = {}
        self.cache = {}

    def __call__(self, file, line, spelling):
        if line is None:
            return None
        occurrences = [
            evidence for evidence in self.builder.callsite_evidence
            if evidence.get("file") == file and evidence.get("line") == line
            and (evidence.get("callee") == spelling or
                 evidence.get("callee", "").rsplit(".", 1)[-1] == spelling)
        ]
        if len(occurrences) != 1:
            return None
        column = int(occurrences[0]["column"])
        language = LANGUAGES.get(Path(file).suffix.lower(), "")
        command = self.commands.get(language) or self.commands.get({
            "typescriptreact": "typescript", "javascriptreact": "javascript",
        }.get(language, language))
        if not isinstance(command, list) or not command:
            return None
        key = (file, line, column, spelling)
        if key in self.cache:
            return self.cache[key]
        try:
            if language not in self.sessions:
                self.sessions[language] = LanguageServer(
                    command, self.builder.repo_path, self.timeout)
            response = self.sessions[language].definition(file, line, column)
        except (OSError, RuntimeError, TimeoutError):
            return None
        if isinstance(response, dict):
            response = [response]
        matches = set()
        for item in response or []:
            location = item.get("targetUri") or item.get("uri", "")
            position = (
                item.get("targetSelectionRange") or
                item.get("targetRange") or item.get("range") or {}
            ).get("start", {})
            rel = _relative(self.builder.repo_path, location)
            if rel is None:
                continue
            target = _definition_node(
                self.builder, rel, int(position.get("line", -1)) + 1)
            if target:
                matches.add(target)
        selected = next(iter(matches)) if len(matches) == 1 else None
        self.cache[key] = selected
        return selected

    def close(self):
        for session in self.sessions.values():
            session.close()
        self.sessions.clear()


def configure_compiler_provider(builder):
    """Discover local compiler indexes; start configured servers on demand."""
    manifest = Path(builder.repo_path) / ".sckg_lsp.json"
    if not manifest.is_file():
        return builder.lsp_provider
    config = json.loads(manifest.read_text(encoding="utf-8"))
    provider = builder.lsp_provider or LSPIndexProvider()
    for name in config.get("definition_indexes", []):
        path = (manifest.parent / name).resolve()
        if path.is_relative_to(manifest.parent.resolve()) and path.is_file():
            provider.load_from_file(str(path))
    for name in config.get("scip_indexes", []):
        path = (manifest.parent / name).resolve()
        if path.is_relative_to(manifest.parent.resolve()) and path.is_file():
            import_scip_json(builder, path, provider)
    # Source repositories are untrusted. Never execute repo-declared
    # language-server commands without a deliberate host-side opt-in.
    commands = (config.get("servers", {})
                if os.environ.get("SCKG_ALLOW_LSP_SUBPROCESS") == "1" else {})
    if commands:
        resolver = CompilerResolver(
            builder, commands, config.get("timeout_seconds", 5))
        provider.set_dynamic_resolver(resolver)
        builder.compiler_resolver = resolver
    builder.lsp_provider = provider
    return provider
