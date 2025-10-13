#!/usr/bin/env python3

import logging
import tempfile
import shutil
import zipfile
import io
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import yaml

from logs import logger, green, yellow, red
from processing import load_and_merge_data, process_files
from git import clone_repository

# --- FastAPI App Setup ---
app = FastAPI(
    title="Injecto API",
    description="A REST API for processing configuration files with YAML data injection using @param and @section directives",
    version="0.1.0"
)

# --- Pydantic Models ---

class ProcessRequest(BaseModel):
    """Request model for processing configuration files."""
    source: str = Field(default="local", description="Source type: 'local' or 'git'")
    repo_url: Optional[str] = Field(default=None, description="Git repository URL (required if source is 'git')")
    branch: Optional[str] = Field(default=None, description="Git branch to clone")
    input_dir: str = Field(description="Input directory path within the source")
    # Removed process_mode - only parameter/section processing is supported
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

def cleanup_temp_directory(temp_dir: Path):
    """Clean up temporary directory."""
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(yellow(f"Failed to cleanup temporary directory {temp_dir}: {e}"))

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
    return HealthResponse(status="healthy", version="0.1.0")

@app.post("/process", response_model=ProcessResponse)
async def process_templates_endpoint(request: ProcessRequest):
    """
    Process configuration files with YAML data using @param and @section directives.
    Returns a summary of the processing results.
    """
    temp_dir = None
    errors = []
    files_processed = 0

    try:
        # Validate request
        if request.source == "git" and not request.repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required when source is 'git'")

        # Create temporary directories
        temp_dir = create_temp_directory()
        input_dir = temp_dir / "input"
        output_dir = temp_dir / "output"

        if request.source == "git":
            # Clone repository
            clone_path = temp_dir / "clone"
            success = clone_repository(
                repo_url=request.repo_url,
                clone_path=str(clone_path),
                branch=request.branch
            )
            if not success:
                raise HTTPException(status_code=400, detail="Failed to clone repository")

            # Set input directory to the specified path within the clone
            actual_input_dir = clone_path / request.input_dir
            if not actual_input_dir.exists():
                raise HTTPException(status_code=400, detail=f"Input directory '{request.input_dir}' not found in repository")
        else:
            # For local source, we'll need to handle file uploads differently
            # For now, return an error as local files need to be uploaded
            raise HTTPException(status_code=400, detail="Local source requires file upload endpoint")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save YAML data to a temporary file for processing
        yaml_file = temp_dir / "data.yaml"
        with open(yaml_file, 'w') as f:
            yaml.dump(request.data, f)

        # Load and merge data
        merged_data = load_and_merge_data([yaml_file])

        # Process files with @param and @section directives
        process_files(actual_input_dir, output_dir, merged_data)
        files_processed = len(list(output_dir.rglob("*")))

        return ProcessResponse(
            status="success",
            message="Configuration files processed successfully",
            files_processed=files_processed,
            errors=errors
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(red(f"API processing error: {e}"), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        if temp_dir:
            cleanup_temp_directory(temp_dir)

@app.post("/process-upload")
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
    temp_dir = None

    try:
        # Create temporary directories first
        temp_dir = create_temp_directory()

        # Parse YAML data - either from config_files or data parameter
        if config_files:
            # Process uploaded YAML files
            yaml_data = {}
            temp_config_files = []

            for config_file in config_files:
                # Save config file temporarily
                config_content = await config_file.read()
                temp_config_path = temp_dir / f"config_{config_file.filename}"
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
            file_path = input_dir / file.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)

            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)

        # Use the already processed/merged YAML data
        merged_data = yaml_data

        # Process files with @param and @section directives
        process_files(input_dir, output_dir, merged_data)

        # Return zip file with results
        return create_zip_response(output_dir)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(red(f"API upload processing error: {e}"), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        if temp_dir:
            cleanup_temp_directory(temp_dir)

@app.post("/process-git-download")
async def process_git_download(request: ProcessRequest):
    """
    Process configuration files from Git repository and return a zip file with results.
    """
    temp_dir = None

    try:
        # Validate request
        if request.source != "git" or not request.repo_url:
            raise HTTPException(status_code=400, detail="This endpoint requires git source with repo_url")

        # Create temporary directories
        temp_dir = create_temp_directory()
        clone_path = temp_dir / "clone"
        output_dir = temp_dir / "output"

        # Clone repository
        success = clone_repository(
            repo_url=request.repo_url,
            clone_path=str(clone_path),
            branch=request.branch
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to clone repository")

        # Set input directory to the specified path within the clone
        actual_input_dir = clone_path / request.input_dir
        if not actual_input_dir.exists():
            raise HTTPException(status_code=400, detail=f"Input directory '{request.input_dir}' not found in repository")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save YAML data to a temporary file for processing
        yaml_file = temp_dir / "data.yaml"
        with open(yaml_file, 'w') as f:
            yaml.dump(request.data, f)

        # Load and merge data
        merged_data = load_and_merge_data([yaml_file])

        # Process files with @param and @section directives
        process_files(actual_input_dir, output_dir, merged_data)

        # Return zip file with results
        return create_zip_response(output_dir)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(red(f"API git download processing error: {e}"), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        if temp_dir:
            cleanup_temp_directory(temp_dir)

# --- Server startup ---
def run_api_server(host: str = "0.0.0.0", port: int = 8000, debug: bool = False):
    """Run the API server."""
    import uvicorn

    log_level = "debug" if debug else "info"
    logger.info(green(f"Starting Injecto API server on {host}:{port}"))

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=debug
    )

if __name__ == "__main__":
    run_api_server(debug=True)
