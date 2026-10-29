"""Tests for the service-token authorization helper."""

import pytest
from fastapi.testclient import TestClient

from injecto import api, auth
from injecto.api import app
from injecto.auth import token_is_authorized


def test_no_configured_token_refuses_everything():
    # Fail closed (OP-260): a missing or empty token must never mean "allow".
    assert token_is_authorized(None, None) is False
    assert token_is_authorized("anything", None) is False
    assert token_is_authorized("", "") is False


def test_the_dev_flag_is_the_only_way_to_run_without_a_token():
    assert token_is_authorized(None, None, auth_disabled=True) is True
    assert token_is_authorized("anything", "", auth_disabled=True) is True


def test_a_configured_token_wins_over_the_dev_flag():
    """Setting the flag next to a real token must not open the service."""
    assert token_is_authorized(None, "s3cr3t-token", auth_disabled=True) is False
    assert token_is_authorized("wrong", "s3cr3t-token", auth_disabled=True) is False


def test_accepts_matching_token():
    assert token_is_authorized("s3cr3t-token", "s3cr3t-token") is True


def test_rejects_wrong_token():
    assert token_is_authorized("wrong", "s3cr3t-token") is False


def test_rejects_missing_token_when_required():
    assert token_is_authorized(None, "s3cr3t-token") is False
    assert token_is_authorized("", "s3cr3t-token") is False


@pytest.fixture
def unconfigured(monkeypatch):
    """Neither a token nor the dev flag: what an unconfigured deployment gets."""
    monkeypatch.setattr(auth, "SERVICE_TOKEN", None)
    monkeypatch.setattr(auth, "AUTH_DISABLED", False, raising=False)


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("post", "/process", {"json": {"repo_url": "https://example.invalid/x.git", "input_dir": "t/", "data": {}}}),
        ("post", "/process-git-download", {"json": {"repo_url": "https://example.invalid/x.git", "input_dir": "t/", "data": {}}}),
        ("post", "/process-upload", {"files": [("files", ("a.tf", b"x = 1\n"))]}),
        ("get", "/catalog", {"params": {"repo_url": "https://example.invalid/x.git"}}),
    ],
)
def test_an_unconfigured_service_refuses_requests(unconfigured, monkeypatch, method, path, kwargs):
    """Without a token every endpoint used to be open to any pod in the cluster."""
    def no_work(*args, **kwargs):
        raise AssertionError("an unauthorized request must be refused before any work")

    for name in ("clone_repository", "get_cached_templates", "resolve_remote_sha", "process_files"):
        monkeypatch.setattr(api, name, no_work)
    client = TestClient(app, raise_server_exceptions=False)

    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_an_unconfigured_service_refuses_to_start(unconfigured):
    """Refusing at startup turns a missing secret into a crash-looping pod the
    operator sees, rather than a running service that answers 401 forever."""
    with pytest.raises(RuntimeError, match="SERVICE_TOKEN"):
        with TestClient(app):
            pass


def test_health_still_answers_without_a_token(unconfigured):
    """Probes carry no token; /health must not be behind the dependency."""
    assert TestClient(app).get("/health").status_code == 200


@pytest.mark.parametrize("value,expected", [("true", True), ("1", True), ("yes", True), ("", False), ("false", False), ("0", False)])
def test_the_dev_flag_parses_like_the_other_boolean_settings(value, expected):
    assert auth.flag_is_set(value) is expected
