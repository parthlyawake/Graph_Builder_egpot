"""Conservative Kafka topic to Avro/PDL payload type relationships.

A Kafka topic is not an Avro record. Bind a schema only when a Java
KafkaTemplate generic value type or KafkaListener argument explicitly names
a unique indexed schema type and is tied to a literal topic.
"""
from __future__ import annotations

import re
from collections import defaultdict


def _schemas(graph):
    by_simple = defaultdict(set)
    for node, data in graph.nodes(data=True):
        if data.get("type") != "schema_contract":
            continue
        if not node.startswith(("contract::avro::", "contract::pdl::")):
            continue
        name = str(data.get("name", node.rsplit(".", 1)[-1]))
        by_simple[name].add(node)
    return by_simple


def _topics(text):
    """Extract literal Java listener topic arrays and typed KafkaTemplate sends."""
    listener = re.compile(
        r'@\s*KafkaListener\s*\(\s*(?:topics\s*=\s*)?(\{[^{}]*\}|"[^"]+")',
        re.DOTALL,
    )
    for match in listener.finditer(text):
        raw = match.group(1)
        if raw.startswith("{"):
            topics = re.findall(r'"([^"]+)"', raw)
            if re.sub(r'"[^"]+"|[\s{},]', "", raw):
                continue
        else:
            topics = [raw[1:-1]]
        suffix = text[match.end():match.end() + 700]
        method = re.search(
            r'(?:public|protected|private)\s+(?:(?:static|final|synchronized)\s+)*'
            r'[\w.<>\[\], ?]+\s+\w+\s*\(([^)]*)\)',
            suffix,
        )
        if not method:
            continue
        params = method.group(1).strip()
        record = re.search(
            r'\bConsumerRecord\s*<\s*[\w.?]+\s*,\s*([\w.]+)\s*>\s+\w+', params
        )
        ordinary = re.match(r'(?:final\s+)?([\w.]+)\s+\w+\b', params)
        value_type = record.group(1) if record else ordinary.group(1) if ordinary else None
        if value_type:
            for topic in topics:
                if topic and ("$"+"{") not in topic and ("#"+"{") not in topic:
                    yield topic, value_type.split(".")[-1], match.start(), "java_kafka_listener"

    generic = re.compile(
        r'\bKafkaTemplate\s*<\s*[\w.?]+\s*,\s*([\w.]+)\s*>\s*([A-Za-z_]\w*)'
    )
    typed = {m.group(2): m.group(1).split(".")[-1] for m in generic.finditer(text)}
    for match in re.finditer(
        r'\b([A-Za-z_]\w*)\s*\.\s*send\s*\(\s*"([^"]+)"', text
    ):
        if (match.group(1) in typed and ("$"+"{") not in match.group(2)
                and ("#"+"{") not in match.group(2)):
            yield match.group(2), typed[match.group(1)], match.start(), "java_kafka_template"

def bind_kafka_payload_schemas(graph, builders):
    types = _schemas(graph)
    count = 0
    for builder in builders:
        for file, lines in sorted(builder.raw_file_lines.items()):
            if not file.endswith(".java"):
                continue
            source = "\n".join(lines)
            if "KafkaListener" not in source and "KafkaTemplate" not in source:
                continue
            # Do not infer relationships from comment-only examples.
            from message_topology import _comments
            source = _comments(source)
            for topic, type_name, offset, kind in _topics(source):
                matching = types.get(type_name, set())
                topic_node = "topic::kafka::" + topic
                if topic_node not in graph or len(matching) != 1:
                    continue
                target = next(iter(matching))
                edge_id = f"kafka_schema::{topic_node}::{target}::{file}:{offset}"
                if graph.has_edge(topic_node, target, key=edge_id):
                    continue
                graph.add_edge(
                    topic_node, target, key=edge_id,
                    relation="PAYLOAD_SCHEMA", layer="Lcontract",
                    c_type=1.0, binding_kind=kind,
                    source_evidence=f"{file}:{source.count(chr(10), 0, offset)+1}",
                    value_type=type_name,
                )
                count += 1
    return count
