"""Translate OTLP/JSON export requests into explicit GRAFT-CKG telemetry records.

Only resource attribute 'sckg.deployment.id' can bind a signal to a deployment;
service.name or service.version alone are never sufficient evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json


def _attributes(items):
    if not isinstance(items, list):
        raise ValueError("OTLP resource.attributes must be an array")
    out = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            raise ValueError("invalid OTLP attribute")
        value = item.get("value", {})
        if not isinstance(value, dict):
            raise ValueError("invalid OTLP attribute value")
        # Keep string attributes only; no speculative object-to-identity coercion.
        if "stringValue" in value:
            if not isinstance(value["stringValue"], str):
                raise ValueError("OTLP stringValue must be a string")
            out[item["key"]] = value["stringValue"]
    return out


def _timestamp_ns(value):
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OTLP timestamp required as Unix nanoseconds") from exc
    if n <= 0:
        raise ValueError("OTLP signal requires a positive Unix nanosecond time")
    return datetime.fromtimestamp(n / 1_000_000_000, tz=timezone.utc).isoformat()


def otlp_to_signals(payload: dict) -> list[dict]:
    """Parse resourceSpans, resourceLogs and resourceMetrics ExportRequest JSON.

    This adapter does not fetch collectors or verify provenance. IDs depend on
    the payload's canonical content, position and signal type. Returns only
    manifest-ready records; use ingest_operational_evidence for strict joins.
    """
    if not isinstance(payload, dict):
        raise ValueError("OTLP payload must be an object")
    signals = []
    canonical_hash = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

    def append(kind, item, resource, timestamp, ordinal):
        attrs = _attributes(resource.get("attributes", []))
        metadata = {k: attrs[k] for k in ("service.name", "service.version") if k in attrs}
        record = {"id": f"otlp-{canonical_hash}-{kind}-{ordinal}", "type": kind,
                  "timestamp": _timestamp_ns(timestamp), "resource": metadata}
        deployment_id = attrs.get("sckg.deployment.id")
        if deployment_id:
            record["deployment_id"] = deployment_id
        signals.append(record)

    categories = (
        ("resourceSpans", "scopeSpans", "spans", "span", ("startTimeUnixNano",)),
        ("resourceLogs", "scopeLogs", "logRecords", "log", ("timeUnixNano", "observedTimeUnixNano")),
    )
    for root_key, scope_key, item_key, kind, clocks in categories:
        groups = payload.get(root_key, [])
        if not isinstance(groups, list):
            raise ValueError(f"{root_key} must be a list")
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError(f"invalid {root_key} entry")
            resource = group.get("resource", {})
            if not isinstance(resource, dict):
                raise ValueError("OTLP resource must be an object")
            scopes = group.get(scope_key, [])
            if not isinstance(scopes, list):
                raise ValueError(f"{scope_key} must be a list")
            for scope in scopes:
                items = scope.get(item_key, [])
                if not isinstance(items, list):
                    raise ValueError(f"{item_key} must be a list")
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError("OTLP signal must be an object")
                    ts = next((item[c] for c in clocks if item.get(c)), None)
                    append(kind, item, resource, ts, len(signals))

    groups = payload.get("resourceMetrics", [])
    if not isinstance(groups, list):
        raise ValueError("resourceMetrics must be a list")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("resource", {}), dict):
            raise ValueError("invalid resourceMetrics entry")
        resource = group.get("resource", {})
        scopes = group.get("scopeMetrics", [])
        if not isinstance(scopes, list):
            raise ValueError("scopeMetrics must be a list")
        for scope in scopes:
            metrics = scope.get("metrics", [])
            if not isinstance(metrics, list):
                raise ValueError("metrics must be a list")
            for metric in metrics:
                if not isinstance(metric, dict):
                    raise ValueError("invalid OTLP metric")
                # One data point -> one time-localized metric evidence record.
                for typ in ("gauge", "sum", "histogram", "exponentialHistogram", "summary"):
                    data = metric.get(typ)
                    if data is None:
                        continue
                    if not isinstance(data, dict) or not isinstance(data.get("dataPoints", []), list):
                        raise ValueError("invalid OTLP metric dataPoints")
                    for point in data.get("dataPoints", []):
                        append("metric", point, resource, point.get("timeUnixNano"), len(signals))
    return signals
