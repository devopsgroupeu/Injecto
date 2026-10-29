"""A slow generation must not stall the rest of the service.

Injecto runs one uvicorn worker. The processing endpoints clone with git and
run `terraform fmt` through subprocess.run, which blocks; inside an `async def`
handler that blocks the event loop itself, so nothing else - not even /health
- is answered until it finishes, and the liveness probe restarts the pod
mid-generate. See OP-264.
"""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from injecto import api

GIT_BODY = {"repo_url": "https://example.invalid/org/x.git", "input_dir": "t/", "data": {}}

# Generous next to an un-blocked /health (milliseconds), well short of how long
# the stand-in operation holds on when nothing releases it.
HEALTH_BUDGET_SECONDS = 1.0
SLOW_OPERATION_SECONDS = 5.0


@pytest.mark.parametrize(
    "endpoint,slow_function,request_kwargs",
    [
        ("/process", "generate_from_git", {"json": GIT_BODY}),
        ("/process-git-download", "generate_from_git", {"json": GIT_BODY}),
        ("/process-upload", "process_files", {"files": [("files", ("a.tf", b"x = 1\n"))]}),
    ],
)
def test_health_answers_while_a_slow_generation_is_in_flight(monkeypatch, endpoint, slow_function, request_kwargs):
    started = threading.Event()
    release = threading.Event()

    def slow(*args, **kwargs):
        # Stands in for a git clone: blocks the calling thread like
        # subprocess.run does. Bounded, so a regression fails instead of hanging.
        started.set()
        release.wait(SLOW_OPERATION_SECONDS)
        if slow_function == "generate_from_git":
            return args[1]  # the request's (empty) scratch dir as the output tree

    monkeypatch.setattr(api, slow_function, slow)
    monkeypatch.setattr(api, "start_metrics_server", lambda: None)

    # One client entered as a context manager shares one event loop across
    # requests, like the single uvicorn worker does in production.
    with TestClient(api.app) as client:
        responses = []
        worker = threading.Thread(target=lambda: responses.append(client.post(endpoint, **request_kwargs)))
        worker.start()
        try:
            assert started.wait(SLOW_OPERATION_SECONDS), "the slow operation never started"

            began = time.monotonic()
            health = client.get("/health")
            elapsed = time.monotonic() - began
            still_in_flight = not release.is_set() and worker.is_alive()
        finally:
            release.set()
            worker.join(SLOW_OPERATION_SECONDS * 2)

    assert health.status_code == 200
    assert still_in_flight and elapsed < HEALTH_BUDGET_SECONDS, (
        f"/health took {elapsed:.2f}s while {endpoint} was running: the event loop was blocked"
    )
    assert responses and responses[0].status_code == 200


def test_the_request_id_still_reaches_logs_written_inside_the_handler(monkeypatch):
    """Sync handlers run on a threadpool thread; the X-Request-ID contextvar the
    middleware binds must travel with them or log correlation breaks."""
    from injecto.logs import request_id_var

    seen = []

    def record(request, temp_dir, use_cache=False):
        seen.append(request_id_var.get())
        return temp_dir

    monkeypatch.setattr(api, "generate_from_git", record)

    response = TestClient(api.app).post("/process", json=GIT_BODY, headers={"X-Request-ID": "corr-123"})

    assert response.status_code == 200
    assert seen == ["corr-123"]


def test_a_sync_upload_handler_still_reads_templates_and_config_files():
    """The upload handler reads UploadFile.file directly now that it is sync;
    both upload lists must still arrive intact."""
    import io
    import zipfile

    response = TestClient(api.app).post(
        "/process-upload",
        files=[
            ("files", ("nested/values.yaml", b"# @param app.name\nname: old\n")),
            ("config_files", ("base.yaml", b"app:\n  name: from-config\n")),
        ],
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("nested/values.yaml").decode() == '# @param app.name\nname: "from-config"\n'
