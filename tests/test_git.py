"""Tests for git URL credential masking (keeps PATs out of the logs)."""

from injecto.git import mask_url_credentials


def test_masks_user_and_pat_in_https_url():
    url = "https://alice:ghp_secretpat@github.com/org/repo.git"
    assert mask_url_credentials(url) == "https://***:***@github.com/org/repo.git"


def test_masks_credentials_inside_a_command_string():
    cmd = "git clone --branch main https://u:p@host/x.git /tmp/x"
    assert mask_url_credentials(cmd) == "git clone --branch main https://***:***@host/x.git /tmp/x"


def test_leaves_credential_free_url_untouched():
    url = "https://github.com/org/repo.git"
    assert mask_url_credentials(url) == url


def test_leaves_plain_text_untouched():
    assert mask_url_credentials("git clone /tmp/local /tmp/dest") == "git clone /tmp/local /tmp/dest"


# --- Clone options and failure reporting (OP-204) ---------------------------

import subprocess

import pytest

from injecto.git import clone_repository


class _FakeCompleted:
    returncode = 0


def test_depth_and_timeout_reach_the_git_command(monkeypatch, tmp_path):
    """The catalog only reads the tip, so a full clone is wasted transfer, and
    an unreachable host must not hang the request."""
    seen = {}

    def fake_run(command, **kwargs):
        seen['command'] = command
        seen['timeout'] = kwargs.get('timeout')
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert clone_repository('https://host/x.git', str(tmp_path / 'c'), depth=1, timeout=30)

    assert '--depth' in seen['command']
    assert seen['command'][seen['command'].index('--depth') + 1] == '1'
    assert seen['timeout'] == 30


def test_depth_is_omitted_when_not_requested(monkeypatch, tmp_path):
    seen = {}

    def fake_run(command, **kwargs):
        seen['command'] = command
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    clone_repository('https://host/x.git', str(tmp_path / 'c'))

    assert '--depth' not in seen['command']


def test_a_failed_clone_does_not_log_the_pat(monkeypatch, tmp_path, caplog):
    """str(CalledProcessError) embeds the whole command, which carries the
    authenticated URL. Masking only the success path leaks the token on exactly
    the path that gets pasted into a bug report."""
    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(
            128, command, stderr="fatal: repository not found\n"
        )

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with caplog.at_level('ERROR'):
        assert not clone_repository(
            'https://host/x.git', str(tmp_path / 'c'), username='alice', pat='ghp_secretpat'
        )

    logged = caplog.text
    assert 'ghp_secretpat' not in logged
    assert '***:***' in logged


def test_a_failed_clone_surfaces_git_stderr(monkeypatch, tmp_path, caplog):
    """git's stderr is the only thing that says *why* a clone failed; without it
    every failure reads the same."""
    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(128, command, stderr="fatal: Remote branch nope not found\n")

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with caplog.at_level('ERROR'):
        clone_repository('https://host/x.git', str(tmp_path / 'c'), branch='nope')

    assert 'Remote branch nope not found' in caplog.text


def test_a_timeout_is_reported_rather_than_raised(monkeypatch, tmp_path, caplog):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with caplog.at_level('ERROR'):
        assert not clone_repository('https://host/x.git', str(tmp_path / 'c'), timeout=30)

    assert 'Timed out' in caplog.text


# --- Cached templates clone (shallow clone + per-key refresh) ---------------

import hashlib
import os

from injecto.git import get_cached_templates


def test_get_cached_templates_clones_into_cache_on_first_use(monkeypatch, tmp_path):
    """First request shallow-clones the templates repo into the cache dir."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"

    seen = []

    def fake_run(command, **kwargs):
        # Simulate git clone actually creating the target directory.
        if command[:2] == ["git", "clone"]:
            os.makedirs(command[-1], exist_ok=True)
        seen.append(command)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    cache_path = get_cached_templates(repo_url, branch, cache_dir=str(tmp_path))

    assert cache_path.exists()
    # First call is the initial shallow clone
    clone_command = seen[0]
    assert clone_command[:2] == ["git", "clone"]
    assert "--depth" in clone_command
    assert str(cache_path) in clone_command


def test_get_cached_templates_refreshes_existing_cache(monkeypatch, tmp_path):
    """Later requests refresh the cached clone with a shallow fetch + reset."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]
    cache_path = tmp_path / cache_key
    cache_path.mkdir()
    (cache_path / "README.md").write_text("templates")

    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    result = get_cached_templates(repo_url, branch, cache_dir=str(tmp_path))

    assert result == cache_path
    assert seen[0][:4] == ["git", "-C", str(cache_path), "fetch"]
    assert "--depth" in seen[0]
    assert seen[1][:4] == ["git", "-C", str(cache_path), "reset"]
    # No full clone on cache hits
    assert all(cmd[0] != "git" or cmd[1] != "clone" for cmd in seen)
