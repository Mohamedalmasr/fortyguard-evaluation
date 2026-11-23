from collections.abc import Callable
from datetime import date, datetime
from math import asin, cos, isfinite, radians, sin, sqrt
import re
from urllib.parse import unquote, urlsplit


class FortyGuardHTTPError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        messages = {
            401: "FortyGuard rejected the API key (HTTP 401).",
            403: "FortyGuard denied access (HTTP 403).",
            429: "FortyGuard returned a rate-limit response (HTTP 429).",
            500: "FortyGuard returned a server error (HTTP 500).",
        }
        super().__init__(messages.get(status_code, f"FortyGuard returned HTTP {status_code}."))


class FortyGuardTransportError(RuntimeError):
    pass


_ENV_ANALYSIS = {
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
}
_HEAT_INTELLIGENCE_ANALYSIS = {
    "geographic",
    "environmental",
    "urban",
    "events",
    "anthropogenic",
}


def _require_object(value, message):
    if not isinstance(value, dict):
        raise ValueError(message)


def _require_fields(value, fields, message):
    if any(field not in value for field in fields):
        raise ValueError(message)


def _require_string(value, message):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)


def _require_number(value, message):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(message)
    if not isfinite(value):
        raise ValueError(message)


def _require_boolean(value, message):
    if not isinstance(value, bool):
        raise ValueError(message)


def _validate_date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field} must use YYYY-MM-DD format.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from None
    return parsed


