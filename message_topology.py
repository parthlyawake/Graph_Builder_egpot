"""AMQP exchange-to-queue topology from source-evidenced broker bindings.

Do not equate an exchange/routing-key publication with direct queue delivery.
Runtime-only declarations or unresolved routing semantics remain unconnected.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict


def _comments(text):
    """Mask C-family comments without changing source offsets."""
    out, i, quote, esc = list(text), 0, None, False
    while i < len(text):
        c = text[i]
        if quote:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"', chr(96)):
            quote = c
            i += 1
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            multi = text.startswith("/*", i)
            end = text.find("*/" if multi else "\n", i+2)
            if end < 0:
                end = len(text)
            else:
                end += 2 if multi else 0
            for k in range(i, end):
                if text[k] != "\n":
                    out[k] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def _python_bindings(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr != "queue_bind":
            continue
        kwargs = {}
        for k in call.keywords:
            if k.arg and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str):
                kwargs[k.arg] = k.value.value
        for k, v in zip(("queue", "exchange", "routing_key"), call.args):
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                kwargs[k] = v.value
        if kwargs.get("queue") and kwargs.get("exchange"):
            yield kwargs["queue"], kwargs["exchange"], kwargs.get("routing_key", ""), call.lineno, "pika"


def _bindings(text, extension):
    if extension == ".py":
        yield from _python_bindings(text)
        return
    clean = _comments(text)
    lit = r'"([^"\\]*(?:\\.[^"\\]*)*)"'
    if extension in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        pat = r"\.\s*bindQueue\s*\(\s*" + lit + r"\s*,\s*" + lit + r"\s*,\s*" + lit
        for m in re.finditer(pat, clean):
            yield m[1], m[2], m[3], clean.count("\n", 0, m.start())+1, "amqplib"
    elif extension == ".go":
        pat = r"\.\s*QueueBind\s*\(\s*" + lit + r"\s*,\s*" + lit + r"\s*,\s*" + lit
        for m in re.finditer(pat, clean):
            yield m[1], m[3], m[2], clean.count("\n", 0, m.start())+1, "go_amqp"
    elif extension in (".java", ".kt"):
        pat = (r"\bnew\s+Binding\s*\(\s*" + lit +
               r"\s*,\s*(?:Binding\.)?DestinationType\.QUEUE\s*,\s*" +
               lit + r"\s*,\s*" + lit)
        for m in re.finditer(pat, clean):
            yield m[1], m[2], m[3], clean.count("\n", 0, m.start())+1, "spring_binding"
        beans = {}
        bean_pat = (r"\b(?:public\s+)?(?:Queue|DirectExchange|TopicExchange|FanoutExchange)"
                    r"\s+(\w+)\s*\([^)]*\)\s*\{\s*return\s+new\s+"
                    r"(Queue|DirectExchange|TopicExchange|FanoutExchange)\s*\(\s*" + lit)
        for m in re.finditer(bean_pat, clean):
            beans[m[1]] = (m[3], m[2])
        binding_pat = (r"\bBindingBuilder\s*\.\s*bind\s*\(\s*(\w+)\s*\(\s*\)\s*\)"
                       r"\s*\.\s*to\s*\(\s*(\w+)\s*\(\s*\)\s*\)"
                       r"(?:\s*\.\s*with\s*\(\s*" + lit + r"\s*\))?")
        for m in re.finditer(binding_pat, clean):
            queue, exchange = beans.get(m[1]), beans.get(m[2])
            if queue and exchange and queue[1] == "Queue":
                yield queue[0], exchange[0], m[3] or "", clean.count("\n", 0, m.start())+1, "spring_builder"
    elif extension in (".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"):
        pat = r"(?:->|\.)\s*(?:BindQueue|bindQueue)\s*\(\s*" + lit + r"\s*,\s*" + lit + r"\s*,\s*" + lit
        for m in re.finditer(pat, clean):
            yield m[1], m[2], m[3], clean.count("\n", 0, m.start())+1, "cpp_amqp"


def _exchange_types(text):
    clean = _comments(text)
    for kind in ("Direct", "Topic", "Fanout"):
        for m in re.finditer(r"\bnew\s+" + kind + r"Exchange\s*\(\s*['\"]([^'\"]+)['\"]", clean):
            yield m[1], kind.lower()
    pat = r"\.\s*(?:assertExchange|exchange_declare|ExchangeDeclare)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"](direct|topic|fanout)['\"]"
    for m in re.finditer(pat, clean):
        yield m[1], m[2]


def _topic_match(pattern, value):
    p, s = pattern.split("."), value.split(".")
    def match(i, j):
        if i == len(p):
            return j == len(s)
        if p[i] == "#":
            return match(i+1, j) or (j < len(s) and match(i, j+1))
        return j < len(s) and (p[i] == "*" or p[i] == s[j]) and match(i+1, j+1)
    return match(0, 0)


def bind_amqp_topology(graph, builders):
    """Route only explicit source-backed exchange/binding/queue relationships."""
    types, bindings = defaultdict(set), []
    for builder in builders:
        for file, lines in sorted(builder.raw_file_lines.items()):
            text = "\n".join(lines)
            for name, kind in _exchange_types(text):
                types[name].add(kind)
            ext = "." + file.rsplit(".", 1)[-1] if "." in file else ""
            for queue, exchange, key, line, source in _bindings(text, ext):
                bindings.append((queue, exchange, key, file, line, source))
    created = 0
    for queue, exchange, key, file, line, how in bindings:
        dest = "queue::amqp::" + queue
        if dest not in graph:
            graph.add_node(dest, type="queue_contract", layer="Lcontract",
                           broker_kind="queue::amqp", name=queue)
        kinds = types.get(exchange, set())
        if len(kinds) > 1:
            continue
        kind = next(iter(kinds), None)
        prefix = "topic::amqp::" + exchange + "/"
        for node in list(graph.nodes):
            if not node.startswith(prefix):
                continue
            published = node[len(prefix):]
            if not (published == key or kind == "fanout" or
                    (kind == "topic" and _topic_match(key, published))):
                continue
            edge_id = f"amqp_route::{node}::{dest}::{file}:{line}"
            if graph.has_edge(node, dest, key=edge_id):
                continue
            graph.add_edge(node, dest, key=edge_id, relation="ROUTES_TO",
                           layer="Lcontract", c_type=1.0, exchange=exchange,
                           exchange_type=kind or "unknown", routing_key=key,
                           source_evidence=f"{file}:{line}", binding_kind=how)
            created += 1
    return {"explicit_bindings": len(bindings), "routed_edges": created}
