"""What the API discloses and echoes (OP-270, B72): internal error detail,
the interactive docs and schema, and the caller's X-Request-ID."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import injecto.api as api
from injecto.api import app

client = TestClient(app, raise_server_exceptions=False)

GIT_BODY = {"repo_url": "https://example.invalid/org/x.git", "input_dir": "t/", "data": {}}
INTERNAL = "/tmp/injecto_api_abc/clone: permission denied"


@pytest.fixture(autouse=True)
def allow_the_test_repo(monkeypatch):
    monkeypatch.setattr(api, "CATALOG_REPO_ALLOWLIST", ["https://example.invalid/org/"])


# --- 500 detail ---------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_a_500_does_not_carry_the_internal_error(endpoint, monkeypatch):
    def boom(request, temp_dir, use_cache=False):
        raise RuntimeError(INTERNAL)

    monkeypatch.setattr(api, "generate_from_git", boom)

    response = client.post(endpoint, json=GIT_BODY)

    assert response.status_code == 500
    assert response.json() == {"detail": "Processing failed"}


def test_the_upload_endpoint_does_not_leak_it_either(monkeypatch):
    def boom(input_dir, output_dir, data):
        raise RuntimeError(INTERNAL)

    monkeypatch.setattr(api, "process_files", boom)

    response = client.post("/process-upload", files=[("files", ("a.tf", b"x = 1\n"))])

    assert response.status_code == 500
    assert INTERNAL not in response.text


# --- Docs and schema ------------------------------------------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_docs_and_the_schema_are_off_by_default(path):
    assert client.get(path).status_code == 404


def test_the_docs_can_be_turned_on_for_development():
    """The app is built at import, so the flag is read in a fresh interpreter."""
    probe = (
        "from fastapi.testclient import TestClient\n"
        "from injecto.api import app\n"
        "c = TestClient(app)\n"
        "print([c.get(p).status_code for p in ('/docs', '/redoc', '/openapi.json')])\n"
    )
    env = {**os.environ, "INJECTO_DOCS_ENABLED": "true", "INJECTO_AUTH_DISABLED": "true"}
    env.pop("SERVICE_TOKEN", None)

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines()[-1] == "[200, 200, 200]"


# --- X-Request-ID ---------------------------------------------------------------


@pytest.mark.parametrize("request_id", ["corr-123", "0f8fad5b-d9cb-469f-a165-70867728950e", "a" * 64])
def test_a_well_formed_request_id_is_kept(request_id):
    response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.parametrize(
    "request_id",
    ["a" * 65, "id with spaces", "<script>", "abc;rm", '{"json":1}', ""],
    ids=["too-long", "spaces", "markup", "semicolon", "json", "empty"],
)
def test_any_other_request_id_is_replaced_with_a_generated_one(request_id):
    response = client.get("/health", headers={"X-Request-ID": request_id})

    echoed = response.headers["X-Request-ID"]
    assert echoed != request_id
    assert re.fullmatch(r"[0-9a-f]{16}", echoed)
