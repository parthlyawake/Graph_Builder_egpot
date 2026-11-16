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
