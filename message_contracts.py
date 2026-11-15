"""Source-evidenced AMQP/RabbitMQ and Kafka event edges.

This pass creates producer/consumer edges only when call syntax, a known client
library and a literal destination agree. An AMQP exchange/routing key is NOT
automatically equivalent to a queue: the broker binding is a separate fact.
"""
from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

from tree_sitter import Language, Parser


def _node(builder, caller, kind, name, file, line, relation):
    if not caller or caller not in builder.graph or not isinstance(name, str) or not name:
        return
    if re.search(r"\s|[{}$]", name) or len(name) > 240:
        return
    nid = kind + "::" + name
    if nid not in builder.graph:
        builder.current_file = file
        builder.add_ckg_node(nid, "topic_contract" if kind.startswith("topic") else "queue_contract",
                             "Lcontract", name, line, code="")
        builder.graph.nodes[nid]["broker_kind"] = kind
    if not any(v == nid and d.get("relation") == relation
               for _, v, d in builder.graph.out_edges(caller, data=True)):
        builder.current_file = file
        builder.add_ckg_edge(caller, nid, relation, "Lcontract")


def _literal_py(node, env=None):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return (env or {}).get(node.id)
    return None


def _python(builder, file, text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    }
    from_imports = {node.module or "" for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)}
    pika = "pika" in imported or any(m.startswith("pika") for m in from_imports)
    kafka = any("kafka" in m for m in imported | from_imports)
    if not pika and not kafka:
        return

    def walk_function(fn):
        name = fn.name
        candidates = [nid for nid, d in builder.graph.nodes(data=True)
                      if d.get("type") == "function" and
                      d.get("line_no") == fn.lineno and
                      d.get("file") == builder.repo_prefix + file]
        caller = candidates[0] if len(candidates) == 1 else None
        if caller is None:
            return
        locals_ = {}
        for statement in fn.body:
            # Do not promote values assigned conditionally to certain evidence.
            if isinstance(statement, (ast.If, ast.For, ast.While, ast.Try, ast.Match)):
                locals_.clear()
            if isinstance(statement, ast.Assign):
                val = _literal_py(statement.value, locals_)
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        locals_[target.id] = val
            for call in ast.walk(statement):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                action = call.func.attr
                values = [_literal_py(v, locals_) for v in call.args]
                kwargs = {k.arg: _literal_py(k.value, locals_) for k in call.keywords
                          if k.arg}

                if pika:
                    if action == "basic_publish":
                        exchange = kwargs.get("exchange", values[0] if values else None)
                        routing = kwargs.get("routing_key", values[1] if len(values) > 1 else None)
                        if exchange == "" and routing:
                            _node(builder, caller, "queue::amqp", routing, file,
                                  call.lineno, "PRODUCES_EVENT")
                        elif exchange and routing:
                            _node(builder, caller, "topic::amqp",
                                  exchange + "/" + routing, file,
                                  call.lineno, "PRODUCES_EVENT")
                    elif action == "basic_consume":
                        queue = kwargs.get("queue", values[0] if values else None)
                        if queue:
                            _node(builder, caller, "queue::amqp", queue, file,
                                  call.lineno, "CONSUMES_EVENT")
                if kafka and action in {"send", "send_and_wait"} and values and values[0]:
                    _node(builder, caller, "topic::kafka", values[0], file,
                          call.lineno, "PRODUCES_EVENT")
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walk_function(item)


def _t(node, data):
    return data[node.start_byte:node.end_byte].decode("utf-8") if node else ""


def _string(node, data):
    raw = _t(node, data)
    if raw.startswith(('"', "'")) and len(raw) >= 2 and raw[-1] == raw[0]:
        return raw[1:-1]
    return None


def _caller(builder, file, node, data):
    cursor = node.parent
    while cursor:
        if cursor.type in {
            "method_declaration", "function_declaration",
            "function_definition", "method_definition",
            "arrow_function", "function", "function_expression",
        }:
            ln = cursor.start_point.row + 1
            candidates = [nid for nid, d in builder.graph.nodes(data=True)
                          if d.get("type") == "function"
                          and d.get("file") == builder.repo_prefix + file
                          and d.get("line_no") == ln]
            if len(candidates) == 1:
                return candidates[0]
        cursor = cursor.parent
    return None