def _validate_time(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError(f"{field} must use HH:MM format.")
    hour, minute = (int(part) for part in value.split(":"))
    if hour > 23 or minute > 59:
        raise ValueError(f"{field} must use HH:MM format.")


def _validate_date_time(value, field, *, nullable=False, max_filter_type=4):
    if value is None and nullable:
        return
    _require_object(value, f"{field} must be an object.")
    _require_fields(value, ("filter_type", "start_date"), f"{field} is missing required fields.")
    filter_type = value["filter_type"]
    if (
        isinstance(filter_type, bool)
        or not isinstance(filter_type, int)
        or filter_type not in range(1, max_filter_type + 1)
    ):
        raise ValueError(f"{field}.filter_type must be between 1 and {max_filter_type}.")
    _validate_date(value["start_date"], f"{field}.start_date")
    if "end_date" in value and value["end_date"] is not None:
        _validate_date(value["end_date"], f"{field}.end_date")
    for time_field in ("start_time", "end_time"):
        if time_field in value and value[time_field] is not None:
            _validate_time(value[time_field], f"{field}.{time_field}")
    if filter_type == 1 and not value.get("start_time"):
        raise ValueError(f"{field}.start_time is required for filter_type 1.")
    if filter_type == 2 and (not value.get("start_time") or not value.get("end_time")):
        raise ValueError(f"{field}.start_time and end_time are required for filter_type 2.")
    if filter_type == 4 and not value.get("end_date"):
        raise ValueError(f"{field}.end_date is required for filter_type 4.")


def _validate_coordinate(value, minimum, maximum, message):
    _require_number(value, message)
    if not minimum <= value <= maximum:
        raise ValueError(message)


def _validate_latitude_longitude(payload, *, names=("latitude", "longitude"), bounded=True):
    latitude_name, longitude_name = names
    _require_fields(payload, names, "Latitude and longitude are required.")
    if bounded:
        _validate_coordinate(payload[latitude_name], -90, 90, "Latitude must be between -90 and 90.")
        _validate_coordinate(payload[longitude_name], -180, 180, "Longitude must be between -180 and 180.")
    else:
        _require_number(payload[latitude_name], "Latitude must be numeric.")
        _require_number(payload[longitude_name], "Longitude must be numeric.")


def _validate_polygon(value):
    _require_object(value, "polygon_aoi must be a GeoJSON object.")
    geometry_type = value.get("type")
    if geometry_type == "Polygon":
        coordinates = value.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("polygon_aoi must contain a closed Polygon.")
        for ring in coordinates:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("polygon_aoi polygon rings must be closed.")
            for position in ring:
                if not isinstance(position, (list, tuple)) or len(position) < 2:
                    raise ValueError("polygon_aoi positions must contain longitude and latitude.")
                _require_number(position[0], "polygon_aoi longitude must be numeric.")
                _require_number(position[1], "polygon_aoi latitude must be numeric.")
    else:
        raise ValueError("polygon_aoi must be a Polygon.")


def _validate_optional_type(payload, field, validator, *, nullable=False):
    if field not in payload:
        return
    value = payload[field]
    if value is None and nullable:
        return
    validator(value)


def _validate_analysis(value, allowed, message, *, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(message)
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise ValueError(message)


def _validate_heatmap(payload):
    _require_object(payload, "Request body must be an object.")
    _require_fields(payload, ("date_time", "polygon_aoi"), "Heatmap request is missing required fields.")
    _validate_date_time(payload["date_time"], "date_time", max_filter_type=4)
    _validate_polygon(payload["polygon_aoi"])
    if "analytic_type" in payload and (
        not isinstance(payload["analytic_type"], str)
        or payload["analytic_type"] not in {"tcm", "time_of_measure", "exceedance", "persistence"}
    ):
        raise ValueError("analytic_type is invalid.")
    if "direction" in payload and payload["direction"] is not None and (
        not isinstance(payload["direction"], str) or payload["direction"] not in {"above", "below"}
    ):
        raise ValueError("direction is invalid.")
    if "granularity" in payload:
        granularity = payload["granularity"]
        if isinstance(granularity, bool) or not isinstance(granularity, int) or granularity not in {20, 60, 80, 100}:
            raise ValueError("granularity must be 20, 60, 80, or 100.")
    _validate_optional_type(payload, "threshold", lambda value: _require_number(value, "threshold must be numeric."), nullable=True)
    _validate_optional_type(payload, "notify_by_email", lambda value: _require_boolean(value, "notify_by_email must be boolean."))
    _validate_optional_type(payload, "heatmap_id", lambda value: _require_string(value, "heatmap_id must be a string."), nullable=True)
    _validate_optional_type(payload, "idempotency_key", lambda value: _require_string(value, "idempotency_key must be a string."), nullable=True)
    _validate_optional_type(payload, "map_type", lambda value: _require_string(value, "map_type must be a string."))
    if "map_type" in payload and payload["map_type"] not in {"bm", "tcm", "tccm"}:
        raise ValueError("map_type is invalid.")


def _validate_satellite(payload):
    _require_object(payload, "Request body must be an object.")
    _require_fields(payload, ("date_time",), "Satellite request is missing required fields.")
    _validate_date_time(payload["date_time"], "date_time", max_filter_type=3)
    _validate_optional_type(payload, "big_area", lambda value: _require_boolean(value, "big_area must be boolean."))
    if "granularity" in payload:
        granularity = payload["granularity"]
        if isinstance(granularity, bool) or not isinstance(granularity, int) or granularity not in {20, 60, 80, 100}:
            raise ValueError("satellite granularity must be 20, 60, 80, or 100.")
    _validate_optional_type(payload, "heatmap_id", lambda value: _require_string(value, "heatmap_id must be a string."), nullable=True)
    if "sat" in payload and payload["sat"] is not None:
        _require_object(payload["sat"], "sat must be an object or null.")
        _validate_latitude_longitude(payload["sat"])


def _validate_streetview(payload):
    _require_object(payload, "Request body must be an object.")
    _require_fields(payload, ("back_view", "horizontal_angle", "latitude", "longitude", "vertical_angle"), "Streetview request is missing required fields.")
    _require_boolean(payload["back_view"], "back_view must be boolean.")
    _require_number(payload["horizontal_angle"], "horizontal_angle must be numeric.")
    if not 0 <= payload["horizontal_angle"] <= 360:
        raise ValueError("horizontal_angle must be between 0 and 360.")
    _require_number(payload["vertical_angle"], "vertical_angle must be numeric.")
    _validate_latitude_longitude(payload)
    if "date_time" in payload:
        _validate_date_time(payload["date_time"], "date_time", nullable=True)
    _validate_optional_type(payload, "heatmap_id", lambda value: _require_string(value, "heatmap_id must be a string."), nullable=True)


def _validate_heat_intelligence(payload):
    _require_object(payload, "Request body must be an object.")
    _require_fields(payload, ("analysis", "date", "latitude", "longitude", "temperature"), "Heat intelligence request is missing required fields.")
    _validate_analysis(
        payload["analysis"], _HEAT_INTELLIGENCE_ANALYSIS,
        "analysis must contain 1 to 5 supported analysis types.", minimum=1, maximum=5
    )
    _validate_date(payload["date"], "date")
    _validate_latitude_longitude(payload, bounded=False)
    _require_number(payload["temperature"], "temperature must be numeric in Fahrenheit.")
    if "date_time" in payload:
        _validate_date_time(payload["date_time"], "date_time", nullable=True)
    _validate_optional_type(payload, "granularity", lambda value: _require_number(value, "granularity must be numeric."))
    _validate_optional_type(payload, "heatmap_id", lambda value: _require_string(value, "heatmap_id must be a string."), nullable=True)
    _validate_optional_type(payload, "notify_by_email", lambda value: _require_boolean(value, "notify_by_email must be boolean."))
    for field in ("polygon", "report_polygon"):
        if field in payload and payload[field] is not None and not isinstance(payload[field], (dict, str)):
            raise ValueError(f"{field} must be an object, string, or null.")
    _validate_optional_type(
        payload, "selected_heat_intelligence_tile_id",
        lambda value: _require_string(value, "selected_heat_intelligence_tile_id must be a string.")
    )


def _validate_env_params(payload):
    _require_object(payload, "Request body must be an object.")
    _require_fields(payload, ("date_time", "latitude", "longitude", "temperature"), "Environment request is missing required fields.")
    _validate_date_time(payload["date_time"], "date_time", max_filter_type=3)
    _validate_latitude_longitude(payload, bounded=False)
    _require_number(payload["temperature"], "temperature must be numeric in Celsius.")
    if "analysis" in payload and payload["analysis"] is not None:
        _validate_analysis(payload["analysis"], _ENV_ANALYSIS, "analysis contains an unsupported field.", minimum=0, maximum=len(_ENV_ANALYSIS))


def _validate_routing(payload):
    _require_object(payload, "Request body must be an object.")
    _require_fields(payload, ("departure_time", "origin", "destination"), "Routing request is missing required fields.")
    departure_time = payload["departure_time"]
    if not isinstance(departure_time, str) or "T" not in departure_time:
        raise ValueError("departure_time must be an ISO-8601 date-time string.")
    try:
        datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("departure_time must be an ISO-8601 date-time string.") from None
    for field in ("origin", "destination"):
        point = payload[field]
        _require_object(point, f"{field} must be an object.")
        _validate_latitude_longitude(point, names=("lat", "lon"))
    origin = payload["origin"]
    destination = payload["destination"]
    if origin["lat"] == destination["lat"] and origin["lon"] == destination["lon"]:
        raise ValueError("origin and destination must differ.")
    latitude_delta = radians(destination["lat"] - origin["lat"])
    longitude_delta = radians(destination["lon"] - origin["lon"])
    origin_latitude = radians(origin["lat"])
    destination_latitude = radians(destination["lat"])
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(origin_latitude) * cos(destination_latitude) * sin(longitude_delta / 2) ** 2
    )
    distance_km = 6371.0 * 2 * asin(sqrt(min(1.0, haversine)))
    if distance_km > 200:
        raise ValueError("Routing distance must not exceed 200 km.")


def _validate_notifications(value, *, require_destination):
    _require_object(value, "notifications must be an object.")
    destinations = 0
    for channel in ("email", "sms", "whatsapp"):
        if channel not in value:
            continue
        recipients = value[channel]
        if not isinstance(recipients, list):
            raise ValueError(f"notifications.{channel} must be an array.")
        for recipient in recipients:
            if not isinstance(recipient, str) or not recipient.strip():
                raise ValueError(f"notifications.{channel} entries must be non-empty strings.")
        destinations += len(recipients)
    if require_destination and destinations == 0:
        raise ValueError("At least one notification destination is required.")


def _validate_monitor_rules(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise ValueError("rules must contain 1 to 20 rules.")
    for rule in value:
        _require_object(rule, "Each rule must be an object.")
        _require_fields(
            rule,
            ("operator", "spatial_aggregation", "temporal_aggregation", "unit"),
            "A rule is missing required fields.",
        )
        if not isinstance(rule["operator"], str) or rule["operator"] not in {"above", "below", "Between"}:
            raise ValueError("Rule operator is invalid.")
        if not isinstance(rule["spatial_aggregation"], str) or rule["spatial_aggregation"] not in {"minimum", "maximum"}:
            raise ValueError("Rule spatial_aggregation is invalid.")
        if not isinstance(rule["temporal_aggregation"], str) or rule["temporal_aggregation"] not in {"minimum", "average", "maximum"}:
            raise ValueError("Rule temporal_aggregation is invalid.")
        if not isinstance(rule["unit"], str) or rule["unit"] not in {"celsius", "fahrenheit"}:
            raise ValueError("Rule unit is invalid.")
        for bound in ("threshold", "lower_bound", "upper_bound"):
            if bound in rule and rule[bound] is not None:
                _require_number(rule[bound], f"Rule {bound} must be numeric.")


def _validate_monitor_boundary(value):
    _require_object(value, "boundary_geojson must be an object.")
    if value.get("type") != "Polygon":
        raise ValueError("boundary_geojson must be a Polygon.")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("boundary_geojson must contain at least one linear ring.")
    for ring in coordinates:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("boundary_geojson linear rings must contain at least four positions.")
        for position in ring:
            if not isinstance(position, (list, tuple)) or len(position) < 2:
                raise ValueError("boundary_geojson positions must contain at least two coordinates.")
            for coordinate in position:
                _require_number(coordinate, "boundary_geojson coordinates must be finite numbers.")
        if list(ring[0]) != list(ring[-1]):
            raise ValueError("boundary_geojson linear rings must be closed.")


def _validate_monitor_body(payload, *, create):
    _require_object(payload, "Monitor request body must be an object.")
    if create:
        _require_fields(
            payload,
            ("heatmap_id", "name", "boundary_geojson", "rules", "notifications"),
            "Monitor creation is missing required fields.",
        )
        _require_string(payload["heatmap_id"], "heatmap_id must be a non-empty string.")
        if not isinstance(payload["name"], str) or not 1 <= len(payload["name"]) <= 120:
            raise ValueError("name must be a string with length 1 to 120.")
        _validate_monitor_boundary(payload["boundary_geojson"])
    if "notifications" in payload:
        _validate_notifications(payload["notifications"], require_destination=create)
    if "rules" in payload:
        _validate_monitor_rules(payload["rules"])
    if not create and ("heatmap_id" in payload or "boundary_geojson" in payload):
        raise ValueError("heatmap_id and boundary_geojson cannot be changed by PATCH.")
    if "boundary_geojson" in payload and payload["boundary_geojson"] is not None:
        _require_object(payload["boundary_geojson"], "boundary_geojson must be an object.")
    if "enabled" in payload:
        _require_boolean(payload["enabled"], "enabled must be boolean.")
    if "generate_report" in payload:
        _require_boolean(payload["generate_report"], "generate_report must be boolean.")
    if "name" in payload and not create and (
        not isinstance(payload["name"], str) or not 1 <= len(payload["name"]) <= 120
    ):
        raise ValueError("name must be a string with length 1 to 120.")
    if "heatmap_id" in payload and payload["heatmap_id"] is not None and not isinstance(payload["heatmap_id"], str):
        raise ValueError("heatmap_id must be a string or null.")


def _validate_monitor_list_params(params):
    if params is None:
        return
    _require_object(params, "Monitor list parameters must be an object.")
    if "cursor" in params and not isinstance(params["cursor"], str):
        raise ValueError("cursor must be a string.")
    if "limit" in params:
        limit = params["limit"]
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100.")
    if "enabled" in params:
        _require_boolean(params["enabled"], "enabled must be boolean.")
    if "heatmap_id" in params and not isinstance(params["heatmap_id"], str):
        raise ValueError("heatmap_id must be a string.")


def _validate_monitor_path(route_path):
    segments = route_path.split("/")
    monitor_id = unquote(segments[3]) if len(segments) == 4 else ""
    if (
        len(segments) != 4
        or segments[:3] != ["", "v1", "monitors"]
        or not monitor_id
        or "/" in monitor_id
        or "\\" in monitor_id
    ):
        raise ValueError("A monitor_id path segment is required.")


def _validate_status_path(route_path):
    segments = route_path.split("/")
    activity_id = unquote(segments[3]) if len(segments) == 4 else ""
    if (
        len(segments) != 4
        or segments[:3] != ["", "v1", "status"]
        or not activity_id
        or "/" in activity_id
        or "\\" in activity_id
    ):
        raise ValueError("An activity_id path segment is required.")


_POST_VALIDATORS = {
    "/v1/heatmap": _validate_heatmap,
    "/v1/satellite": _validate_satellite,
    "/v1/streetview": _validate_streetview,
    "/v1/heat_intelligence": _validate_heat_intelligence,
    "/v1/env_params": _validate_env_params,
    "/v1/routing": _validate_routing,
}


class FortyGuardClient:
    def __init__(self, base_url, api_key, transport: Callable, timeout):
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("A base URL is required.")
        try:
            parsed_url = urlsplit(base_url)
            valid_url = (
                parsed_url.scheme.lower() in {"http", "https"}
                and bool(parsed_url.hostname)
                and not any(character.isspace() for character in parsed_url.hostname)
                and not parsed_url.query
                and not parsed_url.fragment
                and "?" not in base_url
                and "#" not in base_url
            )
            parsed_url.port
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValueError("Base URL must use HTTP or HTTPS and include a valid hostname.")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("An API key is required.")
        if not callable(transport):
            raise TypeError("An HTTP transport callable is required.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("Timeout must be a positive number.")
        try:
            valid_timeout = isfinite(timeout) and timeout > 0
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ValueError("Timeout must be a positive finite number.")

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout

    def get(self, path, *, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, *, json=None):
        return self.request("POST", path, json=json)

    def request(self, method, path, *, params=None, json=None):
        if not isinstance(path, str) or not path.strip():
            raise ValueError("A request path is required.")
        parsed_path = urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc:
            raise ValueError("Request path must be relative.")
        if not isinstance(method, str):
            raise ValueError("HTTP method must be a string.")
        normalized_method = method.upper()
        if normalized_method not in {"GET", "POST"}:
            if normalized_method not in {"PATCH", "DELETE"}:
                raise ValueError("Only GET, POST, PATCH, and DELETE methods are supported.")
        raw_route_path = urlsplit(path).path
        route_path = raw_route_path.rstrip("/")
        validator = _POST_VALIDATORS.get(route_path)
        if normalized_method == "POST" and validator is not None:
            validator(json)
        if normalized_method == "GET" and (
            raw_route_path == "/v1/status"
            or raw_route_path == "/v1/status/"
            or raw_route_path.startswith("/v1/status/")
        ):
            _validate_status_path(raw_route_path)
        if raw_route_path == "/v1/monitors":
            if normalized_method == "POST":
                _validate_monitor_body(json, create=True)
            elif normalized_method == "GET":
                _validate_monitor_list_params(params)
            elif normalized_method in {"PATCH", "DELETE"}:
                raise ValueError("A monitor_id path segment is required.")
        elif raw_route_path == "/v1/monitors/" or raw_route_path.startswith("/v1/monitors/"):
            if normalized_method not in {"GET", "PATCH", "DELETE"}:
                raise ValueError("Unsupported monitor endpoint path.")
            _validate_monitor_path(raw_route_path)
            if normalized_method == "PATCH" and json is not None:
                _validate_monitor_body(json, create=False)

        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            response = self._transport(
                normalized_method,
                url,
                headers={"api-key": self._api_key},
                timeout=self._timeout,
                params=params,
                json=json,
            )
        except Exception:
            raise FortyGuardTransportError("FortyGuard request failed at the transport layer.") from None

        try:
            status_code = response.status_code
        except Exception:
            raise FortyGuardTransportError("FortyGuard returned a malformed response.") from None
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            raise FortyGuardTransportError("FortyGuard returned a malformed response.")
        if not 200 <= status_code < 300:
            raise FortyGuardHTTPError(status_code)
        return response
