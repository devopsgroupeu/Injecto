#!/usr/bin/env python3

import subprocess
import os
import re
import hashlib
import fcntl
import shutil
from pathlib import Path

from .logs import logger, green, yellow, red

# Matches the "user:pass@" segment of a URL so credentials (e.g. a git PAT in an
# authenticated clone URL) can be stripped before anything is written to logs.
_URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def mask_url_credentials(text):
    """Replace any user:pass@ credentials in a string with ://***:***@."""
    return _URL_CREDENTIALS_RE.sub("://***:***@", text)


def clone_repository(repo_url, clone_path, branch=None, username=None, pat=None,
                     depth=None, timeout=None):
    """
    Clones a Git repository from a given URL.

    Args:
        repo_url (str): The URL of the repository to clone.
        clone_path (str): The local path where the repository will be cloned.
        branch (str, optional): The specific branch to clone. Defaults to None.
        username (str, optional): The username for authentication for private repositories. Defaults to None.
        pat (str, optional): The Personal Access Token for authentication for private repositories. Defaults to None.
        depth (int, optional): Truncate history to this many commits. The catalog
            only ever reads the tip, so a full clone is wasted transfer.
        timeout (float, optional): Seconds before the clone is abandoned. Without
            one an unreachable host hangs the caller until git gives up.

    Returns:
        bool: True if the repository was cloned successfully, False otherwise.
    """
    # Create the parent directory if it doesn't exist
    logger.info(
        f"Create the parent directory {os.path.dirname(clone_path)} if it doesn't exist"
    )
    os.makedirs(os.path.dirname(clone_path), exist_ok=True)

    # Check if the clone path already exists and is not empty
    if os.path.exists(clone_path) and os.listdir(clone_path):
        logger.error(red(f"The directory '{clone_path}' is not empty."))
        return False

    # Handle private repository authentication by modifying the URL
    if username and pat:
        # We need to format the URL to include the credentials.
        # This assumes the URL starts with "https://"
        if repo_url.startswith("https://"):
            protocol_end = len("https://")
            base_url = repo_url[protocol_end:]
            authenticated_url = f"https://{username}:{pat}@{base_url}"
        else:
            # Handle other protocols if necessary, but this is the most common.
            logger.error(red("Authentication requires an 'https' URL."))
            return False
    else:
        authenticated_url = repo_url

    # Construct the git clone command
    command = ["git", "clone"]

    if branch:
        command.extend(["--branch", branch])

    if depth:
        command.extend(["--depth", str(depth)])

    # `--` ends option parsing, so a URL or path beginning with '-' is treated as
    # an operand rather than a git option (OP-175).
    command.append("--")
    command.extend([authenticated_url, clone_path])

    # Mask any user:pass@ credentials before logging the command, so an
    # authenticated clone URL never writes a git PAT to the logs.
    logger.info(f"Executing command: {mask_url_credentials(' '.join(command))}")

    try:
        # Restrict which transports git will use. `file` and the transport
        # helpers (`ext::`) are what turn a repository URL into local-file access
        # or command execution; this repo's URL is operator-supplied today, so
        # this is defence in depth rather than a fix for a live vector (OP-175).
        env = {**os.environ, "GIT_ALLOW_PROTOCOL": "https:ssh"}
        subprocess.run(command, check=True, capture_output=True, text=True, env=env,
                       timeout=timeout)
        logger.info(green("Repository cloned successfully!"))
        return True
    except subprocess.CalledProcessError as e:
        # Mask before logging: str(e) embeds the whole command, which carries the
        # authenticated URL. Without this the PAT that mask_url_credentials keeps
        # out of the success path is written verbatim on every failure.
        # git's own stderr is the only thing that says *why* the clone failed
        # ("Repository not found", "could not read Username", "Remote branch not
        # found"); dropping it is what makes clone failures undiagnosable.
        detail = mask_url_credentials(f"{e}")
        if e.stderr:
            detail = f"{detail} | {mask_url_credentials(e.stderr.strip())}"
        logger.error(red(f"Error cloning repository: {detail}"))
        return False
    except subprocess.TimeoutExpired:
        logger.error(red(f"Timed out after {timeout}s cloning repository"))
        return False
    except FileNotFoundError:
        logger.error(
            red(
                "'git' command not found. Please ensure Git is installed and in your system's PATH."
            )
        )
        return False


def get_cached_templates(repo_url, branch, cache_dir=None, timeout=60, dest=None):
    """
    Shallow-clone (or refresh) the templates repo into a persistent cache dir.

    The infra-templates repo is static and small (~90 KB pack), so a full cold
    clone per request is pure waste. The cache is keyed by repo URL + branch:
      - first request: shallow clone (--depth 1 --single-branch) into the cache
      - later requests: shallow fetch + hard reset to the branch tip, so every
        request still sees the latest templates

    A per-key file lock serializes concurrent refreshes (multiple uvicorn
    workers or overlapping requests must not fetch/reset the same repo at once).

    A cache entry is only trusted when it is a real git working tree (it has a
    .git directory). A partial directory left behind by a clone that was killed
    by the timeout is wiped and re-cloned, so a poisoned cache can always
    self-heal. If the refresh (fetch/reset) of a valid cache fails, the older
    valid copy is left in place and the error propagates.

    Args:
        dest (Path, optional): when given, a snapshot of the working tree
            (excluding .git) is copied into it while the per-key lock is still
            held, and `dest` is returned instead of the cache dir. The caller
            owns `dest` and may delete it when done. Without `dest` the cached
            clone directory itself is returned and the caller must NOT delete
            it.

    Returns:
        Path: `dest` if given, else the cached clone directory.
    """
    cache_dir = cache_dir or os.environ.get("TEMPLATES_CACHE_DIR", "/tmp/injecto-templates-cache")
    cache_key = hashlib.sha256(f"{repo_url}|{branch}".encode("utf-8")).hexdigest()[:16]
    cache_path = Path(cache_dir) / cache_key
    lock_path = Path(cache_dir) / f"{cache_key}.lock"

    os.makedirs(cache_dir, exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            if cache_path.exists() and (cache_path / ".git").exists():
                logger.info(f"Refreshing cached templates: {cache_path}")
                subprocess.run(
                    ["git", "-C", str(cache_path), "fetch", "--depth", "1", "origin", branch],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                subprocess.run(
                    ["git", "-C", str(cache_path), "reset", "--hard", "FETCH_HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            else:
                if cache_path.exists():
                    # A non-empty directory without .git is debris from a clone
                    # that was killed by the timeout; clone_repository refuses
                    # non-empty targets, so it must be wiped before retrying.
                    logger.warning(
                        f"Removing invalid cached templates directory: {cache_path}"
                    )
                    shutil.rmtree(cache_path, ignore_errors=True)
                logger.info(f"Cloning templates into cache: {cache_path}")
                success = clone_repository(
                    repo_url, str(cache_path), branch=branch, depth=1, timeout=timeout
                )
                if not success:
                    # Never leave a partial clone behind: it would poison the
                    # cache key until the pod restarts.
                    shutil.rmtree(cache_path, ignore_errors=True)
                    raise RuntimeError(f"Failed to clone templates repository: {repo_url}")
            if dest is not None:
                # Snapshot under the lock: the caller reads a private copy, so a
                # concurrent refresh cannot reset the tree out from under it.
                dest = Path(dest)
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(cache_path, dest, ignore=shutil.ignore_patterns(".git"))
                return dest
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

    return cache_path
