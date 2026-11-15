"""Protobuf fallback validation rejects malformed structure without claiming grammar parity."""
import pytest
from proto_parser import ProtoParser


@pytest.mark.parametrize("schema", [
    'syntax = "proto3"; service Broken { rpc Ping (Req) returns (Resp);',
    'syntax = "proto3"; }',
    'syntax = "proto3"; message Broken { string x = 1; }}',
    'syntax = "proto3"; option go_package = "unfinished;',
])
def test_invalid_schema_is_rejected(schema):
    with pytest.raises(ValueError):
        ProtoParser.validate_structure(schema)


def test_braces_inside_strings_and_comments_are_ignored():
    ProtoParser.validate_structure(
        'syntax = "proto3"; // unused }\n'
        'option java_package = "foo.{test}";\n'
        'message Ok { string value = 1; /* { */ }'
    )
