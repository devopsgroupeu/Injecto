#!/usr/bin/env python3

import logging
import os
import subprocess
import tempfile
import shutil
import time
import zipfile
import io
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any

import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request, Header, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import yaml

from .logs import logger, green, yellow, red, request_id_var
from .processing import GenerationError, load_and_merge_data, process_files
from .formatting import run_terraform_fmt
from .catalog import extract_catalog
from .git import clone_repository, mask_url_credentials
from .version import __version__
from .auth import require_service_token

# --- FastAPI App Setup ---
app = FastAPI(
    title="Injecto API",
    description="A REST API for processing configuration files with YAML data injection using @param and @section directives",
    version=__version__
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Bind the caller's X-Request-ID (or a new one) so it appears in every log
    line for this request and correlates with the backend and other services."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response

# --- Pydantic Models ---

class ProcessRequest(BaseModel):
    """Request model for processing configuration files."""
    # Defaults to "git": both endpoints taking this model require a git source,
    # so the previous "local" default guaranteed a 400 whenever the field was
    # omitted. Local files are uploaded to /process-upload, which does not use
    # this model at all.
    source: str = Field(default="git", description="Source type: only 'git' is accepted; upload local files to /process-upload")
    repo_url: Optional[str] = Field(default=None, description="Git repository URL (required if source is 'git')")
    branch: Optional[str] = Field(default=None, description="Git branch to clone")
    input_dir: str = Field(description="Input directory path within the source")
    data: Dict[str, Any] = Field(description="YAML data as dictionary")

class ProcessResponse(BaseModel):
    """Response model for processing results."""
    status: str
    message: str
    files_processed: int
    errors: List[str] = []

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str

# --- Helper Functions ---

def create_temp_directory() -> Path:
    """Create a temporary directory for processing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="injecto_api_"))
    logger.debug(f"Created temporary directory: {temp_dir}")
    return temp_dir

def safe_upload_path(base_dir: Path, filename: str) -> Path:
    """
    Resolve a client-supplied upload filename to a path that cannot escape base_dir.

    UploadFile.filename comes from the request and FastAPI does not sanitise it.
    Two escapes matter, and the second is the surprising one:

      - `..` segments walk out of the directory, and the caller creates the parent
        for us, so the walk succeeds.
      - an ABSOLUTE filename replaces the base entirely: Path("/in") / "/etc/x"
        is "/etc/x", not "/in/etc/x".

    Nested names are legitimate (templates ship in subdirectories), so the
    directory structure is preserved — only escapes are rejected.
    """
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="Upload is missing a filename")

    base = base_dir.resolve()
    candidate = (base / filename).resolve()
    if candidate == base or not candidate.is_relative_to(base):
        logger.warning(yellow(f"Rejected upload filename escaping the input directory: {filename!r}"))
        raise HTTPException(status_code=400, detail=f"Unsafe upload filename: {filename!r}")
    return candidate

def cleanup_temp_directory(temp_dir: Path):
    """Clean up temporary directory."""
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(yellow(f"Failed to cleanup temporary directory {temp_dir}: {e}"))


@contextmanager
def processing_request(what: str):
    """Own the scratch directory and the error translation for one request.

    All three processing endpoints ran the same twenty-five lines of
    try/except/finally. The GenerationError arm is the load-bearing one
    (OP-214): it is what makes a silently-wrong generation answer 422 instead
    of 500, and keeping three byte-identical copies of it in step by hand is
    exactly how one of them drifts back to a 500.
    """
    temp_dir = None
    try:
        temp_dir = create_temp_directory()
        yield temp_dir

    except HTTPException:
        raise
    except GenerationError as e:
        # 422, not 500: processing worked, the result would just have been silently
        # wrong. The backend maps `code` to a specific user-facing message (OP-214).
        logger.error(red(f"Refusing to return generated output: {e.code}: {e.message}"))
        raise HTTPException(
            status_code=422,
            detail={"code": e.code, "message": e.message, "details": e.details},
        ) from e
    except Exception as e:
        logger.error(red(f"API {what} error: {e}"), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        if temp_dir:
            cleanup_temp_directory(temp_dir)


def create_zip_response(output_dir: Path) -> StreamingResponse:
    """Create a zip file response from the output directory."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(output_dir)
                zip_file.write(file_path, relative_path)

    zip_buffer.seek(0)

    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=processed_files.zip"}
    )

# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version=__version__)

