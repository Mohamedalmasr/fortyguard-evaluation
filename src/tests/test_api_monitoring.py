from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api_client import FortyGuardClient


BASE_URL = "https://example.invalid"
API_KEY = "synthetic-api-key"
BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
}
VALID_RULE = {
    "operator": "above",
    "spatial_aggregation": "maximum",
    "temporal_aggregation": "average",
    "unit": "celsius",
}


def build_client(transport):
    return FortyGuardClient(BASE_URL, API_KEY, transport, timeout=4)


def valid_monitor_body():
    return {
        "heatmap_id": "heatmap-123",
        "name": "Monitor name",
        "boundary_geojson": deepcopy(BOUNDARY),
        "rules": [deepcopy(VALID_RULE)],
        "notifications": {"email": ["ops@example.invalid"]},
    }


def success_transport(status_code=200):
    return Mock(return_value=SimpleNamespace(status_code=status_code))


def test_valid_monitor_creation_reaches_fake_transport_unchanged():
    body = valid_monitor_body()
    body.update({"enabled": True, "generate_report": False, "future_field": "preserved"})
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_args.args == ("POST", f"{BASE_URL}/v1/monitors")
    assert transport.call_args.kwargs["json"] == body


@pytest.mark.parametrize(
    "boundary",
    [
        None,
        [],
        {"type": "Polygon", "coordinates": []},
        {"type": "LineString", "coordinates": [[[0, 0], [1, 0], [0, 0], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [True, 0], [1, 1], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [float("nan"), 0], [1, 1], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [float("inf"), 0], [1, 1], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]},
    ],
)
def test_monitor_creation_rejects_invalid_geojson_boundary(boundary):
    body = valid_monitor_body()
    body["boundary_geojson"] = boundary
    transport = Mock()

    with pytest.raises(ValueError):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


def test_monitor_creation_accepts_positions_with_additional_coordinates():
    body = valid_monitor_body()
    body["boundary_geojson"]["coordinates"] = [
        [[0, 0, 10], [1, 0, 10], [1, 1, 10], [0, 0, 10]]
    ]
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


def test_monitor_detail_get_uses_fake_transport_and_returns_response():
    response = SimpleNamespace(status_code=200)
    transport = Mock(return_value=response)

    result = build_client(transport).get("/v1/monitors/monitor-123")

    assert result is response
    transport.assert_called_once_with(
        "GET",
        f"{BASE_URL}/v1/monitors/monitor-123",
        headers={"api-key": API_KEY},
        timeout=4,
        params=None,
        json=None,
    )


def test_monitor_delete_uses_fake_transport_and_returns_response():
    response = SimpleNamespace(status_code=204)
    transport = Mock(return_value=response)

    result = build_client(transport).request("DELETE", "/v1/monitors/monitor-123")

    assert result is response
    transport.assert_called_once_with(
        "DELETE",
        f"{BASE_URL}/v1/monitors/monitor-123",
        headers={"api-key": API_KEY},
        timeout=4,
        params=None,
        json=None,
    )


@pytest.mark.parametrize(
    "field",
    ["heatmap_id", "name", "boundary_geojson", "rules", "notifications"],
)
def test_monitor_creation_rejects_each_missing_required_field(field):
    body = valid_monitor_body()
    body.pop(field)
    transport = Mock()

    with pytest.raises(ValueError):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


@pytest.mark.parametrize("name", ["", "x" * 121, None, 42])
def test_monitor_creation_rejects_invalid_name(name):
    body = valid_monitor_body()
    body["name"] = name
    transport = Mock()

    with pytest.raises(ValueError, match="name"):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


@pytest.mark.parametrize("name", ["x", "x" * 120])
def test_monitor_creation_accepts_name_length_boundaries(name):
    body = valid_monitor_body()
    body["name"] = name
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


@pytest.mark.parametrize("count", [0, 21])
def test_monitor_creation_rejects_rule_counts_outside_one_to_twenty(count):
    body = valid_monitor_body()
    body["rules"] = [deepcopy(VALID_RULE) for _ in range(count)]
    transport = Mock()

    with pytest.raises(ValueError, match="1 to 20"):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


@pytest.mark.parametrize("count", [1, 20])
def test_monitor_creation_accepts_rule_count_boundaries(count):
    body = valid_monitor_body()
    body["rules"] = [deepcopy(VALID_RULE) for _ in range(count)]
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


@pytest.mark.parametrize("operator", ["above", "below", "Between"])
def test_monitor_rules_accept_documented_operators(operator):
    body = valid_monitor_body()
    body["rules"][0]["operator"] = operator
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


def test_monitor_rules_reject_undocumented_within_interval_operator():
    body = valid_monitor_body()
    body["rules"][0]["operator"] = "within_interval"
    transport = Mock()

    with pytest.raises(ValueError, match="operator"):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spatial_aggregation", "average"),
        ("temporal_aggregation", "sum"),
        ("unit", "kelvin"),
    ],
)
def test_monitor_rules_reject_undocumented_enum_values(field, value):
    body = valid_monitor_body()
    body["rules"][0][field] = value
    transport = Mock()

    with pytest.raises(ValueError):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