def _tree_sitter(builder, file, text):
    suffix = PurePosixPath(file).suffix
    if suffix in {".java"}:
        import tree_sitter_java as grammar
    elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        import tree_sitter_javascript as grammar
    elif suffix in {".ts", ".tsx"}:
        import tree_sitter_typescript as grammar
    elif suffix == ".go":
        import tree_sitter_go as grammar
    else:
        return
    language = (grammar.language_tsx() if suffix == ".tsx" else
                grammar.language_typescript() if suffix == ".ts" else grammar.language())
    source = text.encode("utf-8")
    root = Parser(Language(language)).parse(source).root_node
    java_rabbit = bool(re.search(r"\b(?:RabbitTemplate|RabbitListener)\b", text))
    java_kafka = bool(re.search(r"\b(?:KafkaTemplate|KafkaListener)\b", text))
    js_amqp = bool(re.search(r"\b(?:amqplib|amqp-connection-manager)\b", text))
    go_amqp = bool(re.search(r'["\'][^"\']*/(?:amqp091-go|amqp)["\']', text))

    def nodes(n):
        yield n
        for child in n.named_children:
            yield from nodes(child)

    for node in nodes(root):
        if node.type in {"method_declaration", "function_declaration"} and suffix == ".java":
            caller = _caller(builder, file, node, source)
            if caller is None:
                candidates = [nid for nid, d in builder.graph.nodes(data=True)
                              if d.get("type") == "function" and
                              d.get("file") == builder.repo_prefix + file and
                              d.get("line_no") == node.start_point.row + 1]
                caller = candidates[0] if len(candidates) == 1 else None
            if caller is not None:
                raw = _t(node, source)
                ann = re.search(r"@RabbitListener\s*\(\s*(?:queues\s*=\s*)?[\"]([^\"]+)[\"]", raw)
                if java_rabbit and ann:
                    _node(builder, caller, "queue::amqp", ann.group(1),
                          file, node.start_point.row + 1, "CONSUMES_EVENT")
                ann = re.search(r"@KafkaListener\s*\(\s*(?:topics\s*=\s*)?[\"]([^\"]+)[\"]", raw)
                if java_kafka and ann:
                    _node(builder, caller, "topic::kafka", ann.group(1),
                          file, node.start_point.row + 1, "CONSUMES_EVENT")
        if node.type not in {"method_invocation", "call_expression"}:
            continue
        caller = _caller(builder, file, node, source)
        if caller is None:
            continue
        args = node.child_by_field_name("arguments")
        argnodes = list(args.named_children) if args is not None else []
        values = [_string(arg, source) for arg in argnodes]
        callee = _t(node.child_by_field_name("function"), source) if node.type == "call_expression" else (
            _t(node.child_by_field_name("object"), source) + "." +
            _t(node.child_by_field_name("name"), source))
        action = callee.rsplit(".", 1)[-1]

        if suffix == ".java":
            if java_rabbit and "RabbitTemplate" in text:
                if action == "convertAndSend" and len(values) >= 2:
                    if len(values) >= 3 and values[0] and values[1]:
                        _node(builder, caller, "topic::amqp", values[0] + "/" + values[1],
                              file, node.start_point.row + 1, "PRODUCES_EVENT")
                    elif values[0]:
                        _node(builder, caller, "queue::amqp", values[0],
                              file, node.start_point.row + 1, "PRODUCES_EVENT")
            if java_kafka and action == "send" and values and values[0]:
                _node(builder, caller, "topic::kafka", values[0],
                      file, node.start_point.row + 1, "PRODUCES_EVENT")
        elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"} and js_amqp:
            if action in {"publish"} and len(values) >= 2 and values[0] and values[1]:
                _node(builder, caller, "topic::amqp", values[0] + "/" + values[1],
                      file, node.start_point.row + 1, "PRODUCES_EVENT")
            if action in {"sendToQueue", "consume"} and values and values[0]:
                _node(builder, caller, "queue::amqp", values[0],
                      file, node.start_point.row + 1,
                      "PRODUCES_EVENT" if action == "sendToQueue" else "CONSUMES_EVENT")
        elif suffix == ".go" and go_amqp:
            if action == "Publish" and len(values) >= 2 and values[0] and values[1]:
                _node(builder, caller, "topic::amqp", values[0] + "/" + values[1],
                      file, node.start_point.row + 1, "PRODUCES_EVENT")
            if action == "Consume" and values and values[0]:
                _node(builder, caller, "queue::amqp", values[0],
                      file, node.start_point.row + 1, "CONSUMES_EVENT")


def index_message_contracts(builder):
    for file, lines in sorted(builder.raw_file_lines.items()):
        text = "\n".join(lines)
        if not any(term in text for term in ("pika", "Rabbit", "Kafka", "amqplib", "amqp")):
            continue
        if file.endswith(".py"):
            _python(builder, file, text)
        else:
            _tree_sitter(builder, file, text)