def generate_from_git(request: ProcessRequest, temp_dir: Path) -> Path:
    """Clone, process and format into a fresh output dir; return that dir.

    Shared by /process and /process-git-download, which differ only in what they
    hand back: a JSON summary or the tree as a ZIP. Keeping the pipeline in one
    place is what stops them drifting apart - /process used to skip
    run_terraform_fmt, so the same request produced differently formatted
    Terraform depending on which endpoint you asked.
    """
    if not request.repo_url:
        raise HTTPException(status_code=400, detail="repo_url is required when source is 'git'")

    clone_path = temp_dir / "clone"
    if not clone_repository(
        repo_url=request.repo_url,
        clone_path=str(clone_path),
        branch=request.branch,
    ):
        raise HTTPException(status_code=400, detail="Failed to clone repository")

    input_dir = clone_path / request.input_dir
    if not input_dir.exists():
        raise HTTPException(status_code=400, detail=f"Input directory '{request.input_dir}' not found in repository")

    yaml_file = temp_dir / "data.yaml"
    with open(yaml_file, 'w') as f:
        yaml.dump(request.data, f)
    merged_data = load_and_merge_data([yaml_file])

    output_dir = temp_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    process_files(input_dir, output_dir, merged_data)
    run_terraform_fmt(output_dir)
    return output_dir


@app.post("/process", response_model=ProcessResponse, dependencies=[Depends(require_service_token)])
async def process_templates_endpoint(request: ProcessRequest):
    """
    Dry run: process configuration files from Git and report whether the
    generation succeeds, without returning the tree.

    Runs the identical pipeline as /process-git-download and then discards the
    output, so it answers "would this configuration generate cleanly?" -
    including the 422 refusals - at no transfer cost.
    """
    with processing_request("processing") as temp_dir:
        if request.source != "git":
            raise HTTPException(status_code=400, detail="Local source requires the /process-upload endpoint")

        output_dir = generate_from_git(request, temp_dir)

        return ProcessResponse(
            status="success",
            message="Configuration files processed successfully",
            files_processed=len(list(output_dir.rglob("*"))),
            errors=[]
        )

@app.post("/process-upload", dependencies=[Depends(require_service_token)])
async def process_with_upload(
    files: List[UploadFile] = File(...),
    config_files: List[UploadFile] = File(default=[]),
    data: str = Form(default="{}")
):
    """
    Process uploaded configuration files with YAML data using @param and @section directives.

    Parameters:
    - files: Template/configuration files to process
    - config_files: YAML configuration files to merge (optional - can use data instead)
    - data: JSON data (optional - used if config_files not provided)

    Returns a zip file with processed results.
    """
    with processing_request("upload processing") as temp_dir:
        # Parse YAML data - either from config_files or data parameter
        if config_files:
            # Process uploaded YAML files
            yaml_data = {}
            temp_config_files = []

            for index, config_file in enumerate(config_files):
                # Save config file temporarily. Only the basename is kept: these are
                # merged as YAML and their directory structure is never used, so the
                # simplest safe form is also the correct one. The index keeps two
                # uploads with the same basename from overwriting each other.
                config_content = await config_file.read()
                safe_name = Path(config_file.filename or "").name
                if not safe_name:
                    raise HTTPException(status_code=400, detail="Config upload is missing a filename")
                temp_config_path = temp_dir / f"config_{index}_{safe_name}"
                with open(temp_config_path, 'wb') as f:
                    f.write(config_content)
                temp_config_files.append(temp_config_path)

            # Load and merge YAML files using existing logic
            try:
                yaml_data = load_and_merge_data(temp_config_files)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error processing YAML config files: {e}") from e
        else:
            # Parse JSON data from form parameter
            try:
                yaml_data = yaml.safe_load(data)
                if yaml_data is None:
                    yaml_data = {}
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid YAML/JSON data: {e}") from e
        input_dir = temp_dir / "input"
        output_dir = temp_dir / "output"
        input_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)

        # Save uploaded files
        for file in files:
            file_path = safe_upload_path(input_dir, file.filename)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)

        # Use the already processed/merged YAML data
        merged_data = yaml_data

        # Process files with @param and @section directives
        process_files(input_dir, output_dir, merged_data)

        # Format Terraform files
        run_terraform_fmt(output_dir)

        # Return zip file with results
        return create_zip_response(output_dir)

@app.post("/process-git-download", dependencies=[Depends(require_service_token)])
async def process_git_download(request: ProcessRequest):
    """
    Process configuration files from Git repository and return a zip file with results.

    This is the endpoint the OpenPrime backend calls; /process runs the same
    pipeline but reports a summary instead of returning the tree.
    """
    with processing_request("git download processing") as temp_dir:
        if request.source != "git":
            raise HTTPException(status_code=400, detail="This endpoint requires git source with repo_url")

        output_dir = generate_from_git(request, temp_dir)

        return create_zip_response(output_dir)

# --- Server startup ---
def run_api_server(host: str = "0.0.0.0", port: int = 8000, debug: bool = False):
    """Run the API server."""
    import uvicorn

    log_level = "debug" if debug else "info"
    logger.info(green(f"Starting Injecto API server on {host}:{port}"))

    uvicorn.run(
        "injecto.api:app",
        host=host,
        port=port,
        log_level=log_level,
        log_config=None,  # use our root JSON logging instead of uvicorn's defaults
        reload=debug
    )

if __name__ == "__main__":
    run_api_server(debug=True)


# --- Catalog endpoint ------------------------------------------------------

