from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api_client import FortyGuardClient


BASE_URL = "https://example.invalid"
API_KEY = "synthetic-api-key"
DATE_TIME = {"filter_type": 1, "start_date": "2020-01-02", "start_time": "09:00"}
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
}


def valid_payloads():
    return {
        "/v1/heatmap": {
            "date_time": deepcopy(DATE_TIME),
            "polygon_aoi": deepcopy(POLYGON),
            "granularity": 20,
        },
        "/v1/satellite": {"date_time": deepcopy(DATE_TIME)},
        "/v1/streetview": {
            "back_view": False,
            "horizontal_angle": 360,
            "latitude": 40,
            "longitude": -70,
            "vertical_angle": -999,
        },
        "/v1/heat_intelligence": {
            "analysis": ["environmental"],
            "date": "2020-01-02",
            "latitude": 40,
            "longitude": -70,
            "temperature": 86,
        },
        "/v1/env_params": {
            "date_time": deepcopy(DATE_TIME),
            "latitude": 40,
            "longitude": -70,
            "temperature": 30,
        },
        "/v1/routing": {
            "departure_time": "2026-08-23T13:00:00Z",
            "origin": {"lat": 40, "lon": -70},
            "destination": {"lat": 40, "lon": -69},
        },
    }


def make_client(transport):
    return FortyGuardClient(BASE_URL, API_KEY, transport, timeout=5)


