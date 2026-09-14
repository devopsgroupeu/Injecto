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


def _init_real_repo(path):
    """Create a genuine git working tree at `path` (init + one commit).

    The cache-validity check looks for a .git directory, so a fixture that
    exercises the refresh path must be a real repo, not just a dir with files.
    """
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True, capture_output=True,
    )
    (path / "README.md").write_text("templates")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True, capture_output=True,
    )


def test_get_cached_templates_refreshes_existing_cache(monkeypatch, tmp_path):
    """Later requests refresh the cached clone with a shallow fetch + reset."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]
    cache_path = tmp_path / cache_key
    _init_real_repo(cache_path)

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


def test_a_partial_clone_without_git_is_wiped_and_recloned(monkeypatch, tmp_path):
    """A clone killed by the timeout leaves a non-empty directory without .git.
    That debris must be wiped and re-cloned, not treated as a valid cache
    forever (clone_repository refuses non-empty targets, so it could never
    self-heal otherwise)."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]
    cache_path = tmp_path / cache_key
    cache_path.mkdir()
    (cache_path / "objects").mkdir()
    (cache_path / "objects" / "tmp-pack").write_text("partial clone debris")

    seen = []

    def fake_run(command, **kwargs):
        # Simulate git clone actually creating a working tree with .git.
        if command[:2] == ["git", "clone"]:
            os.makedirs(os.path.join(command[-1], ".git"), exist_ok=True)
        seen.append(command)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    result = get_cached_templates(repo_url, branch, cache_dir=str(tmp_path))

    # The debris was wiped and a fresh clone attempted
    assert seen[0][:2] == ["git", "clone"]
    assert result == cache_path
    assert (cache_path / ".git").exists()


def test_a_failed_clone_cleans_up_the_partial_cache_dir(monkeypatch, tmp_path):
    """A clone that fails inside the cached path must not leave debris behind:
    a partial directory would poison the cache key until the pod restarts."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]

    def fake_run(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            # git creates the target before the transfer fails
            os.makedirs(command[-1], exist_ok=True)
            raise subprocess.CalledProcessError(128, command, stderr="fatal: hung up\n")
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with pytest.raises(RuntimeError, match="Failed to clone templates repository"):
        get_cached_templates(repo_url, branch, cache_dir=str(tmp_path))

    assert not (tmp_path / cache_key).exists()


def test_a_failed_refresh_leaves_the_valid_cache_in_place(monkeypatch, tmp_path):
    """If fetch/reset fails on a valid cache, the older copy is still a working
    tree: keep it and let the error propagate rather than wiping the cache."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]
    cache_path = tmp_path / cache_key
    _init_real_repo(cache_path)

    def fake_run(command, **kwargs):
        if "fetch" in command:
            raise subprocess.TimeoutExpired(command, 60)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with pytest.raises(subprocess.TimeoutExpired):
        get_cached_templates(repo_url, branch, cache_dir=str(tmp_path))

    # The valid cache survived the failed refresh
    assert (cache_path / ".git").exists()
    assert (cache_path / "README.md").exists()


def test_snapshot_dest_receives_the_tree_without_git(monkeypatch, tmp_path):
    """With dest, the caller gets a private snapshot copied under the lock:
    returned path is dest, it holds the tree, and .git is excluded. A stale
    dest is cleared first, and the cache itself keeps its .git."""
    repo_url = "https://github.com/org/templates.git"
    branch = "main"
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]
    cache_path = tmp_path / cache_key

    def fake_run(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            target = command[-1]
            os.makedirs(os.path.join(target, ".git"), exist_ok=True)
            os.makedirs(os.path.join(target, "modules"), exist_ok=True)
            with open(os.path.join(target, "modules", "main.tf"), "w") as f:
                f.write("# template\n")
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, 'run', fake_run)

    dest = tmp_path / "snapshot"
    dest.mkdir()
    (dest / "stale.txt").write_text("from a previous request")

    result = get_cached_templates(repo_url, branch, cache_dir=str(tmp_path), dest=dest)

    assert result == dest
    assert (dest / "modules" / "main.tf").exists()
    assert not (dest / "stale.txt").exists(), "a pre-existing dest must be cleared"
    assert not (dest / ".git").exists()
    assert (cache_path / ".git").exists()
