"""Resource bounds (OP-259, B69): the templates cache, request bodies and the
result ZIP each grew with the request, so one large or unusual request could
exhaust the pod's memory or the node's disk.
"""

import asyncio
import fcntl
import hashlib
import io
import os
import subprocess
import tracemalloc
import zipfile

import pytest
from fastapi.testclient import TestClient

import injecto.api as api
from injecto.api import app, create_zip_response
from injecto.git import get_cached_templates

client = TestClient(app, raise_server_exceptions=False)


class _FakeCompleted:
    returncode = 0


@pytest.fixture
def fake_git(monkeypatch):
    """Clone creates a working tree with a .git dir; fetch and reset succeed."""

    def fake_run(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            os.makedirs(os.path.join(command[-1], ".git"), exist_ok=True)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)


def _entry(cache_dir, repo_url, branch="main"):
    return cache_dir / hashlib.sha256(f"{repo_url}|{branch}".encode()).hexdigest()[:16]


# --- Templates cache -------------------------------------------------------


def test_the_cache_keeps_at_most_max_entries_and_evicts_the_least_recently_used(
    fake_git, monkeypatch, tmp_path
):
    monkeypatch.setenv("TEMPLATES_CACHE_MAX_ENTRIES", "2")
    a, b, c = (f"https://github.com/org/{name}.git" for name in "abc")

    get_cached_templates(a, "main", cache_dir=str(tmp_path))
    get_cached_templates(b, "main", cache_dir=str(tmp_path))
    # a is older than b, until it is used again.
    os.utime(_entry(tmp_path, a), (1000, 1000))
    os.utime(_entry(tmp_path, b), (2000, 2000))
    get_cached_templates(a, "main", cache_dir=str(tmp_path))

    get_cached_templates(c, "main", cache_dir=str(tmp_path))

    assert _entry(tmp_path, a).exists()
    assert not _entry(tmp_path, b).exists()
    assert _entry(tmp_path, c).exists()


def test_an_entry_another_request_is_using_is_not_evicted(fake_git, monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPLATES_CACHE_MAX_ENTRIES", "2")
    a, b, c = (f"https://github.com/org/{name}.git" for name in "abc")
    get_cached_templates(a, "main", cache_dir=str(tmp_path))
    get_cached_templates(b, "main", cache_dir=str(tmp_path))
    os.utime(_entry(tmp_path, a), (1000, 1000))
    os.utime(_entry(tmp_path, b), (2000, 2000))

    # The oldest entry is locked, as it is while a request refreshes or copies it.
    with open(f"{_entry(tmp_path, a)}.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        get_cached_templates(c, "main", cache_dir=str(tmp_path))

    assert _entry(tmp_path, a).exists()
    assert not _entry(tmp_path, b).exists()


# --- Request bodies and uploads ---------------------------------------------


def _upload(*names, size=10):
    return [("files", (name, b"x" * size)) for name in names]


def test_a_body_over_the_limit_answers_413_before_anything_is_processed(monkeypatch):
    monkeypatch.setattr(api, "MAX_REQUEST_BYTES", 1024, raising=False)
    processed = []
    monkeypatch.setattr(api, "process_files", lambda *args: processed.append(args))

    response = client.post("/process-upload", files=_upload("a.tf", size=4096))

    assert response.status_code == 413
    assert processed == []


def test_the_body_limit_covers_the_json_endpoints_too(monkeypatch):
    monkeypatch.setattr(api, "MAX_REQUEST_BYTES", 1024, raising=False)

    response = client.post(
        "/process-git-download",
        json={"repo_url": "https://example.invalid/org/x.git", "input_dir": "t/", "data": {"k": "v" * 4096}},
    )

    assert response.status_code == 413


def test_a_body_without_a_declared_length_is_refused():
    """A chunked body has no length to check up front, so it is not accepted."""

    def chunks():
        yield b"{}"

    response = client.post(
        "/process-git-download", content=chunks(), headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 411


def test_too_many_uploaded_files_answers_413(monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_FILES", 2, raising=False)
    processed = []
    monkeypatch.setattr(api, "process_files", lambda *args: processed.append(args))

    response = client.post("/process-upload", files=_upload("a.tf", "b.tf", "c.tf"))

    assert response.status_code == 413
    assert processed == []


def test_an_upload_within_the_limits_is_processed():
    response = client.post(
        "/process-upload",
        files=[("files", ("main.tf", b'# @param a.b\nx = "old"\n'))],
        data={"data": '{"a": {"b": "new"}}'},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert 'x = "new"' in archive.read("main.tf").decode()


# --- Result ZIP --------------------------------------------------------------


def test_the_result_zip_is_not_held_in_memory(tmp_path):
    """The archive was built in a BytesIO and then copied, so a response cost
    twice its size in memory. Incompressible content keeps the archive as large
    as the input."""
    output_dir = tmp_path / "output"
    (output_dir / "nested").mkdir(parents=True)
    size = 12 * 1024 * 1024
    with open(output_dir / "big.bin", "wb") as f:
        for _ in range(size // (1024 * 1024)):
            f.write(os.urandom(1024 * 1024))
    (output_dir / "nested" / "main.tf").write_text('x = "y"\n')
    received = tmp_path / "received.zip"

    async def drain(response):
        with open(received, "wb") as out:
            async for chunk in response.body_iterator:
                out.write(chunk)

    tracemalloc.start()
    try:
        response = create_zip_response(output_dir)
        asyncio.run(drain(response))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 4 * 1024 * 1024
    assert int(response.headers["Content-Length"]) == received.stat().st_size
    with zipfile.ZipFile(received) as archive:
        assert sorted(archive.namelist()) == ["big.bin", "nested/main.tf"]
        assert archive.getinfo("big.bin").file_size == size