def test_monitor_rule_threshold_fields_remain_optional_and_nullable():
    body = valid_monitor_body()
    body["rules"][0].update({"threshold": None, "lower_bound": None, "upper_bound": None})
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


@pytest.mark.parametrize("notifications", [{}, {"email": []}, {"sms": [" "]}, {"whatsapp": [None]}])
def test_monitor_creation_requires_a_non_empty_notification_destination(notifications):
    body = valid_monitor_body()
    body["notifications"] = notifications
    transport = Mock()

    with pytest.raises(ValueError):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


@pytest.mark.parametrize("channel", ["email", "sms", "whatsapp"])
def test_each_documented_notification_channel_accepts_non_empty_strings(channel):
    body = valid_monitor_body()
    body["notifications"] = {channel: ["synthetic-destination"]}
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


@pytest.mark.parametrize("field", ["enabled", "generate_report"])
@pytest.mark.parametrize("value", [True, False])
def test_monitor_boolean_fields_accept_boolean_values(field, value):
    body = valid_monitor_body()
    body[field] = value
    transport = success_transport(201)

    build_client(transport).post("/v1/monitors", json=body)

    assert transport.call_count == 1


@pytest.mark.parametrize("field", ["enabled", "generate_report"])
def test_monitor_boolean_fields_reject_non_boolean_values(field):
    body = valid_monitor_body()
    body[field] = "true"
    transport = Mock()

    with pytest.raises(ValueError, match=field):
        build_client(transport).post("/v1/monitors", json=body)

    transport.assert_not_called()


@pytest.mark.parametrize("field", ["heatmap_id", "boundary_geojson"])
def test_monitor_patch_rejects_immutable_fields(field):
    transport = Mock()

    with pytest.raises(ValueError, match="cannot be changed"):
        build_client(transport).request("PATCH", "/v1/monitors/monitor-123", json={field: "change"})

    transport.assert_not_called()


def test_monitor_patch_accepts_mutable_fields_and_preserves_unknown_fields():
    body = {
        "name": "Renamed",
        "enabled": False,
        "generate_report": True,
        "rules": [deepcopy(VALID_RULE)],
        "notifications": {"sms": ["synthetic-destination"]},
        "unknown_field": {"value": 1},
    }
    transport = success_transport()

    build_client(transport).request("PATCH", "/v1/monitors/monitor-123", json=body)

    assert transport.call_args.kwargs["json"] == body


@pytest.mark.parametrize("limit", [0, -1, 101, 1.5, True, None])
def test_monitor_list_rejects_invalid_limits(limit):
    transport = Mock()

    with pytest.raises(ValueError, match="limit"):
        build_client(transport).get("/v1/monitors", params={"limit": limit})

    transport.assert_not_called()


@pytest.mark.parametrize("limit", [1, 100])
def test_monitor_list_accepts_limit_boundaries(limit):
    transport = success_transport()

    build_client(transport).get("/v1/monitors", params={"limit": limit})

    assert transport.call_count == 1


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": 3},
        {"enabled": "true"},
        {"heatmap_id": 7},
    ],
)
def test_monitor_list_rejects_invalid_documented_parameter_types(params):
    transport = Mock()

    with pytest.raises(ValueError):
        build_client(transport).get("/v1/monitors", params=params)

    transport.assert_not_called()


def test_monitor_list_preserves_unknown_parameters_without_status_validation():
    params = {"future_filter": "kept", "status": ["unknown-shape"]}
    transport = success_transport()

    build_client(transport).get("/v1/monitors", params=params)

    assert transport.call_args.kwargs["params"] == params


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/monitors/"),
        ("GET", "/v1/monitors/monitor-123/"),
        ("GET", "/v1/monitors//monitor-123"),
        ("GET", "/v1/monitors/monitor-123/extra"),
        ("GET", "/v1/monitors/monitor%2F123"),
        ("PATCH", "/v1/monitors/monitor-123/"),
        ("DELETE", "/v1/monitors//"),
    ],
)
def test_malformed_monitor_paths_fail_before_transport(method, path):
    transport = Mock()

    with pytest.raises(ValueError):
        build_client(transport).request(method, path, json={})

    transport.assert_not_called()


@pytest.mark.parametrize("path", ["/v1/status", "/v1/status/", "/v1/status/id/", "/v1/status/id/extra", "/v1/status/id%2Fpart"])
def test_malformed_status_paths_fail_before_transport(path):
    transport = Mock()

    with pytest.raises(ValueError, match="activity_id"):
        build_client(transport).get(path)

    transport.assert_not_called()


def test_valid_status_path_reaches_fake_transport():
    transport = success_transport()

    build_client(transport).get("/v1/status/activity-123")

    assert transport.call_count == 1
