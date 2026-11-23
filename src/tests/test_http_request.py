from unittest.mock import Mock

import pytest


def request_api_status(api_url, api_key, http_get):
    response = http_get(
        f"{api_url}/v1/status/test",
        headers={"api-key": api_key},
        timeout=20,
    )

    assert response.status_code in [200, 404], (
        f"Unexpected response: {response.status_code}"
    )
    return response


def test_http_request_construction_uses_expected_url_headers_and_timeout():
    response = Mock(status_code=200)
    http_get = Mock(return_value=response)

    result = request_api_status(
        "https://example.invalid", "synthetic-key", http_get
    )

    http_get.assert_called_once_with(
        "https://example.invalid/v1/status/test",
        headers={"api-key": "synthetic-key"},
        timeout=20,
    )
    assert result is response


@pytest.mark.parametrize("status_code", [200, 404])
def test_http_response_handling_accepts_status_codes(status_code):
    response = Mock(status_code=status_code)

    result = request_api_status(
        "https://example.invalid", "synthetic-key", Mock(return_value=response)
    )

    assert result is response


def test_http_response_handling_rejects_unexpected_status():
    response = Mock(status_code=401)

    with pytest.raises(AssertionError, match="Unexpected response: 401"):
        request_api_status(
            "https://example.invalid", "synthetic-key", Mock(return_value=response)
        )