@pytest.mark.parametrize("path", list(valid_payloads()))
def test_valid_endpoint_payloads_reach_only_the_fake_transport(path):
    payload = valid_payloads()[path]
    transport = Mock(return_value=SimpleNamespace(status_code=200))
    client = make_client(transport)

    client.post(path, json=payload)

    transport.assert_called_once_with(
        "POST",
        f"{BASE_URL}{path}",
        headers={"api-key": API_KEY},
        timeout=5,
        params=None,
        json=payload,
    )


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/v1/heatmap", {"date_time": deepcopy(DATE_TIME)}),
        ("/v1/heatmap", {"polygon_aoi": deepcopy(POLYGON)}),
        ("/v1/satellite", {}),
        ("/v1/streetview", {"latitude": 1}),
        ("/v1/heat_intelligence", {"analysis": ["environmental"]}),
        ("/v1/env_params", {"date_time": deepcopy(DATE_TIME)}),
        ("/v1/routing", {"origin": {"lat": 1, "lon": 1}}),
    ],
)
def test_missing_required_endpoint_fields_are_rejected_before_transport(path, payload):
    transport = Mock()
    client = make_client(transport)

    with pytest.raises(ValueError):
        client.post(path, json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize("path", ["/v1/heatmap", "/v1/satellite", "/v1/env_params"])
@pytest.mark.parametrize(
    ("filter_type", "overrides"),
    [
        (1, {}),
        (2, {"start_time": "09:00"}),
        (4, {"start_time": "09:00", "end_time": "10:00"}),
    ],
)
def test_filter_specific_time_and_date_requirements(path, filter_type, overrides):
    payload = valid_payloads()[path]
    payload["date_time"] = {"filter_type": filter_type, "start_date": "2020-01-02", **overrides}
    if path == "/v1/heatmap":
        payload["polygon_aoi"] = deepcopy(POLYGON)
    if path == "/v1/env_params":
        payload.update({"latitude": 40, "longitude": -70, "temperature": 30})
    transport = Mock()
    client = make_client(transport)

    with pytest.raises(ValueError):
        client.post(path, json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize("filter_type", [1, 2, 3])
def test_filter_specific_valid_date_time_shapes(filter_type):
    date_time = {"filter_type": filter_type, "start_date": "2020-01-02"}
    if filter_type == 1:
        date_time["start_time"] = "09:00"
    elif filter_type == 2:
        date_time.update({"start_time": "09:00", "end_time": "10:00"})
    elif filter_type == 4:
        date_time["end_date"] = "2020-01-03"
    payload = valid_payloads()["/v1/env_params"]
    payload["date_time"] = date_time
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/env_params", json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize("path", ["/v1/heatmap", "/v1/satellite", "/v1/env_params"])
def test_filter_type_four_is_supported_only_for_heatmap(path):
    payload = valid_payloads()[path]
    payload["date_time"] = {
        "filter_type": 4,
        "start_date": "2020-01-02",
        "end_date": "2020-01-03",
    }
    if path == "/v1/heatmap":
        payload["polygon_aoi"] = deepcopy(POLYGON)
    if path == "/v1/env_params":
        payload.update({"latitude": 40, "longitude": -70, "temperature": 30})
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    if path == "/v1/heatmap":
        make_client(transport).post(path, json=payload)
        assert transport.call_count == 1
    else:
        with pytest.raises(ValueError, match="filter_type"):
            make_client(transport).post(path, json=payload)
        transport.assert_not_called()


@pytest.mark.parametrize("path", ["/v1/heatmap", "/v1/satellite", "/v1/env_params"])
def test_future_dates_are_not_rejected_without_a_documented_restriction(path):
    payload = valid_payloads()[path]
    payload["date_time"] = {
        "filter_type": 1,
        "start_date": "2099-01-02",
        "start_time": "09:00",
    }
    if path == "/v1/heatmap":
        payload["polygon_aoi"] = deepcopy(POLYGON)
    if path == "/v1/env_params":
        payload.update({"latitude": 40, "longitude": -70, "temperature": 30})
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post(path, json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize("path", ["/v1/satellite", "/v1/env_params"])
def test_filter_type_three_is_supported_for_satellite_and_environment(path):
    payload = valid_payloads()[path]
    payload["date_time"] = {"filter_type": 3, "start_date": "2020-01-02"}
    if path == "/v1/env_params":
        payload.update({"latitude": 40, "longitude": -70, "temperature": 30})
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post(path, json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize("granularity", [20, 60, 80, 100])
def test_heatmap_accepts_documented_granularity_values(granularity):
    payload = valid_payloads()["/v1/heatmap"]
    payload["granularity"] = granularity
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/heatmap", json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize("granularity", [20, 60, 80, 100])
def test_satellite_accepts_documented_granularity_values(granularity):
    payload = valid_payloads()["/v1/satellite"]
    payload["granularity"] = granularity
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/satellite", json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize("granularity", [0, 40, 120, 60.5, True])
def test_heatmap_rejects_undocumented_granularity_before_transport(granularity):
    payload = valid_payloads()["/v1/heatmap"]
    payload["granularity"] = granularity
    transport = Mock()

    with pytest.raises(ValueError, match="granularity"):
        make_client(transport).post("/v1/heatmap", json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize(
    "polygon",
    [
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1]]]},
        {"type": "Polygon", "coordinates": [[[0, "west"], [1, 0], [1, 1], [0, "west"]]]},
    ],
)
def test_heatmap_rejects_invalid_geojson_polygon_before_transport(polygon):
    payload = valid_payloads()["/v1/heatmap"]
    payload["polygon_aoi"] = polygon
    transport = Mock()

    with pytest.raises(ValueError):
        make_client(transport).post("/v1/heatmap", json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize(
    "polygon",
    [
        {"type": "Feature", "geometry": deepcopy(POLYGON), "properties": {}},
        {"type": "FeatureCollection", "features": []},
    ],
)
def test_heatmap_rejects_undocumented_geojson_geometry_types(polygon):
    payload = valid_payloads()["/v1/heatmap"]
    payload["polygon_aoi"] = polygon
    transport = Mock()

    with pytest.raises(ValueError, match="must be a Polygon"):
        make_client(transport).post("/v1/heatmap", json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize(
    ("path", "field", "value"),
    [
        ("/v1/heatmap", "analytic_type", "unknown"),
        ("/v1/heatmap", "direction", "sideways"),
        ("/v1/heatmap", "notify_by_email", "yes"),
        ("/v1/heatmap", "threshold", "30"),
        ("/v1/satellite", "big_area", 1),
        ("/v1/satellite", "granularity", 40),
        ("/v1/streetview", "back_view", 0),
        ("/v1/streetview", "vertical_angle", "100"),
        ("/v1/heat_intelligence", "analysis", ["unknown"]),
        ("/v1/heat_intelligence", "temperature", "86F"),
        ("/v1/env_params", "analysis", ["unknown"]),
        ("/v1/env_params", "temperature", "30C"),
    ],
)
def test_documented_field_types_and_values_are_validated_before_transport(path, field, value):
    payload = valid_payloads()[path]
    payload[field] = value
    transport = Mock()

    with pytest.raises(ValueError):
        make_client(transport).post(path, json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize("angle", [0, 360])
def test_streetview_accepts_horizontal_angle_boundaries(angle):
    payload = valid_payloads()["/v1/streetview"]
    payload["horizontal_angle"] = angle
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/streetview", json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize("angle", [-0.1, 360.1, "90"])
def test_streetview_rejects_invalid_horizontal_angle_before_transport(angle):
    payload = valid_payloads()["/v1/streetview"]
    payload["horizontal_angle"] = angle
    transport = Mock()

    with pytest.raises(ValueError, match="horizontal_angle"):
        make_client(transport).post("/v1/streetview", json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [("temperature", 86), ("date", "2020-01-02")],
)
def test_heat_intelligence_keeps_fahrenheit_payload_unchanged(field, value):
    payload = valid_payloads()["/v1/heat_intelligence"]
    payload[field] = value
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/heat_intelligence", json=payload)

    assert transport.call_args.kwargs["json"][field] == value


def test_env_params_keeps_celsius_payload_unchanged():
    payload = valid_payloads()["/v1/env_params"]
    payload["temperature"] = 30
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/env_params", json=payload)

    assert transport.call_args.kwargs["json"]["temperature"] == 30


@pytest.mark.parametrize(
    "analysis_name",
    [
        "heat_index_celsius",
        "apparent_temperature_celsius",
        "wet_bulb_temperature_celsius",
        "relative_humidity_percent",
        "precipitation_mm",
        "cloud_cover_octas",
        "elevation",
        "air_quality:idx",
        "air_quality_pm2p5:idx",
        "air_quality_pm10:idx",
        "air_quality_no2:idx",
        "aqi_us_co",
        "air_quality_o3:idx",
        "air_quality_so2:idx",
        "methane_ppb",
        "co2_ppm",
        "solar_irradiance",
    ],
)
def test_environment_analysis_accepts_exact_documented_names(analysis_name):
    payload = valid_payloads()["/v1/env_params"]
    payload["analysis"] = [analysis_name]
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/env_params", json=payload)

    assert transport.call_count == 1


@pytest.mark.parametrize(
    "analysis_name",
    ["elevation_meters", "aqi_us", "aqi_us_pm25", "aqi_us_pm10", "aqi_us_no2"],
)
def test_environment_analysis_rejects_non_documented_aliases(analysis_name):
    payload = valid_payloads()["/v1/env_params"]
    payload["analysis"] = [analysis_name]
    transport = Mock()

    with pytest.raises(ValueError, match="analysis"):
        make_client(transport).post("/v1/env_params", json=payload)

    transport.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("origin", {"lat": 91, "lon": 0}),
        ("origin", {"lat": 0, "lon": 181}),
        ("destination", {"lat": -91, "lon": 0}),
        ("destination", {"lat": 0, "lon": -181}),
    ],
)
def test_routing_rejects_out_of_range_coordinates_before_transport(field, value):
    payload = valid_payloads()["/v1/routing"]
    payload[field] = value
    transport = Mock()

    with pytest.raises(ValueError):
        make_client(transport).post("/v1/routing", json=payload)

    transport.assert_not_called()


def test_routing_rejects_identical_endpoints_before_transport():
    payload = valid_payloads()["/v1/routing"]
    payload["destination"] = dict(payload["origin"])
    transport = Mock()

    with pytest.raises(ValueError, match="must differ"):
        make_client(transport).post("/v1/routing", json=payload)

    transport.assert_not_called()


def test_routing_rejects_distance_over_200_km_before_transport():
    payload = valid_payloads()["/v1/routing"]
    payload["destination"] = {"lat": 40, "lon": -67}
    transport = Mock()

    with pytest.raises(ValueError, match="200 km"):
        make_client(transport).post("/v1/routing", json=payload)

    transport.assert_not_called()


def test_routing_accepts_distance_under_200_km():
    payload = valid_payloads()["/v1/routing"]
    payload["destination"] = {"lat": 40, "lon": -68}
    transport = Mock(return_value=SimpleNamespace(status_code=200))

    make_client(transport).post("/v1/routing", json=payload)

    assert transport.call_count == 1
