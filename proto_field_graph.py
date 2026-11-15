"""Protobuf message-field and typed request/response contract graph expansion.

These edges describe schema structure, NOT observed runtime value flow.
Message fields are source-grounded via Proto descriptors (when available).
"""
from __future__ import annotations


def emit_message_fields(graph, message_id, message, *, file_path=""):
    added = 0
    for name, field in sorted(message.fields.items()):
        field_id = f"{message_id}.field::{name}"
        metadata = {
            "id": field_id, "name": name, "type": "proto_field",
            "layer": "Lcontract", "file": file_path, "tag": field.tag,
            "type_name": field.type_name, "repeated": field.repeated,
            "optional": field.optional, "map_key_type": field.map_key_type,
            "map_value_type": field.map_value_type,
        }
        if field_id not in graph:
            graph.add_node(field_id, **metadata)
        key = f"declares::{message_id}:{field_id}"
        if not graph.has_edge(message_id, field_id, key=key):
            graph.add_edge(message_id, field_id, key=key,
                           relation="DECLARES_FIELD", layer="Lcontract")
            added += 1
    for nested_name, nested in sorted(message.nested_messages.items()):
        child_id = f"{message_id}.{nested_name}"
        if child_id not in graph:
            graph.add_node(
                child_id, id=child_id, name=nested_name, type="contract",
                layer="Lcontract", file=file_path)
        key = f"nested::{message_id}:{child_id}"
        if not graph.has_edge(message_id, child_id, key=key):
            graph.add_edge(message_id, child_id, key=key,
                           relation="NESTED_MESSAGE", layer="Lcontract")
            added += 1
        added += emit_message_fields(graph, child_id, nested, file_path=file_path)
    return added


def emit_rpc_message_types(graph, rpc_id, request_name, response_name):
    made = 0
    for message, relation, direction in (
            (request_name, "ACCEPTS_SCHEMA", "request"),
            (response_name, "RETURNS_SCHEMA", "response")):
        message_id = f"contract::message::{message}"
        if message_id not in graph or rpc_id not in graph:
            continue
        source, target = (
            (message_id, rpc_id) if direction == "request"
            else (rpc_id, message_id)
        )
        key = f"rpc_schema::{direction}::{rpc_id}:{message_id}"
        if not graph.has_edge(source, target, key=key):
            graph.add_edge(source, target, key=key,
                           relation=relation, layer="Lcontract",
                           schema_type=message, schema_direction=direction)
            made += 1
    return made
