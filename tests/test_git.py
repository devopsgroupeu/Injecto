"""Tests for git URL credential masking (keeps PATs out of the logs)."""

from git import mask_url_credentials


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