# Injecto clones whatever repo it is handed, so the catalog endpoint is a
# server-side request forgery primitive unless the target is constrained. The
# allowlist holds URL prefixes; empty means the endpoint is disabled rather
# than unrestricted, because an unset variable must never be the permissive case.
CATALOG_REPO_ALLOWLIST = [
    prefix.strip()
    for prefix in os.getenv("CATALOG_REPO_ALLOWLIST", "").split(",")
    if prefix.strip()
]

# git ls-remote is one network round trip against the remote tip. Memoizing it
# briefly keeps a burst of wizard loads from making one call each, while staying
# short enough that a templates merge shows up within the same minute.
CATALOG_SHA_TTL_SECONDS = 30
CATALOG_LS_REMOTE_TIMEOUT_SECONDS = 10
CATALOG_CLONE_TIMEOUT_SECONDS = 60

_sha_cache: Dict[tuple, tuple] = {}
_catalog_cache: Dict[tuple, tuple] = {}


def repo_is_allowed(repo_url: str) -> bool:
    return any(repo_url.startswith(prefix) for prefix in CATALOG_REPO_ALLOWLIST)


def resolve_remote_sha(repo_url: str, branch: str) -> Optional[str]:
    """Return the commit sha at the remote tip, or None if it cannot be read.

    Reading the sha without cloning is what makes the cache worth having: an
    unchanged templates repo costs one ls-remote instead of a clone plus a full
    extraction.
    """
    cache_key = (repo_url, branch)
    cached = _sha_cache.get(cache_key)
    if cached and (time.monotonic() - cached[1]) < CATALOG_SHA_TTL_SECONDS:
        return cached[0]

    try:
        result = subprocess.run(
            ["git", "ls-remote", "--", repo_url, branch],
            capture_output=True, text=True, check=True,
            timeout=CATALOG_LS_REMOTE_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_ALLOW_PROTOCOL": "https:ssh", "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        logger.error(red(f"ls-remote timed out for {mask_url_credentials(repo_url)}"))
        return None
    except subprocess.CalledProcessError as e:
        detail = mask_url_credentials(e.stderr.strip() if e.stderr else f"{e}")
        logger.error(red(f"ls-remote failed: {detail}"))
        return None

    if not result.stdout.strip():
        return None

    sha = result.stdout.split()[0]
    _sha_cache[cache_key] = (sha, time.monotonic())
    return sha


@app.get("/catalog", dependencies=[Depends(require_service_token)])
def get_catalog(
    repo_url: str = Query(..., description="Templates repository to extract from."),
    branch: str = Query("main", description="Branch to read."),
    provider: str = Query("aws", description="Provider directory to scan."),
    if_none_match: Optional[str] = Header(default=None),
):
    """Serve the wizard catalog extracted from a templates repository.

    Declared with `def`, not `async def`, deliberately: this clones and walks a
    filesystem, and FastAPI runs sync handlers in a threadpool. The neighbouring
    /process handlers do the same blocking work on an `async def` and stall the
    event loop for every other request while a clone runs.

    The ETag is the templates commit sha, so a frontend that already holds the
    current catalog revalidates for the cost of one ls-remote.
    """
    if not CATALOG_REPO_ALLOWLIST:
        raise HTTPException(
            status_code=503,
            detail="Catalog extraction is not configured (CATALOG_REPO_ALLOWLIST is unset)",
        )
    if not repo_is_allowed(repo_url):
        raise HTTPException(status_code=400, detail="repo_url is not in the catalog allowlist")

    sha = resolve_remote_sha(repo_url, branch)
    if not sha:
        raise HTTPException(
            status_code=502,
            detail=f"Could not resolve '{branch}' in the templates repository",
        )

    if if_none_match and if_none_match.strip('"') == sha:
        return Response(status_code=304, headers={"ETag": f'"{sha}"'})

    cache_key = (repo_url, branch, provider)
    cached = _catalog_cache.get(cache_key)
    if cached and cached[0] == sha:
        return JSONResponse(content=cached[1], headers={"ETag": f'"{sha}"'})

    temp_dir = Path(tempfile.mkdtemp(prefix="injecto-catalog-"))
    try:
        clone_path = temp_dir / "clone"
        if not clone_repository(
            repo_url=repo_url,
            clone_path=str(clone_path),
            branch=branch,
            depth=1,
            timeout=CATALOG_CLONE_TIMEOUT_SECONDS,
        ):
            raise HTTPException(status_code=502, detail="Failed to clone the templates repository")

        catalog = extract_catalog(clone_path, provider)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if catalog["errors"]:
        # 422 rather than a 200 carrying a partial document: a catalog missing
        # the module whose decorator failed to parse looks exactly like a
        # templates repo that never had it.
        raise HTTPException(
            status_code=422,
            detail={"message": "Templates contain malformed decorators", "errors": catalog["errors"]},
        )

    catalog["commit"] = sha
    _catalog_cache[cache_key] = (sha, catalog)
    return JSONResponse(content=catalog, headers={"ETag": f'"{sha}"'})
