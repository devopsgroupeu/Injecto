# Use a slim Python image for a smaller footprint. Pinned by digest (the
# multi-arch index), so a rebuild uses exactly this image until it is bumped on
# purpose; the tag alone would follow whatever is pushed under it (OP-191).
FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

# The release version, passed in by the publish workflow. It is not just a
# label: it is written into the package below so /health and the OpenAPI docs
# report the version that is actually running. The default marks a local build.
ARG INJECTO_VERSION=0.0.0-dev

# Label the image with metadata
# This helps with image identification and compliance
LABEL org.opencontainers.image.title="injecto"
LABEL org.opencontainers.image.description="A Python tool that automatically replaces placeholders in code or configuration files with values from a YAML file"
LABEL org.opencontainers.image.version="${INJECTO_VERSION}"
LABEL org.opencontainers.image.source="https://github.com/devopsgroupeu/Injecto"
LABEL org.opencontainers.image.authors="Andrej Rabek <andrej.rabek@devopsgroup.sk>"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Set the working directory inside the container
WORKDIR /app

# Terraform for `terraform fmt`. The checksums are the linux lines of
# HashiCorp's terraform_<version>_SHA256SUMS, whose signature was verified
# against HashiCorp's release key when they were pinned. Pinning them here,
# rather than downloading SHA256SUMS next to the zip, means a tampered or
# swapped download fails the build instead of being checked against a file from
# the same host (OP-191). Bump all three together.
ARG TERRAFORM_VERSION=1.11.4
ARG TERRAFORM_SHA256_AMD64=1ce994251c00281d6845f0f268637ba50c0005657eb3cf096b92f753b42ef4dc
ARG TERRAFORM_SHA256_ARM64=a43d1d0da9b9bab214a8305a39db0e40869572594ccf50c416a7756499143633

# Install git for repository cloning and terraform for formatting
RUN apt-get update && \
    apt-get install -y --no-install-recommends git wget unzip && \
    arch="$(dpkg --print-architecture)" && \
    case "$arch" in \
      amd64) sha256="$TERRAFORM_SHA256_AMD64" ;; \
      arm64) sha256="$TERRAFORM_SHA256_ARM64" ;; \
      *) echo "No pinned Terraform checksum for $arch" >&2; exit 1 ;; \
    esac && \
    wget -qO /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${arch}.zip" && \
    echo "${sha256}  /tmp/terraform.zip" | sha256sum -c - && \
    unzip -o /tmp/terraform.zip -d /usr/local/bin && \
    rm /tmp/terraform.zip && \
    apt-get purge -y wget unzip && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
# Running containers as non-root is a best practice.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
# --no-cache-dir reduces image size
# --system installs packages system-wide (good for simple containers)
# Optionally use a virtual environment if preferred
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code directory into the container's working directory
COPY injecto/ ./injecto/

# Stamp the release version into the package. The publish workflow builds from
# the commit that TRIGGERED the release, which is one commit older than
# semantic-release's own `chore(release)` commit - so without this the image
# would always report the previous version.
RUN echo "__version__ = \"${INJECTO_VERSION}\"" > ./injecto/version.py

# Change ownership of the app directory to the non-root user
# This is important if the entrypoint needs to write files (though our script writes outside /app)
RUN chown -R appuser:appgroup /app
# Switch to the non-root user
USER appuser

# Expose port for API mode
EXPOSE 8000

# Prometheus metrics, served on their own port so they are never reachable
# through whatever ingress fronts the API port (see injecto/metrics.py)
EXPOSE 9090

# Define the entrypoint for the container.
# This makes the container behave like an executable for the script.
# Arguments passed to `docker run` will be appended to this command.
ENTRYPOINT ["python", "-m", "injecto.main"]
