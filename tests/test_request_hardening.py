"""Caller-supplied request fields must not reach outside what Injecto serves.

Every cloning endpoint takes a repo_url, and the processing endpoints an
input_dir; /catalog takes a provider. Each was joined or cloned as given. These
lock the guards in place; see OP-259.
"""

import os
import subprocess
import zipfile
import io

import pytest
from fastapi.testclient import TestClient

from injecto import api

ALLOWED_REPO = "https://github.com/devopsgroupeu/openprime-infra-templates.git"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "CATALOG_REPO_ALLOWLIST", ["https://github.com/devopsgroupeu/"])
    return TestClient(api.app, raise_server_exceptions=False)


@pytest.fixture
def clones(monkeypatch):
    """Record every clone attempt on both paths without touching the network."""
    seen = []

    def fake_clone(repo_url, clone_path, **kwargs):
        seen.append({"repo_url": repo_url, **kwargs})
        os.makedirs(os.path.join(clone_path, "templates"))
        return True

    def fake_cached(repo_url, branch, dest=None, **kwargs):
        seen.append({"repo_url": repo_url})
        os.makedirs(os.path.join(dest, "templates"))
        return dest

    monkeypatch.setattr(api, "clone_repository", fake_clone)
    monkeypatch.setattr(api, "get_cached_templates", fake_cached)
    return seen


def body(**overrides):
    return {"repo_url": ALLOWED_REPO, "input_dir": "templates/", "data": {}, **overrides}


# --- repo_url allowlist -------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        ALLOWED_REPO,
        "https://github.com/devopsgroupeu/Injecto",
        "https://GitHub.com/devopsgroupeu/openprime-infra-templates.git",
    ],
)
def test_urls_under_an_allowed_owner_pass(client, url):
    assert api.repo_is_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        # The prefix match let both of these through.
        "https://github.com/devopsgroupeu/../attacker/repo",
        "https://github.com/devopsgroupeu-evil/repo.git",
        # Dot segments however they are spelled.
        "https://github.com/devopsgroupeu/./../attacker/repo",
        "https://github.com/devopsgroupeu/%2e%2e/attacker/repo",
        "https://github.com/devopsgroupeu/%2E%2E/attacker/repo",
        "https://github.com/devopsgroupeu/.%2e/attacker/repo",
        "https://github.com/devopsgroupeu/%252e%252e/attacker/repo",
        "https://github.com/devopsgroupeu/x%2f..%2f..%2fattacker/repo",
        "https://github.com/devopsgroupeu\\..\\attacker/repo",
        # Another owner, host, port or scheme.
        "https://github.com/attacker/repo.git",
        "https://github.com.attacker.io/devopsgroupeu/repo.git",
        "https://github.com:8443/devopsgroupeu/repo.git",
        "http://github.com/devopsgroupeu/repo.git",
        "ssh://git@github.com/devopsgroupeu/repo.git",
        "git@github.com:devopsgroupeu/repo.git",
        "file:///etc/devopsgroupeu",
        # Userinfo: credentials, or a host disguised as one.
        "https://token@github.com/devopsgroupeu/repo.git",
        "https://user:pass@github.com/devopsgroupeu/repo.git",
        "https://github.com@attacker.io/devopsgroupeu/repo.git",
        "https://@github.com/devopsgroupeu/repo.git",
        # Whitespace and control characters git and urlsplit read differently.
        "https://github.com/devopsgroupeu/repo.git\n",
        " https://github.com/devopsgroupeu/repo.git",
        "https://github.com/devopsgroupeu/re\tpo.git",
        # Query, fragment, and nothing at all.
        "https://github.com/devopsgroupeu/repo.git?x=1",
        "https://github.com/devopsgroupeu/repo.git#x",
        "https://github.com/",
        "",
    ],
)
def test_urls_outside_the_allowlist_are_refused(client, url):
    assert not api.repo_is_allowed(url)


@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_cloning_endpoints_refuse_a_repo_outside_the_allowlist(client, clones, endpoint):
    """Only /catalog checked the allowlist; the generation endpoints cloned anything."""
    response = client.post(endpoint, json=body(repo_url="https://github.com/devopsgroupeu/../attacker/repo"))

    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"]
    assert clones == []


