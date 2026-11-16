import pytest
from otlp_manifest import otlp_to_signals


def test_otlp_json_converts_all_three_signals_without_guessing_deployment():
    attrs = [{"key": "service.name", "value": {"stringValue": "checkout"}},
             {"key": "service.version", "value": {"stringValue": "v1"}},
             {"key": "sckg.deployment.id", "value": {"stringValue": "dep1"}}]
    doc = {
        "resourceSpans": [{"resource": {"attributes": attrs}, "scopeSpans": [{"spans": [{"startTimeUnixNano": "1794736800000000000"}]}]}],
        "resourceLogs": [{"resource": {"attributes": attrs[:-1]}, "scopeLogs": [{"logRecords": [{"timeUnixNano": "1794736800000000000"}]}]}],
        "resourceMetrics": [{"resource": {"attributes": attrs}, "scopeMetrics": [{"metrics": [{"gauge": {"dataPoints": [{"timeUnixNano": "1794736800000000000"}]}}]}]}]
    }
    signals = otlp_to_signals(doc)
    assert [r["type"] for r in signals] == ["span", "log", "metric"]
    assert signals[0]["deployment_id"] == "dep1"
    assert "deployment_id" not in signals[1]
    assert len({r["id"] for r in signals}) == 3
    assert otlp_to_signals(doc) == signals


def test_otlp_rejects_missing_clock_and_invalid_type():
    with pytest.raises(ValueError, match="timestamp"):
        otlp_to_signals({"resourceSpans": [{"scopeSpans": [{"spans": [{}]}]}]})
    with pytest.raises(ValueError):
        otlp_to_signals({"resourceLogs": {}})


def test_duplicate_resource_identity_keys_rejected():
    attrs = [{"key": "sckg.deployment.id", "value": {"stringValue": "safe"}},
             {"key": "sckg.deployment.id", "value": {"stringValue": "wrong"}}]
    payload = {"resourceSpans": [{"resource": {"attributes": attrs},
               "scopeSpans": [{"spans": [{"startTimeUnixNano": "1794736800000000000"}]}]}]}
    with pytest.raises(ValueError, match="duplicate OTLP"):
        otlp_to_signals(payload)


def test_timestamp_precision_invalid_types_and_metric_oneof():
    from otlp_manifest import _timestamp_ns
    assert _timestamp_ns("1000000001") == "1970-01-01T00:00:01+00:00"
    assert _timestamp_ns("1000001000") == "1970-01-01T00:00:01.000001+00:00"
    for bad in (1.5, True, None, "0", "1.2", "-1"):
        with pytest.raises(ValueError):
            _timestamp_ns(bad)
    payload = {"resourceMetrics": [{"scopeMetrics": [{"metrics": [
        {"gauge": {"dataPoints": []}, "sum": {"dataPoints": []}}
    ]}]}]}
    with pytest.raises(ValueError, match="one point kind"):
        otlp_to_signals(payload)
