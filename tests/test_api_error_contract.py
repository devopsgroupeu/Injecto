"""The three processing endpoints must translate failures identically.

Each endpoint used to carry its own copy of the same try/except/finally block.
OP-163 collapsed them into `processing_request`; these tests are what stops the
collapse from quietly changing an answer. The 422 arm is the one that matters:
the backend keys its user-facing message off that status and the `code` in the
body (OP-214), so an endpoint that regresses to 500 loses the explanation.
"""

import pytest
from fastapi.testclient import TestClient

import injecto.api as api
from injecto.api import app
from injecto.processing import GenerationError

client = TestClient(app, raise_server_exceptions=False)

GIT_BODY = {"repo_url": "https://example.invalid/x.git", "input_dir": "t/", "data": {}}


@pytest.fixture
def generate_raises(monkeypatch):
    """Make the git pipeline raise whatever the test asks for."""

    def _apply(exc):
        def boom(request, temp_dir, use_cache=False):
            raise exc

        monkeypatch.setattr(api, "generate_from_git", boom)

    return _apply


@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_generation_error_becomes_422_with_the_code_the_backend_reads(endpoint, generate_raises):
    generate_raises(GenerationError("FILES_FAILED", "two files failed", ["a.tf:12"]))

    response = client.post(endpoint, json=GIT_BODY)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "FILES_FAILED"
    assert detail["message"] == "two files failed"
    assert detail["details"] == ["a.tf:12"]


@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_an_unexpected_error_stays_a_500(endpoint, generate_raises):
    """Only a GenerationError means 'the output would be wrong'; the rest are bugs."""
    generate_raises(RuntimeError("disk went away"))

    assert client.post(endpoint, json=GIT_BODY).status_code == 500


@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_a_400_is_passed_through_untouched(endpoint):
    """repo_url is required for a git source, and that check must not become a 500."""
    response = client.post(endpoint, json={"input_dir": "t/", "data": {}})

    assert response.status_code == 400
    assert "repo_url" in response.json()["detail"]


def test_upload_endpoint_translates_generation_errors_the_same_way(monkeypatch):
    def boom(input_dir, output_dir, data):
        raise GenerationError("MULTILINE_VALUE", "would corrupt", ["x.tf:7"])

    monkeypatch.setattr(api, "process_files", boom)

    response = client.post(
        "/process-upload",
        files=[("files", ("a.tf", b"# @param a.b\nx = 1\n"))],
        data={"data": "{}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MULTILINE_VALUE"


def test_source_defaults_to_git_rather_than_a_guaranteed_400():
    """Both endpoints taking ProcessRequest require git, so 'local' was a trap:
    omitting the field could only ever produce 'Local source requires ...'."""
    from injecto.api import ProcessRequest

    assert ProcessRequest(input_dir="t/", data={}).source == "git"


def test_scratch_directory_is_removed_even_when_the_request_fails(generate_raises, monkeypatch):
    created = []
    real_create = api.create_temp_directory

    def record():
        path = real_create()
        created.append(path)
        return path

    monkeypatch.setattr(api, "create_temp_directory", record)
    generate_raises(GenerationError("FILES_FAILED", "boom", []))

    client.post("/process", json=GIT_BODY)

    assert created, "the endpoint never created a scratch directory"
    assert not created[0].exists()
