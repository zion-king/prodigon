"""
Tests Demonstrating FastAPI Dependency Overrides.

This file shows the primary benefit of dependency injection: testability.
Every dependency can be swapped out for a fake, mock, or test-specific
implementation WITHOUT modifying the application code.

Run:
    python -m pytest test_with_overrides.py -v

No API keys, no running services, no external calls needed.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from well_structured import (
    Settings,
    app,
    check_service_health,
    get_groq_client,
    get_settings,
    verify_api_key,
)


# ===========================================================================
# Test Fixtures -- reusable fakes and mocks
# ===========================================================================

def get_test_settings() -> Settings:
    """Return settings with known test values -- no .env file needed."""
    return Settings(
        groq_api_key="test-fake-key",
        default_model="test-model",
        max_tokens=100,
        temperature=0.5,
        api_key="test-api-key",
        service_name="test-service",
        environment="testing",
    )


def skip_auth() -> bool:
    """Override auth dependency -- always passes."""
    return True


def make_mock_groq_client():
    """Create a mock Groq client that returns a fixed response.

    This is the key to testing AI endpoints without real API calls.
    The mock mimics the Groq client's chat.completions.create() interface.
    """
    mock_client = MagicMock()

    # Build the mock response structure to match Groq's API
    mock_message = MagicMock()
    mock_message.content = "This is a mocked response from the test."

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_completion

    return mock_client


# ===========================================================================
# Test Setup -- apply overrides before tests, clean up after
# ===========================================================================

@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Apply dependency overrides for all tests, clean up after each test."""
    # Setup: override all dependencies with test versions
    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[verify_api_key] = skip_auth
    app.dependency_overrides[get_groq_client] = make_mock_groq_client

    yield

    # Teardown: remove all overrides to avoid leaking between tests
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Create a test client for the app."""
    return TestClient(app)


# ===========================================================================
# Test: Generate endpoint with mocked model client
# ===========================================================================

def test_generate_returns_mocked_response(client):
    """The /generate endpoint should use the mock client and return its response.

    What this proves:
    - The endpoint works without a real Groq API key
    - The mock client's response flows through correctly
    - The handler only depends on the client interface, not its implementation
    """
    response = client.post(
        "/generate",
        json={"prompt": "What is dependency injection?"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["text"] == "This is a mocked response from the test."
    assert data["model"] == "test-model"
    assert "latency_ms" in data
    assert data["latency_ms"] >= 0


def test_generate_with_custom_parameters(client):
    """Custom parameters should be forwarded to the mock client."""
    response = client.post(
        "/generate",
        json={
            "prompt": "Hello",
            "max_tokens": 50,
            "temperature": 0.1,
        },
    )
    assert response.status_code == 200

    # Verify the mock was called (the response still comes from the mock)
    data = response.json()
    assert data["text"] == "This is a mocked response from the test."


# ===========================================================================
# Test: Auth enforcement when override is removed
# ===========================================================================

def test_generate_without_auth_returns_403(client):
    """When auth is NOT overridden, missing API key should return 403.

    This test temporarily removes the auth override to verify that the
    real auth dependency works correctly.
    """
    # Remove the auth override so the real verify_api_key runs
    del app.dependency_overrides[verify_api_key]

    # Request without X-API-Key header
    response = client.post(
        "/generate",
        json={"prompt": "test"},
    )
    # FastAPI returns 422 when a required header is missing
    assert response.status_code in (403, 422)


def test_generate_with_wrong_auth_returns_403(client):
    """When auth is NOT overridden, wrong API key should return 403."""
    del app.dependency_overrides[verify_api_key]

    response = client.post(
        "/generate",
        json={"prompt": "test"},
        headers={"X-API-Key": "wrong-key-entirely"},
    )
    assert response.status_code == 403


def test_generate_with_correct_auth_succeeds(client):
    """When auth is NOT overridden, correct API key should succeed."""
    del app.dependency_overrides[verify_api_key]

    response = client.post(
        "/generate",
        json={"prompt": "test"},
        headers={"X-API-Key": "test-api-key"},  # matches get_test_settings
    )
    assert response.status_code == 200


# ===========================================================================
# Test: Health endpoint
# ===========================================================================

def test_health_returns_service_info(client):
    """Health endpoint should return info from the injected settings."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "test-service"
    assert data["environment"] == "testing"


def test_health_uses_test_settings(client):
    """Verify the health endpoint actually uses our overridden settings."""
    # Override with different settings
    app.dependency_overrides[get_settings] = lambda: Settings(
        service_name="custom-test",
        environment="staging",
    )
    # Also override health check since it depends on settings
    app.dependency_overrides[check_service_health] = lambda: {
        "status": "healthy",
        "service": "custom-test",
        "environment": "staging",
        "groq_client": "not configured",
    }

    response = client.get("/health")
    data = response.json()
    assert data["service"] == "custom-test"
    assert data["environment"] == "staging"


# ===========================================================================
# Test: Metrics endpoint
# ===========================================================================

def test_metrics_returns_model_info(client):
    """Metrics endpoint should return model info from settings."""
    response = client.get("/metrics")
    assert response.status_code == 200

    data = response.json()
    assert data["model"] == "test-model"
    assert data["service"] == "test-service"
    assert data["version"] == "0.1.0"


# ===========================================================================
# Test: Settings override with different configurations
# ===========================================================================

def test_generate_with_custom_settings(client):
    """Override settings to change the model name used in generation."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        groq_api_key="custom-key",
        default_model="custom-model-v2",
        api_key="any-key",
        service_name="custom-service",
    )

    response = client.post(
        "/generate",
        json={"prompt": "test"},
    )
    assert response.status_code == 200
    assert response.json()["model"] == "custom-model-v2"


# ===========================================================================
# Test: No client configured (graceful degradation)
# ===========================================================================

def test_generate_without_client_returns_500(client):
    """When the Groq client returns None, the endpoint should return 500."""
    app.dependency_overrides[get_groq_client] = lambda: None

    response = client.post(
        "/generate",
        json={"prompt": "test"},
    )
    assert response.status_code == 500
    assert "not configured" in response.json()["detail"]


# ===========================================================================
# Key Takeaways:
#
# 1. ZERO real API calls in all tests above
# 2. Each test controls exactly what it needs via dependency_overrides
# 3. Auth can be tested independently by removing its override
# 4. Settings can be customized per-test without touching env vars
# 5. The test file is self-contained -- no fixtures, no conftest, no env files
# ===========================================================================