@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_cloning_endpoints_refuse_when_no_allowlist_is_configured(client, clones, monkeypatch, endpoint):
    """Same as /catalog: an unset allowlist disables cloning instead of allowing everything."""
    monkeypatch.setattr(api, "CATALOG_REPO_ALLOWLIST", [])

    assert client.post(endpoint, json=body()).status_code == 503
    assert clones == []


def test_catalog_refuses_the_dot_segment_bypass(client, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("an unallowed repo must be refused before any git call")

    monkeypatch.setattr(api, "resolve_remote_sha", no_network)
    monkeypatch.setattr(api, "clone_repository", no_network)

    response = client.get("/catalog", params={"repo_url": "https://github.com/devopsgroupeu/../attacker/repo"})
    assert response.status_code == 400


# --- input_dir ----------------------------------------------------------------


@pytest.fixture
def walked(monkeypatch):
    """Record the directory handed to the walk instead of walking it: without
    the guard, input_dir "/" processes the whole filesystem."""
    seen = []
    monkeypatch.setattr(api, "process_files", lambda input_dir, output_dir, data: seen.append(input_dir))
    return seen


@pytest.mark.parametrize("input_dir", ["../", "../../..", "templates/../../x", "/etc", "/"])
@pytest.mark.parametrize("endpoint", ["/process", "/process-git-download"])
def test_input_dir_cannot_leave_the_clone(client, clones, walked, endpoint, input_dir):
    response = client.post(endpoint, json=body(input_dir=input_dir))

    assert response.status_code == 400
    assert "input_dir" in response.json()["detail"]
    assert walked == []


def test_input_dir_through_a_symlinked_directory_is_refused(client, walked, monkeypatch, tmp_path):
    """resolve() is what catches this one: the requested path has no `..`, the
    repository's own symlink supplies the escape."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("leaked")

    def fake_clone(repo_url, clone_path, **kwargs):
        os.makedirs(clone_path)
        os.symlink(outside, os.path.join(clone_path, "templates"))
        return True

    monkeypatch.setattr(api, "clone_repository", fake_clone)

    response = client.post("/process", json=body())
    assert response.status_code == 400
    assert walked == []


def test_a_normal_input_dir_still_processes(client, clones):
    response = client.post("/process", json=body())

    assert response.status_code == 200, response.text


# --- /process clone limits ----------------------------------------------------


def test_the_process_clone_is_shallow_and_bounded(client, clones):
    """An unbounded clone of a large or stalled remote held the request open
    indefinitely; the cached path and /catalog already used depth 1 and 60 s."""
    client.post("/process", json=body())

    assert clones[0]["depth"] == 1
    assert clones[0]["timeout"]


# --- symlinks on the path the backend calls -----------------------------------


def test_process_git_download_does_not_ship_a_symlink_target(client, monkeypatch, tmp_path):
    """The cache snapshot used copytree without symlinks=True, which copies a
    link's target as a regular file, so the walk never saw a symlink at all."""
    secret = tmp_path / "secret.txt"
    secret.write_text("SERVICE_TOKEN=leaked\n")
    monkeypatch.setenv("TEMPLATES_CACHE_DIR", str(tmp_path / "cache"))

    def fake_run(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            target = command[-1]
            os.makedirs(os.path.join(target, ".git"))
            os.makedirs(os.path.join(target, "templates"))
            os.symlink(secret, os.path.join(target, "templates", "values.yaml"))

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = client.post("/process-git-download", json=body())

    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            contents = b"".join(archive.read(name) for name in archive.namelist())
        assert b"leaked" not in contents
    assert response.status_code != 200


# --- /catalog provider --------------------------------------------------------


@pytest.mark.parametrize("provider", ["../../..", "aws/../../x", "AWS", "a b", ""])
def test_catalog_provider_must_be_a_plain_directory_name(client, monkeypatch, provider):
    def no_network(*args, **kwargs):
        raise AssertionError("an invalid provider must be refused before any git call")

    monkeypatch.setattr(api, "resolve_remote_sha", no_network)
    monkeypatch.setattr(api, "clone_repository", no_network)

    response = client.get("/catalog", params={"repo_url": ALLOWED_REPO, "provider": provider})
    assert response.status_code == 400
