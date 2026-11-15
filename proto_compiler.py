"""Protobuf descriptor-backed parsing using the official protoc compiler.

When grpc_tools is installed and imports resolve, descriptor compilation gives
full Proto2/Proto3 grammar semantics. Otherwise callers retain their existing
conservative source parser. The caller must not claim descriptor completeness
on a fallback. Only files inside the configured repository are read.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path


def compile_proto_file(file_path, source_root):
    """Return (ProtoFile, 'protoc') or (None, diagnostic)."""
    try:
        from grpc_tools import protoc
        from google.protobuf import descriptor_pb2
        import grpc_tools
        from proto_parser import (
            ProtoField, ProtoRPC, ProtoMessage, ProtoService, ProtoFile
        )
    except ImportError:
        return None, "grpc_tools not installed"
    root, file_path = Path(source_root).resolve(), Path(file_path).resolve()
    if not file_path.is_relative_to(root) or file_path.suffix != ".proto":
        return None, "proto path outside source root"
    relative = file_path.relative_to(root).as_posix()
    with tempfile.TemporaryDirectory() as temp:
        descriptor_path = Path(temp) / "graph.pb"
        with contextlib.redirect_stderr(io.StringIO()):
            status = protoc.main([
                "protoc", f"-I{root}", f"-I{Path(grpc_tools.__file__).parent / '_proto'}",
                f"--descriptor_set_out={descriptor_path}",
                "--include_imports", relative
            ])
        if status != 0 or not descriptor_path.is_file():
            return None, "protoc returned an error (imports or invalid syntax)"
        descriptors = descriptor_pb2.FileDescriptorSet()
        descriptors.ParseFromString(descriptor_path.read_bytes())
    matched = next((item for item in descriptors.file if item.name == relative), None)
    if matched is None:
        return None, "compiled descriptor does not contain requested file"

    schema = ProtoFile(
        syntax=matched.syntax or "proto2",
        package=matched.package,
        imports=list(matched.dependency),
    )
    for enum in matched.enum_type:
        schema.enums[enum.name] = [x.name for x in enum.value]

    # Descriptor map-entry messages are compiler artifacts, not user message
    # declarations, but their key/value fields define map<K,V> properties.
    def lookup_nested(message, name):
        return next((m for m in message.nested_type if m.name == name), None)

    primitives = {
        descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE: "double",
        descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT: "float",
        descriptor_pb2.FieldDescriptorProto.TYPE_INT64: "int64",
        descriptor_pb2.FieldDescriptorProto.TYPE_UINT64: "uint64",
        descriptor_pb2.FieldDescriptorProto.TYPE_INT32: "int32",
        descriptor_pb2.FieldDescriptorProto.TYPE_FIXED64: "fixed64",
        descriptor_pb2.FieldDescriptorProto.TYPE_FIXED32: "fixed32",
        descriptor_pb2.FieldDescriptorProto.TYPE_BOOL: "bool",
        descriptor_pb2.FieldDescriptorProto.TYPE_STRING: "string",
        descriptor_pb2.FieldDescriptorProto.TYPE_BYTES: "bytes",
        descriptor_pb2.FieldDescriptorProto.TYPE_UINT32: "uint32",
        descriptor_pb2.FieldDescriptorProto.TYPE_SFIXED32: "sfixed32",
        descriptor_pb2.FieldDescriptorProto.TYPE_SFIXED64: "sfixed64",
        descriptor_pb2.FieldDescriptorProto.TYPE_SINT32: "sint32",
        descriptor_pb2.FieldDescriptorProto.TYPE_SINT64: "sint64",
    }

    def convert_message(descriptor):
        message = ProtoMessage(name=descriptor.name)
        for field in descriptor.field:
            typename = (
                field.type_name.rsplit(".", 1)[-1]
                if field.type_name
                else primitives.get(field.type, "unknown")
            )
            map_key = map_value = ""
            if field.type == descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE:
                nested = lookup_nested(descriptor, typename)
                if nested and nested.options.map_entry:
                    key, value = nested.field
                    map_key = primitives.get(key.type, key.type_name.rsplit(".", 1)[-1])
                    map_value = primitives.get(value.type, value.type_name.rsplit(".", 1)[-1])
                    typename = f"map<{map_key},{map_value}>"
            message.fields[field.name] = ProtoField(
                name=field.name, type_name=typename, tag=field.number,
                repeated=(field.label == descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
                          and not map_key),
                optional=bool(field.proto3_optional) or
                         field.label == descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
                map_key_type=map_key, map_value_type=map_value,
            )
        for nested in descriptor.nested_type:
            if not nested.options.map_entry:
                message.nested_messages[nested.name] = convert_message(nested)
        for enum in descriptor.enum_type:
            message.enums[enum.name] = [value.name for value in enum.value]
        return message

    for message in matched.message_type:
        if not message.options.map_entry:
            schema.messages[message.name] = convert_message(message)
    for service in matched.service:
        item = ProtoService(name=service.name)
        for method in service.method:
            item.rpcs[method.name] = ProtoRPC(
                name=method.name,
                request_type=method.input_type.rsplit(".", 1)[-1],
                response_type=method.output_type.rsplit(".", 1)[-1],
                request_stream=method.client_streaming,
                response_stream=method.server_streaming,
            )
        schema.services[item.name] = item
    return schema, "protoc"
