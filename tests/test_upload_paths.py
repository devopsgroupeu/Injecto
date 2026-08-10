"""Tests for upload filename handling on the API's file-upload paths.

`UploadFile.filename` is client-controlled and FastAPI does not sanitise it, so
joining it onto a base directory is an escape primitive. These lock the guard in
place; see OP-192.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from api import safe_upload_path


@pytest.fixture
def base(tmp_path):
    d = tmp_path / "input"
    d.mkdir()
    return d


def test_plain_filename_lands_inside_the_base(base):
    assert safe_upload_path(base, "main.tf") == (base.resolve() / "main.tf")


def test_nested_filename_is_allowed(base):
    """Templates legitimately ship in subdirectories, so nesting must still work."""
    result = safe_upload_path(base, "terraform/aws/main.tf")
    assert result == (base.resolve() / "terraform/aws/main.tf")
    assert result.is_relative_to(base.resolve())


@pytest.mark.parametrize(
    "filename",
    [
        "../escaped.tf",
        "../../escaped.tf",
        "a/../../../escaped.tf",
        "./../../escaped.tf",
    ],
)
def test_parent_traversal_is_rejected(base, filename):
    with pytest.raises(HTTPException) as excinfo:
        safe_upload_path(base, filename)
    assert excinfo.value.status_code == 400


@pytest.mark.parametrize("filename", ["/etc/cron.d/pwned", "/tmp/escaped.tf"])
def test_absolute_filename_is_rejected(base, filename):
    """The non-obvious escape: an absolute right-hand side replaces the base.

    Path("/in") / "/etc/x" is "/etc/x", so without this guard an absolute
    filename writes wherever it points, no `..` required.
    """
    with pytest.raises(HTTPException) as excinfo:
        safe_upload_path(base, filename)
    assert excinfo.value.status_code == 400


@pytest.mark.parametrize("filename", ["", "   ", None])
def test_missing_filename_is_rejected(base, filename):
    with pytest.raises(HTTPException) as excinfo:
        safe_upload_path(base, filename)
    assert excinfo.value.status_code == 400


def test_filename_resolving_to_the_base_itself_is_rejected(base):
    with pytest.raises(HTTPException):
        safe_upload_path(base, ".")


def test_the_guard_actually_prevents_the_write(base):
    """End-to-end on the primitive: the rejected path is never created.

    Mirrors the production loop, which does `mkdir(parents=True)` on the joined
    path's parent — that is what made the traversal succeed rather than fail.
    """
    outside = base.parent / "escaped.tf"

    with pytest.raises(HTTPException):
        path = safe_upload_path(base, "../escaped.tf")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("owned")

    assert not outside.exists()
