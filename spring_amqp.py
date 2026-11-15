"""Source-grounded Spring AMQP listener-container and adapter resolution.

Covers queues configured through SimpleMessageListenerContainer#setQueueNames
and the MessageListenerAdapter default handler method. Configuration alone
does not prove a listener, so the queue, adapter and handler wiring must
appear together in source.
"""
from __future__ import annotations

import re

from message_topology import _comments


def _constants(clean):
    result = {}
    for match in re.finditer(
        r"\b(?:final\s+)?(?:static\s+)?(?:final\s+)?String\s+"
        r"([A-Za-z_]\w*)\s*=\s*\"([^\"]+)\"\s*;", clean
    ):
        if match.group(1) in result and result[match.group(1)] != match.group(2):
            result[match.group(1)] = None
        else:
            result[match.group(1)] = match.group(2)
    return result


def _constant(expr, constants):
    expr = expr.strip()
    if len(expr) >= 2 and expr[0] == expr[-1] == '"':
        return expr[1:-1]
    expr = re.sub(r"^this\.", "", expr)
    return constants.get(expr)


def _source_handlers(builder, class_name, method_name):
    matched = [
        nid for nid, data in builder.graph.nodes(data=True)
        if data.get("type") in {"function", "method"}
        and data.get("name") == method_name
        and class_name in nid
    ]
    return matched[0] if len(set(matched)) == 1 else None


def bind_spring_listener_containers(builder):
    graph = builder.graph
    linked = 0
    for file, lines in sorted(builder.raw_file_lines.items()):
        if not file.endswith((".java", ".kt")):
            continue
        content = "\n".join(lines)
        if "SimpleMessageListenerContainer" not in content or "MessageListenerAdapter" not in content:
            continue
        text = _comments(content)
        constants = _constants(text)
        queues = set()
        for m in re.finditer(r"\.\s*setQueueNames\s*\(\s*([^),]+)", text):
            queue = _constant(m.group(1), constants)
            if queue:
                queues.add(queue)
        if not queues or "setMessageListener" not in text:
            continue
        # The Spring adapter's default method is handleMessage unless an
        # explicit setDefaultListenerMethod overrides it.
        default = re.search(
            r"\.\s*setDefaultListenerMethod\s*\(\s*\"([A-Za-z_]\w*)\"", text
        )
        method = default[1] if default else "handleMessage"
        named_fields = {
            v: cls
            for cls, v in re.findall(
                r"\b([A-Z][A-Za-z_]\w*)\s+([a-z_][A-Za-z_0-9]*)\s*;", text
            )
        }
        adapter_args = re.findall(
            r"\bnew\s+MessageListenerAdapter\s*\(\s*([a-zA-Z_]\w*)", text
        )
        typed = {named_fields.get(arg) for arg in adapter_args if arg in named_fields}
        typed.discard(None)
        if len(typed) != 1:
            continue
        handler_class = next(iter(typed))
        handler = _source_handlers(builder, handler_class, method)
        if handler is None:
            continue
        for queue in queues:
            nid = "queue::amqp::" + queue
            if nid not in graph:
                graph.add_node(nid, type="queue_contract", name=queue,
                               layer="Lcontract", broker_kind="queue::amqp")
            key = f"spring_container::{handler}::{nid}::{file}"
            if graph.has_edge(handler, nid, key=key):
                continue
            graph.add_edge(
                handler, nid, key=key, relation="CONSUMES_EVENT", layer="Lcontract",
                c_type=1.0, binding_kind="spring_message_listener_adapter",
                source_evidence=file, handler_method=method)
            linked += 1
    return linked
