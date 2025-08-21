# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Injecto is a Python-based configuration file processing tool that processes `@param` and `@section` directives in configuration files using YAML data. It supports both CLI and REST API modes.

## Core Processing

Injecto processes files with two types of directives:

1. **@param directives**: Replace values on the following line using YAML data paths
   ```
   # @param eks.cluster.name
   cluster_name = "placeholder"
   ```

2. **@section directives**: Enable/disable code sections based on YAML boolean values
   ```
   # @section features.monitoring begin
   monitoring_enabled = true
   # @section features.monitoring end
   ```

## CLI Usage

### Basic Commands

```bash
# Local execution with local files
python3 src/main.py --input-dir ~/config/ --output-dir ./output --data-files ~/data/config.yaml

# Git repository as source
python3 src/main.py --source git --repo-url https://github.com/example/configs.git --branch main --input-dir configs/ --output-dir ./output --data-files ~/data/config.yaml

# Docker execution
docker run --rm -v ~/configs:/configs -v ~/data:/data -v "$(pwd)/output":/output ghcr.io/devopsgroupeu/injecto:latest --input-dir /configs --output-dir /output --data-files /data/config.yaml

# Docker Compose (CLI mode)
docker-compose up injecto
```

### Development commands

```bash
# Install dependencies
pip install -r requirements.txt

# Enable debug logging
python3 src/main.py --debug [other args]

# Build Docker image
docker build -t injecto .
```

## API Mode Usage

### Starting the API Server

```bash
# Start API server (CLI equivalent)
python3 src/main.py --api --host 0.0.0.0 --port 8000

# With debug mode
python3 src/main.py --api --host 0.0.0.0 --port 8000 --debug

# Docker Compose (API mode)
docker-compose up injecto-api
```

### API Endpoints

#### Health Check
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

#### Process Git Repository (JSON Response)
```bash
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "source": "git",
    "repo_url": "https://github.com/example/configs.git",
    "branch": "main",
    "input_dir": "configs/",
    "data": {
      "eks": {
        "cluster": {
          "name": "production-cluster"
        }
      },
      "features": {
        "monitoring": true
      }
    }
  }'
```

**Response:**
```json
{
  "status": "success",
  "message": "Configuration files processed successfully",
  "files_processed": 5,
  "errors": []
}
```

#### Process Uploaded Files (ZIP Response)

**Option 1: Using separate YAML config files (recommended)**
```bash
curl -X POST http://localhost:8000/process-upload \
  -F "files=@template1.tf" \
  -F "files=@template2.yaml" \
  -F "config_files=@common.yaml" \
  -F "config_files=@environment.yaml" \
  -F "config_files=@secrets.yaml" \
  -o result.zip
```

**Option 2: Using inline JSON data**
```bash
curl -X POST http://localhost:8000/process-upload \
  -F "files=@config1.yaml" \
  -F "files=@config2.tf" \
  -F "data={\"key\": \"value\", \"features\": {\"monitoring\": true}}" \
  -o result.zip
```

#### Process Git Repository and Download (ZIP Response)
```bash
curl -X POST http://localhost:8000/process-git-download \
  -H "Content-Type: application/json" \
  -d '{
    "source": "git",
    "repo_url": "https://github.com/example/configs.git",
    "input_dir": "configs/",
    "data": {
      "database": {
        "host": "prod-db.example.com",
        "port": 5432
      }
    }
  }' \
  -o processed_configs.zip
```

## API vs CLI Comparison

| Feature | CLI Mode | API Mode |
|---------|----------|----------|
| **Input Source** | Local files or Git repo | Git repo or uploaded files |
| **Data Input** | Multiple YAML files on filesystem | Multiple YAML file uploads OR JSON in request body |
| **Output** | Files written to filesystem | JSON response or ZIP download |
| **Batch Processing** | Single execution | Multiple requests supported |
| **Integration** | Shell scripts, CI/CD | Web applications, services |
| **Authentication** | File system permissions | Can be extended with API auth |
| **Multiple YAML Files** | `--data-files file1.yaml file2.yaml` | `config_files=@file1.yaml -F config_files=@file2.yaml` |

## Usage Examples

### CLI Example
```bash
# Process Terraform configurations with environment-specific values
python3 src/main.py \
  --source git \
  --repo-url https://github.com/company/terraform-configs.git \
  --input-dir environments/production/ \
  --output-dir ./terraform-production/ \
  --data-files ./values/prod.yaml ./values/common.yaml
```

### API Example

**Example 1: Processing with multiple YAML configuration files**
```python
import requests

# Upload template files and multiple YAML config files
files_to_process = [
    ('files', open('kubernetes-deployment.yaml', 'rb')),
    ('files', open('service.yaml', 'rb')),
]

config_files = [
    ('config_files', open('common.yaml', 'rb')),
    ('config_files', open('production.yaml', 'rb')),
    ('config_files', open('secrets.yaml', 'rb')),
]

response = requests.post(
    'http://localhost:8000/process-upload',
    files=files_to_process + config_files
)

# Save processed configurations
with open('processed_k8s_configs.zip', 'wb') as f:
    f.write(response.content)

# Close file handles
for _, file_handle in files_to_process + config_files:
    file_handle.close()
```

**Example 2: Processing Git repository with JSON data**
```python
import requests
import json

# Configuration data
config_data = {
    "environment": "production",
    "database": {
        "host": "prod-db.company.com",
        "port": 5432
    },
    "features": {
        "caching": True,
        "debug_mode": False
    }
}

# Process configuration files from Git repository
response = requests.post('http://localhost:8000/process-git-download',
    json={
        "source": "git",
        "repo_url": "https://github.com/company/app-configs.git",
        "input_dir": "config-templates/",
        "data": config_data
    }
)

# Save processed configurations
with open('processed_configs.zip', 'wb') as f:
    f.write(response.content)
```

## Architecture

### Core Components

1. **main.py** - Entry point with CLI argument parsing and API server startup
2. **processing.py** - Handles `@param` and `@section` directive processing
3. **api.py** - FastAPI REST API endpoints for web service integration
4. **git.py** - Git repository cloning functionality for remote sources
5. **logs.py** - Centralized logging with colorama for colored output

### Data Processing

- **YAML Data Loading**: Supports multiple YAML files with deep merge strategy
- **Nested Path Access**: Use dot notation (e.g., `database.host`) to access nested values
- **Value Formatting**: Automatic formatting for different file types (quoted strings, booleans)
- **Section Control**: Enable/disable code blocks based on boolean YAML values

### Error Handling

- **Validation**: Input validation for required parameters and file existence
- **Graceful Failures**: Detailed error messages for debugging
- **Logging**: Comprehensive logging at different levels (DEBUG, INFO, WARNING, ERROR)

The tool maintains file structure in output directories and handles both in-place editing (CLI) and temporary processing (API).
