from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api_client import (
    FortyGuardClient,
    FortyGuardHTTPError,
    FortyGuardTransportError,
)


API_KEY = "synthetic-api-key"
BASE_URL = "https://example.invalid"


def build_client(transport, timeout=3.5):
    return FortyGuardClient(BASE_URL, API_KEY, transport, timeout)


@pytest.mark.parametrize("status_code", [401, 403, 429, 500])
def test_documented_http_error_statuses_are_sanitized(status_code):
    response = SimpleNamespace(status_code=status_code, headers={"Retry-After": "1"})
    transport = Mock(return_value=response)
    client = build_client(transport)

    with pytest.raises(FortyGuardHTTPError) as error:
        client.get("/v1/status/test")

    assert error.value.status_code == status_code
    assert API_KEY not in str(error.value)
    assert "authorization" not in str(error.value).lower()
    transport.assert_called_once_with(
        "GET",
        f"{BASE_URL}/v1/status/test",
        headers={"api-key": API_KEY},
        timeout=3.5,
        params=None,
        json=None,
    )


def test_successful_response_is_returned_with_configured_timeout():
    response = SimpleNamespace(status_code=200)
    transport = Mock(return_value=response)
    client = build_client(transport, timeout=8)

    result = client.get("v1/status/test", params={"check": "local"})

    assert result is response
    transport.assert_called_once_with(
        "GET",
        f"{BASE_URL}/v1/status/test",
        headers={"api-key": API_KEY},
        timeout=8,
        params={"check": "local"},
        json=None,
    )


@pytest.mark.parametrize("status_code", [429, 500])
def test_post_is_not_retried_after_error_status(status_code):
    transport = Mock(return_value=SimpleNamespace(status_code=status_code))
    client = build_client(transport)

    with pytest.raises(FortyGuardHTTPError):
        client.post("/v1/activities", json={"kind": "synthetic"})

    assert transport.call_count == 1
    assert transport.call_args.kwargs["headers"] == {"api-key": API_KEY}


def test_post_is_not_retried_after_transport_timeout():
    transport = Mock(side_effect=TimeoutError(f"failed using {API_KEY}"))
    client = build_client(transport)

    with pytest.raises(FortyGuardTransportError) as error:
        client.post("/v1/activities", json={"kind": "synthetic"})

    assert transport.call_count == 1
    assert API_KEY not in str(error.value)


def test_transport_error_message_does_not_expose_api_key_or_authorization_headers():
    transport = Mock(side_effect=RuntimeError(f"{API_KEY} authorization: {API_KEY}"))
    client = build_client(transport)

    with pytest.raises(FortyGuardTransportError) as error:
        client.get("/v1/status/test")

    assert API_KEY not in str(error.value)
    assert "authorization" not in str(error.value).lower()
    assert transport.call_count == 1


@pytest.mark.parametrize("api_key", ["", " \t "])
def test_missing_or_blank_api_key_fails_before_transport(api_key):
    transport = Mock()

    with pytest.raises(ValueError, match="An API key is required"):
        FortyGuardClient(BASE_URL, api_key, transport, timeout=3)

    transport.assert_not_called()


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_timeout_fails_before_transport(timeout):
    transport = Mock()

    with pytest.raises(ValueError, match="positive finite number"):
        FortyGuardClient(BASE_URL, API_KEY, transport, timeout=timeout)

    transport.assert_not_called()


@pytest.mark.parametrize("method", [None, 1, object()])
def test_non_string_http_method_fails_before_transport(method):
    transport = Mock()
    client = build_client(transport)

    with pytest.raises(ValueError, match="HTTP method must be a string"):
        client.request(method, "/v1/status/test")

    transport.assert_not_called()


@pytest.mark.parametrize(
    "base_url",
    [
        "example.invalid",
        "ftp://example.invalid",
        "https:///missing-host",
        "https://bad host",
        "https://example.invalid:invalid-port",
        "https://[invalid-ipv6",
        "https://example.invalid?token=synthetic",
        "https://example.invalid#synthetic-fragment",
        "https://example.invalid?",
        "https://example.invalid#",
    ],
)
def test_invalid_base_url_fails_before_transport(base_url):
    transport = Mock()

    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        FortyGuardClient(base_url, API_KEY, transport, timeout=3)

    transport.assert_not_called()


@pytest.mark.parametrize("path", ["https://other.invalid/v1/items", "//other.invalid/v1/items"])
def test_absolute_and_network_location_paths_are_rejected(path):
    transport = Mock()
    client = build_client(transport)

    with pytest.raises(ValueError, match="Request path must be relative"):
        client.get(path)

    transport.assert_not_called()


@pytest.mark.parametrize("status_code", [None, "200", True, 99, 600])
def test_invalid_transport_status_codes_are_sanitized(status_code):
    response = SimpleNamespace(
        status_code=status_code,
        body=f"response includes {API_KEY}",
    )
    transport = Mock(return_value=response)
    client = build_client(transport)

    with pytest.raises(FortyGuardTransportError) as error:
        client.get("/v1/status/test")

    assert str(error.value) == "FortyGuard returned a malformed response."
    assert API_KEY not in str(error.value)
    assert transport.call_count == 1


def test_malformed_transport_response_property_error_is_sanitized():
    class MalformedResponse:
        @property
        def status_code(self):
            raise RuntimeError(f"invalid response containing {API_KEY}")

    transport = Mock(return_value=MalformedResponse())
    client = build_client(transport)

    with pytest.raises(FortyGuardTransportError) as error:
        client.get("/v1/status/test")

    assert str(error.value) == "FortyGuard returned a malformed response."
    assert API_KEY not in str(error.value)
    assert transport.call_count == 1


def test_concurrent_requests_use_local_fake_transport_and_isolated_calls():
    worker_count = 8
    start_barrier = Barrier(worker_count)
    records = []
    records_lock = Lock()

    def fake_transport(method, url, *, headers, timeout, params, json):
        start_barrier.wait(timeout=3)
        with records_lock:
            records.append((method, url, headers.copy(), timeout))
        return SimpleNamespace(status_code=200, url=url)

    client = build_client(fake_transport, timeout=2)
    paths = [f"/v1/local/{index}" for index in range(worker_count)]

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        responses = list(executor.map(client.get, paths))

    assert len(records) == worker_count
    assert {record[1] for record in records} == {
        f"{BASE_URL}{path}" for path in paths
    }
    assert all(record[0] == "GET" for record in records)
    assert all(record[2] == {"api-key": API_KEY} for record in records)
    assert all(record[3] == 2 for record in records)
    assert {response.url for response in responses} == {
        f"{BASE_URL}{path}" for path in paths
    }
