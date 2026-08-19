#!/usr/bin/env python3
"""GET /catalog: allowlist, sha caching, ETag revalidation and error mapping.

Cloning is stubbed rather than exercised. OP-175 restricts git to
``GIT_ALLOW_PROTOCOL=https:ssh``, which blocks both ``file://`` and bare local
paths, so the fixture repo the ticket suggests cannot be cloned at all -- that
restriction is verified in test_git.py, and clone_repository is tested on its
own. Stubbing also gives a call counter, which is the only honest way to assert
that an unchanged sha does not clone.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from injecto import api

FIXTURE = Path(__file__).parent / 'fixtures' / 'catalog'
ALLOWED_REPO = 'https://github.com/devopsgroupeu/openprime-infra-templates.git'


@pytest.fixture
def client(monkeypatch):
    """A client whose clones are stubbed and whose caches start empty."""
    monkeypatch.setattr(api, 'CATALOG_REPO_ALLOWLIST', ['https://github.com/devopsgroupeu/'])
    monkeypatch.setattr(api, '_sha_cache', {})
    monkeypatch.setattr(api, '_catalog_cache', {})
    return TestClient(api.app)


@pytest.fixture
def stub_git(monkeypatch):
    """Stub ls-remote and clone; returns the mutable call record."""
    calls = {'sha': 'abc123', 'clones': 0, 'ls_remotes': 0, 'tree': FIXTURE}

    def fake_sha(repo_url, branch):
        calls['ls_remotes'] += 1
        return calls['sha']

    def fake_clone(repo_url, clone_path, branch=None, depth=None, timeout=None, **kwargs):
        calls['clones'] += 1
        import shutil
        shutil.copytree(calls['tree'], clone_path)
        return True

    monkeypatch.setattr(api, 'resolve_remote_sha', fake_sha)
    monkeypatch.setattr(api, 'clone_repository', fake_clone)
    return calls


def get(client, **params):
    query = {'repo_url': ALLOWED_REPO, **params}
    return client.get('/catalog', params=query)


# --- Happy path -------------------------------------------------------------

def test_returns_the_catalog_with_the_commit_sha_as_etag(client, stub_git):
    response = get(client)

    assert response.status_code == 200
    assert response.headers['etag'] == '"abc123"'

    body = response.json()
    assert body['schemaVersion'] == 1
    assert body['commit'] == 'abc123'
    assert set(body['services']) == {'vpc', 'rds'}


def test_provider_is_forwarded_to_extraction(client, stub_git):
    """The fixture carries only aws/, so asking for azure must report a missing
    provider rather than silently serving the aws catalog."""
    response = get(client, provider='azure')

    assert response.status_code == 422
    assert any(e['code'] == 'NO_TFVARS' for e in response.json()['detail']['errors'])


# --- Caching ----------------------------------------------------------------

def test_unchanged_sha_does_not_clone_again(client, stub_git):
    """The whole point of resolving the sha first: an unchanged templates repo
    must cost one ls-remote, not a clone plus a full extraction."""
    assert get(client).status_code == 200
    assert stub_git['clones'] == 1

    assert get(client).status_code == 200
    assert stub_git['clones'] == 1
    assert stub_git['ls_remotes'] == 2


def test_a_new_sha_reclones(client, stub_git):
    get(client)
    stub_git['sha'] = 'def456'

    response = get(client)
    assert response.headers['etag'] == '"def456"'
    assert stub_git['clones'] == 2


def test_if_none_match_revalidates_to_304(client, stub_git):
    etag = get(client).headers['etag']

    response = client.get(
        '/catalog',
        params={'repo_url': ALLOWED_REPO},
        headers={'If-None-Match': etag},
    )
    assert response.status_code == 304
    assert response.headers['etag'] == etag


def test_304_does_not_clone(client, stub_git):
    """A revalidating frontend must not cost a clone, or the ETag buys nothing."""
    response = client.get(
        '/catalog',
        params={'repo_url': ALLOWED_REPO},
        headers={'If-None-Match': '"abc123"'},
    )
    assert response.status_code == 304
    assert stub_git['clones'] == 0


def test_a_stale_if_none_match_gets_the_document(client, stub_git):
    response = client.get(
        '/catalog',
        params={'repo_url': ALLOWED_REPO},
        headers={'If-None-Match': '"an-older-sha"'},
    )
    assert response.status_code == 200
    assert response.headers['etag'] == '"abc123"'


# --- Guards -----------------------------------------------------------------

def test_repo_outside_the_allowlist_is_rejected(client, stub_git):
    response = get(client, repo_url='https://github.com/attacker/evil.git')

    assert response.status_code == 400
    assert 'allowlist' in response.json()['detail']
    assert stub_git['clones'] == 0


def test_an_unset_allowlist_disables_the_endpoint(client, stub_git, monkeypatch):
    """An unset variable must never be the permissive case -- Injecto clones
    whatever it is handed, so an empty allowlist that meant 'anything' would be
    a server-side request forgery primitive."""
    monkeypatch.setattr(api, 'CATALOG_REPO_ALLOWLIST', [])

    assert get(client).status_code == 503
    assert stub_git['clones'] == 0


def test_missing_service_token_is_rejected(client, stub_git, monkeypatch):
    monkeypatch.setattr('injecto.auth.SERVICE_TOKEN', 's3cr3t')

    assert get(client).status_code == 401
    assert stub_git['clones'] == 0


def test_valid_service_token_is_accepted(client, stub_git, monkeypatch):
    monkeypatch.setattr('injecto.auth.SERVICE_TOKEN', 's3cr3t')

    response = client.get(
        '/catalog',
        params={'repo_url': ALLOWED_REPO},
        headers={'X-Service-Token': 's3cr3t'},
    )
    assert response.status_code == 200


# --- Failure mapping --------------------------------------------------------

def test_unresolvable_branch_is_502(client, stub_git, monkeypatch):
    monkeypatch.setattr(api, 'resolve_remote_sha', lambda repo_url, branch: None)

    response = get(client, branch='no-such-branch')
    assert response.status_code == 502
    assert 'no-such-branch' in response.json()['detail']


def test_failed_clone_is_502(client, stub_git, monkeypatch):
    monkeypatch.setattr(api, 'clone_repository', lambda **kwargs: False)

    assert get(client).status_code == 502


def test_malformed_decorators_are_422_with_locations(client, stub_git, tmp_path):
    """Never a truncated 200: a catalog missing the module whose decorator failed
    to parse is indistinguishable from a templates repo that never had it."""
    broken = tmp_path / 'broken'
    provider_dir = broken / 'templates' / 'terraform' / 'aws'
    provider_dir.mkdir(parents=True)
    (provider_dir / 'terraform.auto.tfvars').write_text(
        '# @param services.eks.tags\neks_tags = []\n'
    )
    (provider_dir / 'main.tf').write_text(
        '# @section services.eks.enabled begin\nmodule "eks" {}\n'
        '# @section services.eks.enabled end\n'
    )
    stub_git['tree'] = broken

    response = get(client)
    assert response.status_code == 422

    errors = response.json()['detail']['errors']
    assert any(e['code'] == 'UNKNOWN_TYPE' for e in errors)
    assert all(e['file'] and e['line'] for e in errors)


def test_a_broken_catalog_is_not_cached(client, stub_git, tmp_path):
    """Caching a 422 would keep serving it after the templates are fixed, until
    the next commit changed the sha."""
    broken = tmp_path / 'broken'
    provider_dir = broken / 'templates' / 'terraform' / 'aws'
    provider_dir.mkdir(parents=True)
    (provider_dir / 'terraform.auto.tfvars').write_text('# @param bad.path.too.deep\nx = 1\n')
    stub_git['tree'] = broken

    assert get(client).status_code == 422

    stub_git['tree'] = FIXTURE
    assert get(client).status_code == 200


# --- Temp directory hygiene -------------------------------------------------

def test_clone_directory_is_removed_even_on_failure(client, stub_git, monkeypatch):
    """The endpoint clones into mkdtemp on every miss; leaking those fills the
    container's disk one wizard load at a time."""
    created = []
    real_mkdtemp = api.tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(api.tempfile, 'mkdtemp', tracking_mkdtemp)
    monkeypatch.setattr(api, 'extract_catalog', lambda *a, **k: 1 / 0)

    with pytest.raises(ZeroDivisionError):
        get(client)

    assert created, 'the endpoint did not create a temp directory'
    assert not any(path.exists() for path in created)
